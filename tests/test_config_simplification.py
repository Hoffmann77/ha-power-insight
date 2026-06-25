"""Tests for the per-scope options categories and adapter field audit."""
from __future__ import annotations

import pytest

from custom_components.power_insight.config_flow import (
    BATTERY_FIELDS,
    OPTION_CATEGORIES,
    DEFAULT_SELECTION,
    default_scopes,
    build_scope_schema,
    collect_scope_selection,
)
from custom_components.power_insight.const import (
    CONF_POWER_ENTITY,
    SCOPES,
    SCOPE_SUPPORTED_OPTIONS,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _all_category_leaves() -> set[str]:
    return {leaf for cat in OPTION_CATEGORIES for leaf, _ in cat.leaves}


# --- Categories only expose supported leaves, never CO2 ---

def test_categories_have_no_co2_options() -> None:
    assert not any("co2" in leaf for leaf in _all_category_leaves())


def test_every_supported_leaf_has_a_category() -> None:
    """Each leaf a scope supports must be reachable through some category."""
    category_leaves = _all_category_leaves()
    for scope in SCOPES:
        missing = SCOPE_SUPPORTED_OPTIONS[scope] - category_leaves
        assert not missing, f"{scope} supports uncategorised leaves: {missing}"


# --- Fresh-install defaults are sane and scope-filtered ---

def test_default_scopes_are_subsets_of_support() -> None:
    scopes = default_scopes()
    assert set(scopes) == set(SCOPES)
    for scope, leaves in scopes.items():
        assert set(leaves) <= SCOPE_SUPPORTED_OPTIONS[scope]
        assert set(leaves) <= DEFAULT_SELECTION


def test_default_includes_cost_savings_and_distribution() -> None:
    combined = set(default_scopes()["combined"])
    assert "calculate_cost_saving_rates" in combined
    assert "enable_distribution_power" in combined


# --- Scope schema build / collect round-trips ---

def test_scope_schema_round_trip() -> None:
    """Selecting every supported leaf and reading it back is loss-free."""
    for scope in SCOPES:
        supported = SCOPE_SUPPORTED_OPTIONS[scope]
        schema = build_scope_schema(scope, supported)
        # Build a user_input that selects everything shown in the schema.
        user_input: dict = {}
        for cat in OPTION_CATEGORIES:
            shown = [lk for lk, _ in cat.leaves if lk in supported]
            if not shown:
                continue
            user_input[cat.field] = True if cat.toggle else shown
        collected = set(collect_scope_selection(scope, user_input))
        assert collected == set(supported)
        assert schema is not None


# --- Battery power entity is required ---

def test_battery_power_entity_required() -> None:
    assert BATTERY_FIELDS[CONF_POWER_ENTITY].required is True
