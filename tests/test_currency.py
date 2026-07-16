"""Tests for currency handling — sensor units and config-flow input units."""
from __future__ import annotations

import types

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.power_insight.config_flow import (
    build_schema,
    PV_SYSTEM_FIELDS,
)
from custom_components.power_insight.sensor import _resolve_currency_unit
from .conftest import (
    DOMAIN,
    FULL_OPTIONS,
    PV_SUB_ID,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _unit(hass: HomeAssistant, entry: MockConfigEntry, suffix: str) -> str | None:
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.unique_id and ent.unique_id.endswith(suffix):
            state = hass.states.get(ent.entity_id)
            return state.attributes.get("unit_of_measurement") if state else None
    return None


# ---------------------------------------------------------------------------
# _resolve_currency_unit (pure helper)
# ---------------------------------------------------------------------------

def test_resolve_currency_unit_substitutes() -> None:
    hass = types.SimpleNamespace(config=types.SimpleNamespace(currency="GBP"))
    assert _resolve_currency_unit("EUR/h", hass) == "GBP/h"
    assert _resolve_currency_unit("EUR/kWh", hass) == "GBP/kWh"
    assert _resolve_currency_unit("EUR", hass) == "GBP"
    # Non-currency units are untouched.
    assert _resolve_currency_unit("W", hass) == "W"


def test_resolve_currency_unit_falls_back_to_eur() -> None:
    # No hass / no configured currency keeps the literal placeholder.
    assert _resolve_currency_unit("EUR/h", None) == "EUR/h"
    hass = types.SimpleNamespace(config=types.SimpleNamespace(currency=None))
    assert _resolve_currency_unit("EUR/h", hass) == "EUR/h"


# ---------------------------------------------------------------------------
# Sensor units follow hass.config.currency
# ---------------------------------------------------------------------------

async def test_sensor_units_follow_currency(hass: HomeAssistant) -> None:
    """Rate, total and price sensors report the configured currency."""
    await hass.config.async_update(currency="USD")

    grid = make_grid_subentry_data()
    grid["data"]["adapter"]["config"][
        "grid_electricity_price_entity"
    ] = "sensor.grid_price"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=FULL_OPTIONS,
        subentries_data=[grid, make_pv_subentry_data()],
    )
    hass.states.async_set("sensor.grid_power", "1000", {"unit_of_measurement": "W"})
    hass.states.async_set(
        "sensor.grid_price", "0.30", {"unit_of_measurement": "USD/kWh"}
    )
    hass.states.async_set("sensor.pv_power", "-50", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)
    await hass.async_block_till_done()

    # Rate sensor (EUR/h -> USD/h)
    assert _unit(hass, entry, f"{PV_SUB_ID}_operating_cost_rate") == "USD/h"
    # Accumulated total (EUR -> USD)
    assert _unit(hass, entry, f"{PV_SUB_ID}_total_operating_cost") == "USD"
    # Price sensor (EUR/kWh -> USD/kWh)
    assert (
        _unit(hass, entry, "combined_levelized_price_of_electricity") == "USD/kWh"
    )


# ---------------------------------------------------------------------------
# Config-flow money selectors follow the currency
# ---------------------------------------------------------------------------

def _selector_for(schema, field_name):
    for marker, sel in schema.schema.items():
        if getattr(marker, "schema", marker) == field_name:
            return sel
    return None


def test_money_selectors_use_currency() -> None:
    schema = build_schema(PV_SYSTEM_FIELDS, "config", currency="USD")
    cost = _selector_for(schema, "lifetime_cost")
    comp = _selector_for(schema, "export_compensation")
    assert cost.config["unit_of_measurement"] == "USD"
    assert comp.config["unit_of_measurement"] == "USD/kWh"


def test_money_selectors_default_currency() -> None:
    schema = build_schema(PV_SYSTEM_FIELDS, "config")
    assert _selector_for(schema, "lifetime_cost").config[
        "unit_of_measurement"
    ] == "EUR"
