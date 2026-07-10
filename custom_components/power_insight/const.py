"""Constants."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.util.event_type import EventType

if TYPE_CHECKING:
    from homeassistant.core import (
        EventStateChangedData, EventStateReportedData
    )


PLATFORMS = [Platform.SENSOR]

DOMAIN = "power_insight"

# Structural keys
CONF_KEY = "key"
CONF_ADAPTER_TYPE = "adapter_type"

# Common adapter fields
CONF_POWER_ENTITY = "power_entity"
CONF_POWER_ENTITY_INVERTED = "power_entity_inverted"

# Grid adapter fields
CONF_ELECTRICITY_PRICE_ENTITY = "grid_electricity_price_entity"
CONF_CO2_INTENSITY_ENTITY = "co2_intensity_entity"

# Raw calculation inputs (top-level storage)
CONF_LIFETIME_PRODUCTION = "lifetime_production"
CONF_LIFETIME_COST = "lifetime_cost"
CONF_CO2_FOOTPRINT = "co2_footprint"

# Calculated values - PV System (stored in adapter.config)
CONF_INITIAL_LCOE = "default_lcoe"
CONF_CURRENT_LCOE = "current_lcoe"
CONF_INITIAL_CO2_INTENSITY = "default_co2_intensity"
CONF_CURRENT_CO2_INTENSITY = "current_co2_intensity"

# Calculated values - Battery (stored in adapter.config)
CONF_INITIAL_LCOS = "default_lcos"
CONF_CURRENT_LCOS = "current_lcos"

# Correction factor (current_lcoe / default_lcoe), stored in adapter.config
CONF_CORRECTION_FACTOR = "correction_factor"

# Ledger of retired (removed end-of-life) adapters, stored in ConfigEntry.data
CONF_RETIRED_ADAPTERS = "retired_adapters"

# PV/Battery user settings (stored in adapter.config)
CONF_EXPORTS_POWER = "exports_power"
CONF_EXPORT_COMPENSATION = "export_compensation"

# Battery specific (stored in adapter.config)
CONF_BAT_EFFICIENCY = "battery_efficiency"
CONF_CHARGE_FROM_ADAPTERS = "charge_from_adapters"




# Option keys — import these in sensor.py to gate entity registration.

CONF_CALCULATE_INSTANTANEOUS_RATES = "calculate_instantaneous_rates"
CONF_CALCULATE_INSTANTANEOUS_SAVING_RATES = "calculate_instantaneous_saving_rates"
CONF_CALCULATE_ACCUMULATED_ENTITIES = "calculate_accumulated_entities"

CONF_ENABLE_DEBUG_ENTITIES = "debug_power_entities"
# Legacy combined power-share toggle (pre-redesign); kept only so the options
# migration can read it. Superseded by the distribution/share keys below.
CONF_ENABLE_POWER_SHARES = "enable_power_shares"

# Power-distribution categories (replace CONF_ENABLE_POWER_SHARES)
CONF_ENABLE_DISTRIBUTION_POWER = "enable_distribution_power"      # watt split
CONF_ENABLE_DISTRIBUTION_RATIOS = "enable_distribution_ratios"    # *_ratio %
CONF_ENABLE_DISTRIBUTION_SHARES = "enable_distribution_shares"    # *_share %
CONF_ENABLE_CHARGING_SOURCE_SHARES = "enable_charging_source_shares"  # battery
CONF_ENABLE_POWER_SOURCE_SHARES = "enable_power_source_shares"        # consumer

# Export compensation (split out of the cost-rate / accumulate-cost keys)
CONF_ENABLE_EXPORT_COMPENSATION_RATE = "enable_export_compensation_rate"
CONF_ACCUMULATE_EXPORT_COMPENSATION = "accumulate_export_compensation"

CONF_CALCULATE_COST_RATES = "calculate_cost_rates"
CONF_CALCULATE_LEVELIZED_COST_RATES = "calculate_levelized_cost_rates"
CONF_CALCULATE_CO2_INTENSITY_RATES = "calculate_co2_intensity_rates"
CONF_CALCULATE_LEVELIZED_CO2_INTENSITY_RATES = "calculate_levelized_co2_intensity_rates"

CONF_CALCULATE_COST_SAVING_RATES = "calculate_cost_saving_rates"
CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES = "calculate_levelized_cost_saving_rates"
CONF_CALCULATE_CO2_SAVING_RATES = "calculate_co2_saving_rates"
CONF_CALCULATE_LEVELIZED_CO2_SAVING_RATES = "calculate_levelized_co2_saving_rates"


CONF_ACCUMULATE_COST_RATES = "accumulate_cost_rates"
CONF_ACCUMULATE_LEVELIZED_COST_RATES = "accumulate_levelized_cost_rates"
CONF_ACCUMULATE_CO2_INTENSITY_RATES = "accumulate_co2_intensity_rates"
CONF_ACCUMULATE_LEVELIZED_CO2_INTENSITY_RATES = "accumulate_levelized_co2_intensity_rates"

CONF_ACCUMULATE_COST_SAVING_RATES = "accumulate_cost_saving_rates"
CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES = "accumulate_levelized_cost_saving_rates"
CONF_ACCUMULATE_CO2_SAVING_RATES = "accumulate_co2_saving_rates"
CONF_ACCUMULATE_LEVELIZED_CO2_SAVING_RATES = "accumulate_levelized_co2_saving_rates"


# ---------------------------------------------------------------------------
# Option scopes
#
# Sensor selection is configured per scope: the whole-home aggregate
# ("combined") plus one scope per device type. Each scope only offers the leaf
# options that its sensors support. Stored as entry.options["scopes"][scope] =
# [enabled leaf keys]; see docs/options-flow-redesign.md.
# ---------------------------------------------------------------------------

SCOPE_COMBINED = "combined"
SCOPES = (SCOPE_COMBINED, "grid", "pv_system", "battery", "consumer")

# ---------------------------------------------------------------------------
# Options presets
# ---------------------------------------------------------------------------

CONF_PRESET = "preset"

PRESET_MINIMAL = "minimal"
PRESET_RECOMMENDED = "recommended"
PRESET_EXTENDED = "extended"
PRESET_ALL = "all"
PRESET_CUSTOM = "custom"

SCOPE_SUPPORTED_OPTIONS: dict[str, set[str]] = {
    SCOPE_COMBINED: {
        CONF_CALCULATE_COST_RATES,
        CONF_CALCULATE_LEVELIZED_COST_RATES,
        CONF_CALCULATE_COST_SAVING_RATES,
        CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
        CONF_ACCUMULATE_COST_RATES,
        CONF_ACCUMULATE_LEVELIZED_COST_RATES,
        CONF_ACCUMULATE_COST_SAVING_RATES,
        CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
        CONF_ENABLE_DISTRIBUTION_POWER,
        CONF_ENABLE_DISTRIBUTION_RATIOS,
    },
    "grid": {
        CONF_CALCULATE_COST_RATES,
        CONF_ACCUMULATE_COST_RATES,
        CONF_ENABLE_EXPORT_COMPENSATION_RATE,
        CONF_ACCUMULATE_EXPORT_COMPENSATION,
        CONF_ENABLE_DISTRIBUTION_POWER,
        CONF_ENABLE_DISTRIBUTION_RATIOS,
        CONF_ENABLE_DISTRIBUTION_SHARES,
    },
    "pv_system": {
        CONF_CALCULATE_COST_RATES,
        CONF_CALCULATE_LEVELIZED_COST_RATES,
        CONF_CALCULATE_COST_SAVING_RATES,
        CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
        CONF_ENABLE_EXPORT_COMPENSATION_RATE,
        CONF_ACCUMULATE_EXPORT_COMPENSATION,
        CONF_ACCUMULATE_COST_RATES,
        CONF_ACCUMULATE_LEVELIZED_COST_RATES,
        CONF_ACCUMULATE_COST_SAVING_RATES,
        CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
        CONF_ENABLE_DISTRIBUTION_POWER,
        CONF_ENABLE_DISTRIBUTION_RATIOS,
        CONF_ENABLE_DISTRIBUTION_SHARES,
    },
    "battery": {
        CONF_CALCULATE_COST_RATES,
        CONF_CALCULATE_LEVELIZED_COST_RATES,
        CONF_CALCULATE_COST_SAVING_RATES,
        CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
        CONF_ENABLE_EXPORT_COMPENSATION_RATE,
        CONF_ACCUMULATE_EXPORT_COMPENSATION,
        CONF_ACCUMULATE_COST_RATES,
        CONF_ACCUMULATE_LEVELIZED_COST_RATES,
        CONF_ACCUMULATE_COST_SAVING_RATES,
        CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
        CONF_ENABLE_DISTRIBUTION_POWER,
        CONF_ENABLE_DISTRIBUTION_RATIOS,
        CONF_ENABLE_DISTRIBUTION_SHARES,
        CONF_ENABLE_CHARGING_SOURCE_SHARES,
    },
    "consumer": {
        CONF_CALCULATE_COST_RATES,
        CONF_CALCULATE_LEVELIZED_COST_RATES,
        CONF_ENABLE_POWER_SOURCE_SHARES,
    },
}








# EVENTS
# ------------------------------------------------------------------------->
# EVENT_STATE_CHANGED: EventType[EventStateChangedData] = EventType("state_changed")

# EVENT_STATE_REPORTED: EventType[EventStateReportedData] = EventType("state_reported")
