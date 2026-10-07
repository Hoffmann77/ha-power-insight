"""A consumer's per-source energy outlives the source it names.

"Energy from Solar PV" belongs to the consumer. When the PV system is removed
the sensor is no longer created, but the energy it counted was consumed, so
its final value is frozen into the source ledger and shown as "Energy from
removed devices". See ``retired_sources.py``.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    CONS_SUB_ID,
    DOMAIN,
    PV_SUB_ID,
    make_consumer_subentry_data,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

ENERGY = ["accumulate_power_source_energy"]
REMOVED = "energy_from_removed_devices"


def _entry(consumer_options: list[str] = ENERGY) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={"schema": 2, "scopes": {"consumer": consumer_options}},
        subentries_data=[
            make_grid_subentry_data(),
            make_pv_subentry_data(),
            make_consumer_subentry_data(power_from_adapters=[PV_SUB_ID]),
        ],
    )


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{CONS_SUB_ID}_{key}"
    )


def _state(hass: HomeAssistant, entry: MockConfigEntry, key: str):
    entity_id = _entity_id(hass, entry, key)
    return None if entity_id is None else hass.states.get(entity_id)


def _set(hass: HomeAssistant, entity: str, watts: float) -> None:
    hass.states.async_set(f"sensor.{entity}", str(watts), {"unit_of_measurement": "W"})


async def _settle(hass: HomeAssistant) -> None:
    for _ in range(4):
        await hass.async_block_till_done()


async def _draw_an_hour_from_pv(hass: HomeAssistant, entry: MockConfigEntry) -> float:
    """Grid 500 W, PV 500 W, the PV-only consumer draws 400 W for an hour.

    Returns the consumer's energy from PV: 0.4 kWh.
    """
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _set(hass, "grid_power", 500)
        _set(hass, "pv_power", 500)
        _set(hass, "consumer_power", -400)
        await setup_integration(hass, entry)

        _set(hass, "grid_power", 500)
        await _settle(hass)
        frozen.move_to(t0 + timedelta(hours=1))
        _set(hass, "grid_power", 500)
        await _settle(hass)

    energy = float(_state(hass, entry, f"energy_from_{PV_SUB_ID}").state)
    assert energy == pytest.approx(0.4, abs=1e-3)
    return energy


def _ledger(entry: MockConfigEntry) -> list[dict]:
    return entry.data.get("retired_sources", [])


async def test_removing_a_source_freezes_the_consumers_energy_from_it(
    hass: HomeAssistant,
) -> None:
    """The consumer's 0.4 kWh from the PV system survive the PV system.

    They are frozen into the ledger, shown as "Energy from removed devices"
    with the device by name, and the old per-source entity is disabled with
    its history rather than deleted.
    """
    entry = _entry()
    energy = await _draw_an_hour_from_pv(hass, entry)
    old_entity = _entity_id(hass, entry, f"energy_from_{PV_SUB_ID}")

    hass.config_entries.async_remove_subentry(entry, PV_SUB_ID)
    await _settle(hass)

    [retired] = _ledger(entry)
    assert retired["subentry_id"] == PV_SUB_ID
    assert retired["totals"] == {CONS_SUB_ID: {"energy_from": pytest.approx(energy)}}

    removed = _state(hass, entry, REMOVED)
    assert removed is not None
    assert float(removed.state) == pytest.approx(energy)
    assert removed.attributes["unit_of_measurement"] == "kWh"
    assert removed.attributes["device_class"] == "energy"
    # A step at removal is not consumption in that hour: no statistics.
    assert "state_class" not in removed.attributes
    assert retired["title"] in removed.attributes

    registry_entry = er.async_get(hass).async_get(old_entity)
    assert registry_entry is not None
    assert registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_a_reload_freezes_nothing_and_counts_nothing_twice(
    hass: HomeAssistant,
) -> None:
    """Only a removal freezes a total; reloading afterwards keeps one entry.

    A reload tears every sensor down too, but the source is still there, so
    nothing is recorded. After a removal, further reloads read the ledger and
    never add to it.
    """
    entry = _entry()
    energy = await _draw_an_hour_from_pv(hass, entry)

    await hass.config_entries.async_reload(entry.entry_id)
    await _settle(hass)
    assert _ledger(entry) == []
    assert _state(hass, entry, REMOVED) is None

    hass.config_entries.async_remove_subentry(entry, PV_SUB_ID)
    await _settle(hass)
    await hass.config_entries.async_reload(entry.entry_id)
    await _settle(hass)

    assert len(_ledger(entry)) == 1
    assert float(_state(hass, entry, REMOVED).state) == pytest.approx(energy)


async def test_a_total_that_was_not_running_is_not_captured(
    hass: HomeAssistant,
) -> None:
    """The documented gap: no running total, nothing to freeze.

    With the per-source energy option off there is no "Energy from Solar PV"
    to tear down when the PV system is removed, so the ledger stays empty.
    """
    entry = _entry(["enable_power_source_power"])
    _set(hass, "grid_power", 500)
    _set(hass, "pv_power", 500)
    _set(hass, "consumer_power", -400)
    await setup_integration(hass, entry)
    await _settle(hass)

    hass.config_entries.async_remove_subentry(entry, PV_SUB_ID)
    await _settle(hass)

    assert _ledger(entry) == []


async def test_removing_the_consumer_prunes_its_frozen_totals(
    hass: HomeAssistant,
) -> None:
    """A removed consumer leaves nothing behind in the source ledger.

    Its "Energy from removed devices" goes with it, so the next setup drops
    its frozen totals, and the source entry they hung from.
    """
    entry = _entry()
    await _draw_an_hour_from_pv(hass, entry)
    hass.config_entries.async_remove_subentry(entry, PV_SUB_ID)
    await _settle(hass)
    assert len(_ledger(entry)) == 1

    hass.config_entries.async_remove_subentry(entry, CONS_SUB_ID)
    await _settle(hass)

    assert _ledger(entry) == []


# ---------------------------------------------------------------------------
# Energy shares
# ---------------------------------------------------------------------------

SHARES = ["accumulate_power_source_energy", "enable_energy_source_shares"]


def _share(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> float:
    state = _state(hass, entry, key)
    assert state is not None, f"{key} was not created"
    assert state.state not in ("unknown", "unavailable"), f"{key} is {state.state}"
    return float(state.state)


async def _draw_two_hours(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """An hour on PV alone, then an hour on the grid alone, 400 W each.

    The unrestricted consumer draws 0.4 kWh from each: a lifetime mix of
    50 % PV and 50 % grid, whatever the mix is right now.
    """
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _set(hass, "grid_power", 0)
        _set(hass, "pv_power", 400)
        _set(hass, "consumer_power", -400)
        await setup_integration(hass, entry)

        _set(hass, "pv_power", 400)
        await _settle(hass)
        frozen.move_to(t0 + timedelta(hours=1))
        _set(hass, "grid_power", 400)
        _set(hass, "pv_power", 0)
        await _settle(hass)
        frozen.move_to(t0 + timedelta(hours=2))
        _set(hass, "grid_power", 400)
        await _settle(hass)


def _unrestricted(options: list[str]) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={"schema": 2, "scopes": {"consumer": options}},
        subentries_data=[
            make_grid_subentry_data(),
            make_pv_subentry_data(),
            make_consumer_subentry_data(),
        ],
    )


async def test_energy_shares_are_the_lifetime_mix(hass: HomeAssistant) -> None:
    """Half the energy came from each source, so each share reads 50 %.

    The power share right now is 100 % grid; the energy share remembers the
    hour on PV. The shares add up to 100 %.
    """
    from .conftest import GRID_SUB_ID

    entry = _unrestricted(SHARES)
    await _draw_two_hours(hass, entry)

    pv = _share(hass, entry, f"energy_share_from_{PV_SUB_ID}")
    grid = _share(hass, entry, f"energy_share_from_{GRID_SUB_ID}")
    assert pv == pytest.approx(50.0, abs=0.5)
    assert grid == pytest.approx(50.0, abs=0.5)
    assert pv + grid == pytest.approx(100.0)

    state = _state(hass, entry, f"energy_share_from_{PV_SUB_ID}")
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.attributes["state_class"] == "measurement"
    assert _state(hass, entry, "energy_share_from_removed_devices") is None


async def test_energy_shares_keep_a_removed_source(hass: HomeAssistant) -> None:
    """After removing the PV system its half stays in the mix.

    The grid's share does not jump to 100 %: the PV's 0.4 kWh are frozen and
    shown as the removed devices' share, 50 %.
    """
    from .conftest import GRID_SUB_ID

    entry = _unrestricted(SHARES)
    await _draw_two_hours(hass, entry)

    hass.config_entries.async_remove_subentry(entry, PV_SUB_ID)
    await _settle(hass)
    _set(hass, "grid_power", 400)
    await _settle(hass)

    grid = _share(hass, entry, f"energy_share_from_{GRID_SUB_ID}")
    removed = _share(hass, entry, "energy_share_from_removed_devices")
    assert grid == pytest.approx(50.0, abs=0.5)
    assert removed == pytest.approx(50.0, abs=0.5)
    assert grid + removed == pytest.approx(100.0)


async def test_energy_shares_are_unknown_before_anything_was_drawn(
    hass: HomeAssistant,
) -> None:
    """A share of nothing is undefined, not 0 %."""
    entry = _unrestricted(SHARES)
    _set(hass, "grid_power", 0)
    _set(hass, "pv_power", 0)
    _set(hass, "consumer_power", 0)
    await setup_integration(hass, entry)
    await _settle(hass)

    assert _state(hass, entry, f"energy_share_from_{PV_SUB_ID}").state == "unknown"


def test_choosing_energy_shares_turns_on_the_energy_totals() -> None:
    """The shares are worked out from the totals, so selecting them adds both."""
    from custom_components.power_insight.config_flow import scope_ui_to_leaves

    leaves = scope_ui_to_leaves("consumer", {"energy_source_shares": True})
    assert leaves == sorted(SHARES)
