"""Sensor entities for the PowerInsight integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPower,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)

from .entity import (
    BaseEventSensorEntity,
    BaseEventIntegrationSensorEntity,
    IntegrationSensorExtraStoredData,
)
from .utils import get_value
from .power_insight import PowerInsight, AbstractBaseAdapter
from . import MyConfigEntry
from .const import (
    DOMAIN,
    SCOPE_COMBINED,
    CONF_ENABLE_DEBUG_ENTITIES,
    CONF_ENABLE_DISTRIBUTION_POWER,
    CONF_ENABLE_DISTRIBUTION_RATIOS,
    CONF_ENABLE_DISTRIBUTION_SHARES,
    CONF_ENABLE_CHARGING_SOURCE_SHARES,
    CONF_ENABLE_POWER_SOURCE_SHARES,
    CONF_ENABLE_EXPORT_COMPENSATION_RATE,
    CONF_ACCUMULATE_EXPORT_COMPENSATION,
    CONF_CALCULATE_COST_RATES,
    CONF_CALCULATE_LEVELIZED_COST_RATES,
    CONF_CALCULATE_COST_SAVING_RATES,
    CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
    CONF_ACCUMULATE_COST_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_RATES,
    CONF_ACCUMULATE_COST_SAVING_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
    CONF_RETIRED_ADAPTERS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PowerInsightSensorDescription(SensorEntityDescription):
    """Provide the description of a PowerInsight sensor."""

    entities_fn: Callable[[PowerInsight], list[str]]
    exists_fn: Callable[..., bool] = lambda _: True
    value_fn: Callable[[PowerInsight], dict[str, float | None] | float | None]
    transform_fn: Callable[[float], float] = lambda value: value
    # When True, a per-adapter sensor scales its displayed value by the
    # adapter's correction factor (levelized quantities only).
    apply_correction_factor: bool = False


@dataclass(frozen=True, kw_only=True)
class PowerInsightIntegrationSensorDescription(SensorEntityDescription):
    """Provide a description of a PowerInsight integration sensor."""

    entities_fn: Callable[[PowerInsight], list[str]]
    exists_fn: Callable[..., bool] = lambda _: True
    integration_value_fn: Callable[[PowerInsight], dict[str, float | None] | float | None]
    transform_fn: Callable[[float], float] = lambda value: value
    # When True, the per-adapter integration sensor accumulates the base rate
    # but displays the running total scaled by the adapter's correction factor.
    apply_correction_factor: bool = False


# ---------------------------------------------------------------------------
# Hub-level sensors
# ---------------------------------------------------------------------------

POWER_INSIGHT_SENSORS = (
    PowerInsightSensorDescription(
        key="available_power",
        name="Available power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.gross_power,
    ),
    PowerInsightSensorDescription(
        key="combined_export_ratio",
        name="Combined export ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.gross_power_export_ratio,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="combined_self_consumption_power",
        name="Combined self-consumption power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.combined_consumption,
    ),
    PowerInsightSensorDescription(
        key="combined_self_consumption_ratio",
        name="Combined self-consumption ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.gross_power_consumption_ratio,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="combined_self_consumption_cost_savings_rate",
        name="Combined self-consumption cost savings rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_avoided_cost_rate,
    ),
    PowerInsightSensorDescription(
        key="combined_charging_power",
        name="Combined charging power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.combined_charging_power,
    ),
    PowerInsightSensorDescription(
        key="combined_standby_power",
        name="Combined standby power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.combined_standby_power,
    ),
    PowerInsightSensorDescription(
        key="combined_charging_ratio",
        name="Combined charging ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.gross_power_charging_ratio,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="combined_standby_ratio",
        name="Combined standby ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.gross_power_standby_ratio,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="combined_price_of_electricity",
        name="Combined price of electricity",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_coe,
    ),
    PowerInsightSensorDescription(
        key="combined_levelized_price_of_electricity",
        name="Combined levelized price of electricity",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_lcoe,
    ),
    PowerInsightSensorDescription(
        key="combined_cost_rate",
        name="Combined cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.combined_coe_rate,
    ),
    PowerInsightSensorDescription(
        key="combined_levelized_cost_rate",
        name="Combined levelized cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.combined_lcoe_rate_corrected,
    ),
    PowerInsightSensorDescription(
        key="combined_operating_cost_rate",
        name="Combined operating cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_coo_rate,
    ),
    PowerInsightSensorDescription(
        key="combined_levelized_operating_cost_rate",
        name="Combined levelized operating cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_lcoo_rate_corrected,
    ),
    PowerInsightSensorDescription(
        key="combined_cost_savings_rate",
        name="Combined cost savings rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_saving_rate,
    ),
    PowerInsightSensorDescription(
        key="combined_levelized_cost_savings_rate",
        name="Combined levelized cost savings rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_levelized_saving_rate_corrected,
    ),
)

POWER_INSIGHT_INTEGRATION_SENSORS = (
    PowerInsightIntegrationSensorDescription(
        key="combined_total_operating_costs",
        name="Combined total operating costs",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.combined_coo_rate,
    ),
    PowerInsightIntegrationSensorDescription(
        key="combined_total_self_consumption_cost_savings",
        name="Combined total self-consumption cost savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.combined_avoided_cost_rate,
    ),
    PowerInsightIntegrationSensorDescription(
        key="combined_total_cost_savings",
        name="Combined total cost savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.combined_saving_rate,
    ),
)


# ---------------------------------------------------------------------------
# Combined accumulated levelized sensors (derived + retired-adapter ledger)
#
# These do NOT integrate a pre-summed combined rate. Instead they derive their
# value at read time as the sum of the per-adapter base accumulated totals
# (each already scaled by that adapter's correction factor for display) plus a
# persistent ledger of removed end-of-life adapters. This keeps the combined
# total consistent with the per-adapter totals, makes lifetime-value
# corrections retroactive, and prevents a removed device from dropping its
# historical contribution.
# ---------------------------------------------------------------------------

# Maps each combined ledger sensor key to the per-adapter accumulated key it
# sums over.
COMBINED_LEDGER_ADAPTER_KEYS: dict[str, str] = {
    "combined_total_levelized_operating_costs": "total_levelized_operating_costs",
    "combined_total_levelized_cost_savings": "total_levelized_cost_savings",
}

# Per-adapter accumulated keys whose final corrected value is frozen into the
# retired-adapter ledger when a device is removed.
LEVELIZED_TOTAL_KEYS = frozenset(COMBINED_LEDGER_ADAPTER_KEYS.values())

POWER_INSIGHT_COMBINED_LEDGER_SENSORS = (
    PowerInsightSensorDescription(
        key="combined_total_levelized_operating_costs",
        name="Combined total levelized operating costs",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: None,
    ),
    PowerInsightSensorDescription(
        key="combined_total_levelized_cost_savings",
        name="Combined total levelized cost savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: None,
    ),
)


# ---------------------------------------------------------------------------
# Grid adapter sensors
# ---------------------------------------------------------------------------

POWER_INSIGHT_GRID_ADAPTER_SENSORS = (
    # Import / export both physically happen at the (single) grid connection,
    # so the grid device owns both sides of the meter.
    PowerInsightSensorDescription(
        key="import_power",
        name="Import power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.grid_adapters_import_power,
    ),
    PowerInsightSensorDescription(
        key="export_power",
        name="Export power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.grid_adapters_export_power,
    ),
    PowerInsightSensorDescription(
        key="cost_rate",
        name="Cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_price + obj.source_entities_power,
        value_fn=lambda obj: obj.grid_adapters_coe_rate,
    ),
    PowerInsightSensorDescription(
        key="export_compensation_rate",
        name="Export compensation rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_price + obj.source_entities_power,
        value_fn=lambda obj: obj.grid_adapters_export_compensation_rate,
    ),
    PowerInsightSensorDescription(
        key="consumption_ratio",
        name="Consumption ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.grid_adapters_consumption_ratios,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="consumption_share",
        name="Consumption share",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.grid_adapters_consumption_shares,
        transform_fn=lambda val: val * 100,
    ),
    # --- Requires new power_insight.py dict-properties; uncomment when ready ---
    # PowerInsightSensorDescription(
    #     key="charging_ratio",
    #     name="Charging ratio",
    #     icon="mdi:percent",
    #     native_unit_of_measurement=PERCENTAGE,
    #     state_class=SensorStateClass.MEASUREMENT,
    #     suggested_display_precision=0,
    #     entities_fn=lambda obj: obj.source_entities_power,
    #     value_fn=lambda obj: obj.grid_adapters_charging_ratio,
    #     transform_fn=lambda val: val * 100,
    # ),
    # PowerInsightSensorDescription(
    #     key="charging_share",
    #     name="Charging share",
    #     icon="mdi:percent",
    #     native_unit_of_measurement=PERCENTAGE,
    #     state_class=SensorStateClass.MEASUREMENT,
    #     suggested_display_precision=0,
    #     entities_fn=lambda obj: obj.source_entities_power,
    #     value_fn=lambda obj: obj.grid_adapters_combined_charging_share,
    #     transform_fn=lambda val: val * 100,
    # ),
    # PowerInsightSensorDescription(
    #     key="standby_ratio",
    #     name="Standby ratio",
    #     icon="mdi:percent",
    #     native_unit_of_measurement=PERCENTAGE,
    #     state_class=SensorStateClass.MEASUREMENT,
    #     suggested_display_precision=0,
    #     entities_fn=lambda obj: obj.source_entities_power,
    #     value_fn=lambda obj: obj.grid_adapters_standby_ratio,
    #     transform_fn=lambda val: val * 100,
    # ),
    # PowerInsightSensorDescription(
    #     key="standby_share",
    #     name="Standby share",
    #     icon="mdi:percent",
    #     native_unit_of_measurement=PERCENTAGE,
    #     state_class=SensorStateClass.MEASUREMENT,
    #     suggested_display_precision=0,
    #     entities_fn=lambda obj: obj.source_entities_power,
    #     value_fn=lambda obj: obj.grid_adapters_standby_share,
    #     transform_fn=lambda val: val * 100,
    # ),
)

POWER_INSIGHT_GRID_ADAPTER_INTEGRATION_SENSORS = (
    PowerInsightIntegrationSensorDescription(
        key="total_cost",
        name="Total cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_price + obj.source_entities_power,
        integration_value_fn=lambda obj: obj.grid_adapters_coe_rate,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_export_compensation",
        name="Total export compensation",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_price + obj.source_entities_power,
        integration_value_fn=lambda obj: obj.grid_adapters_export_compensation_rate,
    ),
)


# ---------------------------------------------------------------------------
# PV adapter sensors
# ---------------------------------------------------------------------------

POWER_INSIGHT_PV_ADAPTER_SENSORS = (
    PowerInsightSensorDescription(
        key="export_power",
        name="Export power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.prod_adapters_export_power,
    ),
    PowerInsightSensorDescription(
        key="export_ratio",
        name="Export ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.prod_adapters_export_ratios,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="export_share",
        name="Export share",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.prod_adapters_export_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="export_compensation_rate",
        name="Export compensation rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.prod_adapters_export_compensation_rates,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_power",
        name="Self-consumption power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.prod_adapters_consumption_power,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_ratio",
        name="Self-consumption ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.prod_adapters_consumption_ratios,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_share",
        name="Self-consumption share",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.prod_adapters_consumption_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_cost_savings_rate",
        name="Self-consumption cost savings rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.prod_adapters_avoided_cost_rates,
    ),
    PowerInsightSensorDescription(
        key="operating_cost_rate",
        name="Operating cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.prod_adapters_coo_rates,
    ),
    PowerInsightSensorDescription(
        key="levelized_operating_cost_rate",
        name="Levelized operating cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        value_fn=lambda obj: obj.prod_adapters_lcoo_rates,
        apply_correction_factor=True,
    ),
    PowerInsightSensorDescription(
        key="cost_savings_rate",
        name="Cost savings rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.prod_adapters_cost_saving_rates,
    ),
    PowerInsightSensorDescription(
        key="levelized_cost_savings_rate",
        name="Levelized cost savings rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        value_fn=lambda obj: obj.prod_adapters_levelized_cost_saving_rates,
        apply_correction_factor=True,
    ),
)

POWER_INSIGHT_PV_ADAPTER_INTEGRATION_SENSORS = (
    PowerInsightIntegrationSensorDescription(
        key="total_export_compensation",
        name="Total export compensation",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.exports_power,
        integration_value_fn=lambda obj: obj.prod_adapters_export_compensation_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_operating_costs",
        name="Total operating costs",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.prod_adapters_coo_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_levelized_operating_costs",
        name="Total levelized operating costs",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        integration_value_fn=lambda obj: obj.prod_adapters_lcoo_rates,
        apply_correction_factor=True,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_self_consumption_cost_savings",
        name="Total self-consumption cost savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.prod_adapters_avoided_cost_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_cost_savings",
        name="Total cost savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.prod_adapters_cost_saving_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_levelized_cost_savings",
        name="Total levelized cost savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        integration_value_fn=lambda obj: obj.prod_adapters_levelized_cost_saving_rates,
        apply_correction_factor=True,
    ),
)


# ---------------------------------------------------------------------------
# Storage (battery) adapter sensors
# ---------------------------------------------------------------------------
# Identical structure to POWER_INSIGHT_PV_ADAPTER_SENSORS but pointing to
# storage_adapters_* properties.  Charging-source-share sensors are added
# dynamically in async_setup_entry.

POWER_INSIGHT_STORAGE_ADAPTER_SENSORS = (
    PowerInsightSensorDescription(
        key="export_power",
        name="Export power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.storage_adapters_export_power,
    ),
    PowerInsightSensorDescription(
        key="export_ratio",
        name="Export ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.storage_adapters_export_ratios,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="export_share",
        name="Export share",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.storage_adapters_export_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="export_compensation_rate",
        name="Export compensation rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.storage_adapters_export_compensation_rates,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_power",
        name="Self-consumption power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.storage_adapters_consumption_power,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_ratio",
        name="Self-consumption ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.storage_adapters_consumption_ratios,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_share",
        name="Self-consumption share",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.storage_adapters_consumption_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_cost_savings_rate",
        name="Self-consumption cost savings rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.storage_adapters_avoided_cost_rates,
    ),
    PowerInsightSensorDescription(
        key="operating_cost_rate",
        name="Operating cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.storage_adapters_coo_rates,
    ),
    PowerInsightSensorDescription(
        key="levelized_operating_cost_rate",
        name="Levelized operating cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        value_fn=lambda obj: obj.storage_adapters_lcoo_rates,
        apply_correction_factor=True,
    ),
    PowerInsightSensorDescription(
        key="cost_savings_rate",
        name="Cost savings rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.storage_adapters_cost_saving_rates,
    ),
    PowerInsightSensorDescription(
        key="levelized_cost_savings_rate",
        name="Levelized cost savings rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        value_fn=lambda obj: obj.storage_adapters_levelized_cost_saving_rates,
        apply_correction_factor=True,
    ),
)

POWER_INSIGHT_STORAGE_ADAPTER_INTEGRATION_SENSORS = (
    PowerInsightIntegrationSensorDescription(
        key="total_export_compensation",
        name="Total export compensation",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.exports_power,
        integration_value_fn=lambda obj: obj.storage_adapters_export_compensation_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_operating_costs",
        name="Total operating costs",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.storage_adapters_coo_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_levelized_operating_costs",
        name="Total levelized operating costs",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        integration_value_fn=lambda obj: obj.storage_adapters_lcoo_rates,
        apply_correction_factor=True,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_self_consumption_cost_savings",
        name="Total self-consumption cost savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.storage_adapters_avoided_cost_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_cost_savings",
        name="Total cost savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.storage_adapters_cost_saving_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_levelized_cost_savings",
        name="Total levelized cost savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        integration_value_fn=lambda obj: obj.storage_adapters_levelized_cost_saving_rates,
        apply_correction_factor=True,
    ),
)


# ---------------------------------------------------------------------------
# Consumer adapter sensors
# ---------------------------------------------------------------------------

POWER_INSIGHT_CONS_ADAPTER_SENSORS = (
    PowerInsightSensorDescription(
        key="operating_cost_rate",
        name="Operating cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.cons_adapters_coo_rates,
    ),
    PowerInsightSensorDescription(
        key="levelized_operating_cost_rate",
        name="Levelized operating cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.cons_adapters_lcoo_rates,
    ),
)

POWER_INSIGHT_CONS_ADAPTER_INTEGRATION_SENSORS: tuple[
    PowerInsightIntegrationSensorDescription, ...
] = ()


# ---------------------------------------------------------------------------
# Options wrapper
# ---------------------------------------------------------------------------


class OptionsWrapper:
    """Scope-aware view over the per-scope options dict.

    Options are stored as ``entry.options["scopes"][scope] = [enabled leaf
    keys]`` plus the global ``debug_power_entities`` flag. ``check(key, scope)``
    resolves whether a leaf option is enabled for a given scope.
    """

    def __init__(self, options: dict) -> None:
        """Initialise from the raw options dict."""
        self._options = options
        scopes = options.get("scopes", {})
        self._by_scope: dict[str, set[str]] = {
            scope: set(leaves) for scope, leaves in scopes.items()
        }

    def check(self, key: str, scope: str = SCOPE_COMBINED) -> bool:
        """Return True if *key* is enabled for *scope*."""
        if key == CONF_ENABLE_DEBUG_ENTITIES:
            return bool(self._options.get(key, False))
        return key in self._by_scope.get(scope, set())


# ---------------------------------------------------------------------------
# Option gating
# ---------------------------------------------------------------------------
#
# Maps a sensor description ``key`` to the integration option that controls
# whether it is created. A sensor whose key is absent here is not option-gated
# (it is still subject to its adapter-capability ``exists_fn``). This is the
# single source of truth for which option enables which sensor; each setup loop
# evaluates it against the scope it is building (combined / grid / pv_system /
# battery / consumer). Dynamic per-source sensors (charging shares, consumer
# source ratios) are gated inline in ``async_setup_entry``, since their keys are
# built at runtime.
_SENSOR_OPTION_GATE: dict[str, str] = {
    # --- Diagnostics ---
    "available_power": CONF_ENABLE_DEBUG_ENTITIES,
    # --- Power distribution (W) ---
    "import_power": CONF_ENABLE_DISTRIBUTION_POWER,                # grid
    "export_power": CONF_ENABLE_DISTRIBUTION_POWER,                # grid / pv / storage
    "self_consumption_power": CONF_ENABLE_DISTRIBUTION_POWER,      # pv / storage
    "combined_self_consumption_power": CONF_ENABLE_DISTRIBUTION_POWER,
    "combined_charging_power": CONF_ENABLE_DISTRIBUTION_POWER,
    "combined_standby_power": CONF_ENABLE_DISTRIBUTION_POWER,
    # --- Power distribution ratios ---
    "combined_export_ratio": CONF_ENABLE_DISTRIBUTION_RATIOS,
    "combined_self_consumption_ratio": CONF_ENABLE_DISTRIBUTION_RATIOS,
    "combined_charging_ratio": CONF_ENABLE_DISTRIBUTION_RATIOS,
    "combined_standby_ratio": CONF_ENABLE_DISTRIBUTION_RATIOS,
    "consumption_ratio": CONF_ENABLE_DISTRIBUTION_RATIOS,          # grid
    "export_ratio": CONF_ENABLE_DISTRIBUTION_RATIOS,              # pv / storage
    "self_consumption_ratio": CONF_ENABLE_DISTRIBUTION_RATIOS,
    # --- Power distribution shares ---
    "consumption_share": CONF_ENABLE_DISTRIBUTION_SHARES,         # grid
    "export_share": CONF_ENABLE_DISTRIBUTION_SHARES,             # pv / storage
    "self_consumption_share": CONF_ENABLE_DISTRIBUTION_SHARES,
    # --- Export compensation ---
    "export_compensation_rate": CONF_ENABLE_EXPORT_COMPENSATION_RATE,
    "total_export_compensation": CONF_ACCUMULATE_EXPORT_COMPENSATION,
    # --- Cost rates ---
    "cost_rate": CONF_CALCULATE_COST_RATES,                       # grid
    "operating_cost_rate": CONF_CALCULATE_COST_RATES,
    "combined_cost_rate": CONF_CALCULATE_COST_RATES,
    "combined_operating_cost_rate": CONF_CALCULATE_COST_RATES,
    "combined_price_of_electricity": CONF_CALCULATE_COST_RATES,
    # --- Levelized cost rates ---
    "levelized_operating_cost_rate": CONF_CALCULATE_LEVELIZED_COST_RATES,
    "combined_levelized_price_of_electricity": CONF_CALCULATE_LEVELIZED_COST_RATES,
    "combined_levelized_cost_rate": CONF_CALCULATE_LEVELIZED_COST_RATES,
    "combined_levelized_operating_cost_rate": CONF_CALCULATE_LEVELIZED_COST_RATES,
    # --- Cost savings rates ---
    "self_consumption_cost_savings_rate": CONF_CALCULATE_COST_SAVING_RATES,
    "cost_savings_rate": CONF_CALCULATE_COST_SAVING_RATES,
    "combined_self_consumption_cost_savings_rate": CONF_CALCULATE_COST_SAVING_RATES,
    "combined_cost_savings_rate": CONF_CALCULATE_COST_SAVING_RATES,
    # --- Levelized cost savings rates ---
    "levelized_cost_savings_rate": CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
    "combined_levelized_cost_savings_rate": CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
    # --- Accumulated costs ---
    "total_cost": CONF_ACCUMULATE_COST_RATES,                     # grid
    "total_operating_costs": CONF_ACCUMULATE_COST_RATES,
    "combined_total_operating_costs": CONF_ACCUMULATE_COST_RATES,
    "total_levelized_operating_costs": CONF_ACCUMULATE_LEVELIZED_COST_RATES,
    "combined_total_levelized_operating_costs": CONF_ACCUMULATE_LEVELIZED_COST_RATES,
    # --- Accumulated cost savings ---
    "total_self_consumption_cost_savings": CONF_ACCUMULATE_COST_SAVING_RATES,
    "total_cost_savings": CONF_ACCUMULATE_COST_SAVING_RATES,
    "combined_total_self_consumption_cost_savings": CONF_ACCUMULATE_COST_SAVING_RATES,
    "combined_total_cost_savings": CONF_ACCUMULATE_COST_SAVING_RATES,
    "total_levelized_cost_savings": CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
    "combined_total_levelized_cost_savings": CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
}


def _option_gated_out(description, options: OptionsWrapper, scope: str) -> bool:
    """Return True if *description* is gated off for *scope* by the options."""
    gate = _SENSOR_OPTION_GATE.get(description.key)
    return gate is not None and not options.check(gate, scope)


@callback
def _sync_entity_enabled_state(
    hass: HomeAssistant,
    entry: ConfigEntry,
    wanted_unique_ids: set[str],
) -> None:
    """Disable entities whose option is off; re-enable them when it is back on.

    Rather than deleting the entities of a disabled sensor group (which would
    drop their recorded history), we mark them disabled in the entity registry.
    They are hidden and stop updating, but keep their history and are restored
    the moment the option is re-enabled. Entities the user disabled themselves
    (``disabled_by == USER``) are never touched.
    """
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.platform != DOMAIN or ent.domain != "sensor":
            continue
        if ent.unique_id in wanted_unique_ids:
            if ent.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                ent_reg.async_update_entity(ent.entity_id, disabled_by=None)
        elif ent.disabled_by is None:
            ent_reg.async_update_entity(
                ent.entity_id,
                disabled_by=er.RegistryEntryDisabler.INTEGRATION,
            )


def _resolve_currency_unit(unit: str | None, hass: HomeAssistant | None) -> str | None:
    """Replace the ``EUR`` placeholder in a unit with the configured currency.

    Falls back to the literal (``EUR``) when no currency is configured, so
    existing setups keep their units unchanged.
    """
    if unit and "EUR" in unit and hass is not None:
        currency = hass.config.currency
        if currency:
            return unit.replace("EUR", currency)
    return unit


def _retired_ledger_sum(config_entry: ConfigEntry, per_adapter_key: str) -> float:
    """Sum the frozen contributions of retired adapters for a levelized key.

    A retired (removed end-of-life) adapter's final corrected accumulated total
    is persisted in ``config_entry.data[CONF_RETIRED_ADAPTERS]`` so that the
    combined total never drops when the device is removed.
    """
    total = 0.0
    for retired in config_entry.data.get(CONF_RETIRED_ADAPTERS, []):
        value = retired.get("totals", {}).get(per_adapter_key)
        if value is not None:
            total += value
    return total


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_entry(
        hass: HomeAssistant,
        entry: MyConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    power_insight = entry.runtime_data.power_insight
    if power_insight.grid_adapter is None:
        return
    options_wrapped = OptionsWrapper(entry.options)
    # Unique IDs of every sensor we create this run, used afterwards to disable
    # (and later re-enable) entities whose controlling option has been toggled.
    created_unique_ids: set[str] = set()

    def _add(entities: list, **kwargs) -> None:
        """Register a batch of entities and record their unique IDs."""
        created_unique_ids.update(ent.unique_id for ent in entities)
        async_add_entities(entities, **kwargs)

    # --- Hub-level sensors ---
    entities: list = []
    for description in POWER_INSIGHT_SENSORS:
        if not description.exists_fn(options_wrapped):
            continue
        if _option_gated_out(description, options_wrapped, SCOPE_COMBINED):
            continue
        entities.append(PowerInsightSensor(
            description=description,
            config_entry=entry,
            source_entities=description.entities_fn(power_insight),
            power_insight=power_insight,
        ))

    for description in POWER_INSIGHT_INTEGRATION_SENSORS:
        if not description.exists_fn(options_wrapped):
            continue
        if _option_gated_out(description, options_wrapped, SCOPE_COMBINED):
            continue
        entities.append(PowerInsightIntegrationSensor(
            description=description,
            config_entry=entry,
            source_entities=description.entities_fn(power_insight),
            power_insight=power_insight,
        ))

    # Combined accumulated levelized sensors are derived (summed from the
    # per-adapter base totals + retired-adapter ledger), not integrated.
    for description in POWER_INSIGHT_COMBINED_LEDGER_SENSORS:
        if not description.exists_fn(options_wrapped):
            continue
        if _option_gated_out(description, options_wrapped, SCOPE_COMBINED):
            continue
        entities.append(PowerInsightCombinedLedgerSensor(
            description=description,
            config_entry=entry,
            source_entities=description.entities_fn(power_insight),
            power_insight=power_insight,
        ))

    _add(entities)

    # --- Grid adapter sensors ---
    grid_adapter = power_insight.grid_adapter
    entities = []
    for description in POWER_INSIGHT_GRID_ADAPTER_SENSORS:
        if not description.exists_fn(options_wrapped):
            continue
        if _option_gated_out(description, options_wrapped, "grid"):
            continue
        entities.append(PowerInsightAdapterSensor(
            description=description,
            config_entry=entry,
            source_entities=description.entities_fn(power_insight),
            power_insight=power_insight,
            device_adapter=grid_adapter,
        ))

    for description in POWER_INSIGHT_GRID_ADAPTER_INTEGRATION_SENSORS:
        if not description.exists_fn(options_wrapped):
            continue
        if _option_gated_out(description, options_wrapped, "grid"):
            continue
        entities.append(PowerInsightAdapterIntegrationSensor(
            description=description,
            config_entry=entry,
            source_entities=description.entities_fn(power_insight),
            power_insight=power_insight,
            device_adapter=grid_adapter,
        ))

    _add(entities, config_subentry_id=grid_adapter.uid)

    # --- PV adapter sensors ---
    for adapter in power_insight.pv_system_adapters:
        entities = []
        for description in POWER_INSIGHT_PV_ADAPTER_SENSORS:
            if not description.exists_fn(adapter):
                continue
            if _option_gated_out(description, options_wrapped, "pv_system"):
                continue
            entities.append(PowerInsightAdapterSensor(
                description=description,
                config_entry=entry,
                source_entities=description.entities_fn(power_insight),
                power_insight=power_insight,
                device_adapter=adapter,
            ))

        for description in POWER_INSIGHT_PV_ADAPTER_INTEGRATION_SENSORS:
            if not description.exists_fn(adapter):
                continue
            if _option_gated_out(description, options_wrapped, "pv_system"):
                continue
            entities.append(PowerInsightAdapterIntegrationSensor(
                description=description,
                config_entry=entry,
                source_entities=description.entities_fn(power_insight),
                power_insight=power_insight,
                device_adapter=adapter,
            ))

        _add(entities, config_subentry_id=adapter.uid)

    # --- Battery adapter sensors ---
    for adapter in power_insight.storage_adapters:
        entities = []

        for description in POWER_INSIGHT_STORAGE_ADAPTER_SENSORS:
            if not description.exists_fn(adapter):
                continue
            if _option_gated_out(description, options_wrapped, "battery"):
                continue
            entities.append(PowerInsightAdapterSensor(
                description=description,
                config_entry=entry,
                source_entities=description.entities_fn(power_insight),
                power_insight=power_insight,
                device_adapter=adapter,
            ))

        for description in POWER_INSIGHT_STORAGE_ADAPTER_INTEGRATION_SENSORS:
            if not description.exists_fn(adapter):
                continue
            if _option_gated_out(description, options_wrapped, "battery"):
                continue
            entities.append(PowerInsightAdapterIntegrationSensor(
                description=description,
                config_entry=entry,
                source_entities=description.entities_fn(power_insight),
                power_insight=power_insight,
                device_adapter=adapter,
            ))

        # Dynamic charging source share sensors — one per power-providing
        # adapter the battery is actually configured to charge from. A source
        # the user did not select under "Charge From" gets no sensor (e.g. no
        # "Charging share from Grid" when the battery cannot charge from grid).
        # These are power-share sensors, so gate them on that option too.
        if options_wrapped.check(CONF_ENABLE_CHARGING_SOURCE_SHARES, "battery"):
            for source_adapter in power_insight.gross_power_adapters:
                if source_adapter.uid not in adapter.charge_from_adapters:
                    continue
                name = source_adapter.verbose_name
                dynamic_description = PowerInsightSensorDescription(
                    key=f"charging_share_from_{name}",
                    name=f"Charging share from {name}",
                    icon="mdi:percent",
                    native_unit_of_measurement=PERCENTAGE,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=0,
                    entities_fn=lambda obj: obj.source_entities_power,
                    value_fn=lambda obj: obj.storage_adapters_charging_source_shares,
                    transform_fn=lambda val: val * 100,
                )
                entities.append(PowerInsightDynamicAdapterSensor(
                    description=dynamic_description,
                    config_entry=entry,
                    source_entities=dynamic_description.entities_fn(power_insight),
                    power_insight=power_insight,
                    device_adapter=adapter,
                    dynamic_adapter=source_adapter,
                ))

        _add(entities, config_subentry_id=adapter.uid)

    # --- Consumer adapter sensors ---
    for adapter in power_insight.consumer_adapters:
        entities = []

        for description in POWER_INSIGHT_CONS_ADAPTER_SENSORS:
            if not description.exists_fn(adapter):
                continue
            if _option_gated_out(description, options_wrapped, "consumer"):
                continue
            entities.append(PowerInsightAdapterSensor(
                description=description,
                config_entry=entry,
                source_entities=description.entities_fn(power_insight),
                power_insight=power_insight,
                device_adapter=adapter,
            ))

        for description in POWER_INSIGHT_CONS_ADAPTER_INTEGRATION_SENSORS:
            if not description.exists_fn(adapter):
                continue
            if _option_gated_out(description, options_wrapped, "consumer"):
                continue
            entities.append(PowerInsightAdapterIntegrationSensor(
                description=description,
                config_entry=entry,
                source_entities=description.entities_fn(power_insight),
                power_insight=power_insight,
                device_adapter=adapter,
            ))

        # Dynamic consumption source share sensors — one per power-providing
        # adapter. These are power-share sensors, so gate them on that option.
        if options_wrapped.check(CONF_ENABLE_POWER_SOURCE_SHARES, "consumer"):
            for source_adapter in power_insight.gross_power_adapters:
                name = source_adapter.verbose_name
                dynamic_description = PowerInsightSensorDescription(
                    key=f"{name}_ratio",
                    name=f"{name} ratio",
                    icon="mdi:percent",
                    native_unit_of_measurement=PERCENTAGE,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=0,
                    entities_fn=lambda obj: obj.source_entities_power,
                    value_fn=lambda obj: obj.cons_adapters_source_shares,
                    transform_fn=lambda val: val * 100,
                )
                entities.append(PowerInsightDynamicAdapterSensor(
                    description=dynamic_description,
                    config_entry=entry,
                    source_entities=dynamic_description.entities_fn(power_insight),
                    power_insight=power_insight,
                    device_adapter=adapter,
                    dynamic_adapter=source_adapter,
                ))

        _add(entities, config_subentry_id=adapter.uid)

    # Disable entities whose controlling option is now off (keeping their
    # history), and re-enable any we previously disabled that are wanted again.
    _sync_entity_enabled_state(hass, entry, created_unique_ids)

    # Register the ``set_value`` service as a platform entity service. HA
    # resolves the target entity itself; only integration (accumulation)
    # sensors implement ``async_set_value``, so seeding a running total is
    # scoped to those entities automatically.
    entity_platform.async_get_current_platform().async_register_entity_service(
        "set_value",
        {vol.Required("value"): vol.Coerce(float)},
        "async_set_value",
    )


# ---------------------------------------------------------------------------
# Sensor entity classes
# ---------------------------------------------------------------------------


class BasePowerInsightSensor(BaseEventSensorEntity):
    """Base sensor entity."""

    entity_description: PowerInsightSensorDescription

    _attr_has_entity_name = True

    def __init__(
            self,
            description: PowerInsightSensorDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
    ) -> None:
        """Initialize the base sensor entity."""
        super().__init__(source_entities, power_insight)
        self.entity_description = description
        self.config_entry = config_entry

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Substitute the HA-configured currency for the EUR placeholder."""
        return _resolve_currency_unit(
            self.entity_description.native_unit_of_measurement, self.hass
        )


class PowerInsightSensor(BasePowerInsightSensor):
    """Hub-level sensor reading directly from PowerInsight."""

    def __init__(
            self,
            description: PowerInsightSensorDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
    ) -> None:
        """Initialize sensor entity."""
        super().__init__(description, config_entry, source_entities, power_insight)
        self._attr_unique_id = (
            f"{self.config_entry.entry_id}_{self.entity_description.key}"
        )
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name=self.config_entry.title or "PowerInsight",
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        value = self.entity_description.value_fn(self.power_insight)
        if value is not None:
            value = self.entity_description.transform_fn(value)
        return value


class PowerInsightCombinedLedgerSensor(PowerInsightSensor):
    """Combined accumulated levelized sensor derived from per-adapter totals.

    Recomputes on every source event as the sum of the active per-adapter base
    accumulated totals (each already scaled by its adapter's correction factor
    for display) plus the frozen contributions of removed end-of-life adapters.
    It stores no running total itself, so there is no reload double-count, and
    a lifetime-value correction is reflected retroactively and consistently in
    both the per-adapter and the combined totals.
    """

    def __init__(
            self,
            description: PowerInsightSensorDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
    ) -> None:
        """Initialize the combined ledger sensor."""
        super().__init__(description, config_entry, source_entities, power_insight)
        self._per_adapter_key = COMBINED_LEDGER_ADAPTER_KEYS[description.key]

    @property
    def native_value(self) -> float | None:
        """Return the summed per-adapter totals plus the retired ledger."""
        ent_reg = er.async_get(self.hass)
        total = 0.0
        for uid in self.power_insight.levelized_correction_factors:
            unique_id = (
                f"{self.config_entry.entry_id}_{uid}_{self._per_adapter_key}"
            )
            entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id is None:
                continue
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable"):
                continue
            try:
                total += float(state.state)
            except (ValueError, TypeError):
                continue

        total += _retired_ledger_sum(self.config_entry, self._per_adapter_key)
        return total


class PowerInsightAdapterSensor(BasePowerInsightSensor):
    """Per-adapter sensor that extracts its value from a uid-keyed dict."""

    def __init__(
            self,
            description: PowerInsightSensorDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
            device_adapter: AbstractBaseAdapter,
    ) -> None:
        """Initialize adapter sensor entity."""
        super().__init__(description, config_entry, source_entities, power_insight)
        self.device_adapter = device_adapter

        uid = f"{self.config_entry.entry_id}_{self.device_adapter.uid}"
        self._attr_unique_id = f"{uid}_{self.entity_description.key}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.device_adapter.uid)},
            name=f"{self.config_entry.title} {self.device_adapter.verbose_name}",
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        value = self.entity_description.value_fn(self.power_insight)
        value = get_value(self.device_adapter.uid, value)
        if value is not None:
            value = self.entity_description.transform_fn(value)
            if self.entity_description.apply_correction_factor:
                value = value * self.device_adapter.correction_factor
        return value


class PowerInsightDynamicAdapterSensor(BasePowerInsightSensor):
    """Per-adapter sensor that extracts its value from a nested uid-keyed dict.

    Used for sensors where the result depends on two adapters:
    ``value_fn`` returns ``{device_adapter_uid: {dynamic_adapter_uid: value}}``.
    """

    def __init__(
            self,
            description: PowerInsightSensorDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
            device_adapter: AbstractBaseAdapter,
            dynamic_adapter: AbstractBaseAdapter,
    ) -> None:
        """Initialize dynamic adapter sensor entity."""
        super().__init__(description, config_entry, source_entities, power_insight)
        self.device_adapter = device_adapter
        self.dynamic_adapter = dynamic_adapter

        uid = f"{self.config_entry.entry_id}_{self.device_adapter.uid}"
        self._attr_unique_id = f"{uid}_{self.entity_description.key}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.device_adapter.uid)},
            name=f"{self.config_entry.title} {self.device_adapter.verbose_name}",
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        value = self.entity_description.value_fn(self.power_insight)
        value = get_value(self.device_adapter.uid, value)
        value = get_value(self.dynamic_adapter.uid, value)
        if value is not None:
            value = self.entity_description.transform_fn(value)
        return value


# ---------------------------------------------------------------------------
# Integration sensor entity classes
# ---------------------------------------------------------------------------


class BasePowerInsightIntegrationSensor(BaseEventIntegrationSensorEntity):
    """Base integration sensor entity."""

    entity_description: PowerInsightIntegrationSensorDescription

    _attr_has_entity_name = True

    def __init__(
            self,
            description: PowerInsightIntegrationSensorDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
    ) -> None:
        """Initialize the base integration sensor entity."""
        super().__init__(source_entities, power_insight)
        self.entity_description = description
        self.config_entry = config_entry

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Substitute the HA-configured currency for the EUR placeholder."""
        return _resolve_currency_unit(
            self.entity_description.native_unit_of_measurement, self.hass
        )


class PowerInsightIntegrationSensor(BasePowerInsightIntegrationSensor):
    """Hub-level integration sensor."""

    def __init__(
            self,
            description: PowerInsightIntegrationSensorDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
    ) -> None:
        """Initialize the integration sensor entity."""
        super().__init__(description, config_entry, source_entities, power_insight)
        self._attr_unique_id = (
            f"{self.config_entry.entry_id}_{self.entity_description.key}"
        )
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name=self.config_entry.title or "PowerInsight",
        )

    @property
    def integration_value(self) -> float | None:
        """Return the current rate value to integrate."""
        value = self.entity_description.integration_value_fn(self.power_insight)
        if value is not None:
            value = self.entity_description.transform_fn(value)
        return value


class PowerInsightAdapterIntegrationSensor(BasePowerInsightIntegrationSensor):
    """Per-adapter integration sensor that extracts its value from a uid-keyed dict."""

    def __init__(
            self,
            description: PowerInsightIntegrationSensorDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
            device_adapter: AbstractBaseAdapter,
    ) -> None:
        """Initialize the adapter integration sensor entity."""
        super().__init__(description, config_entry, source_entities, power_insight)
        self.device_adapter = device_adapter

        uid = f"{self.config_entry.entry_id}_{self.device_adapter.uid}"
        self._attr_unique_id = f"{uid}_{self.entity_description.key}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.device_adapter.uid)},
            name=f"{self.config_entry.title} {self.device_adapter.verbose_name}",
        )

    @property
    def integration_value(self) -> float | None:
        """Return the current (base) rate value to integrate.

        The correction factor is deliberately NOT applied here — the running
        total accumulates the base rate so that the factor can be applied to
        the displayed total retroactively.
        """
        value = self.entity_description.integration_value_fn(self.power_insight)
        value = get_value(self.device_adapter.uid, value)
        if value is not None:
            value = self.entity_description.transform_fn(value)
        return value

    @property
    def native_value(self) -> Decimal | None:
        """Return the accumulated base total, scaled for display if requested."""
        base = self._state
        if base is not None and self.entity_description.apply_correction_factor:
            return base * Decimal(str(self.device_adapter.correction_factor))
        return base

    @property
    def extra_restore_state_data(self) -> IntegrationSensorExtraStoredData:
        """Persist the BASE running total (not the corrected display)."""
        return IntegrationSensorExtraStoredData(
            self._state,
            self.native_unit_of_measurement,
            self._last_valid_state,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Freeze this levelized total into the ledger on device removal.

        HA core never calls a component-level subentry-removal hook, and it
        clears the removed subentry's entities synchronously before any reload
        runs — so the only reliable place to capture a removed device's final
        accumulated total is here, in its own teardown. We distinguish a genuine
        device removal (the subentry is gone from the config entry) from an
        ordinary reload (the subentry still exists), and only snapshot the former.
        """
        await super().async_will_remove_from_hass()

        key = self.entity_description.key
        if (
            not self.entity_description.apply_correction_factor
            or key not in LEVELIZED_TOTAL_KEYS
        ):
            return

        uid = self.device_adapter.uid
        # Subentry still present -> this is a reload/unload, not a removal.
        if uid in self.config_entry.subentries:
            return

        value = self.native_value  # corrected (base * factor) total
        if value is None:
            return

        ledger = list(self.config_entry.data.get(CONF_RETIRED_ADAPTERS, []))
        # Idempotent: skip if this (device, key) was already captured.
        if any(
            entry.get("subentry_id") == uid and key in entry.get("totals", {})
            for entry in ledger
        ):
            return

        ledger.append(
            {
                "subentry_id": uid,
                "title": self.device_adapter.verbose_name,
                "totals": {key: float(value)},
            }
        )
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_RETIRED_ADAPTERS: ledger},
        )
