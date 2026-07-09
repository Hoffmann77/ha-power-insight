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
from homeassistant.data_entry_flow import FlowResult, section
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
    CONF_PRESET,
    PRESET_MINIMAL,
    PRESET_RECOMMENDED,
    PRESET_EXTENDED,
    PRESET_ALL,
    PRESET_CUSTOM,

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
# PRESET DEFINITIONS
# ============================================================================

PRESET_SELECTIONS: dict[str, frozenset[str]] = {
    PRESET_MINIMAL: frozenset({
        CONF_ENABLE_DISTRIBUTION_POWER,
        CONF_CALCULATE_COST_SAVING_RATES,
        CONF_ACCUMULATE_COST_SAVING_RATES,
    }),
    PRESET_RECOMMENDED: frozenset({
        CONF_ENABLE_DISTRIBUTION_POWER,
        CONF_ENABLE_DISTRIBUTION_RATIOS,
        CONF_ENABLE_DISTRIBUTION_SHARES,
        CONF_ENABLE_CHARGING_SOURCE_SHARES,
        CONF_ENABLE_POWER_SOURCE_SHARES,
        CONF_CALCULATE_COST_SAVING_RATES,
        CONF_ACCUMULATE_COST_SAVING_RATES,
        CONF_ENABLE_EXPORT_COMPENSATION_RATE,
        CONF_ACCUMULATE_EXPORT_COMPENSATION,
    }),
    PRESET_EXTENDED: frozenset({
        CONF_ENABLE_DISTRIBUTION_POWER,
        CONF_ENABLE_DISTRIBUTION_RATIOS,
        CONF_ENABLE_DISTRIBUTION_SHARES,
        CONF_ENABLE_CHARGING_SOURCE_SHARES,
        CONF_ENABLE_POWER_SOURCE_SHARES,
        CONF_CALCULATE_COST_SAVING_RATES,
        CONF_ACCUMULATE_COST_SAVING_RATES,
        CONF_ENABLE_EXPORT_COMPENSATION_RATE,
        CONF_ACCUMULATE_EXPORT_COMPENSATION,
        CONF_CALCULATE_COST_RATES,
        CONF_ACCUMULATE_COST_RATES,
    }),
    PRESET_ALL: frozenset({
        CONF_ENABLE_DISTRIBUTION_POWER,
        CONF_ENABLE_DISTRIBUTION_RATIOS,
        CONF_ENABLE_DISTRIBUTION_SHARES,
        CONF_ENABLE_CHARGING_SOURCE_SHARES,
        CONF_ENABLE_POWER_SOURCE_SHARES,
        CONF_CALCULATE_COST_SAVING_RATES,
        CONF_ACCUMULATE_COST_SAVING_RATES,
        CONF_ENABLE_EXPORT_COMPENSATION_RATE,
        CONF_ACCUMULATE_EXPORT_COMPENSATION,
        CONF_CALCULATE_COST_RATES,
        CONF_ACCUMULATE_COST_RATES,
        CONF_CALCULATE_LEVELIZED_COST_RATES,
        CONF_ACCUMULATE_LEVELIZED_COST_RATES,
        CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
        CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
    }),
}


def default_scopes(preset: str = PRESET_RECOMMENDED) -> dict[str, list[str]]:
    """Return the per-scope selection for *preset*, intersected with scope support."""
    selection = PRESET_SELECTIONS.get(preset, PRESET_SELECTIONS[PRESET_RECOMMENDED])
    return {
        scope: sorted(selection & SCOPE_SUPPORTED_OPTIONS[scope])
        for scope in SCOPES
    }


# ============================================================================
# OPTIONS FLOW HELPERS  (new-style per-scope pages)
# ============================================================================

def _preset_selector(include_custom: bool = True) -> selector.SelectSelector:
    """Build a list-mode select selector for the preset options."""
    options = [
        selector.SelectOptionDict(value=PRESET_MINIMAL, label="Minimal"),
        selector.SelectOptionDict(value=PRESET_RECOMMENDED, label="Recommended"),
        selector.SelectOptionDict(value=PRESET_EXTENDED, label="Extended"),
        selector.SelectOptionDict(value=PRESET_ALL, label="All"),
    ]
    if include_custom:
        options.append(selector.SelectOptionDict(value=PRESET_CUSTOM, label="Custom"))
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.LIST,
        )
    )


def _cost_method_options(scope: str) -> list[selector.SelectOptionDict]:
    """Return available cost-method selector options for *scope*."""
    supported = SCOPE_SUPPORTED_OPTIONS.get(scope, set())
    opts = [selector.SelectOptionDict(value="none", label="None")]
    has_std = CONF_CALCULATE_COST_RATES in supported
    has_lvl = CONF_CALCULATE_LEVELIZED_COST_RATES in supported
    if has_std:
        opts.append(selector.SelectOptionDict(value="standard", label="Standard"))
    if has_lvl:
        opts.append(selector.SelectOptionDict(value="levelized", label="Levelized"))
    if has_std and has_lvl:
        opts.append(selector.SelectOptionDict(value="both", label="Both"))
    return opts


def _savings_method_options(scope: str) -> list[selector.SelectOptionDict]:
    """Return available savings-method selector options for *scope*."""
    supported = SCOPE_SUPPORTED_OPTIONS.get(scope, set())
    opts = [selector.SelectOptionDict(value="none", label="None")]
    has_std = CONF_CALCULATE_COST_SAVING_RATES in supported
    has_lvl = CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES in supported
    if has_std:
        opts.append(selector.SelectOptionDict(value="standard", label="Standard"))
    if has_lvl:
        opts.append(selector.SelectOptionDict(value="levelized", label="Levelized"))
    if has_std and has_lvl:
        opts.append(selector.SelectOptionDict(value="both", label="Both"))
    return opts


def build_scope_form(scope: str, defaults: dict) -> vol.Schema:
    """Build the new-style options schema for one device scope."""
    supported = SCOPE_SUPPORTED_OPTIONS.get(scope, set())
    fields: dict = {}

    # --- Power sensors section ---
    power_fields: dict = {}
    if CONF_ENABLE_DISTRIBUTION_POWER in supported:
        power_fields[vol.Required(
            "distribution_power", default=defaults.get("distribution_power", False)
        )] = BOOLEAN_SELECTOR
    if CONF_ENABLE_DISTRIBUTION_RATIOS in supported:
        power_fields[vol.Required(
            "distribution_ratios", default=defaults.get("distribution_ratios", False)
        )] = BOOLEAN_SELECTOR
    if CONF_ENABLE_DISTRIBUTION_SHARES in supported:
        power_fields[vol.Required(
            "distribution_shares", default=defaults.get("distribution_shares", False)
        )] = BOOLEAN_SELECTOR
    if CONF_ENABLE_CHARGING_SOURCE_SHARES in supported:
        power_fields[vol.Required(
            "charging_source_shares", default=defaults.get("charging_source_shares", False)
        )] = BOOLEAN_SELECTOR
    if CONF_ENABLE_POWER_SOURCE_SHARES in supported:
        power_fields[vol.Required(
            "power_source_shares", default=defaults.get("power_source_shares", False)
        )] = BOOLEAN_SELECTOR
    if power_fields:
        fields[vol.Required("power_sensors")] = section(
            vol.Schema(power_fields), {"collapsed": False}
        )

    # --- Export compensation section ---
    exp_fields: dict = {}
    if CONF_ENABLE_EXPORT_COMPENSATION_RATE in supported:
        exp_fields[vol.Required(
            "export_compensation_rate",
            default=defaults.get("export_compensation_rate", False),
        )] = BOOLEAN_SELECTOR
    if CONF_ACCUMULATE_EXPORT_COMPENSATION in supported:
        exp_fields[vol.Required(
            "export_compensation_total",
            default=defaults.get("export_compensation_total", False),
        )] = BOOLEAN_SELECTOR
    if exp_fields:
        fields[vol.Required("export_compensation")] = section(
            vol.Schema(exp_fields), {"collapsed": False}
        )

    # --- Cost calculation section ---
    cost_opts = _cost_method_options(scope)
    if len(cost_opts) > 1:
        cost_fields: dict = {
            vol.Required(
                "cost_method", default=defaults.get("cost_method", "none")
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=cost_opts, mode=selector.SelectSelectorMode.LIST
                )
            ),
        }
        has_acc = bool(
            {CONF_ACCUMULATE_COST_RATES, CONF_ACCUMULATE_LEVELIZED_COST_RATES} & supported
        )
        if has_acc:
            cost_fields[vol.Required(
                "accumulate_costs", default=defaults.get("accumulate_costs", False)
            )] = BOOLEAN_SELECTOR
        fields[vol.Required("costs")] = section(
            vol.Schema(cost_fields), {"collapsed": False}
        )

    # --- Savings section ---
    sav_opts = _savings_method_options(scope)
    if len(sav_opts) > 1:
        sav_fields: dict = {
            vol.Required(
                "savings_method", default=defaults.get("savings_method", "none")
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=sav_opts, mode=selector.SelectSelectorMode.LIST
                )
            ),
        }
        has_acc_sav = bool(
            {CONF_ACCUMULATE_COST_SAVING_RATES, CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES}
            & supported
        )
        if has_acc_sav:
            sav_fields[vol.Required(
                "accumulate_savings", default=defaults.get("accumulate_savings", False)
            )] = BOOLEAN_SELECTOR
        fields[vol.Required("savings")] = section(
            vol.Schema(sav_fields), {"collapsed": False}
        )

    return vol.Schema(fields)


def scope_ui_to_leaves(scope: str, user_input: dict) -> list[str]:
    """Map new-style UI form values to a sorted list of enabled leaf keys."""
    supported = SCOPE_SUPPORTED_OPTIONS.get(scope, set())
    enabled: set[str] = set()

    if user_input.get("distribution_power"):
        enabled.add(CONF_ENABLE_DISTRIBUTION_POWER)
    if user_input.get("distribution_ratios"):
        enabled.add(CONF_ENABLE_DISTRIBUTION_RATIOS)
    if user_input.get("distribution_shares"):
        enabled.add(CONF_ENABLE_DISTRIBUTION_SHARES)
    if user_input.get("charging_source_shares"):
        enabled.add(CONF_ENABLE_CHARGING_SOURCE_SHARES)
    if user_input.get("power_source_shares"):
        enabled.add(CONF_ENABLE_POWER_SOURCE_SHARES)
    if user_input.get("export_compensation_rate"):
        enabled.add(CONF_ENABLE_EXPORT_COMPENSATION_RATE)
    if user_input.get("export_compensation_total"):
        enabled.add(CONF_ACCUMULATE_EXPORT_COMPENSATION)

    cost_method = user_input.get("cost_method", "none")
    if cost_method in ("standard", "both"):
        enabled.add(CONF_CALCULATE_COST_RATES)
    if cost_method in ("levelized", "both"):
        enabled.add(CONF_CALCULATE_LEVELIZED_COST_RATES)
    if user_input.get("accumulate_costs") and cost_method != "none":
        if cost_method in ("standard", "both"):
            enabled.add(CONF_ACCUMULATE_COST_RATES)
        if cost_method in ("levelized", "both"):
            enabled.add(CONF_ACCUMULATE_LEVELIZED_COST_RATES)

    savings_method = user_input.get("savings_method", "none")
    if savings_method in ("standard", "both"):
        enabled.add(CONF_CALCULATE_COST_SAVING_RATES)
    if savings_method in ("levelized", "both"):
        enabled.add(CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES)
    if user_input.get("accumulate_savings") and savings_method != "none":
        if savings_method in ("standard", "both"):
            enabled.add(CONF_ACCUMULATE_COST_SAVING_RATES)
        if savings_method in ("levelized", "both"):
            enabled.add(CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES)

    return sorted(enabled & supported)


def scope_leaves_to_ui_defaults(scope: str, leaves: set[str]) -> dict:
    """Reconstruct UI form defaults from stored leaf keys for *scope*."""
    supported = SCOPE_SUPPORTED_OPTIONS.get(scope, set())
    result: dict = {
        "distribution_power": CONF_ENABLE_DISTRIBUTION_POWER in leaves,
        "distribution_ratios": CONF_ENABLE_DISTRIBUTION_RATIOS in leaves,
        "distribution_shares": CONF_ENABLE_DISTRIBUTION_SHARES in leaves,
        "charging_source_shares": CONF_ENABLE_CHARGING_SOURCE_SHARES in leaves,
        "power_source_shares": CONF_ENABLE_POWER_SOURCE_SHARES in leaves,
        "export_compensation_rate": CONF_ENABLE_EXPORT_COMPENSATION_RATE in leaves,
        "export_compensation_total": CONF_ACCUMULATE_EXPORT_COMPENSATION in leaves,
    }

    has_cost = CONF_CALCULATE_COST_RATES in leaves and CONF_CALCULATE_COST_RATES in supported
    has_lcost = (
        CONF_CALCULATE_LEVELIZED_COST_RATES in leaves
        and CONF_CALCULATE_LEVELIZED_COST_RATES in supported
    )
    if has_cost and has_lcost:
        result["cost_method"] = "both"
    elif has_lcost:
        result["cost_method"] = "levelized"
    elif has_cost:
        result["cost_method"] = "standard"
    else:
        result["cost_method"] = "none"

    result["accumulate_costs"] = bool(
        {CONF_ACCUMULATE_COST_RATES, CONF_ACCUMULATE_LEVELIZED_COST_RATES} & leaves
    )

    has_sav = (
        CONF_CALCULATE_COST_SAVING_RATES in leaves
        and CONF_CALCULATE_COST_SAVING_RATES in supported
    )
    has_lsav = (
        CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES in leaves
        and CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES in supported
    )
    if has_sav and has_lsav:
        result["savings_method"] = "both"
    elif has_lsav:
        result["savings_method"] = "levelized"
    elif has_sav:
        result["savings_method"] = "standard"
    else:
        result["savings_method"] = "none"

    result["accumulate_savings"] = bool(
        {CONF_ACCUMULATE_COST_SAVING_RATES, CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES}
        & leaves
    )

    return result


def _flatten_scope_sections(user_input: dict) -> dict:
    """Flatten section-nested form values into a single-level dict."""
    flat: dict = {}
    for key, value in user_input.items():
        if isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    return flat


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

    Step 1 (user): collects the integration name.
    Step 2 (preset): picks a sensor preset for the initial options.
    Grid and device adapters are added afterwards as subentries via the
    "Add device" button.
    """

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        self._title: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the integration title."""
        errors: dict[str, str] = {}

        if user_input is not None:
            title = user_input.get(CONF_NAME, "").strip()
            if not title:
                errors[CONF_NAME] = "invalid_name"
            else:
                self._title = title
                return await self.async_step_preset()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_NAME, default=""): TEXT_SELECTOR}
            ),
            errors=errors,
        )

    async def async_step_preset(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a sensor preset for this installation."""
        if user_input is not None:
            preset = user_input.get(CONF_PRESET, PRESET_RECOMMENDED)
            return self.async_create_entry(
                title=self._title,
                data={},
                options={
                    "schema": 2,
                    "scopes": default_scopes(preset),
                    CONF_ENABLE_DEBUG_ENTITIES: False,
                    CONF_PRESET: preset,
                },
            )

        return self.async_show_form(
            step_id="preset",
            data_schema=vol.Schema({
                vol.Required(CONF_PRESET, default=PRESET_RECOMMENDED): _preset_selector(
                    include_custom=False
                ),
            }),
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
    """Multi-step options flow with preset selection and per-scope pages.

    Step init:   Pick a preset (applies immediately) or choose Custom.
    Custom path: One page per device class present in the installation
                 (combined → grid → pv_system → battery → consumer).
    """

    def __init__(self) -> None:
        self._scopes: dict[str, list[str]] = {}
        self._debug: bool = False
        self._device_types: set[str] = set()

    def _init_device_types(self) -> None:
        """Populate _device_types from the current subentries."""
        self._device_types = {
            sub.data.get("adapter", {}).get("adapter_type")
            for sub in self.config_entry.subentries.values()
        } - {None}

    def _next_scope_step(self, after: str) -> str | None:
        """Return the next step id in the chain after *after*, or None if done."""
        order = ["combined", "grid", "pv_system", "battery", "consumer"]
        for scope in order[order.index(after) + 1:]:
            if scope in self._device_types:
                return scope
        return None

    def _last_scope(self) -> str:
        """Return the final scope step in the navigation chain."""
        for scope in reversed(["combined", "grid", "pv_system", "battery", "consumer"]):
            if scope == "combined" or scope in self._device_types:
                return scope
        return "combined"

    async def _finish(self) -> FlowResult:
        """Run feasibility check and save, or re-show the last scope form."""
        stored = self.config_entry.options.get("scopes", {})
        new_scopes = {
            scope: self._scopes.get(scope, sorted(stored.get(scope, [])))
            for scope in SCOPES
        }
        new_options = {
            "schema": 2,
            "scopes": new_scopes,
            CONF_ENABLE_DEBUG_ENTITIES: self._debug,
            CONF_PRESET: PRESET_CUSTOM,
        }
        problems = check_options_feasibility(self.config_entry, new_options)
        if not problems:
            return self.async_create_entry(title="", data=new_options)

        last = self._last_scope()
        defaults = scope_leaves_to_ui_defaults(last, set(self._scopes.get(last, [])))
        return self.async_show_form(
            step_id=last,
            data_schema=build_scope_form(last, defaults),
            errors={"base": "reconfigure_adapters_first"},
            description_placeholders={
                "adapters_needing_reconfigure": ", ".join(problems),
            },
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show preset selector; non-custom presets save immediately."""
        self._init_device_types()

        if user_input is not None:
            preset = user_input.get(CONF_PRESET, PRESET_CUSTOM)
            self._debug = bool(user_input.get(CONF_ENABLE_DEBUG_ENTITIES, False))

            if preset != PRESET_CUSTOM:
                stored = self.config_entry.options.get("scopes", {})
                new_scopes = {
                    scope: sorted(
                        PRESET_SELECTIONS[preset] & SCOPE_SUPPORTED_OPTIONS[scope]
                    ) if (scope == SCOPE_COMBINED or scope in self._device_types)
                    else sorted(stored.get(scope, []))
                    for scope in SCOPES
                }
                return self.async_create_entry(
                    title="",
                    data={
                        "schema": 2,
                        "scopes": new_scopes,
                        CONF_ENABLE_DEBUG_ENTITIES: self._debug,
                        CONF_PRESET: preset,
                    },
                )

            return await self.async_step_combined()

        current_preset = self.config_entry.options.get(CONF_PRESET, PRESET_CUSTOM)
        current_debug = bool(
            self.config_entry.options.get(CONF_ENABLE_DEBUG_ENTITIES, False)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_PRESET, default=current_preset): _preset_selector(),
                vol.Required(
                    CONF_ENABLE_DEBUG_ENTITIES, default=current_debug
                ): BOOLEAN_SELECTOR,
            }),
        )

    async def async_step_combined(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure combined (whole-home aggregate) sensors."""
        if user_input is not None:
            flat = _flatten_scope_sections(user_input)
            self._scopes[SCOPE_COMBINED] = scope_ui_to_leaves(SCOPE_COMBINED, flat)
            next_step = self._next_scope_step("combined")
            if next_step is None:
                return await self._finish()
            return await getattr(self, f"async_step_{next_step}")()

        stored = set(
            self.config_entry.options.get("scopes", {}).get(SCOPE_COMBINED, [])
        )
        return self.async_show_form(
            step_id="combined",
            data_schema=build_scope_form(
                SCOPE_COMBINED, scope_leaves_to_ui_defaults(SCOPE_COMBINED, stored)
            ),
        )

    async def async_step_grid(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure grid adapter sensors."""
        if user_input is not None:
            flat = _flatten_scope_sections(user_input)
            self._scopes["grid"] = scope_ui_to_leaves("grid", flat)
            next_step = self._next_scope_step("grid")
            if next_step is None:
                return await self._finish()
            return await getattr(self, f"async_step_{next_step}")()

        stored = set(self.config_entry.options.get("scopes", {}).get("grid", []))
        return self.async_show_form(
            step_id="grid",
            data_schema=build_scope_form(
                "grid", scope_leaves_to_ui_defaults("grid", stored)
            ),
        )

    async def async_step_pv_system(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure PV system adapter sensors."""
        if user_input is not None:
            flat = _flatten_scope_sections(user_input)
            self._scopes["pv_system"] = scope_ui_to_leaves("pv_system", flat)
            next_step = self._next_scope_step("pv_system")
            if next_step is None:
                return await self._finish()
            return await getattr(self, f"async_step_{next_step}")()

        stored = set(self.config_entry.options.get("scopes", {}).get("pv_system", []))
        return self.async_show_form(
            step_id="pv_system",
            data_schema=build_scope_form(
                "pv_system", scope_leaves_to_ui_defaults("pv_system", stored)
            ),
        )

    async def async_step_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure battery adapter sensors."""
        if user_input is not None:
            flat = _flatten_scope_sections(user_input)
            self._scopes["battery"] = scope_ui_to_leaves("battery", flat)
            next_step = self._next_scope_step("battery")
            if next_step is None:
                return await self._finish()
            return await getattr(self, f"async_step_{next_step}")()

        stored = set(self.config_entry.options.get("scopes", {}).get("battery", []))
        return self.async_show_form(
            step_id="battery",
            data_schema=build_scope_form(
                "battery", scope_leaves_to_ui_defaults("battery", stored)
            ),
        )

    async def async_step_consumer(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure consumer adapter sensors."""
        if user_input is not None:
            flat = _flatten_scope_sections(user_input)
            self._scopes["consumer"] = scope_ui_to_leaves("consumer", flat)
            return await self._finish()

        stored = set(self.config_entry.options.get("scopes", {}).get("consumer", []))
        return self.async_show_form(
            step_id="consumer",
            data_schema=build_scope_form(
                "consumer", scope_leaves_to_ui_defaults("consumer", stored)
            ),
        )