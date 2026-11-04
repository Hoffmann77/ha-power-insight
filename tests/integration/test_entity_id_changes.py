"""Changing an entity ID in the entity registry renames the entity in place.

From Home Assistant 2026.11 an entity whose ``entity_id`` changes is updated in
place, without ``async_will_remove_from_hass`` / ``async_added_to_hass``, if it
implements ``async_entity_id_changed``. Every class here that overrides an add
or remove hook opts in. Only the energy shares follow other entities by entity
ID, so a renamed total has to tell them its new one.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import async_get_platforms
import homeassistant.util.dt as dt_util
from pytest_homeassistant.common import MockConfigEntry

from .conftest import (
    CONS_SUB_ID,
    DOMAIN,
    GRID_SUB_ID,
    PV_SUB_ID,
    make_consumer_subentry_data,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

SHARES = ["accumulate_power_source_energy", "enable_energy_source_shares"]


def _entry(consumer_options: list[str]) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={"schema": 2, "scopes": {"consumer": consumer_options}},
        subentries_data=[
            make_grid_subentry_data(),
            make_pv_subentry_data(),
            make_consumer_subentry_data(),
        ],
    )


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{CONS_SUB_ID}_{key}"
    )
    assert entity_id is not None, f"{key} was not created"
    return entity_id


def _entity(hass: HomeAssistant, entity_id: str) -> Entity:
    for platform in async_get_platforms(hass, DOMAIN):
        if entity_id in platform.entities:
            return platform.entities[entity_id]
    raise AssertionError(f"{entity_id} is not added")


def _count_adds(entity: Entity) -> list[None]:
    """Record every later ``async_added_to_hass`` of ``entity``."""
    calls: list[None] = []
    original = entity.async_added_to_hass

    async def _counted() -> None:
        calls.append(None)
        await original()

    entity.async_added_to_hass = _counted  # type: ignore[method-assign]
    return calls


def _set(hass: HomeAssistant, entity: str, watts: float) -> None:
    hass.states.async_set(f"sensor.{entity}", str(watts), {"unit_of_measurement": "W"})


async def _settle(hass: HomeAssistant) -> None:
    for _ in range(4):
        await hass.async_block_till_done()


async def _rename(hass: HomeAssistant, old: str, new: str) -> None:
    er.async_get(hass).async_update_entity(old, new_entity_id=new)
    await _settle(hass)


@pytest.mark.parametrize(
    "key",
    [
        f"power_from_{PV_SUB_ID}",
        f"energy_from_{PV_SUB_ID}",
        f"energy_share_from_{PV_SUB_ID}",
    ],
    ids=["power", "total", "share"],
)
async def test_renamed_in_place(hass: HomeAssistant, key: str) -> None:
    """The same entity carries on under the new ID, without being added again.

    One of each kind of class that overrides an add or remove hook: an
    instantaneous sensor, a running total and an energy share. Being added
    again would restore the total and restart its current slice.
    """
    entry = _entry([*SHARES, "enable_power_source_power"])
    _set(hass, "grid_power", 0)
    _set(hass, "pv_power", 400)
    _set(hass, "consumer_power", -400)
    await setup_integration(hass, entry)
    await _settle(hass)

    old = _entity_id(hass, entry, key)
    entity = _entity(hass, old)
    adds = _count_adds(entity)

    await _rename(hass, old, "sensor.renamed")

    assert adds == []
    assert _entity(hass, "sensor.renamed") is entity
    assert hass.states.get(old) is None
    assert hass.states.get("sensor.renamed") is not None


async def test_renamed_total_keeps_counting(hass: HomeAssistant) -> None:
    """A total renamed mid-hour still counts the whole hour: 400 W → 0.4 kWh."""
    entry = _entry(SHARES)
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _set(hass, "grid_power", 0)
        _set(hass, "pv_power", 400)
        _set(hass, "consumer_power", -400)
        await setup_integration(hass, entry)
        _set(hass, "pv_power", 400)
        await _settle(hass)

        frozen.move_to(t0 + timedelta(minutes=30))
        await _rename(
            hass, _entity_id(hass, entry, f"energy_from_{PV_SUB_ID}"), "sensor.pv_kwh"
        )

        frozen.move_to(t0 + timedelta(hours=1))
        _set(hass, "pv_power", 400)
        await _settle(hass)

    assert float(hass.states.get("sensor.pv_kwh").state) == pytest.approx(0.4, abs=1e-3)


async def test_share_follows_a_renamed_total(hass: HomeAssistant) -> None:
    """The share updates when only the renamed total moves.

    An hour on the grid alone (0.4 kWh, PV share 0 %), then the PV total is
    renamed, then an hour on PV alone. In that second hour the grid total
    stays at 0.4 kWh, so the PV total is the only one whose state changes:
    the PV share can only reach 50 % if it follows that total under its new
    ID.
    """
    entry = _entry(SHARES)
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _set(hass, "grid_power", 400)
        _set(hass, "pv_power", 0)
        _set(hass, "consumer_power", -400)
        await setup_integration(hass, entry)
        _set(hass, "grid_power", 400)
        await _settle(hass)

        frozen.move_to(t0 + timedelta(hours=1))
        _set(hass, "grid_power", 0)
        _set(hass, "pv_power", 400)
        await _settle(hass)
        share = _entity_id(hass, entry, f"energy_share_from_{PV_SUB_ID}")
        assert float(hass.states.get(share).state) == pytest.approx(0.0)

        await _rename(
            hass, _entity_id(hass, entry, f"energy_from_{PV_SUB_ID}"), "sensor.pv_kwh"
        )

        frozen.move_to(t0 + timedelta(hours=2))
        _set(hass, "pv_power", 400)
        await _settle(hass)

    assert float(hass.states.get("sensor.pv_kwh").state) == pytest.approx(0.4, abs=1e-3)
    assert float(hass.states.get(share).state) == pytest.approx(50.0, abs=0.5)
    grid_share = _entity_id(hass, entry, f"energy_share_from_{GRID_SUB_ID}")
    assert float(hass.states.get(grid_share).state) == pytest.approx(50.0, abs=0.5)
