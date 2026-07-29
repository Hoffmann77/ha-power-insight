"""Tests for user-seeded starting totals (baseline offsets on accumulation sensors).

Covers the sensor mechanism (baseline added on top of the live accumulator, and its
coexistence with the ``set_value`` service) plus the config-flow round-trips that
persist the values into entry options (combined) and subentry data (per-adapter).
"""
from __future__ import annotations

import copy

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    DOMAIN,
    GRID_SUB_ID,
    PV_SUB_ID,
    BASE_OPTIONS,
    FULL_OPTIONS,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, suffix: str) -> str | None:
    """Return the entity_id of the sensor whose unique_id ends with *suffix*."""
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.unique_id and ent.unique_id.endswith(suffix):
            return ent.entity_id
    return None


async def _set_value(hass: HomeAssistant, entity_id: str, value: float) -> None:
    """Seed an accumulation sensor's running total via the set_value service."""
    await hass.services.async_call(
        DOMAIN,
        "set_value",
        {"value": value},
        target={"entity_id": entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()


# ---------------------------------------------------------------------------
# Sensor mechanism — combined
# ---------------------------------------------------------------------------


async def test_combined_baseline_shown_before_accumulation(hass: HomeAssistant) -> None:
    """With a seeded baseline and no accumulation yet, the sensor reads the baseline."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={**FULL_OPTIONS, "starting_totals": {"combined_total_cost_savings": 500.0}},
        subentries_data=[make_grid_subentry_data(), make_pv_subentry_data()],
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    entity_id = _entity_id(hass, entry, "combined_total_cost_savings")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert float(state.state) == pytest.approx(500.0)


async def test_combined_baseline_adds_to_accumulator(hass: HomeAssistant) -> None:
    """The displayed total is the baseline plus the live accumulator (set_value seed)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={**FULL_OPTIONS, "starting_totals": {"combined_total_cost_savings": 500.0}},
        subentries_data=[make_grid_subentry_data(), make_pv_subentry_data()],
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    entity_id = _entity_id(hass, entry, "combined_total_cost_savings")
    await _set_value(hass, entity_id, 30.0)

    state = hass.states.get(entity_id)
    assert float(state.state) == pytest.approx(530.0)


async def test_combined_without_baseline_unchanged(hass: HomeAssistant) -> None:
    """Absent baseline leaves behavior identical: set_value seed shows unmodified."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=FULL_OPTIONS,
        subentries_data=[make_grid_subentry_data(), make_pv_subentry_data()],
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    entity_id = _entity_id(hass, entry, "combined_total_cost_savings")
    await _set_value(hass, entity_id, 30.0)

    state = hass.states.get(entity_id)
    assert float(state.state) == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Sensor mechanism — per-adapter
# ---------------------------------------------------------------------------


async def test_per_adapter_baseline_adds_to_accumulator(hass: HomeAssistant) -> None:
    """A per-adapter seed offsets that adapter's total (no correction factor here)."""
    pv_data = copy.deepcopy(make_pv_subentry_data())
    pv_data["data"]["starting_totals"] = {"total_cost_savings": 200.0}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=FULL_OPTIONS,
        subentries_data=[make_grid_subentry_data(), pv_data],
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    entity_id = _entity_id(hass, entry, f"{PV_SUB_ID}_total_cost_savings")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert float(state.state) == pytest.approx(200.0)

    await _set_value(hass, entity_id, 15.0)
    state = hass.states.get(entity_id)
    assert float(state.state) == pytest.approx(215.0)


async def test_per_adapter_baseline_does_not_leak_to_levelized(
    hass: HomeAssistant,
) -> None:
    """A plain-total seed must not offset the sibling levelized total (not seeded)."""
    pv_data = copy.deepcopy(make_pv_subentry_data())
    pv_data["data"]["starting_totals"] = {"total_cost_savings": 200.0}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=FULL_OPTIONS,
        subentries_data=[make_grid_subentry_data(), pv_data],
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    lev_id = _entity_id(hass, entry, f"{PV_SUB_ID}_total_levelized_cost_savings")
    assert lev_id is not None
    state = hass.states.get(lev_id)
    # No seed on the levelized total -> no baseline; starts at zero/unknown, not 200.
    assert state.state in ("0", "0.0", "unknown", "unavailable")


# ---------------------------------------------------------------------------
# Options flow round-trip — combined
# ---------------------------------------------------------------------------


async def _run_combined_then_grid(
    hass: HomeAssistant, entry: MockConfigEntry, starting_totals: dict
):
    """Drive the custom options flow through combined + grid to completion."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"preset": "custom", "debug_power_entities": False},
    )
    assert result["step_id"] == "combined"

    combined_input = {
        "power_sensors": {"distribution_power": False, "distribution_ratios": False},
        "costs": {"cost_method": "none", "accumulate_costs": False},
        "savings": {"savings_method": "none", "accumulate_savings": False},
        "financial_return": {
            "financial_return_method": "none",
            "accumulate_financial_return": False,
        },
    }
    if starting_totals is not None:
        combined_input["starting_totals"] = starting_totals
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=combined_input
    )
    assert result["step_id"] == "grid"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "power_sensors": {
                "distribution_power": False,
                "distribution_ratios": False,
                "distribution_shares": False,
            },
            "export_compensation": {
                "export_compensation_rate": False,
                "export_compensation_total": False,
            },
            "costs": {"cost_method": "none", "accumulate_costs": False},
        },
    )
    return result


async def test_options_flow_persists_combined_starting_totals(
    hass: HomeAssistant,
) -> None:
    """Values entered in the combined step land in entry.options['starting_totals']."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data()],
    )
    entry.add_to_hass(hass)

    result = await _run_combined_then_grid(
        hass, entry, {"combined_total_cost_savings": 500.0}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["starting_totals"] == {"combined_total_cost_savings": 500.0}


async def test_options_flow_clears_combined_starting_totals(
    hass: HomeAssistant,
) -> None:
    """Submitting an empty section removes a previously stored baseline (drops to 0)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={**BASE_OPTIONS, "starting_totals": {"combined_total_cost_savings": 500.0}},
        subentries_data=[make_grid_subentry_data()],
    )
    entry.add_to_hass(hass)

    result = await _run_combined_then_grid(hass, entry, {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert "starting_totals" not in entry.options


# ---------------------------------------------------------------------------
# Reconfigure round-trip — per-adapter
# ---------------------------------------------------------------------------


async def test_reconfigure_persists_pv_starting_totals(hass: HomeAssistant) -> None:
    """The per-adapter reconfigure step stores starting totals on the subentry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data(), make_pv_subentry_data()],
    )
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"),
        context={"source": "reconfigure", "subentry_id": PV_SUB_ID},
    )
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            "power_entity": "sensor.pv_power",
            "power_entity_inverted": False,
            "lifetime_production": 10000.0,
            "lifetime_cost": 1000.0,
            "starting_totals": {"total_cost_savings": 123.0},
        },
    )
    assert result["type"] == FlowResultType.ABORT

    assert entry.subentries[PV_SUB_ID].data["starting_totals"] == {
        "total_cost_savings": 123.0
    }


async def test_reconfigure_clears_pv_starting_totals(hass: HomeAssistant) -> None:
    """Clearing the fields removes the stored starting totals from the subentry."""
    pv_data = copy.deepcopy(make_pv_subentry_data())
    pv_data["data"]["starting_totals"] = {"total_cost_savings": 123.0}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data(), pv_data],
    )
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"),
        context={"source": "reconfigure", "subentry_id": PV_SUB_ID},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            "power_entity": "sensor.pv_power",
            "power_entity_inverted": False,
            "lifetime_production": 10000.0,
            "lifetime_cost": 1000.0,
            "starting_totals": {},
        },
    )
    assert result["type"] == FlowResultType.ABORT
    assert "starting_totals" not in entry.subentries[PV_SUB_ID].data
