"""Tests for the per-scope options form and adapter field audit."""
from __future__ import annotations

import pytest

from custom_components.power_insight.config_flow import (
    BATTERY_FIELDS,
    PV_SYSTEM_FIELDS,
    PRESET_SELECTIONS,
    default_scopes,
    build_scope_form,
    scope_ui_to_leaves,
    scope_leaves_to_ui_defaults,
    _is_field_required,
)
from custom_components.power_insight.const import (
    CONF_POWER_ENTITY,
    CONF_LIFETIME_PRODUCTION,
    CONF_LIFETIME_COST,
    CONF_PRESET,
    SCOPES,
    SCOPE_SUPPORTED_OPTIONS,
    PRESET_MINIMAL,
    PRESET_RECOMMENDED,
    PRESET_EXTENDED,
    PRESET_CUSTOM,
    CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


# --- Preset selections only expose supported leaves, never CO2 ---

def test_preset_selections_have_no_co2_options() -> None:
    for preset, leaves in PRESET_SELECTIONS.items():
        co2_leaves = {leaf for leaf in leaves if "co2" in leaf}
        assert not co2_leaves, f"Preset {preset!r} contains CO2 leaf keys: {co2_leaves}"


def test_preset_selections_are_subsets_of_all_supported() -> None:
    """Each preset's leaves must be known to at least one scope."""
    all_supported = set().union(*SCOPE_SUPPORTED_OPTIONS.values())
    for preset, leaves in PRESET_SELECTIONS.items():
        unsupported = leaves - all_supported
        assert not unsupported, (
            f"Preset {preset!r} references unknown leaf keys: {unsupported}"
        )


# --- Fresh-install defaults are sane and scope-filtered ---

def test_default_scopes_are_subsets_of_support() -> None:
    scopes = default_scopes()
    assert set(scopes) == set(SCOPES)
    for scope, leaves in scopes.items():
        assert set(leaves) <= SCOPE_SUPPORTED_OPTIONS[scope]


def test_default_includes_cost_savings_and_distribution() -> None:
    combined = set(default_scopes()["combined"])
    assert "accumulate_cost_saving_rates" in combined
    assert "enable_distribution_power" in combined


def test_all_presets_produce_valid_scopes() -> None:
    for preset in (PRESET_MINIMAL, PRESET_RECOMMENDED, PRESET_EXTENDED):
        scopes = default_scopes(preset)
        assert set(scopes) == set(SCOPES)
        for scope, leaves in scopes.items():
            assert set(leaves) <= SCOPE_SUPPORTED_OPTIONS[scope], (
                f"Preset {preset!r}, scope {scope!r}: "
                f"leaves exceed scope support: {set(leaves) - SCOPE_SUPPORTED_OPTIONS[scope]}"
            )


# --- Levelized cost savings land only where they are supported ---

def test_levelized_cost_savings_in_extended() -> None:
    """The Extended preset enables the levelized cost-savings rate + accumulation."""
    leaves = PRESET_SELECTIONS[PRESET_EXTENDED]
    assert CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES in leaves
    assert CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES in leaves


def test_levelized_cost_savings_land_in_supporting_scopes_only() -> None:
    """Wherever a preset enables them, they surface under combined/pv_system/
    battery only — never grid or consumer."""
    keys = {
        CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
        CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
    }
    for preset in (PRESET_MINIMAL, PRESET_RECOMMENDED, PRESET_EXTENDED):
        selected = keys & PRESET_SELECTIONS[preset]
        scopes = default_scopes(preset)
        for scope in ("combined", "pv_system", "battery"):
            assert selected <= set(scopes[scope]), (preset, scope)
        for scope in ("grid", "consumer"):
            assert not (keys & set(scopes[scope])), (preset, scope)


# --- UI form round-trips ---

def test_scope_ui_round_trip() -> None:
    """scope_leaves_to_ui_defaults → scope_ui_to_leaves must be lossless."""
    for scope in SCOPES:
        supported = SCOPE_SUPPORTED_OPTIONS[scope]
        ui_defaults = scope_leaves_to_ui_defaults(scope, supported)
        recovered = set(scope_ui_to_leaves(scope, ui_defaults))
        assert recovered == supported, (
            f"{scope!r} round-trip mismatch — "
            f"lost: {supported - recovered}, gained: {recovered - supported}"
        )


def test_scope_form_builds_for_all_scopes() -> None:
    """build_scope_form must not raise for any scope."""
    for scope in SCOPES:
        defaults = scope_leaves_to_ui_defaults(scope, set())
        schema = build_scope_form(scope, defaults)
        assert schema is not None


def test_empty_leaf_set_round_trip() -> None:
    """Starting from no leaves enabled should produce all-false / none UI defaults."""
    for scope in SCOPES:
        ui_defaults = scope_leaves_to_ui_defaults(scope, set())
        recovered = scope_ui_to_leaves(scope, ui_defaults)
        assert recovered == [], f"{scope!r}: empty leaves → non-empty recovered: {recovered}"


# --- Battery power entity is required ---

def test_battery_power_entity_required() -> None:
    assert BATTERY_FIELDS[CONF_POWER_ENTITY].required is True


# --- Hybrid: lifetime inputs optional under presets, required under custom ---

def _options_with_levelized(preset: str) -> dict:
    return {
        "scopes": {"pv_system": [CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES]},
        CONF_PRESET: preset,
    }


@pytest.mark.parametrize("fields", [PV_SYSTEM_FIELDS, BATTERY_FIELDS])
def test_lifetime_optional_under_preset(fields) -> None:
    """A named preset never forces lifetime cost/production, even with levelized on."""
    options = _options_with_levelized(PRESET_RECOMMENDED)
    for key in (CONF_LIFETIME_PRODUCTION, CONF_LIFETIME_COST):
        assert _is_field_required(fields[key], options) is False, key


@pytest.mark.parametrize("fields", [PV_SYSTEM_FIELDS, BATTERY_FIELDS])
def test_lifetime_required_under_custom(fields) -> None:
    """Custom options keep the old behaviour: required when levelized is enabled."""
    options = _options_with_levelized(PRESET_CUSTOM)
    for key in (CONF_LIFETIME_PRODUCTION, CONF_LIFETIME_COST):
        assert _is_field_required(fields[key], options) is True, key
