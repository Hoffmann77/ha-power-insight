"""Tests for the running totals carrying the history from the devices' apps.

The home is the plan's first example (docs/dev/carried-over-history.md): one
PV system that produced 10,000 kWh and one battery that charged 2,500 kWh
from it and discharged 2,200, 4,000 kWh fed in, a tariff of 0.34, feed-in
0.08, LCOE 0.10 and LCOS 0.15. Every reading is 0 W, so the sensors count
nothing themselves and each total reads exactly what it carries over.
"""

from __future__ import annotations

import copy
from datetime import timedelta

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    BAT_SUB_ID,
    DOMAIN,
    GRID_SUB_ID,
    PV_SUB_ID,
    make_battery_subentry_data,
    make_grid_subentry_data,
    make_pv_subentry_data,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

SINCE = "2026-08-14T08:00:00+00:00"

_DEVICE_TOTALS = [
    "accumulate_cost_saving_rates",
    "accumulate_levelized_cost_saving_rates",
    "accumulate_export_compensation",
    "accumulate_financial_return",
    "accumulate_levelized_financial_return",
    "accumulate_cost_rates",
    "accumulate_levelized_cost_rates",
]
_OPTIONS = {
    "schema": 2,
    "scopes": {
        "combined": [
            "accumulate_cost_saving_rates",
            "accumulate_levelized_cost_saving_rates",
            "accumulate_financial_return",
            "accumulate_cost_rates",
        ],
        "grid": ["accumulate_export_compensation"],
        "pv_system": _DEVICE_TOTALS,
        "battery": _DEVICE_TOTALS,
    },
}


def _with(subentry: dict, history: dict | None) -> dict:
    subentry = copy.deepcopy(subentry)
    subentry["data"]["counting_since"] = SINCE
    if history is not None:
        subentry["data"]["history"] = history
    return subentry


def _entry(grid_history: dict | None = None) -> MockConfigEntry:
    grid = _with(
        make_grid_subentry_data(),
        {"home_fed_in": 4000.0, "average_tariff": 0.34} if grid_history is None else grid_history,
    )
    grid["data"]["adapter"]["config"]["grid_electricity_price_entity"] = "sensor.grid_price"
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        minor_version=5,
        options=_OPTIONS,
        subentries_data=[
            grid,
            _with(make_pv_subentry_data(), {"produced": 10000.0}),
            _with(
                make_battery_subentry_data(charge_from_adapters=[PV_SUB_ID]),
                {"charged": 2500.0, "grid_charged": 0.0, "discharged": 2200.0},
            ),
        ],
    )


def _readings(hass: HomeAssistant) -> None:
    for name in ("grid_power", "pv_power", "battery_power"):
        hass.states.async_set(f"sensor.{name}", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.grid_price", "0.30", {"unit_of_measurement": "EUR/kWh"})


async def _settle(hass: HomeAssistant) -> None:
    for _ in range(4):
        await hass.async_block_till_done()


async def _counting(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up, then let an hour pass, so every total has counted (nothing).

    Two readings at the same instant close it: the first makes the totals
    count the hour, the second refreshes the combined levelized totals, which
    sum the per-device totals as they stood at the last changed reading.
    """
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _readings(hass)
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await _settle(hass)
        frozen.move_to(t0 + timedelta(hours=1))
        await _refresh(hass)


async def _refresh(hass: HomeAssistant) -> None:
    """Change a reading and change it back, at the same instant: nothing is
    counted, but every sensor recalculates.
    """
    for watts in ("1", "0"):
        hass.states.async_set("sensor.grid_power", watts, {"unit_of_measurement": "W"})
        await _settle(hass)


def _state(hass: HomeAssistant, entry: MockConfigEntry, unique_suffix: str):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{unique_suffix}"
    )
    assert entity_id is not None, unique_suffix
    return hass.states.get(entity_id)


def _value(hass: HomeAssistant, entry: MockConfigEntry, unique_suffix: str) -> float:
    return float(_state(hass, entry, unique_suffix).state)


async def test_device_totals_carry_their_history(hass: HomeAssistant) -> None:
    """Each device's totals read what it counted (nothing) plus the plan's
    first example: the PV 1,190 saved, 840 levelized, 320 export
    compensation, 1,510 and 760 financial return; the battery 748 and 168
    saved, 250 levelized operating cost from the PV energy it charged.
    """
    entry = _entry()
    await _counting(hass, entry)

    expected = {
        f"{PV_SUB_ID}_total_cost_savings": 1190.0,
        f"{PV_SUB_ID}_total_levelized_cost_savings": 840.0,
        f"{PV_SUB_ID}_total_export_compensation": 320.0,
        f"{PV_SUB_ID}_total_financial_return": 1510.0,
        f"{PV_SUB_ID}_total_levelized_financial_return": 760.0,
        f"{BAT_SUB_ID}_total_cost_savings": 748.0,
        f"{BAT_SUB_ID}_total_levelized_cost_savings": 168.0,
        f"{BAT_SUB_ID}_total_operating_cost": 0.0,
        f"{BAT_SUB_ID}_total_levelized_operating_cost": 250.0,
    }
    actual = {suffix: _value(hass, entry, suffix) for suffix in expected}
    assert actual == pytest.approx(expected, abs=1e-6)


async def test_whole_home_totals_carry_every_devices_history(
    hass: HomeAssistant,
) -> None:
    """A combined total stays the sum of its devices: savings 1,190 + 748,
    financial return 1,510 + 748, levelized savings 840 + 168, and the
    charging cost is the battery's grid charging, none. The grid's export
    compensation is the whole home's: the PV's 320.
    """
    entry = _entry()
    await _counting(hass, entry)

    assert _value(hass, entry, "combined_total_cost_savings") == pytest.approx(1938.0)
    assert _value(hass, entry, "combined_total_financial_return") == pytest.approx(2258.0)
    assert _value(hass, entry, "combined_total_levelized_cost_savings") == pytest.approx(1008.0)
    assert _value(hass, entry, "combined_total_charging_cost") == pytest.approx(0.0)
    assert _value(hass, entry, f"{GRID_SUB_ID}_total_export_compensation") == (
        pytest.approx(320.0)
    )


async def test_attributes_split_carried_over_from_tracked(hass: HomeAssistant) -> None:
    """The attributes show what was carried over, up to when, and what the
    sensor counted itself, so the user can see where the number comes from.
    """
    entry = _entry()
    await _counting(hass, entry)

    attributes = _state(hass, entry, f"{PV_SUB_ID}_total_cost_savings").attributes
    assert attributes["carried_over"] == pytest.approx(1190.0)
    assert attributes["carried_over_until"] == SINCE
    assert attributes["tracked"] == pytest.approx(0.0)


async def test_a_reload_does_not_add_the_history_twice(hass: HomeAssistant) -> None:
    """The restored total is what the sensor counted, never what it displayed,
    so a reload (or a restart) adds the history once, not on top of itself.
    """
    entry = _entry()
    await _counting(hass, entry)
    expected = {
        f"{PV_SUB_ID}_total_cost_savings": 1190.0,
        "combined_total_cost_savings": 1938.0,
    }
    assert {s: _value(hass, entry, s) for s in expected} == pytest.approx(expected)

    await hass.config_entries.async_reload(entry.entry_id)
    await _settle(hass)
    assert {s: _value(hass, entry, s) for s in expected} == pytest.approx(expected)


async def test_a_total_missing_a_term_says_why(hass: HomeAssistant) -> None:
    """Without the average tariff the savings carry nothing: the total reads
    only what it counted, and the attribute gives the reason. The export
    compensation needs only the feed-in tariff and still carries its 320.
    The combined savings name the devices left out.
    """
    entry = _entry(grid_history={"home_fed_in": 4000.0})
    await _counting(hass, entry)

    savings = _state(hass, entry, f"{PV_SUB_ID}_total_cost_savings")
    assert float(savings.state) == pytest.approx(0.0)
    assert savings.attributes["carried_over_missing"] == "no_tariff"
    assert "carried_over" not in savings.attributes
    assert _value(hass, entry, f"{PV_SUB_ID}_total_export_compensation") == (
        pytest.approx(320.0)
    )
    combined = _state(hass, entry, "combined_total_cost_savings")
    assert combined.attributes["carried_over_missing"] == {
        "Solar PV": "no_tariff",
        "Battery": "no_tariff",
    }


async def test_a_removed_device_stays_in_the_whole_home_totals(
    hass: HomeAssistant,
) -> None:
    """Removing the battery keeps its 748 in the combined savings, so they
    still read 1,938, and its levelized 168 in the combined levelized
    savings, through the ledger that froze its total as displayed.
    """
    entry = _entry()
    await _counting(hass, entry)

    assert hass.config_entries.async_remove_subentry(entry, BAT_SUB_ID)
    await _settle(hass)
    await _refresh(hass)

    assert _value(hass, entry, "combined_total_cost_savings") == pytest.approx(1938.0)
    assert _value(hass, entry, "combined_total_levelized_cost_savings") == (
        pytest.approx(1008.0)
    )


async def test_a_correction_restates_the_carried_over_history(
    hass: HomeAssistant,
) -> None:
    """Doubling the PV's correction factor (LCOE 0.10 → 0.20) restates the
    history at the reload it causes: the PV's levelized savings become
    3,500 × 0.14 = 490 and the battery's 748 − 330 − 500 = −82, because the
    PV energy it charged now costs twice as much. Standard savings stay.
    """
    entry = _entry()
    await _counting(hass, entry)

    pv = entry.subentries[PV_SUB_ID]
    config = {**pv.data["adapter"]["config"], "correction_factor": 2.0}
    hass.config_entries.async_update_subentry(
        entry, pv, data={**pv.data, "adapter": {**pv.data["adapter"], "config": config}}
    )
    await _settle(hass)

    assert _value(hass, entry, f"{PV_SUB_ID}_total_levelized_cost_savings") == (
        pytest.approx(490.0)
    )
    assert _value(hass, entry, f"{BAT_SUB_ID}_total_levelized_cost_savings") == (
        pytest.approx(-82.0)
    )
    assert _value(hass, entry, f"{PV_SUB_ID}_total_cost_savings") == pytest.approx(1190.0)
