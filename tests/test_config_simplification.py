"""Tests for the config-flow simplification and field audit (items A & B)."""
from __future__ import annotations

import pytest

from custom_components.power_insight.config_flow import (
    BATTERY_FIELDS,
    CONFIG_ENTRY_FIELDS,
    INSTANTANEOUS_RATES_SELECTOR,
    INSTANTANEOUS_SAVING_RATES_SELECTOR,
    ACCUMULATED_ENTITIES_SELECTOR,
)
from custom_components.power_insight.const import (
    CONF_POWER_ENTITY,
    CONF_CALCULATE_INSTANTANEOUS_RATES,
    CONF_CALCULATE_INSTANTANEOUS_SAVING_RATES,
    CONF_CALCULATE_ACCUMULATED_ENTITIES,
    CONF_CALCULATE_COST_SAVING_RATES,
    CONF_ACCUMULATE_COST_SAVING_RATES,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _option_values(select_selector) -> set[str]:
    return {opt["value"] for opt in select_selector.config["options"]}


# --- A1: the three multiselects are options-only with new defaults ---

def test_multiselects_are_options_only() -> None:
    for key in (
        CONF_CALCULATE_INSTANTANEOUS_RATES,
        CONF_CALCULATE_INSTANTANEOUS_SAVING_RATES,
        CONF_CALCULATE_ACCUMULATED_ENTITIES,
    ):
        field = CONFIG_ENTRY_FIELDS[key]
        assert field.in_config_flow is False
        assert field.in_options_flow is True


def test_fresh_install_defaults() -> None:
    assert CONFIG_ENTRY_FIELDS[CONF_CALCULATE_INSTANTANEOUS_RATES].default == []
    assert CONFIG_ENTRY_FIELDS[
        CONF_CALCULATE_INSTANTANEOUS_SAVING_RATES
    ].default == [CONF_CALCULATE_COST_SAVING_RATES]
    assert CONFIG_ENTRY_FIELDS[
        CONF_CALCULATE_ACCUMULATED_ENTITIES
    ].default == [CONF_ACCUMULATE_COST_SAVING_RATES]


# --- A2: CO2 options stripped from the three selectors ---

def test_selectors_have_no_co2_options() -> None:
    for selector in (
        INSTANTANEOUS_RATES_SELECTOR,
        INSTANTANEOUS_SAVING_RATES_SELECTOR,
        ACCUMULATED_ENTITIES_SELECTOR,
    ):
        assert not any("co2" in value for value in _option_values(selector))


# --- B1: battery power entity is required ---

def test_battery_power_entity_required() -> None:
    assert BATTERY_FIELDS[CONF_POWER_ENTITY].required is True
