"""End-to-end integration tests: config entry -> loaded integration -> sensor states.

These build a real ``ConfigEntry`` with subentries, load the integration via
pytest-homeassistant-custom-component, feed source-entity states, and assert the
actual rendered HA sensor states — instantaneous, accumulated (time-driven), and
the removal-ledger lifecycle.
"""
from __future__ import annotations

import copy
from datetime import timedelta

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    DOMAIN,
    GRID_SUB_ID,
    PV_SUB_ID,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_obj(hass: HomeAssistant, entry: MockConfigEntry, suffix: str):
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.unique_id and ent.unique_id.endswith(suffix):
            return hass.states.get(ent.entity_id)
    return None


def _float(hass: HomeAssistant, entry: MockConfigEntry, suffix: str) -> float:
    st = _state_obj(hass, entry, suffix)
    assert st is not None, f"sensor *{suffix} not found"
    assert st.state not in ("unknown", "unavailable"), f"*{suffix} is {st.state}"
    return float(st.state)


def _grid_with_price() -> dict:
    grid = copy.deepcopy(make_grid_subentry_data())
    grid["data"]["adapter"]["config"][
        "grid_electricity_price_entity"
    ] = "sensor.grid_price"
    return grid


def _set(hass: HomeAssistant, entity_id: str, value, unit: str | None = "W") -> None:
    attrs = {"unit_of_measurement": unit} if unit else {}
    hass.states.async_set(entity_id, str(value), attrs)


async def _settle(hass: HomeAssistant) -> None:
    """Flush the coalesced (call_soon) sensor state writes a few times.

    Post-setup state events propagate engine -> custom event -> sensor write
    over a couple of event-loop iterations, and the derived combined sensor
    reads its siblings' already-written states, so several flushes are needed.
    """
    for _ in range(4):
        await hass.async_block_till_done()


# ---------------------------------------------------------------------------
# Test 1 — instantaneous sensor values
# ---------------------------------------------------------------------------

async def test_e2e_instantaneous_sensor_values(hass: HomeAssistant) -> None:
    """From config entry to rendered instantaneous sensor states."""
    pv = copy.deepcopy(make_pv_subentry_data())
    pv["data"]["adapter"]["config"]["correction_factor"] = 1.5
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={
            "schema": 2,
            "scopes": {
                "combined": [
                    "calculate_cost_rates", "calculate_levelized_cost_rates",
                ],
                "grid": ["calculate_cost_rates"],
                "pv_system": [
                    "calculate_cost_rates", "calculate_levelized_cost_rates",
                ],
            },
        },
        subentries_data=[_grid_with_price(), pv],
    )
    _set(hass, "sensor.grid_power", 1000)
    _set(hass, "sensor.grid_price", 0.30, unit="EUR/kWh")
    _set(hass, "sensor.pv_power", 2000)
    await setup_integration(hass, entry)
    await hass.async_block_till_done()

    # grid import 1 kW * 0.30 = 0.30 EUR/h
    assert _float(hass, entry, f"{GRID_SUB_ID}_import_cost_rate") == pytest.approx(0.30)
    # combined cost rate = grid 0.30 + PV 0.0
    assert _float(hass, entry, "combined_cost_rate") == pytest.approx(0.30)
    # combined price = 0.30 / 3 kW gross = 0.10 EUR/kWh
    assert _float(hass, entry, "combined_price_of_electricity") == pytest.approx(0.10)
    # corrected levelized rate = grid 0.30*1.0 + PV (2kW*0.10)=0.20 * 1.5 = 0.60
    # (base would be 0.50 — proves the correction factor flows end-to-end)
    assert _float(hass, entry, "combined_levelized_cost_rate") == pytest.approx(0.60)

    unit = _state_obj(hass, entry, "combined_cost_rate").attributes.get(
        "unit_of_measurement"
    )
    assert unit == "EUR/h"


# ---------------------------------------------------------------------------
# Test 2 — accumulated value over simulated time
# ---------------------------------------------------------------------------

async def test_e2e_accumulated_value_over_time(hass: HomeAssistant) -> None:
    """A constant rate held across an hour integrates into the total sensor.

    A constant rate (1 kW import * 0.30 = 0.30 EUR/h) is held and re-reported an
    hour later, so the trapezoidal step is exact regardless of propagation lag.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={
            "schema": 2,
            "scopes": {
                "grid": ["calculate_cost_rates", "accumulate_cost_rates"],
            },
        },
        subentries_data=[_grid_with_price(), make_pv_subentry_data()],
    )
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _set(hass, "sensor.grid_power", 1000)
        _set(hass, "sensor.grid_price", 0.30, unit="EUR/kWh")
        _set(hass, "sensor.pv_power", 2000)
        await setup_integration(hass, entry)

        # Anchor the integral at t0 (re-report the unchanged value).
        _set(hass, "sensor.grid_power", 1000)
        await _settle(hass)

        # One hour later, re-report and integrate the held 0.30 EUR/h rate.
        frozen.move_to(t0 + timedelta(hours=1))
        _set(hass, "sensor.grid_power", 1000)
        await _settle(hass)

    rate = _float(hass, entry, f"{GRID_SUB_ID}_import_cost_rate")
    total = _float(hass, entry, f"{GRID_SUB_ID}_total_import_cost")
    assert rate == pytest.approx(0.30)
    # 0.30 EUR/h held for 1 h = 0.30 EUR.
    assert total == pytest.approx(0.30, abs=1e-3)


# ---------------------------------------------------------------------------
# Test 3 — removal-ledger lifecycle
# ---------------------------------------------------------------------------

async def test_e2e_removal_ledger_lifecycle(hass: HomeAssistant) -> None:
    """Accumulate, remove the device, and verify the frozen ledger persists."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={
            "schema": 2,
            "scopes": {
                "combined": ["accumulate_levelized_cost_rates"],
                "pv_system": ["accumulate_levelized_cost_rates"],
            },
        },
        subentries_data=[_grid_with_price(), make_pv_subentry_data()],
    )
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _set(hass, "sensor.grid_power", 1000)
        _set(hass, "sensor.grid_price", 0.30, unit="EUR/kWh")
        _set(hass, "sensor.pv_power", -100)  # constant standby: PV consumes 100 W
        await setup_integration(hass, entry)

        # Anchor at t0, then integrate the held levelized operating-cost rate
        # (0.1 kW * 0.30 EUR/kWh = 0.03 EUR/h) over one hour.
        _set(hass, "sensor.pv_power", -100)
        await _settle(hass)
        frozen.move_to(t0 + timedelta(hours=1))
        _set(hass, "sensor.pv_power", -100)
        await _settle(hass)

    per_adapter = _float(
        hass, entry, f"{PV_SUB_ID}_total_levelized_operating_cost"
    )
    assert per_adapter == pytest.approx(0.03, abs=1e-3)
    # The derived combined sensor equals the sum of active per-adapter totals.
    combined = _float(hass, entry, "combined_total_levelized_operating_cost")
    assert combined == pytest.approx(per_adapter, abs=1e-6)

    # Remove the PV device. HA clears its entities, whose teardown snapshots
    # the final levelized total into the ledger (entry.data).
    hass.config_entries.async_remove_subentry(entry, PV_SUB_ID)
    await _settle(hass)

    # Each device snapshots its two levelized totals as separate ledger entries;
    # sum the operating-costs key across them.
    ledger = entry.data.get("retired_adapters", [])
    op_total = sum(
        e.get("totals", {}).get("total_levelized_operating_cost", 0.0)
        for e in ledger
    )
    assert op_total == pytest.approx(per_adapter, abs=1e-6)

    # The frozen contribution persists in the combined total though the PV
    # device is gone. Re-report a source entity to refresh the derived sensor.
    _set(hass, "sensor.grid_power", 1000)
    await _settle(hass)
    combined_after = _float(hass, entry, "combined_total_levelized_operating_cost")
    assert combined_after == pytest.approx(per_adapter, abs=1e-6)

    # Reload again: no double-count.
    await hass.config_entries.async_reload(entry.entry_id)
    await _settle(hass)
    _set(hass, "sensor.grid_power", 1000)
    await _settle(hass)
    combined_reloaded = _float(
        hass, entry, "combined_total_levelized_operating_cost"
    )
    assert combined_reloaded == pytest.approx(per_adapter, abs=1e-6)
