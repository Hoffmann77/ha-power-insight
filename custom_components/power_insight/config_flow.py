"""Config flow for Power Insight integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import issue_registry as ir, selector
from homeassistant.const import CONF_NAME
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    CONF_KEY,
    CONF_ADAPTER_TYPE,
    CONF_POWER_ENTITY,
    CONF_POWER_ENTITY_INVERTED,
    CONF_ELECTRICITY_PRICE_ENTITY,
    CONF_CO2_INTENSITY_ENTITY,
    CONF_LIFETIME_PRODUCTION,
    CONF_LIFETIME_COST,
    CONF_CO2_FOOTPRINT,
    CONF_INITIAL_LCOE,
    CONF_CURRENT_LCOE,
    CONF_INITIAL_LCOS,
    CONF_CURRENT_LCOS,
    CONF_CORRECTION_FACTOR,
    CONF_INITIAL_CO2_INTENSITY,
    CONF_CURRENT_CO2_INTENSITY,
    CONF_EXPORTS_POWER,
    CONF_EXPORT_COMPENSATION,
    CONF_BAT_EFFICIENCY,
    CONF_CHARGE_FROM_GRID,
    CONF_CHARGE_FROM_ADAPTERS,
    CONF_ENABLE_DEBUG_ENTITIES,
    CONF_ENABLE_DISTRIBUTION_POWER,
    CONF_ENABLE_DISTRIBUTION_RATIOS,
    CONF_ENABLE_DISTRIBUTION_SHARES,
    CONF_ENABLE_CHARGING_SOURCE_SHARES,
    CONF_ENABLE_POWER_SOURCE_SHARES,
    CONF_ENABLE_EXPORT_COMPENSATION_RATE,
    CONF_ACCUMULATE_EXPORT_COMPENSATION,
    SCOPES,
    SCOPE_COMBINED,
    SCOPE_SUPPORTED_OPTIONS,

    CONF_CALCULATE_COST_RATES,
    CONF_CALCULATE_LEVELIZED_COST_RATES,
    CONF_CALCULATE_CO2_INTENSITY_RATES,
    CONF_CALCULATE_LEVELIZED_CO2_INTENSITY_RATES,

    CONF_CALCULATE_COST_SAVING_RATES,
    CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
    CONF_CALCULATE_CO2_SAVING_RATES,
    CONF_CALCULATE_LEVELIZED_CO2_SAVING_RATES,

    CONF_ACCUMULATE_COST_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_RATES,
    CONF_ACCUMULATE_CO2_INTENSITY_RATES,
    CONF_ACCUMULATE_LEVELIZED_CO2_INTENSITY_RATES,

    CONF_ACCUMULATE_COST_SAVING_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
    CONF_ACCUMULATE_CO2_SAVING_RATES,
    CONF_ACCUMULATE_LEVELIZED_CO2_SAVING_RATES,
)

_LOGGER = logging.getLogger(__name__)

# Toggle for entity validation - set to False to disable during development
ENABLE_ENTITY_VALIDATION = True


# ============================================================================
# OPTION REQUIREMENT HELPERS
# ============================================================================

_COST_OPTIONS = {
    CONF_CALCULATE_COST_RATES,
    CONF_CALCULATE_LEVELIZED_COST_RATES,
    CONF_CALCULATE_COST_SAVING_RATES,
    CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
    CONF_ACCUMULATE_COST_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_RATES,
    CONF_ACCUMULATE_COST_SAVING_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
}
_CO2_OPTIONS = {
    CONF_CALCULATE_CO2_INTENSITY_RATES,
    CONF_CALCULATE_LEVELIZED_CO2_INTENSITY_RATES,
    CONF_CALCULATE_CO2_SAVING_RATES,
    CONF_CALCULATE_LEVELIZED_CO2_SAVING_RATES,
}
_LEVELIZED_COST_OPTIONS = {
    CONF_CALCULATE_LEVELIZED_COST_RATES,
    CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
}
_LEVELIZED_CO2_OPTIONS = {
    CONF_CALCULATE_LEVELIZED_CO2_INTENSITY_RATES,
    CONF_CALCULATE_LEVELIZED_CO2_SAVING_RATES,
}
_COST_SAVING_OPTIONS = {
    CONF_CALCULATE_COST_SAVING_RATES,
    CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
    CONF_ACCUMULATE_COST_SAVING_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
    CONF_ENABLE_EXPORT_COMPENSATION_RATE,
    CONF_ACCUMULATE_EXPORT_COMPENSATION,
}


def _all_enabled_leaves(options: dict) -> set[str]:
    """Return the union of enabled leaf option keys across every scope."""
    leaves: set[str] = set()
    for scope_leaves in options.get("scopes", {}).values():
        leaves.update(scope_leaves)
    return leaves


def _price_entity_required(options: dict) -> bool:
    return bool(_all_enabled_leaves(options) & _COST_OPTIONS)

def _co2_entity_required(options: dict) -> bool:
    return bool(_all_enabled_leaves(options) & _CO2_OPTIONS)

def _export_compensation_required(options: dict) -> bool:
    return bool(_all_enabled_leaves(options) & _COST_SAVING_OPTIONS)

def _levelized_cost_required(options: dict) -> bool:
    return bool(_all_enabled_leaves(options) & _LEVELIZED_COST_OPTIONS)

def _levelized_co2_required(options: dict) -> bool:
    return bool(_all_enabled_leaves(options) & _LEVELIZED_CO2_OPTIONS)

def _levelized_production_required(options: dict) -> bool:
    return _levelized_cost_required(options) or _levelized_co2_required(options)


# ============================================================================
# HELPERS
# ============================================================================

def _build_charge_from_selector(
    entry: ConfigEntry,
    exclude_subentry_id: str | None = None,
) -> selector.SelectSelector:
    """Build the dynamic multi-select selector for charge_from_adapters.

    Called by ``build_schema`` when resolving ``AdapterField.selector_fn``
    for ``CONF_CHARGE_FROM_ADAPTERS``.  Includes the grid adapter (if
    configured) followed by all PV-system adapters.
    """
    options: list[selector.SelectOptionDict] = []

    # Include the grid adapter as a selectable charge source.
    for subentry in entry.subentries.values():
        if exclude_subentry_id and subentry.subentry_id == exclude_subentry_id:
            continue
        adapter = subentry.data.get("adapter", {})
        if adapter.get("adapter_type") == "grid":
            options.append(
                selector.SelectOptionDict(
                    value=subentry.subentry_id,
                    label="Grid",
                )
            )

    # Include PV-system adapters.
    options.extend(
        _get_pv_adapter_options(entry, exclude_subentry_id=exclude_subentry_id)
    )

    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            multiple=True,
            mode=selector.SelectSelectorMode.LIST,
        )
    )


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_entity_exists(hass, entity_id: str | None) -> bool:
    """Validate that an entity exists in Home Assistant."""
    if not ENABLE_ENTITY_VALIDATION:
        return True
    if entity_id is None:
        return True
    state = hass.states.get(entity_id)
    return state is not None and state.state != "unavailable"


def validate_power_entity(hass, entity_id: str | None) -> bool:
    """Validate power entity exists and reports a power unit."""
    if not ENABLE_ENTITY_VALIDATION:
        return True
    if entity_id is None:
        return True
    state = hass.states.get(entity_id)
    if state is None:
        return False
    if state.state == "unavailable":
        return True
    unit = state.attributes.get("unit_of_measurement", "")
    return unit in ["W", "kW", "MW"]


# ============================================================================
# CALCULATION FUNCTIONS
# ============================================================================

def calculate_lcoe(
    fields: dict[str, Any], existing_data: dict[str, Any] | None = None
) -> float | None:
    """Calculate Levelized Cost of Electricity (EUR/kWh)."""
    costs = fields.get(CONF_LIFETIME_COST)
    production = fields.get(CONF_LIFETIME_PRODUCTION)
    if not costs or not production:
        return None
    return costs / production


def calculate_lcos(
    fields: dict[str, Any], existing_data: dict[str, Any] | None = None
) -> float | None:
    """Calculate Levelized Cost of Storage (EUR/kWh)."""
    costs = fields.get(CONF_LIFETIME_COST)
    production = fields.get(CONF_LIFETIME_PRODUCTION)
    if not costs or not production:
        return None
    return costs / production


def calculate_co2_intensity(
    fields: dict[str, Any], existing_data: dict[str, Any] | None = None
) -> float | None:
    """Calculate CO2 intensity (g/kWh)."""
    footprint = fields.get(CONF_CO2_FOOTPRINT)
    production = fields.get(CONF_LIFETIME_PRODUCTION)
    if not footprint or not production:
        return None
    return (footprint / production) * 1000


def calculate_correction_factor(
    fields: dict[str, Any], existing_data: dict[str, Any] | None = None
) -> float:
    """Return current_lcoe / default_lcoe for a PV adapter.

    The base (default) LCOE is immutable and read from the existing adapter
    config; the current LCOE is derived from the edited lifetime values. The
    factor is time-constant, so multiplying an accumulated base total by it is
    exact and retroactive. Defaults to 1.0 when either value is unavailable.
    """
    base = (existing_data or {}).get(CONF_INITIAL_LCOE)
    current = calculate_lcoe(fields)
    if not base or current is None:
        return 1.0
    return current / base


def calculate_correction_factor_lcos(
    fields: dict[str, Any], existing_data: dict[str, Any] | None = None
) -> float:
    """Return current_lcos / default_lcos for a battery adapter."""
    base = (existing_data or {}).get(CONF_INITIAL_LCOS)
    current = calculate_lcos(fields)
    if not base or current is None:
        return 1.0
    return current / base


# ============================================================================
# FIELD DEFINITION CLASSES
# ============================================================================

@dataclass(frozen=True, kw_only=True)
class EntryField:
    """A configuration field on the main config entry (name/options)."""

    selector: selector.Selector
    required: bool = False
    default: Any = vol.UNDEFINED
    validator: Callable[[Any, Any], bool] | None = None
    error_key: str = "invalid_input"

    # Flow visibility
    in_config_flow: bool = True
    in_options_flow: bool = False

    description: str | None = None


@dataclass(frozen=True, kw_only=True)
class AdapterField:
    """A user-input field on an adapter subentry.

    Exactly one of ``selector`` or ``selector_fn`` must be set:
    - ``selector``: a static, pre-built selector instance.
    - ``selector_fn``: a callable that receives the parent ``ConfigEntry`` and
      an optional ``exclude_subentry_id`` string, and returns a freshly-built
      selector.  Use this for fields whose options depend on the current set of
      subentries (e.g. a multi-select listing sibling adapters).
    """

    selector: selector.Selector | None = None
    selector_fn: Callable[..., selector.Selector] | None = None
    # Builds a selector from the HA-configured currency code (money fields).
    currency_selector_fn: Callable[[str], selector.Selector] | None = None
    required: bool = False
    # When provided, overrides `required` dynamically based on current entry options.
    required_fn: Callable[[dict], bool] | None = None
    default: Any = vol.UNDEFINED
    validator: Callable[[Any, Any], bool] | None = None
    error_key: str = "invalid_input"

    # Flow visibility
    in_config_flow: bool = True
    in_reconfigure_flow: bool = False

    # Storage target (mutually exclusive)
    store_in_data: bool = False           # stored at subentry.data top level
    store_in_adapter_config: bool = False  # stored at subentry.data["adapter"]["config"]

    description: str | None = None


@dataclass(frozen=True, kw_only=True)
class CalculatedAdapterField:
    """A value derived from other fields; never shown in the UI."""

    calculator: Callable[[dict[str, Any], dict[str, Any] | None], Any]
    depends_on: list[str] | None = None

    # Flow visibility
    in_config_flow: bool = True
    in_reconfigure_flow: bool = False

    # Storage target (mutually exclusive)
    store_in_data: bool = False
    store_in_adapter_config: bool = False


# ============================================================================
# SELECTOR DEFINITIONS
# ============================================================================

TEXT_SELECTOR = selector.TextSelector()

ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor")
)

ENTITY_SELECTOR_WITH_INPUT = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["sensor", "input_number"])
)

BOOLEAN_SELECTOR = selector.BooleanSelector()

ENERGY_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(min=1, max=10**8, unit_of_measurement="kWh", mode="box")
)

def make_money_selector(currency: str) -> selector.NumberSelector:
    """Build a money input selector labelled with the configured currency."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1, max=10**8, unit_of_measurement=currency, mode="box"
        )
    )


CO2_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(min=1, max=10**8, unit_of_measurement="kg", mode="box")
)

PERCENT_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(min=1, max=100, unit_of_measurement="%", mode="slider")
)

def make_compensation_selector(currency: str) -> selector.NumberSelector:
    """Build an export-compensation selector labelled with ``<currency>/kWh``."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0.0, max=100.0, step=0.01,
            unit_of_measurement=f"{currency}/kWh", mode="box",
        )
    )

# ============================================================================
# OPTION CATEGORIES  (per-scope options flow)
#
# Sensor selection is grouped into human-readable categories, each mapping to
# one or more leaf option keys. A category is shown in a scope only when that
# scope supports at least one of its leaves (SCOPE_SUPPORTED_OPTIONS). See
# docs/options-flow-redesign.md.
# ============================================================================

@dataclass(frozen=True)
class OptionCategory:
    """A user-facing options category mapped to one or more leaf option keys."""

    field: str
    leaves: tuple[tuple[str, str], ...]   # (leaf_key, choice_label)
    toggle: bool = False                  # True → single boolean leaf


OPTION_CATEGORIES: tuple[OptionCategory, ...] = (
    OptionCategory(
        "distribution_power", ((CONF_ENABLE_DISTRIBUTION_POWER, ""),), toggle=True
    ),
    OptionCategory("cost_rates", (
        (CONF_CALCULATE_COST_RATES, "Cost"),
        (CONF_CALCULATE_LEVELIZED_COST_RATES, "Levelized cost"),
    )),
    OptionCategory("cost_savings_rates", (
        (CONF_CALCULATE_COST_SAVING_RATES, "Cost savings"),
        (CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES, "Levelized cost savings"),
    )),
    OptionCategory("export_compensation", (
        (CONF_ENABLE_EXPORT_COMPENSATION_RATE, "Rate"),
        (CONF_ACCUMULATE_EXPORT_COMPENSATION, "Accumulated total"),
    )),
    OptionCategory("accumulated_costs", (
        (CONF_ACCUMULATE_COST_RATES, "Cost"),
        (CONF_ACCUMULATE_LEVELIZED_COST_RATES, "Levelized cost"),
    )),
    OptionCategory("accumulated_cost_savings", (
        (CONF_ACCUMULATE_COST_SAVING_RATES, "Cost savings"),
        (CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES, "Levelized cost savings"),
    )),
    OptionCategory(
        "distribution_ratios", ((CONF_ENABLE_DISTRIBUTION_RATIOS, ""),), toggle=True
    ),
    OptionCategory(
        "distribution_shares", ((CONF_ENABLE_DISTRIBUTION_SHARES, ""),), toggle=True
    ),
    OptionCategory(
        "charging_source_shares",
        ((CONF_ENABLE_CHARGING_SOURCE_SHARES, ""),), toggle=True,
    ),
    OptionCategory(
        "power_source_shares",
        ((CONF_ENABLE_POWER_SOURCE_SHARES, ""),), toggle=True,
    ),
)

# Fresh-install default selection (intersected per scope with its support).
DEFAULT_SELECTION: set[str] = {
    CONF_CALCULATE_COST_SAVING_RATES,
    CONF_ACCUMULATE_COST_SAVING_RATES,
    CONF_ENABLE_EXPORT_COMPENSATION_RATE,
    CONF_ACCUMULATE_EXPORT_COMPENSATION,
    CONF_ENABLE_DISTRIBUTION_POWER,
    CONF_ENABLE_DISTRIBUTION_RATIOS,
    CONF_ENABLE_DISTRIBUTION_SHARES,
    CONF_ENABLE_CHARGING_SOURCE_SHARES,
    CONF_ENABLE_POWER_SOURCE_SHARES,
}


def default_scopes() -> dict[str, list[str]]:
    """Return the per-scope default selection, intersected with scope support."""
    return {
        scope: sorted(DEFAULT_SELECTION & SCOPE_SUPPORTED_OPTIONS[scope])
        for scope in SCOPES
    }


def _scope_category(category: OptionCategory, scope: str):
    """Return (supported leaves, selector) for *category* in *scope*, or None."""
    supported = [
        (leaf, label) for leaf, label in category.leaves
        if leaf in SCOPE_SUPPORTED_OPTIONS[scope]
    ]
    if not supported:
        return None
    if category.toggle:
        return supported, BOOLEAN_SELECTOR
    return supported, selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=leaf, label=label)
                for leaf, label in supported
            ],
            mode=selector.SelectSelectorMode.LIST,
            multiple=True,
        )
    )


def build_scope_schema(scope: str, current: set[str]) -> vol.Schema:
    """Build the options form schema for one scope."""
    fields: dict = {}
    for category in OPTION_CATEGORIES:
        resolved = _scope_category(category, scope)
        if resolved is None:
            continue
        supported, sel = resolved
        if category.toggle:
            leaf = supported[0][0]
            fields[vol.Required(category.field, default=leaf in current)] = sel
        else:
            default = [leaf for leaf, _ in supported if leaf in current]
            fields[vol.Optional(category.field, default=default)] = sel
    return vol.Schema(fields)


def collect_scope_selection(scope: str, user_input: dict) -> list[str]:
    """Turn a scope form submission into a sorted list of enabled leaf keys."""
    selected: set[str] = set()
    for category in OPTION_CATEGORIES:
        resolved = _scope_category(category, scope)
        if resolved is None:
            continue
        supported, _ = resolved
        if category.field not in user_input:
            continue
        if category.toggle:
            if user_input[category.field]:
                selected.add(supported[0][0])
        else:
            selected.update(user_input[category.field])
    return sorted(selected)


# ============================================================================
# ADAPTER FIELD DEFINITIONS
# ============================================================================

GRID_FIELDS: dict[str, AdapterField] = {
    CONF_POWER_ENTITY: AdapterField(
        selector=ENTITY_SELECTOR,
        required=True,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
        validator=validate_power_entity,
        error_key="invalid_power_entity",
    ),
    CONF_POWER_ENTITY_INVERTED: AdapterField(
        selector=BOOLEAN_SELECTOR,
        required=True,
        default=False,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
    ),
    # Required only when the corresponding savings option is enabled
    CONF_ELECTRICITY_PRICE_ENTITY: AdapterField(
        selector=ENTITY_SELECTOR_WITH_INPUT,
        required=False,
        required_fn=_price_entity_required,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
        validator=validate_entity_exists,
        error_key="invalid_price_entity",
    ),
    CONF_CO2_INTENSITY_ENTITY: AdapterField(
        selector=ENTITY_SELECTOR,
        required=False,
        required_fn=_co2_entity_required,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
        validator=validate_entity_exists,
        error_key="invalid_co2_entity",
    ),
}

PV_SYSTEM_FIELDS: dict[str, AdapterField | CalculatedAdapterField] = {
    CONF_NAME: AdapterField(
        selector=TEXT_SELECTOR,
        required=True,
        default="PV System",
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
    CONF_POWER_ENTITY: AdapterField(
        selector=ENTITY_SELECTOR,
        required=True,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
        validator=validate_power_entity,
        error_key="invalid_power_entity",
    ),
    CONF_POWER_ENTITY_INVERTED: AdapterField(
        selector=BOOLEAN_SELECTOR,
        required=True,
        default=False,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
    ),
    CONF_EXPORTS_POWER: AdapterField(
        selector=BOOLEAN_SELECTOR,
        required=True,
        default=True,
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
    CONF_EXPORT_COMPENSATION: AdapterField(
        currency_selector_fn=make_compensation_selector,
        required=False,
        required_fn=_export_compensation_required,
        default=0.08,
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
    # Raw calculation inputs — optional by default, required when levelized is active.
    # Editable on reconfigure: updating these recomputes current_lcoe and a
    # correction factor that retroactively rescales displayed levelized values.
    CONF_LIFETIME_PRODUCTION: AdapterField(
        selector=ENERGY_SELECTOR,
        required=False,
        required_fn=_levelized_production_required,
        default=vol.UNDEFINED,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_data=True,
        description=(
            "Updating the lifetime values applies a correction factor that "
            "retroactively rescales this device's displayed levelized values. "
            "Note: once a device is removed, its contribution to the combined "
            "totals is frozen at its removal value."
        ),
    ),
    CONF_LIFETIME_COST: AdapterField(
        currency_selector_fn=make_money_selector,
        required=False,
        required_fn=_levelized_cost_required,
        default=vol.UNDEFINED,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_data=True,
    ),
    CONF_CO2_FOOTPRINT: AdapterField(
        selector=CO2_SELECTOR,
        required=False,
        required_fn=_levelized_co2_required,
        default=vol.UNDEFINED,
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_data=True,
    ),
    # Calculated fields — derived from the raw inputs above.
    # The initial (base) LCOE is immutable; current_lcoe and the correction
    # factor are recomputed on reconfigure from the edited lifetime values.
    CONF_INITIAL_LCOE: CalculatedAdapterField(
        calculator=calculate_lcoe,
        depends_on=[CONF_LIFETIME_COST, CONF_LIFETIME_PRODUCTION],
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
    CONF_CURRENT_LCOE: CalculatedAdapterField(
        calculator=calculate_lcoe,
        depends_on=[CONF_LIFETIME_COST, CONF_LIFETIME_PRODUCTION],
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
    ),
    CONF_CORRECTION_FACTOR: CalculatedAdapterField(
        calculator=calculate_correction_factor,
        depends_on=[CONF_LIFETIME_COST, CONF_LIFETIME_PRODUCTION],
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
    ),
    CONF_INITIAL_CO2_INTENSITY: CalculatedAdapterField(
        calculator=calculate_co2_intensity,
        depends_on=[CONF_CO2_FOOTPRINT, CONF_LIFETIME_PRODUCTION],
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
    CONF_CURRENT_CO2_INTENSITY: CalculatedAdapterField(
        calculator=calculate_co2_intensity,
        depends_on=[CONF_CO2_FOOTPRINT, CONF_LIFETIME_PRODUCTION],
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
}

BATTERY_FIELDS: dict[str, AdapterField | CalculatedAdapterField] = {
    CONF_NAME: AdapterField(
        selector=TEXT_SELECTOR,
        required=True,
        default="Battery",
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
    CONF_POWER_ENTITY: AdapterField(
        selector=ENTITY_SELECTOR,
        required=True,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
        validator=validate_power_entity,
        error_key="invalid_power_entity",
    ),
    CONF_POWER_ENTITY_INVERTED: AdapterField(
        selector=BOOLEAN_SELECTOR,
        required=True,
        default=False,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
    ),
    CONF_BAT_EFFICIENCY: AdapterField(
        selector=PERCENT_SELECTOR,
        required=True,
        default=95,
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
    CONF_EXPORTS_POWER: AdapterField(
        selector=BOOLEAN_SELECTOR,
        required=True,
        default=False,
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
    CONF_EXPORT_COMPENSATION: AdapterField(
        currency_selector_fn=make_compensation_selector,
        required=False,
        required_fn=_export_compensation_required,
        default=0.0,
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
    CONF_CHARGE_FROM_ADAPTERS: AdapterField(
        selector_fn=_build_charge_from_selector,
        required=False,
        default=[],
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
    ),
    # Raw calculation inputs — optional by default, required when levelized is active.
    # Editable on reconfigure: updating these recomputes current_lcos and a
    # correction factor that retroactively rescales displayed levelized values.
    CONF_LIFETIME_PRODUCTION: AdapterField(
        selector=ENERGY_SELECTOR,
        required=False,
        required_fn=_levelized_production_required,
        default=vol.UNDEFINED,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_data=True,
        description=(
            "Updating the lifetime values applies a correction factor that "
            "retroactively rescales this device's displayed levelized values. "
            "Note: once a device is removed, its contribution to the combined "
            "totals is frozen at its removal value."
        ),
    ),
    CONF_LIFETIME_COST: AdapterField(
        currency_selector_fn=make_money_selector,
        required=False,
        required_fn=_levelized_cost_required,
        default=vol.UNDEFINED,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_data=True,
    ),
    CONF_CO2_FOOTPRINT: AdapterField(
        selector=CO2_SELECTOR,
        required=False,
        required_fn=_levelized_co2_required,
        default=vol.UNDEFINED,
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_data=True,
    ),
    # Calculated fields.
    # The initial (base) LCOS is immutable; current_lcos and the correction
    # factor are recomputed on reconfigure from the edited lifetime values.
    CONF_INITIAL_LCOS: CalculatedAdapterField(
        calculator=calculate_lcos,
        depends_on=[CONF_LIFETIME_COST, CONF_LIFETIME_PRODUCTION],
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
    CONF_CURRENT_LCOS: CalculatedAdapterField(
        calculator=calculate_lcos,
        depends_on=[CONF_LIFETIME_COST, CONF_LIFETIME_PRODUCTION],
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
    ),
    CONF_CORRECTION_FACTOR: CalculatedAdapterField(
        calculator=calculate_correction_factor_lcos,
        depends_on=[CONF_LIFETIME_COST, CONF_LIFETIME_PRODUCTION],
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
    ),
    CONF_INITIAL_CO2_INTENSITY: CalculatedAdapterField(
        calculator=calculate_co2_intensity,
        depends_on=[CONF_CO2_FOOTPRINT, CONF_LIFETIME_PRODUCTION],
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
    CONF_CURRENT_CO2_INTENSITY: CalculatedAdapterField(
        calculator=calculate_co2_intensity,
        depends_on=[CONF_CO2_FOOTPRINT, CONF_LIFETIME_PRODUCTION],
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
}

CONSUMER_FIELDS: dict[str, AdapterField] = {
    CONF_NAME: AdapterField(
        selector=TEXT_SELECTOR,
        required=True,
        default="Consumer",
        in_config_flow=True,
        in_reconfigure_flow=False,
        store_in_adapter_config=True,
    ),
    CONF_POWER_ENTITY: AdapterField(
        selector=ENTITY_SELECTOR,
        required=True,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
        validator=validate_power_entity,
        error_key="invalid_power_entity",
    ),
    CONF_POWER_ENTITY_INVERTED: AdapterField(
        selector=BOOLEAN_SELECTOR,
        required=True,
        default=False,
        in_config_flow=True,
        in_reconfigure_flow=True,
        store_in_adapter_config=True,
    ),
}

# Map adapter type strings to their field definitions (used by reconfigure)
ADAPTER_TYPE_FIELDS: dict[str, dict[str, AdapterField | CalculatedAdapterField]] = {
    "grid": GRID_FIELDS,
    "pv_system": PV_SYSTEM_FIELDS,
    "battery": BATTERY_FIELDS,
    "consumer": CONSUMER_FIELDS,
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _is_field_required(
    field_def: AdapterField | EntryField,
    options: dict,
) -> bool:
    """Resolve the effective required-ness of a field given current options."""
    if isinstance(field_def, AdapterField) and field_def.required_fn is not None:
        return field_def.required_fn(options)
    return field_def.required


def _field_in_flow(
    field_def: AdapterField | CalculatedAdapterField | EntryField,
    flow_type: str,
) -> bool:
    """Return whether a field is shown/processed in the given flow."""
    if isinstance(field_def, EntryField):
        if flow_type == "config":
            return field_def.in_config_flow
        if flow_type == "options":
            return field_def.in_options_flow
        return True
    if isinstance(field_def, AdapterField):
        if flow_type == "config":
            return field_def.in_config_flow
        if flow_type == "reconfigure":
            return field_def.in_reconfigure_flow
        return True
    return False  # CalculatedAdapterField is never user-visible


def build_schema(
    fields: dict[str, AdapterField | CalculatedAdapterField | EntryField],
    flow_type: str,
    user_input: dict[str, Any] | None = None,
    options: dict | None = None,
    entry: ConfigEntry | None = None,
    exclude_subentry_id: str | None = None,
    currency: str = "EUR",
) -> vol.Schema:
    """Build a voluptuous schema from field definitions.

    flow_type:            "config" | "reconfigure" | "options"
    options:              current entry options, used to evaluate required_fn.
    entry:                parent ConfigEntry, required when any field uses selector_fn.
    exclude_subentry_id:  passed through to selector_fn (e.g. to omit the
                          subentry currently being reconfigured from its own
                          selector options).
    currency:             ISO currency code used to label money input fields.
    """
    options = options or {}
    schema_dict: dict = {}

    for field_name, field_def in fields.items():
        # Calculated fields are never rendered in the UI
        if isinstance(field_def, CalculatedAdapterField):
            continue

        # Filter by flow visibility
        if isinstance(field_def, EntryField):
            if flow_type == "config" and not field_def.in_config_flow:
                continue
            if flow_type == "options" and not field_def.in_options_flow:
                continue
        elif isinstance(field_def, AdapterField):
            if flow_type == "config" and not field_def.in_config_flow:
                continue
            if flow_type == "reconfigure" and not field_def.in_reconfigure_flow:
                continue

        # Determine the default value (prefer sticky re-shown user input)
        default = field_def.default
        if user_input is not None and field_name in user_input:
            default = user_input[field_name]

        is_required = _is_field_required(field_def, options)
        key = (
            vol.Required(field_name, default=default)
            if is_required
            else vol.Optional(field_name, default=default)
        )

        # Resolve the selector: prefer the currency factory, then selector_fn
        # (dynamic), then the static selector.
        if isinstance(field_def, AdapterField) and field_def.currency_selector_fn is not None:
            resolved_selector = field_def.currency_selector_fn(currency)
        elif isinstance(field_def, AdapterField) and field_def.selector_fn is not None:
            resolved_selector = field_def.selector_fn(
                entry, exclude_subentry_id=exclude_subentry_id
            )
        else:
            resolved_selector = field_def.selector

        schema_dict[key] = resolved_selector

    return vol.Schema(schema_dict)


def validate_fields(
    hass,
    fields: dict[str, AdapterField | CalculatedAdapterField | EntryField],
    user_input: dict[str, Any],
    options: dict | None = None,
    flow_type: str = "config",
) -> dict[str, str]:
    """Validate user input against field definitions.

    Runs registered per-field validators and checks that dynamically required
    fields are not missing.  Only fields visible in *flow_type* are checked for
    required-ness, so config-only fields are not flagged during a reconfigure.
    """
    options = options or {}
    errors: dict[str, str] = {}

    # Per-field validator checks
    for field_name, value in user_input.items():
        if field_name not in fields:
            continue
        field_def = fields[field_name]
        if isinstance(field_def, (AdapterField, EntryField)) and field_def.validator:
            try:
                if not field_def.validator(hass, value):
                    errors[field_name] = field_def.error_key
            except Exception as err:
                _LOGGER.error("Validation error for %s: %s", field_name, err)
                errors[field_name] = field_def.error_key

    # Dynamic required-ness check (only for fields shown in this flow)
    for field_name, field_def in fields.items():
        if isinstance(field_def, CalculatedAdapterField):
            continue
        if not _field_in_flow(field_def, flow_type):
            continue
        if _is_field_required(field_def, options):
            val = user_input.get(field_name)
            if val is None or val is vol.UNDEFINED:
                errors.setdefault(field_name, "required")

    return errors


def calculate_fields(
    fields: dict[str, AdapterField | CalculatedAdapterField],
    user_input: dict[str, Any],
    flow_type: str,
    options: dict | None = None,
    existing_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate CalculatedAdapterFields and merge results into a copy of user_input.

    A calculated field is skipped (set to None) when any of its depends_on
    inputs are absent or falsy.
    """
    result = user_input.copy()

    for field_name, field_def in fields.items():
        if not isinstance(field_def, CalculatedAdapterField):
            continue

        should_calculate = (
            (flow_type == "config" and field_def.in_config_flow)
            or (flow_type == "reconfigure" and field_def.in_reconfigure_flow)
        )
        if not should_calculate:
            continue

        if field_def.depends_on and any(
            not result.get(dep) for dep in field_def.depends_on
        ):
            result[field_name] = None
            continue

        result[field_name] = field_def.calculator(result, existing_data)

    return result


def split_by_storage(
    fields: dict[str, AdapterField | CalculatedAdapterField],
    user_input: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split computed input into (adapter_config, top_level_data) by storage flag."""
    adapter_config: dict[str, Any] = {}
    top_level_data: dict[str, Any] = {}

    for field_name, value in user_input.items():
        if field_name not in fields:
            continue
        field_def = fields[field_name]
        if isinstance(field_def, (AdapterField, CalculatedAdapterField)):
            if field_def.store_in_adapter_config:
                adapter_config[field_name] = value
            elif field_def.store_in_data:
                top_level_data[field_name] = value

    return adapter_config, top_level_data


def check_existing_slugs(
    parent_entry: ConfigEntry, exclude_id: str | None = None
) -> set[str]:
    """Return the set of adapter keys already used by the entry's subentries."""
    existing: set[str] = set()
    for subentry in parent_entry.subentries.values():
        if exclude_id and subentry.subentry_id == exclude_id:
            continue
        adapter = subentry.data.get("adapter", {})
        if CONF_KEY in adapter:
            existing.add(adapter[CONF_KEY])
    return existing


def _has_grid_subentry(entry: ConfigEntry) -> bool:
    """Return True when the entry already contains a grid subentry."""
    return any(
        sub.data.get("adapter", {}).get("adapter_type") == "grid"
        for sub in entry.subentries.values()
    )


def _get_pv_adapter_options(
    entry: ConfigEntry,
    exclude_subentry_id: str | None = None,
) -> list[selector.SelectOptionDict]:
    """Return SelectOptionDicts for every pv_system subentry in *entry*.

    *exclude_subentry_id* can be used to omit the subentry currently being
    reconfigured (not needed for batteries, but kept for symmetry).
    """
    options = []
    for subentry in entry.subentries.values():
        if exclude_subentry_id and subentry.subentry_id == exclude_subentry_id:
            continue
        adapter = subentry.data.get("adapter", {})
        if adapter.get("adapter_type") == "pv_system":
            options.append(
                selector.SelectOptionDict(
                    value=subentry.subentry_id,
                    label=subentry.title,
                )
            )
    return options





# ============================================================================
# OPTIONS FEASIBILITY CHECK
# ============================================================================

def check_options_feasibility(
    entry: ConfigEntry,
    new_options: dict,
) -> list[str]:
    """Return titles of subentries that require reconfiguring for new_options.

    An empty list means all subentries already satisfy the new requirements.
    """
    needs_reconfigure = []
    scopes = new_options.get("scopes", {})

    for subentry in entry.subentries.values():
        adapter = subentry.data.get("adapter", {})
        adapter_type = adapter.get("adapter_type")
        config = adapter.get("config", {})

        # A device needs data when the category is enabled in its own scope or
        # in the combined scope (combined sensors aggregate the device).
        enabled = set(scopes.get(adapter_type, [])) | set(
            scopes.get(SCOPE_COMBINED, [])
        )
        calc_cost = bool(enabled & _COST_OPTIONS)
        calc_co2 = bool(enabled & _CO2_OPTIONS)
        levelized = bool(enabled & (_LEVELIZED_COST_OPTIONS | _LEVELIZED_CO2_OPTIONS))

        if adapter_type == "grid":
            missing = (
                calc_cost and not config.get(CONF_ELECTRICITY_PRICE_ENTITY)
            ) or (
                calc_co2 and not config.get(CONF_CO2_INTENSITY_ENTITY)
            )
            if missing:
                needs_reconfigure.append(subentry.title)

        elif adapter_type in ("pv_system", "battery"):
            if not levelized:
                continue
            data = subentry.data
            missing = (
                not data.get(CONF_LIFETIME_PRODUCTION)
                or (calc_cost and not data.get(CONF_LIFETIME_COST))
                or (calc_co2 and not data.get(CONF_CO2_FOOTPRINT))
            )
            if missing:
                needs_reconfigure.append(subentry.title)

    return needs_reconfigure


# ============================================================================
# MAIN CONFIG FLOW
# ============================================================================

class PowerInsightConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Power Insight.

    The initial step collects the integration name and the options that are
    relevant at setup time (calculate_cost_savings, calculate_co2_savings,
    calculation_method).  Grid and device adapters are added afterwards as
    subentries via the "Add device" button.
    """

    VERSION = 1
    MINOR_VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the integration title and seed the default per-scope options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            title = user_input.get(CONF_NAME, "").strip()
            if not title:
                errors[CONF_NAME] = "invalid_name"
            else:
                # The initial form only collects the name; seed the per-scope
                # default selection so fresh installs register sensible sensors
                # before the user opens the options flow.
                return self.async_create_entry(
                    title=title,
                    data={},
                    options={
                        "schema": 2,
                        "scopes": default_scopes(),
                        CONF_ENABLE_DEBUG_ENTITIES: False,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_NAME, default=""): TEXT_SELECTOR}
            ),
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentry types this integration supports."""
        return {"adapter": AdapterSubentryFlow}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PowerInsightOptionsFlow:
        """Return the options flow handler."""
        return PowerInsightOptionsFlow()


# ============================================================================
# SUBENTRY FLOW  (grid / PV system / battery / consumer)
# ============================================================================

class AdapterSubentryFlow(ConfigSubentryFlow):
    """Subentry flow for adding and reconfiguring adapters."""

    def __init__(self) -> None:
        super().__init__()
        self._adapter_type: str | None = None
        self._adapter_fields: dict | None = None

    def _current_options(self) -> dict:
        """Return the parent entry's current options."""
        return self._get_entry().options or {}

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        menu_options = ["pv_system", "battery", "consumer"]
        if not _has_grid_subentry(self._get_entry()):
            menu_options = ["grid"] + menu_options

        return self.async_show_menu(
            step_id="user",
            menu_options=menu_options,
        )

    # ------------------------------------------------------------------
    # Per-type dispatch
    # ------------------------------------------------------------------

    async def async_step_grid(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Entry point for grid adapter; enforces a single grid per entry."""
        if _has_grid_subentry(self._get_entry()):
            return self.async_abort(reason="grid_already_configured")
        self._adapter_type = "grid"
        self._adapter_fields = GRID_FIELDS
        return await self.async_step_configure(user_input)

    async def async_step_pv_system(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._adapter_type = "pv_system"
        self._adapter_fields = PV_SYSTEM_FIELDS
        return await self.async_step_configure(user_input)

    async def async_step_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._adapter_type = "battery"
        self._adapter_fields = BATTERY_FIELDS
        return await self.async_step_configure(user_input)

    async def async_step_consumer(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._adapter_type = "consumer"
        self._adapter_fields = CONSUMER_FIELDS
        return await self.async_step_configure(user_input)

    # ------------------------------------------------------------------
    # Shared configure step
    # ------------------------------------------------------------------

    async def async_step_configure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Generic configure step shared by all adapter types."""
        errors: dict[str, str] = {}
        options = self._current_options()
        parent_entry = self._get_entry()

        if user_input is not None:
            validation_errors = validate_fields(
                self.hass, self._adapter_fields, user_input, options, "config"
            )
            errors.update(validation_errors)

            if not errors:
                # Determine key and title
                if self._adapter_type == "grid":
                    key = "grid"
                    title = "Grid"
                else:
                    name = user_input.get(CONF_NAME, "").strip()
                    title = name or self._adapter_type.replace("_", " ").title()
                    key = slugify(name) if name else slugify(self._adapter_type)
                    existing = check_existing_slugs(parent_entry)
                    if not key or key == "unknown":
                        errors["base"] = "invalid_name"
                    elif key in existing:
                        errors["base"] = "name_not_unique"

            if not errors:
                complete = calculate_fields(
                    self._adapter_fields, user_input, "config", options
                )
                adapter_config, top_level_data = split_by_storage(
                    self._adapter_fields, complete
                )

                entry_data = {
                    "adapter": {
                        "adapter_type": self._adapter_type,
                        "key": key,
                        "config": adapter_config,
                    },
                    **top_level_data,
                }

                result = self.async_create_entry(title=title, data=entry_data)

                # When a charge source (grid or pv_system) is added, prompt
                # every existing battery adapter to be reconfigured so the user
                # can update their charge_from_adapters settings.
                if self._adapter_type in ("grid", "pv_system"):
                    for sub in parent_entry.subentries.values():
                        if sub.data.get("adapter", {}).get("adapter_type") == "battery":
                            ir.async_create_issue(
                                self.hass,
                                DOMAIN,
                                f"reconfigure_battery_{sub.subentry_id}",
                                is_fixable=False,
                                severity=ir.IssueSeverity.WARNING,
                                translation_key="reconfigure_battery_adapters",
                                translation_placeholders={"battery_name": sub.title},
                            )
                    # No explicit reload here: adding the subentry fires the
                    # config-entry update listener, which performs the reload.
                    # Reloading here as well would double-reload (deprecated
                    # since HA 2026.6).

                return result

        schema = build_schema(
            self._adapter_fields, "config", user_input, options, entry=parent_entry,
            currency=self.hass.config.currency or "EUR",
        )

        return self.async_show_form(
            step_id="configure",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "adapter_type": self._adapter_type.replace("_", " ").title(),
            },
        )

    # ------------------------------------------------------------------
    # Reconfigure step
    # ------------------------------------------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure entity IDs (and other reconfigure-flagged fields)."""
        errors: dict[str, str] = {}
        options = self._current_options()
        parent_entry = self._get_entry()

        subentry = self._get_reconfigure_subentry()
        adapter = subentry.data.get("adapter", {})
        self._adapter_type = adapter.get("adapter_type")
        self._adapter_fields = ADAPTER_TYPE_FIELDS[self._adapter_type]

        if user_input is not None:
            validation_errors = validate_fields(
                self.hass, self._adapter_fields, user_input, options, "reconfigure"
            )
            errors.update(validation_errors)

            if not errors:
                # Evaluate calculated fields (current_lcoe/lcos, correction
                # factor) from the edited lifetime values, reading the immutable
                # base (default_lcoe/lcos) from the existing config.
                complete = calculate_fields(
                    self._adapter_fields,
                    user_input,
                    "reconfigure",
                    options,
                    existing_data=adapter.get("config", {}),
                )
                new_adapter_config, new_top_level = split_by_storage(
                    self._adapter_fields, complete
                )

                adapter_config = adapter.get("config", {}).copy()
                adapter_config.update(new_adapter_config)

                updated = subentry.data.copy()
                updated.update(new_top_level)
                updated["adapter"] = {
                    "adapter_type": self._adapter_type,
                    "key": adapter.get("key"),
                    "config": adapter_config,
                }
                # Dismiss the per-battery reconfigure issue (raised when a
                # charge-source adapter was added or removed) now that the
                # user has reconfigured this battery.
                ir.async_delete_issue(
                    self.hass, DOMAIN, f"reconfigure_battery_{subentry.subentry_id}"
                )
                # Update without reloading here: the subentry change fires the
                # config-entry update listener, which performs the single
                # reload. Combining a reloading flow method with the update
                # listener is deprecated since HA 2026.6.
                return self.async_update_and_abort(
                    self._get_entry(), subentry, data=updated
                )

        # Seed with existing adapter config values.
        seed = {
            k: v
            for k, v in adapter.get("config", {}).items()
            if k in self._adapter_fields
        }
        # store_in_data fields (e.g. lifetime values) live at the subentry top
        # level, not in adapter.config — seed them so reconfigure pre-fills them.
        for k, v in subentry.data.items():
            if k != "adapter" and k in self._adapter_fields:
                seed.setdefault(k, v)

        # For charge_from_adapters, strip stale subentry IDs before seeding so
        # the selector is pre-populated with only currently valid selections.
        # Valid sources are grid and pv_system adapters.
        if CONF_CHARGE_FROM_ADAPTERS in seed:
            valid_source_ids = {
                sub.subentry_id
                for sub in parent_entry.subentries.values()
                if sub.data.get("adapter", {}).get("adapter_type") in ("grid", "pv_system")
            }
            seed[CONF_CHARGE_FROM_ADAPTERS] = [
                i for i in seed[CONF_CHARGE_FROM_ADAPTERS] if i in valid_source_ids
            ]

        schema = build_schema(
            self._adapter_fields,
            "reconfigure",
            seed,
            options,
            entry=parent_entry,
            exclude_subentry_id=subentry.subentry_id,
            currency=self.hass.config.currency or "EUR",
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "adapter_type": self._adapter_type.replace("_", " ").title(),
            },
        )


# ============================================================================
# OPTIONS FLOW
# ============================================================================

class PowerInsightOptionsFlow(OptionsFlow):
    """Per-scope options flow.

    A menu offers the whole-home (combined) scope plus one section per
    configured device type, then a diagnostics section and a save action. Each
    section edits only the categories that scope supports. The working
    selection is accumulated across steps and written on save.
    """

    def __init__(self) -> None:
        """Initialise the working selection lazily."""
        self._scopes: dict[str, set[str]] | None = None
        self._debug: bool = False

    def _load(self) -> None:
        """Load the working selection from the stored options once."""
        if self._scopes is not None:
            return
        options = self.config_entry.options
        stored = options.get("scopes", {})
        self._scopes = {scope: set(stored.get(scope, [])) for scope in SCOPES}
        self._debug = bool(options.get(CONF_ENABLE_DEBUG_ENTITIES, False))

    def _present_device_scopes(self) -> list[str]:
        """Return device-type scopes that have at least one subentry."""
        types = {
            sub.data.get("adapter", {}).get("adapter_type")
            for sub in self.config_entry.subentries.values()
        }
        return [t for t in ("grid", "pv_system", "battery", "consumer") if t in types]

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the section menu."""
        self._load()
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                SCOPE_COMBINED,
                *self._present_device_scopes(),
                "diagnostics",
                "save",
            ],
        )

    async def _async_scope_step(
        self, scope: str, user_input: dict[str, Any] | None
    ) -> FlowResult:
        """Render / collect one scope's category selection."""
        self._load()
        if user_input is not None:
            self._scopes[scope] = set(collect_scope_selection(scope, user_input))
            return await self.async_step_init()
        return self.async_show_form(
            step_id=scope,
            data_schema=build_scope_schema(scope, self._scopes[scope]),
        )

    async def async_step_combined(self, user_input=None) -> FlowResult:
        """Edit the whole-home (combined) scope."""
        return await self._async_scope_step(SCOPE_COMBINED, user_input)

    async def async_step_grid(self, user_input=None) -> FlowResult:
        """Edit the grid scope."""
        return await self._async_scope_step("grid", user_input)

    async def async_step_pv_system(self, user_input=None) -> FlowResult:
        """Edit the PV-system scope."""
        return await self._async_scope_step("pv_system", user_input)

    async def async_step_battery(self, user_input=None) -> FlowResult:
        """Edit the battery scope."""
        return await self._async_scope_step("battery", user_input)

    async def async_step_consumer(self, user_input=None) -> FlowResult:
        """Edit the consumer scope."""
        return await self._async_scope_step("consumer", user_input)

    async def async_step_diagnostics(self, user_input=None) -> FlowResult:
        """Edit the global diagnostics toggle."""
        self._load()
        if user_input is not None:
            self._debug = bool(user_input.get(CONF_ENABLE_DEBUG_ENTITIES, False))
            return await self.async_step_init()
        return self.async_show_form(
            step_id="diagnostics",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_ENABLE_DEBUG_ENTITIES, default=self._debug
                ): BOOLEAN_SELECTOR,
            }),
        )

    def _compose(self) -> dict:
        """Build the options dict from the working selection."""
        return {
            "schema": 2,
            "scopes": {scope: sorted(self._scopes[scope]) for scope in SCOPES},
            CONF_ENABLE_DEBUG_ENTITIES: self._debug,
        }

    async def async_step_save(self, user_input=None) -> FlowResult:
        """Validate against existing adapters and persist the options."""
        self._load()
        new_options = self._compose()
        problems = check_options_feasibility(self.config_entry, new_options)
        if problems and user_input is None:
            # Some devices lack data the new options need. Warn, but let the
            # user confirm (submit) to apply anyway, then reconfigure them.
            return self.async_show_form(
                step_id="save",
                data_schema=vol.Schema({}),
                errors={"base": "reconfigure_adapters_first"},
                description_placeholders={
                    "adapters_needing_reconfigure": ", ".join(problems),
                },
            )
        return self.async_create_entry(title="", data=new_options)