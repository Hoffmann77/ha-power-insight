"""Correction factor when lifetime values are added AFTER initial setup.

Reproduces the reported workflow: create a PV system without lifetime
cost/production, then add them later in the reconfigure flow, then edit them
again. The base LCOE must be established on the first reconfigure that supplies
lifetime values (not only at creation) so the correction factor works.
"""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    DOMAIN,
    FULL_OPTIONS,
    make_grid_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _grid_with_price() -> dict:
    grid = make_grid_subentry_data()
    grid["data"]["adapter"]["config"][
        "grid_electricity_price_entity"
    ] = "sensor.grid_price"
    return grid


def _pv_subentry(entry):
    for sub in entry.subentries.values():
        if sub.data.get("adapter", {}).get("adapter_type") == "pv_system":
            return sub
    return None


def _levelized_state(hass, entry, sub_id):
    ent_reg = er.async_get(hass)
    suffix = f"{sub_id}_levelized_cost_savings_rate"
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.unique_id and ent.unique_id.endswith(suffix):
            return hass.states.get(ent.entity_id)
    return None


async def _reconfigure(hass, entry, sub_id, user_input):
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"),
        context={"source": "reconfigure", "subentry_id": sub_id},
    )
    await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input=user_input
    )
    await hass.async_block_till_done()


async def test_lifetime_added_via_reconfigure_then_edited(hass: HomeAssistant) -> None:
    """Base LCOE is captured on the reconfigure that first adds lifetime values."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Homegrid", options=FULL_OPTIONS,
        subentries_data=[_grid_with_price()],
    )
    hass.states.async_set("sensor.grid_power", "1000", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.grid_price", "0.30", {"unit_of_measurement": "EUR/kWh"})
    hass.states.async_set("sensor.pv_power", "2000", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    # --- Create a PV system WITHOUT lifetime cost / production ---
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"), context={"source": "user"},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"next_step_id": "pv_system"},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            "name": "PV System",
            "power_entity": "sensor.pv_power",
            "power_entity_inverted": False,
            "exports_power": True,
            "export_compensation": 0.08,
        },
    )
    await hass.async_block_till_done()

    pv = _pv_subentry(entry)
    assert pv is not None
    sub_id = pv.subentry_id
    cfg = pv.data["adapter"]["config"]
    # No lifetime values -> no base, no current, and no levelized sensor.
    assert cfg.get("default_lcoe") is None
    assert cfg.get("current_lcoe") is None
    assert _levelized_state(hass, entry, sub_id) is None

    # --- Reconfigure #1: add lifetime values (cost 20000 / prod 150000) ---
    await _reconfigure(hass, entry, sub_id, {
        "power_entity": "sensor.pv_power",
        "power_entity_inverted": False,
        "lifetime_production": 150000.0,
        "lifetime_cost": 20000.0,
    })
    cfg = _pv_subentry(entry).data["adapter"]["config"]
    assert cfg["default_lcoe"] == pytest.approx(0.13333333333333333)  # base captured now
    assert cfg["current_lcoe"] == pytest.approx(0.13333333333333333)
    assert cfg["correction_factor"] == pytest.approx(1.0)  # base == current
    first = _levelized_state(hass, entry, sub_id)
    assert first is not None
    base_value = float(first.state)

    # --- Reconfigure #2: raise cost 20000 -> 30000 (LCOE 0.1333 -> 0.20) ---
    await _reconfigure(hass, entry, sub_id, {
        "power_entity": "sensor.pv_power",
        "power_entity_inverted": False,
        "lifetime_production": 150000.0,
        "lifetime_cost": 30000.0,
    })
    cfg = _pv_subentry(entry).data["adapter"]["config"]
    assert cfg["default_lcoe"] == pytest.approx(0.13333333333333333)  # PRESERVED
    assert cfg["current_lcoe"] == pytest.approx(0.20)
    assert cfg["correction_factor"] == pytest.approx(1.5)  # 0.20 / 0.1333

    second = _levelized_state(hass, entry, sub_id)
    assert second is not None
    assert float(second.state) == pytest.approx(base_value * 1.5, rel=1e-6)
