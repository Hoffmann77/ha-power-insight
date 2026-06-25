"""Tests for the correction-factor reconfigure flow and sensor display (item C)."""
from __future__ import annotations

import copy

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    DOMAIN,
    BASE_OPTIONS,
    FULL_OPTIONS,
    PV_SUB_ID,
    GRID_SUB_ID,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _pv_state(hass: HomeAssistant, entry: MockConfigEntry, suffix: str):
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.unique_id and ent.unique_id.endswith(suffix):
            return hass.states.get(ent.entity_id)
    return None


# ---------------------------------------------------------------------------
# C2 — reconfigure recomputes the correction factor
# ---------------------------------------------------------------------------

async def test_reconfigure_pv_computes_correction_factor(
    hass: HomeAssistant,
) -> None:
    """Editing lifetime cost yields current_lcoe and a correction factor.

    The immutable base (default_lcoe) is left unchanged and the lifetime
    values are written back to the subentry top level.
    """
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
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    # Double the lifetime cost (production unchanged): lcoe 0.10 -> 0.20.
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            "power_entity": "sensor.pv_power",
            "power_entity_inverted": False,
            "lifetime_production": 10000.0,
            "lifetime_cost": 2000.0,
        },
    )
    assert result["type"] == FlowResultType.ABORT  # update_reload_and_abort

    subentry = entry.subentries[PV_SUB_ID]
    config = subentry.data["adapter"]["config"]
    assert config["default_lcoe"] == 0.10  # base unchanged
    assert config["current_lcoe"] == pytest.approx(0.20)
    assert config["correction_factor"] == pytest.approx(2.0)
    # Lifetime values are persisted at the subentry top level.
    assert subentry.data["lifetime_cost"] == 2000.0


# ---------------------------------------------------------------------------
# A3 — per-adapter levelized sensors gated on adapter.lcoe
# ---------------------------------------------------------------------------

async def test_levelized_sensors_absent_without_lcoe(hass: HomeAssistant) -> None:
    """A PV adapter without a configured LCOE gets no levelized sensors."""
    pv_data = copy.deepcopy(make_pv_subentry_data())
    # Remove the levelized cost so adapter.lcoe is None.
    pv_data["data"]["adapter"]["config"].pop("default_lcoe")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data(), pv_data],
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    ent_reg = er.async_get(hass)
    uids = {
        e.unique_id
        for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    }
    assert f"{entry.entry_id}_{PV_SUB_ID}_levelized_operating_cost_rate" not in uids


async def test_levelized_sensors_present_with_lcoe(hass: HomeAssistant) -> None:
    """A PV adapter with a configured LCOE gets levelized sensors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=FULL_OPTIONS,
        subentries_data=[make_grid_subentry_data(), make_pv_subentry_data()],
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    ent_reg = er.async_get(hass)
    uids = {
        e.unique_id
        for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    }
    assert f"{entry.entry_id}_{PV_SUB_ID}_levelized_operating_cost_rate" in uids


# ---------------------------------------------------------------------------
# C4 — per-adapter levelized display is scaled by the correction factor
# ---------------------------------------------------------------------------

async def test_levelized_measurement_scaled_by_factor(hass: HomeAssistant) -> None:
    """The displayed levelized savings rate equals the base value × factor."""
    grid_data = copy.deepcopy(make_grid_subentry_data())
    grid_data["data"]["adapter"]["config"][
        "grid_electricity_price_entity"
    ] = "sensor.grid_price"
    pv_data = copy.deepcopy(make_pv_subentry_data())
    pv_data["data"]["adapter"]["config"]["correction_factor"] = 2.0
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=FULL_OPTIONS,
        subentries_data=[grid_data, pv_data],
    )
    hass.states.async_set(
        "sensor.grid_power", "1000", {"unit_of_measurement": "W"}
    )
    hass.states.async_set(
        "sensor.grid_price", "0.30", {"unit_of_measurement": "EUR/kWh"}
    )
    hass.states.async_set(
        "sensor.pv_power", "2000", {"unit_of_measurement": "W"}
    )
    await setup_integration(hass, entry)
    await hass.async_block_till_done()

    pi = entry.runtime_data.power_insight
    base = pi.prod_adapters_levelized_cost_saving_rates.get(PV_SUB_ID)
    state = _pv_state(hass, entry, f"{PV_SUB_ID}_levelized_cost_savings_rate")
    assert state is not None
    assert base is not None
    assert float(state.state) == pytest.approx(base * 2.0, rel=1e-6)


# ---------------------------------------------------------------------------
# C5b — combined derived sensor reads the retired-adapter ledger
#
# The full removal lifecycle (accumulate -> remove -> snapshot -> reload) is
# covered end-to-end in tests/test_end_to_end.py; here we only check the read
# side: a pre-seeded ledger is reflected in the combined derived sensor.
# ---------------------------------------------------------------------------

async def test_combined_ledger_sensor_includes_retired_totals(
    hass: HomeAssistant,
) -> None:
    """The combined derived sensor adds the frozen retired-adapter totals."""
    from custom_components.power_insight.const import (
        CONF_CALCULATE_ACCUMULATED_ENTITIES,
        CONF_ACCUMULATE_LEVELIZED_COST_RATES,
        CONF_RETIRED_ADAPTERS,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={
            CONF_CALCULATE_ACCUMULATED_ENTITIES: [
                CONF_ACCUMULATE_LEVELIZED_COST_RATES
            ],
        },
        data={
            CONF_RETIRED_ADAPTERS: [
                {
                    "subentry_id": "01OLDPV0000000000000000001",
                    "adapter_type": "pv_system",
                    "title": "Old PV",
                    "retired_at": "2026-01-01T00:00:00+00:00",
                    "totals": {"total_levelized_operating_costs": 42.0},
                }
            ],
        },
        subentries_data=[make_grid_subentry_data()],
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    ent_reg = er.async_get(hass)
    uid = f"{entry.entry_id}_combined_total_levelized_operating_costs"
    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, uid)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    # No active levelized adapters; the value is just the frozen ledger sum.
    assert float(state.state) == pytest.approx(42.0)
