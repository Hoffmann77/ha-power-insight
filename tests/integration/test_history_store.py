"""Tests for keeping the carried-over history in the config entry.

``history_store.py`` solves the history at setup whenever the entered figures
changed, stores the records in ``entry.data["history"]``, and keeps a
removed device's record, inputs and last price.
"""

from __future__ import annotations

import copy

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.power_insight.history_store import (
    price_lookup,
    stored_records,
)

from .conftest import (
    BAT_SUB_ID,
    BASE_OPTIONS,
    DOMAIN,
    GRID_SUB_ID,
    PV_SUB_ID,
    make_battery_subentry_data,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

SINCE = "2026-08-14T08:00:00+00:00"
CARPORT_SUB_ID = "01PV0000000000000000000002"


def _with(subentry: dict, history: dict | None = None, since: str = SINCE) -> dict:
    """``subentry`` with history entered and a counting start."""
    subentry = copy.deepcopy(subentry)
    subentry["data"]["counting_since"] = since
    if history is not None:
        subentry["data"]["history"] = history
    return subentry


def _entry(*subentries: dict) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        minor_version=5,
        options=BASE_OPTIONS,
        subentries_data=list(subentries),
    )


def _home(history: dict | None = None) -> dict:
    return _with(make_grid_subentry_data(), {"home_fed_in": 4000.0, "average_tariff": 0.34, **(history or {})})


def _carport(history: dict | None = None, since: str = SINCE) -> dict:
    return _with(
        make_pv_subentry_data(CARPORT_SUB_ID, power_entity="sensor.carport_power"),
        history,
        since,
    )


def _states(hass: HomeAssistant) -> None:
    for name in ("grid_power", "pv_power", "carport_power", "battery_power"):
        hass.states.async_set(f"sensor.{name}", "0", {"unit_of_measurement": "W"})


async def _reload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


async def _single(hass: HomeAssistant) -> MockConfigEntry:
    """The plan's first example: one PV system, one battery charging from it."""
    entry = _entry(
        _home(),
        _with(make_pv_subentry_data(), {"produced": 10000.0}),
        _with(
            make_battery_subentry_data(charge_from_adapters=[PV_SUB_ID]),
            {"charged": 2500.0, "grid_charged": 0.0, "discharged": 2200.0},
        ),
    )
    _states(hass)
    await setup_integration(hass, entry)
    return entry


async def test_setup_solves_and_stores_the_history(hass: HomeAssistant) -> None:
    """Setting up with history entered stores what it solved to: the PV's
    3,500 kWh into the home and 4,000 fed in, the battery's 2,200 into the
    home and its 2,500 charged from the PV. The feed-in tariff defaults to
    the export compensation the PV is configured with (0.08).
    """
    entry = await _single(hass)
    records = stored_records(entry)

    assert records[PV_SUB_ID].flows.to_home == pytest.approx(3500.0)
    assert records[PV_SUB_ID].flows.exported == pytest.approx(4000.0)
    assert records[PV_SUB_ID].feed_in_tariff == 0.08
    assert records[PV_SUB_ID].tariff == 0.34
    assert records[BAT_SUB_ID].flows.from_pv == pytest.approx({PV_SUB_ID: 2500.0})
    assert entry.data["history"]["last_price"] == pytest.approx(
        {PV_SUB_ID: 0.10, BAT_SUB_ID: 0.15}
    )


async def test_no_history_writes_nothing(hass: HomeAssistant) -> None:
    """An entry without history entered gets no history key at all."""
    entry = _entry(_with(make_grid_subentry_data()), _with(make_pv_subentry_data()))
    _states(hass)
    await setup_integration(hass, entry)
    assert "history" not in entry.data


async def test_the_solved_history_is_frozen_until_figures_change(
    hass: HomeAssistant,
) -> None:
    """A reload with the same figures does not re-solve: a record changed
    behind the solver's back stays as it is. Changing an entered figure does
    re-solve.
    """
    entry = await _single(hass)
    history = copy.deepcopy(entry.data["history"])
    history["records"][PV_SUB_ID]["flows"]["to_home"] = 1.0
    hass.config_entries.async_update_entry(entry, data={**entry.data, "history": history})
    await hass.async_block_till_done()
    await _reload(hass, entry)
    assert stored_records(entry)[PV_SUB_ID].flows.to_home == 1.0

    pv = entry.subentries[PV_SUB_ID]
    hass.config_entries.async_update_subentry(
        entry, pv, data={**pv.data, "history": {"produced": 11000.0}}
    )
    await hass.async_block_till_done()
    assert stored_records(entry)[PV_SUB_ID].flows.to_home == pytest.approx(4500.0)


async def test_a_removed_device_keeps_its_history(hass: HomeAssistant) -> None:
    """Removing the battery re-solves nothing: the PV keeps the 3,500 kWh it
    was credited with, and the battery's record and last price stay, so its
    carried-over totals, and a battery history pricing its charging at the
    removed device's LCOE, still have what they need.
    """
    entry = await _single(hass)
    assert hass.config_entries.async_remove_subentry(entry, BAT_SUB_ID)
    await hass.async_block_till_done()

    records = stored_records(entry)
    assert records[PV_SUB_ID].flows.to_home == pytest.approx(3500.0)
    assert records[BAT_SUB_ID].flows.to_home == pytest.approx(2200.0)
    assert entry.data["history"]["last_price"][BAT_SUB_ID] == pytest.approx(0.15)

    price = price_lookup(entry, entry.runtime_data.power_insight)
    assert price(BAT_SUB_ID) == pytest.approx(0.15)
    assert price(PV_SUB_ID) == pytest.approx(0.10)
    assert price(GRID_SUB_ID) is None


async def test_a_re_solve_still_counts_a_removed_device(hass: HomeAssistant) -> None:
    """Roof and carport split the home's 4,000 kWh fed in 8 : 2. After the
    carport is removed, a changed tariff re-solves the history; the
    carport's kWh are still part of the home's totals, so the roof keeps
    its 3,200 kWh rather than taking the carport's share too.
    """
    entry = _entry(
        _home(),
        _with(make_pv_subentry_data(), {"produced": 8000.0}),
        _carport({"produced": 2000.0}),
    )
    _states(hass)
    await setup_integration(hass, entry)
    assert stored_records(entry)[PV_SUB_ID].flows.exported == pytest.approx(3200.0)

    assert hass.config_entries.async_remove_subentry(entry, CARPORT_SUB_ID)
    await hass.async_block_till_done()
    grid = entry.subentries[GRID_SUB_ID]
    hass.config_entries.async_update_subentry(
        entry, grid, data={**grid.data, "history": {"home_fed_in": 4000.0, "average_tariff": 0.30}}
    )
    await hass.async_block_till_done()

    records = stored_records(entry)
    assert records[PV_SUB_ID].tariff == 0.30
    assert records[PV_SUB_ID].flows.exported == pytest.approx(3200.0)
    assert records[CARPORT_SUB_ID].tariff == 0.34  # frozen with its device


async def test_figures_that_do_not_balance_keep_the_last_history(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """The flows refuse figures that cannot balance; if some arrive anyway
    (edited outside the flow), the history solved last is kept and a
    warning names the problem.
    """
    entry = await _single(hass)
    pv = entry.subentries[PV_SUB_ID]
    hass.config_entries.async_update_subentry(
        entry, pv, data={**pv.data, "history": {"produced": 10000.0, "fed_in": 20000.0}}
    )
    await hass.async_block_till_done()

    assert stored_records(entry)[PV_SUB_ID].flows.to_home == pytest.approx(3500.0)
    assert "history_fed_in_exceeds_output" in caplog.text


async def test_a_device_added_later_stands_alone(hass: HomeAssistant) -> None:
    """The carport was set up two days after the grid, so its history is
    standalone: its own feed-in and tariff, none of the home's figures.
    """
    entry = _entry(
        _home(),
        _carport(
            {"produced": 3000.0, "fed_in": 1000.0, "average_tariff": 0.30},
            since="2026-08-16T09:00:00+00:00",
        ),
    )
    _states(hass)
    await setup_integration(hass, entry)

    record = stored_records(entry)[CARPORT_SUB_ID]
    assert record.tariff == 0.30
    assert record.flows.to_home == pytest.approx(2000.0)
    assert entry.data["history"]["inputs"][CARPORT_SUB_ID]["standalone"] is True


async def test_a_correction_is_priced_live(hass: HomeAssistant) -> None:
    """A live device's price is its LCOE times its correction factor, read
    from the engine at the time, so an edited lifetime cost restates its
    history without re-solving anything.
    """
    entry = _entry(
        _home(),
        _with(make_pv_subentry_data(), {"produced": 10000.0}),
    )
    _states(hass)
    await setup_integration(hass, entry)

    pv = entry.subentries[PV_SUB_ID]
    config = {**pv.data["adapter"]["config"], "correction_factor": 2.0}
    hass.config_entries.async_update_subentry(
        entry, pv, data={**pv.data, "adapter": {**pv.data["adapter"], "config": config}}
    )
    await hass.async_block_till_done()

    price = price_lookup(entry, entry.runtime_data.power_insight)
    assert price(PV_SUB_ID) == pytest.approx(0.20)
    assert entry.data["history"]["last_price"][PV_SUB_ID] == pytest.approx(0.20)


def _tariff_issue(hass: HomeAssistant, entry: MockConfigEntry):
    from homeassistant.helpers import issue_registry as ir

    return ir.async_get(hass).async_get_issue(
        DOMAIN, f"history_tariff_missing_{entry.entry_id}"
    )


async def test_a_missing_tariff_raises_a_repair_issue_until_added(
    hass: HomeAssistant,
) -> None:
    """The PV system has kWh history, but neither it nor the grid has an
    average grid tariff, so its savings carry nothing. A repair issue names
    it and says where to add the tariff; once the grid has one, the issue
    goes away at the setup that follows.
    """
    entry = _entry(
        _with(make_grid_subentry_data(), {"home_fed_in": 4000.0}),
        _with(make_pv_subentry_data(), {"produced": 10000.0}),
    )
    _states(hass)
    await setup_integration(hass, entry)

    issue = _tariff_issue(hass, entry)
    assert issue is not None
    assert issue.translation_placeholders["devices"] == "Solar PV"

    grid = entry.subentries[GRID_SUB_ID]
    hass.config_entries.async_update_subentry(
        entry, grid,
        data={**grid.data, "history": {"home_fed_in": 4000.0, "average_tariff": 0.34}},
    )
    await hass.async_block_till_done()
    assert _tariff_issue(hass, entry) is None


@pytest.mark.parametrize(
    ("grid_history", "pv_history"),
    [
        pytest.param(
            {"home_fed_in": 4000.0},
            {"produced": 10000.0, "average_tariff": 0.30},
            id="device-has-its-own-tariff",
        ),
        pytest.param(None, None, id="no-history"),
    ],
)
async def test_no_repair_issue_when_nothing_waits_for_a_tariff(
    hass: HomeAssistant, grid_history: dict | None, pv_history: dict | None
) -> None:
    """A device with its own tariff values its own kWh, and an installation
    without history has nothing to value: neither raises the issue.
    """
    entry = _entry(
        _with(make_grid_subentry_data(), grid_history),
        _with(make_pv_subentry_data(), pv_history),
    )
    _states(hass)
    await setup_integration(hass, entry)
    assert _tariff_issue(hass, entry) is None
