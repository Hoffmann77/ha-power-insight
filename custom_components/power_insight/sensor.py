"""Sensor entities for the PowerInsight integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)

from .entity import (
    BaseEventSensorEntity,
    BaseEventIntegrationSensorEntity,
    IntegrationSensorExtraStoredData,
)
from .utils import get_value
from .retired_sources import record_retired_source, retired_source_totals
from .history_store import (
    ATTR_TRACKED,
    DeviceHistory,
    device_carried_over,
    summed_carried_over,
)
from .power_insight import (
    PowerInsight,
    AbstractBaseAdapter,
    BaseProductionAdapter,
    UNIT_PREFIXES,
)
from . import MyConfigEntry
from .const import (
    DOMAIN,
    SCOPE_COMBINED,
    CONF_ENABLE_DEBUG_ENTITIES,
    CONF_ENABLE_DISTRIBUTION_POWER,
    CONF_ENABLE_DISTRIBUTION_RATIOS,
    CONF_ENABLE_DISTRIBUTION_SHARES,
    CONF_ENABLE_HOME_BASE_LOAD,
    CONF_ENABLE_CHARGING_SOURCE_SHARES,
    CONF_ENABLE_POWER_SOURCE_SHARES,
    CONF_ENABLE_POWER_SOURCE_POWER,
    CONF_ACCUMULATE_POWER_SOURCE_ENERGY,
    CONF_ENABLE_ENERGY_SOURCE_SHARES,
    CONF_ENABLE_EXPORT_COMPENSATION_RATE,
    CONF_ACCUMULATE_EXPORT_COMPENSATION,
    CONF_CALCULATE_COST_RATES,
    CONF_CALCULATE_LEVELIZED_COST_RATES,
    CONF_CALCULATE_COST_SAVING_RATES,
    CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
    CONF_CALCULATE_FINANCIAL_RETURN_RATE,
    CONF_CALCULATE_LEVELIZED_FINANCIAL_RETURN_RATE,
    CONF_ACCUMULATE_COST_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_RATES,
    CONF_ACCUMULATE_COST_SAVING_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
    CONF_ACCUMULATE_FINANCIAL_RETURN,
    CONF_ACCUMULATE_LEVELIZED_FINANCIAL_RETURN,
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
    # Optional uid-keyed dict of extra state attributes for a per-adapter
    # sensor, published alongside the value.
    attributes_fn: Callable[[PowerInsight], dict[str, float]] | None = None
    # When True, a per-adapter sensor scales its displayed value by the
    # adapter's correction factor (levelized quantities only).
    apply_correction_factor: bool = False
    # When True, the sensor is only created when its provider device is a
    # configured charge source for at least one battery (charging channel).
    # exists_fn cannot express this — it has no reference to the battery set —
    # so it is checked inline in async_setup_entry.
    charge_gated: bool = False
    # When True, the sensor is only created when every production adapter (PV +
    # battery) has lifetime cost data (lcoe) configured.  exists_fn cannot
    # express this — it has no reference to the adapter set — so it is checked
    # inline in async_setup_entry.
    lcoe_gated: bool = False


@dataclass(frozen=True, kw_only=True)
class PowerInsightIntegrationSensorDescription(SensorEntityDescription):
    """Provide a description of a PowerInsight integration sensor."""

    entities_fn: Callable[[PowerInsight], list[str]]
    exists_fn: Callable[..., bool] = lambda _: True
    integration_value_fn: Callable[[PowerInsight], dict[str, float | None] | float | None]
    # Splits integration_value_fn by which adapter's correction factor scales
    # each part, so the accumulated total can be re-corrected exactly. Without
    # it the total is corrected by the owning adapter's factor alone, which is
    # only right when the rate depends on that adapter's price and no other.
    integration_components_fn: Callable[
        [PowerInsight], dict[str, dict[str, float] | None]
    ] | None = None
    transform_fn: Callable[[float], float] = lambda value: value
    # When True, the per-adapter integration sensor accumulates the base rate
    # but displays the running total corrected for edited lifetime costs.
    apply_correction_factor: bool = False
    # SI prefix of the accumulated unit relative to the rate's: "k" turns a
    # rate in W into a total in kWh. None keeps EUR/h -> EUR.
    unit_prefix: str | None = None
    # The total of history.py this sensor carries over from the devices' apps.
    # A per-device sensor adds its own device's; a whole-home one (combined,
    # or the grid's) adds every device's, removed devices included.
    history_key: str | None = None
    # A consumer's per-source total that outlives its source: when the source
    # is removed, the total is frozen into the source ledger under this key
    # (see retired_sources.py) rather than vanishing with its sensor.
    retired_source_key: str | None = None


# ---------------------------------------------------------------------------
# Hub-level sensors
# ---------------------------------------------------------------------------

POWER_INSIGHT_SENSORS = (
    PowerInsightSensorDescription(
        key="available_power",
        translation_key="available_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.gross_power,
    ),
    PowerInsightSensorDescription(
        # How much more the metered sinks drew than the sources supplied. The
        # engine balances the readings by meeting in the middle; this is the
        # gap it closed. Persistently large means a misconfigured meter.
        key="metering_imbalance",
        translation_key="metering_imbalance",
        icon="mdi:scale-unbalanced",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.metering_imbalance,
    ),
    PowerInsightSensorDescription(
        key="combined_export_ratio",
        translation_key="export_ratio",
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
        translation_key="home_consumption_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.combined_consumption,
    ),
    PowerInsightSensorDescription(
        key="combined_self_consumption_ratio",
        translation_key="home_consumption_ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.gross_power_consumption_ratio,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="combined_financial_return_rate",
        translation_key="financial_return_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_financial_return_rate,
    ),
    PowerInsightSensorDescription(
        key="combined_levelized_financial_return_rate",
        translation_key="levelized_financial_return_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_levelized_financial_return_rate_corrected,
        lcoe_gated=True,
    ),
    PowerInsightSensorDescription(
        key="combined_charging_power",
        translation_key="battery_charging_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.combined_charging_power,
    ),
    PowerInsightSensorDescription(
        key="combined_standby_power",
        translation_key="system_standby_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.combined_standby_power,
    ),
    PowerInsightSensorDescription(
        key="combined_charging_ratio",
        translation_key="battery_charging_ratio",
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
        translation_key="system_standby_ratio",
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
        translation_key="price_of_electricity",
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
        translation_key="levelized_price_of_electricity",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_lcoe,
        lcoe_gated=True,
    ),
    PowerInsightSensorDescription(
        key="combined_cost_rate",
        translation_key="cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.combined_coe_rate,
    ),
    PowerInsightSensorDescription(
        key="combined_levelized_cost_rate",
        translation_key="levelized_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.combined_lcoe_rate_corrected,
        lcoe_gated=True,
    ),
    PowerInsightSensorDescription(
        key="combined_charging_cost_rate",
        translation_key="charging_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_charging_cost_rate,
    ),
    PowerInsightSensorDescription(
        key="combined_levelized_charging_cost_rate",
        translation_key="levelized_charging_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_lcoo_rate_corrected,
        lcoe_gated=True,
    ),
    PowerInsightSensorDescription(
        key="combined_device_operating_cost_rate",
        translation_key="device_operating_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_device_operating_cost_rate,
    ),
    PowerInsightSensorDescription(
        key="combined_levelized_device_operating_cost_rate",
        translation_key="levelized_device_operating_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_levelized_device_operating_cost_rate_corrected,
        lcoe_gated=True,
    ),
    PowerInsightSensorDescription(
        key="combined_consumption_cost_rate",
        translation_key="consumption_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_consumption_cost_rate,
    ),
    PowerInsightSensorDescription(
        key="combined_levelized_consumption_cost_rate",
        translation_key="levelized_consumption_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_levelized_consumption_cost_rate,
        lcoe_gated=True,
    ),
    PowerInsightSensorDescription(
        key="combined_standby_cost_rate",
        translation_key="levelized_system_standby_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_levelized_standby_cost_rate,
        lcoe_gated=True,
    ),
    PowerInsightSensorDescription(
        key="combined_export_cost_rate",
        translation_key="levelized_export_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_levelized_export_cost_rate,
        lcoe_gated=True,
    ),
    PowerInsightSensorDescription(
        key="combined_cost_savings_rate",
        translation_key="cost_savings_rate",
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
        translation_key="levelized_cost_savings_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.combined_levelized_saving_rate_corrected,
        lcoe_gated=True,
    ),
)

# ---------------------------------------------------------------------------
# Home base load
#
# Everything consumed without a sensor on it. It already competes for power in
# the provenance solve, and in most homes it is the single largest consumer —
# so leaving it out of the results makes the per-device figures fail to add up
# to the totals. It has no config subentry: the device is synthesised here.
# ---------------------------------------------------------------------------

POWER_INSIGHT_HOME_BASE_LOAD_SENSORS = (
    PowerInsightSensorDescription(
        key="home_base_load_power",
        translation_key="power",
        icon="mdi:home-lightning-bolt-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.home_base_load_power,
        attributes_fn=lambda obj: obj.home_base_load_source_shares,
    ),
    PowerInsightSensorDescription(
        key="home_base_load_avoided_cost_rate",
        translation_key="avoided_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.home_base_load_avoided_cost_rate,
    ),
)


POWER_INSIGHT_INTEGRATION_SENSORS = (
    PowerInsightIntegrationSensorDescription(
        key="combined_total_charging_cost",
        history_key="total_operating_cost",
        translation_key="total_charging_cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.combined_charging_cost_rate,
    ),
    PowerInsightIntegrationSensorDescription(
        key="combined_total_consumption_cost",
        translation_key="total_consumption_cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.combined_consumption_cost_rate,
    ),
    PowerInsightIntegrationSensorDescription(
        key="combined_total_financial_return",
        history_key="total_financial_return",
        translation_key="total_financial_return",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.combined_financial_return_rate,
    ),
    PowerInsightIntegrationSensorDescription(
        key="combined_total_cost_savings",
        history_key="total_cost_savings",
        translation_key="total_cost_savings",
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
    "combined_total_levelized_device_operating_cost": "total_levelized_operating_cost",
    "combined_total_levelized_cost_savings": "total_levelized_cost_savings",
    "combined_total_levelized_financial_return": "total_levelized_financial_return",
}

# Per-adapter accumulated keys whose final corrected value is frozen into the
# retired-adapter ledger when a device is removed.
LEVELIZED_TOTAL_KEYS = frozenset(COMBINED_LEDGER_ADAPTER_KEYS.values())

POWER_INSIGHT_COMBINED_LEDGER_SENSORS = (
    PowerInsightSensorDescription(
        key="combined_total_levelized_device_operating_cost",
        translation_key="total_levelized_device_operating_cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: None,
        lcoe_gated=True,
    ),
    PowerInsightSensorDescription(
        key="combined_total_levelized_cost_savings",
        translation_key="total_levelized_cost_savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: None,
        lcoe_gated=True,
    ),
    PowerInsightSensorDescription(
        key="combined_total_levelized_financial_return",
        translation_key="total_levelized_financial_return",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: None,
        lcoe_gated=True,
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
        translation_key="import_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: {obj.grid_adapter.uid: obj.combined_grid_import},
    ),
    PowerInsightSensorDescription(
        key="export_power",
        translation_key="export_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: {obj.grid_adapter.uid: obj.combined_grid_export},
    ),
    PowerInsightSensorDescription(
        key="import_cost_rate",
        translation_key="import_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_price + obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_coe_rate,
    ),
    PowerInsightSensorDescription(
        key="export_compensation_rate",
        translation_key="export_compensation_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_price + obj.source_entities_power,
        value_fn=lambda obj: {obj.grid_adapter.uid: obj.combined_export_compensation_rate},
    ),
    PowerInsightSensorDescription(
        key="consumption_ratio",
        translation_key="import_to_home_consumption_ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_consumption_ratios,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="consumption_share",
        translation_key="share_of_home_consumption",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_consumption_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="consumption_power",
        translation_key="import_to_home_consumption",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_consumption_power,
    ),
    PowerInsightSensorDescription(
        key="charging_ratio",
        translation_key="import_to_batteries_ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_charging_ratios,
        transform_fn=lambda val: val * 100,
        charge_gated=True,
    ),
    PowerInsightSensorDescription(
        key="charging_share",
        translation_key="share_of_battery_charging",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_charging_shares,
        transform_fn=lambda val: val * 100,
        charge_gated=True,
    ),
    PowerInsightSensorDescription(
        key="charging_power",
        translation_key="import_to_batteries",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_charging_power,
        charge_gated=True,
    ),
    PowerInsightSensorDescription(
        key="standby_ratio",
        translation_key="import_to_system_standby_ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_standby_ratios,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="standby_share",
        translation_key="share_of_system_standby",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_standby_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="standby_power",
        translation_key="import_to_system_standby",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_standby_power,
    ),
)

POWER_INSIGHT_GRID_ADAPTER_INTEGRATION_SENSORS = (
    PowerInsightIntegrationSensorDescription(
        key="total_import_cost",
        translation_key="total_import_cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_price + obj.source_entities_power,
        integration_value_fn=lambda obj: obj.source_adapters_coe_rate,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_export_compensation",
        history_key="total_export_compensation",
        translation_key="total_export_compensation",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_price + obj.source_entities_power,
        integration_value_fn=lambda obj: {obj.grid_adapter.uid: obj.combined_export_compensation_rate},
    ),
)


# ---------------------------------------------------------------------------
# PV adapter sensors
# ---------------------------------------------------------------------------

POWER_INSIGHT_PV_ADAPTER_SENSORS = (
    PowerInsightSensorDescription(
        key="export_power",
        translation_key="production_to_grid",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.source_adapters_export_power,
    ),
    PowerInsightSensorDescription(
        key="export_ratio",
        translation_key="production_to_grid_ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.source_adapters_export_ratios,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="export_share",
        translation_key="share_of_grid_export",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.source_adapters_export_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="export_compensation_rate",
        translation_key="export_compensation_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.source_adapters_export_compensation_rates,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_power",
        translation_key="production_to_home_consumption",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_consumption_power,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_ratio",
        translation_key="production_to_home_consumption_ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_consumption_ratios,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_share",
        translation_key="share_of_home_consumption",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_consumption_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="charging_ratio",
        translation_key="production_to_batteries_ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_charging_ratios,
        transform_fn=lambda val: val * 100,
        charge_gated=True,
    ),
    PowerInsightSensorDescription(
        key="charging_share",
        translation_key="share_of_battery_charging",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_charging_shares,
        transform_fn=lambda val: val * 100,
        charge_gated=True,
    ),
    PowerInsightSensorDescription(
        key="charging_power",
        translation_key="production_to_batteries",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_charging_power,
        charge_gated=True,
    ),
    PowerInsightSensorDescription(
        key="standby_ratio",
        translation_key="production_to_system_standby_ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_standby_ratios,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="standby_share",
        translation_key="share_of_system_standby",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_standby_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="standby_power",
        translation_key="production_to_system_standby",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_standby_power,
    ),
    PowerInsightSensorDescription(
        key="financial_return_rate",
        translation_key="financial_return_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.adapters_financial_return_rates,
    ),
    PowerInsightSensorDescription(
        key="levelized_financial_return_rate",
        translation_key="levelized_financial_return_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        value_fn=lambda obj: obj.adapters_levelized_financial_return_rates_corrected,
    ),
    PowerInsightSensorDescription(
        key="operating_cost_rate",
        translation_key="operating_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.source_adapters_coo_rates,
    ),
    PowerInsightSensorDescription(
        key="levelized_operating_cost_rate",
        translation_key="levelized_operating_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        value_fn=lambda obj: obj.source_adapters_lcoo_rates_corrected,
    ),
    PowerInsightSensorDescription(
        # The gross figure behind the saving: what this device kept off the
        # grid bill, before its own draw is taken off. The consumers' avoided
        # costs are the same euros from the other end — never add the two.
        key="avoided_cost_rate",
        translation_key="avoided_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.source_adapters_avoided_cost_rates,
    ),
    PowerInsightSensorDescription(
        key="cost_savings_rate",
        translation_key="cost_savings_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.adapters_saving_rates,
    ),
    PowerInsightSensorDescription(
        key="levelized_cost_savings_rate",
        translation_key="levelized_cost_savings_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        value_fn=lambda obj: obj.adapters_levelized_saving_rates_corrected,
    ),
)

POWER_INSIGHT_PV_ADAPTER_INTEGRATION_SENSORS = (
    PowerInsightIntegrationSensorDescription(
        key="total_export_compensation",
        history_key="total_export_compensation",
        translation_key="total_export_compensation",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.exports_power,
        integration_value_fn=lambda obj: obj.source_adapters_export_compensation_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_operating_cost",
        translation_key="total_operating_cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.source_adapters_coo_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_levelized_operating_cost",
        translation_key="total_levelized_operating_cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        integration_value_fn=lambda obj: obj.source_adapters_lcoo_rates,
        integration_components_fn=lambda obj: obj.source_adapters_lcoo_rate_components,
        apply_correction_factor=True,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_avoided_cost",
        history_key="total_avoided_cost",
        translation_key="total_avoided_cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.source_adapters_avoided_cost_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_cost_savings",
        history_key="total_cost_savings",
        translation_key="total_cost_savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.adapters_saving_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_levelized_cost_savings",
        history_key="total_levelized_cost_savings",
        translation_key="total_levelized_cost_savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        integration_value_fn=lambda obj: obj.adapters_levelized_saving_rates,
        integration_components_fn=lambda obj: obj.adapters_levelized_saving_rate_components,
        apply_correction_factor=True,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_financial_return",
        history_key="total_financial_return",
        translation_key="total_financial_return",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.adapters_financial_return_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_levelized_financial_return",
        history_key="total_levelized_financial_return",
        translation_key="total_levelized_financial_return",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        integration_value_fn=lambda obj: obj.adapters_levelized_financial_return_rates,
        integration_components_fn=lambda obj: obj.adapters_levelized_financial_return_rate_components,
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
        translation_key="discharge_to_grid",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.source_adapters_export_power,
    ),
    PowerInsightSensorDescription(
        key="export_ratio",
        translation_key="discharge_to_grid_ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.source_adapters_export_ratios,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="export_share",
        translation_key="share_of_grid_export",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.source_adapters_export_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="export_compensation_rate",
        translation_key="export_compensation_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.source_adapters_export_compensation_rates,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_power",
        translation_key="discharge_to_home_consumption",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_consumption_power,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_ratio",
        translation_key="discharge_to_home_consumption_ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_consumption_ratios,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_share",
        translation_key="share_of_home_consumption",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_consumption_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="charging_ratio",
        translation_key="discharge_to_batteries_ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_charging_ratios,
        transform_fn=lambda val: val * 100,
        charge_gated=True,
    ),
    PowerInsightSensorDescription(
        key="charging_share",
        translation_key="share_of_battery_charging",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_charging_shares,
        transform_fn=lambda val: val * 100,
        charge_gated=True,
    ),
    PowerInsightSensorDescription(
        key="charging_power",
        translation_key="discharge_to_batteries",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_charging_power,
        charge_gated=True,
    ),
    PowerInsightSensorDescription(
        key="standby_ratio",
        translation_key="discharge_to_system_standby_ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_standby_ratios,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="standby_share",
        translation_key="share_of_system_standby",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_standby_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="standby_power",
        translation_key="discharge_to_system_standby",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.source_adapters_standby_power,
    ),
    PowerInsightSensorDescription(
        key="financial_return_rate",
        translation_key="financial_return_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.adapters_financial_return_rates,
    ),
    PowerInsightSensorDescription(
        key="levelized_financial_return_rate",
        translation_key="levelized_financial_return_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        value_fn=lambda obj: obj.adapters_levelized_financial_return_rates_corrected,
    ),
    PowerInsightSensorDescription(
        key="operating_cost_rate",
        translation_key="operating_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.source_adapters_coo_rates,
        attributes_fn=lambda obj: obj.sink_adapters_restriction_deficit,
    ),
    PowerInsightSensorDescription(
        key="levelized_operating_cost_rate",
        translation_key="levelized_operating_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        value_fn=lambda obj: obj.source_adapters_lcoo_rates_corrected,
        attributes_fn=lambda obj: obj.sink_adapters_restriction_deficit,
    ),
    PowerInsightSensorDescription(
        # The gross figure behind the saving: what this device kept off the
        # grid bill, before its own draw is taken off. The consumers' avoided
        # costs are the same euros from the other end — never add the two.
        key="avoided_cost_rate",
        translation_key="avoided_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.source_adapters_avoided_cost_rates,
    ),
    PowerInsightSensorDescription(
        key="cost_savings_rate",
        translation_key="cost_savings_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.adapters_saving_rates,
    ),
    PowerInsightSensorDescription(
        key="levelized_cost_savings_rate",
        translation_key="levelized_cost_savings_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        value_fn=lambda obj: obj.adapters_levelized_saving_rates_corrected,
    ),
)

POWER_INSIGHT_STORAGE_ADAPTER_INTEGRATION_SENSORS = (
    PowerInsightIntegrationSensorDescription(
        key="total_export_compensation",
        history_key="total_export_compensation",
        translation_key="total_export_compensation",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.exports_power,
        integration_value_fn=lambda obj: obj.source_adapters_export_compensation_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_operating_cost",
        history_key="total_operating_cost",
        translation_key="total_operating_cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.source_adapters_coo_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_levelized_operating_cost",
        history_key="total_levelized_operating_cost",
        translation_key="total_levelized_operating_cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        integration_value_fn=lambda obj: obj.source_adapters_lcoo_rates,
        integration_components_fn=lambda obj: obj.source_adapters_lcoo_rate_components,
        apply_correction_factor=True,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_avoided_cost",
        history_key="total_avoided_cost",
        translation_key="total_avoided_cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.source_adapters_avoided_cost_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_cost_savings",
        history_key="total_cost_savings",
        translation_key="total_cost_savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.adapters_saving_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_levelized_cost_savings",
        history_key="total_levelized_cost_savings",
        translation_key="total_levelized_cost_savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        integration_value_fn=lambda obj: obj.adapters_levelized_saving_rates,
        integration_components_fn=lambda obj: obj.adapters_levelized_saving_rate_components,
        apply_correction_factor=True,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_financial_return",
        history_key="total_financial_return",
        translation_key="total_financial_return",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.adapters_financial_return_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_levelized_financial_return",
        history_key="total_levelized_financial_return",
        translation_key="total_levelized_financial_return",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda adapter: adapter.lcoe is not None,
        integration_value_fn=lambda obj: obj.adapters_levelized_financial_return_rates,
        integration_components_fn=lambda obj: obj.adapters_levelized_financial_return_rate_components,
        apply_correction_factor=True,
    ),
)


# ---------------------------------------------------------------------------
# Consumer adapter sensors
# ---------------------------------------------------------------------------

POWER_INSIGHT_CONS_ADAPTER_SENSORS = (
    PowerInsightSensorDescription(
        key="consumption_share",
        translation_key="consumption_share",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.sink_adapters_consumption_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="operating_cost_rate",
        translation_key="operating_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.sink_adapters_coo_rates,
        attributes_fn=lambda obj: obj.sink_adapters_restriction_deficit,
    ),
    PowerInsightSensorDescription(
        key="levelized_operating_cost_rate",
        translation_key="levelized_operating_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.sink_adapters_lcoo_rates,
        attributes_fn=lambda obj: obj.sink_adapters_restriction_deficit,
    ),
    PowerInsightSensorDescription(
        key="avoided_cost_rate",
        translation_key="avoided_cost_rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.sink_adapters_avoided_cost_rates,
    ),
)

POWER_INSIGHT_CONS_ADAPTER_INTEGRATION_SENSORS = (
    PowerInsightIntegrationSensorDescription(
        key="total_operating_cost",
        translation_key="total_operating_cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.sink_adapters_coo_rates,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_levelized_operating_cost",
        translation_key="total_levelized_operating_cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.sink_adapters_lcoo_rates,
        # A consumer has no lifetime cost of its own, so the correction is
        # per *supplying* device: each accumulated component is scaled by the
        # factor of the source it came from.
        integration_components_fn=lambda obj: obj.sink_adapters_lcoo_rate_components,
        apply_correction_factor=True,
    ),
    PowerInsightIntegrationSensorDescription(
        key="total_avoided_cost",
        translation_key="total_avoided_cost",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        integration_value_fn=lambda obj: obj.sink_adapters_avoided_cost_rates,
    ),
)


# The key a consumer's "Energy from {source}" is frozen under in the source
# ledger when its source is removed.
RETIRED_ENERGY_FROM = "energy_from"

# What a consumer drew from sources that have since been removed. No state
# class: the value steps up once at each removal, and that step is energy
# already recorded in the old per-source sensor's history — long-term
# statistics would count it a second time, as if consumed in that hour.
ENERGY_FROM_REMOVED_DEVICES = SensorEntityDescription(
    key="energy_from_removed_devices",
    translation_key="energy_from_removed_devices",
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    device_class=SensorDeviceClass.ENERGY,
    suggested_display_precision=2,
)

# A consumer's lifetime energy mix, from its per-source energy totals.
ENERGY_SHARE_FROM = SensorEntityDescription(
    key="energy_share_from",
    translation_key="energy_share_from",
    icon="mdi:percent",
    native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=0,
)
ENERGY_SHARE_FROM_REMOVED_DEVICES = SensorEntityDescription(
    key="energy_share_from_removed_devices",
    translation_key="energy_share_from_removed_devices",
    icon="mdi:percent",
    native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=0,
)


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
    "metering_imbalance": CONF_ENABLE_DEBUG_ENTITIES,
    # --- Power distribution (W) ---
    "import_power": CONF_ENABLE_DISTRIBUTION_POWER,                # grid
    "export_power": CONF_ENABLE_DISTRIBUTION_POWER,                # grid / pv / storage
    "consumption_power": CONF_ENABLE_DISTRIBUTION_POWER,           # grid
    "self_consumption_power": CONF_ENABLE_DISTRIBUTION_POWER,      # pv / storage
    "charging_power": CONF_ENABLE_DISTRIBUTION_POWER,              # grid / pv / storage
    "standby_power": CONF_ENABLE_DISTRIBUTION_POWER,               # grid
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
    "charging_ratio": CONF_ENABLE_DISTRIBUTION_RATIOS,           # grid / pv / storage
    "standby_ratio": CONF_ENABLE_DISTRIBUTION_RATIOS,           # grid / pv / storage
    # --- Power distribution shares ---
    "consumption_share": CONF_ENABLE_DISTRIBUTION_SHARES,         # grid / consumer
    "export_share": CONF_ENABLE_DISTRIBUTION_SHARES,             # pv / storage
    "self_consumption_share": CONF_ENABLE_DISTRIBUTION_SHARES,
    "charging_share": CONF_ENABLE_DISTRIBUTION_SHARES,          # grid / pv / storage
    "standby_share": CONF_ENABLE_DISTRIBUTION_SHARES,          # grid / pv / storage
    # --- Export compensation ---
    "export_compensation_rate": CONF_ENABLE_EXPORT_COMPENSATION_RATE,
    "total_export_compensation": CONF_ACCUMULATE_EXPORT_COMPENSATION,
    # --- Cost rates ---
    "import_cost_rate": CONF_CALCULATE_COST_RATES,                # grid
    "operating_cost_rate": CONF_CALCULATE_COST_RATES,
    "combined_cost_rate": CONF_CALCULATE_COST_RATES,
    "home_base_load_power": CONF_ENABLE_HOME_BASE_LOAD,
    "home_base_load_avoided_cost_rate": CONF_ENABLE_HOME_BASE_LOAD,
    "combined_charging_cost_rate": CONF_CALCULATE_COST_RATES,
    "combined_device_operating_cost_rate": CONF_CALCULATE_COST_RATES,
    "combined_consumption_cost_rate": CONF_CALCULATE_COST_RATES,
    "combined_price_of_electricity": CONF_CALCULATE_COST_RATES,
    # --- Levelized cost rates ---
    "levelized_operating_cost_rate": CONF_CALCULATE_LEVELIZED_COST_RATES,
    "combined_levelized_price_of_electricity": CONF_CALCULATE_LEVELIZED_COST_RATES,
    "combined_levelized_cost_rate": CONF_CALCULATE_LEVELIZED_COST_RATES,
    "combined_levelized_charging_cost_rate": CONF_CALCULATE_LEVELIZED_COST_RATES,
    "combined_levelized_device_operating_cost_rate": CONF_CALCULATE_LEVELIZED_COST_RATES,
    "combined_levelized_consumption_cost_rate": CONF_CALCULATE_LEVELIZED_COST_RATES,
    "combined_standby_cost_rate": CONF_CALCULATE_LEVELIZED_COST_RATES,
    "combined_export_cost_rate": CONF_CALCULATE_LEVELIZED_COST_RATES,
    # --- Cost savings rates ---
    "avoided_cost_rate": CONF_CALCULATE_COST_SAVING_RATES,
    "cost_savings_rate": CONF_CALCULATE_COST_SAVING_RATES,
    "combined_cost_savings_rate": CONF_CALCULATE_COST_SAVING_RATES,
    # --- Levelized cost savings rates ---
    "levelized_cost_savings_rate": CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
    "combined_levelized_cost_savings_rate": CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,
    # --- Financial return rates ---
    "financial_return_rate": CONF_CALCULATE_FINANCIAL_RETURN_RATE,
    "combined_financial_return_rate": CONF_CALCULATE_FINANCIAL_RETURN_RATE,
    # --- Levelized financial return rates ---
    "levelized_financial_return_rate": CONF_CALCULATE_LEVELIZED_FINANCIAL_RETURN_RATE,
    "combined_levelized_financial_return_rate": CONF_CALCULATE_LEVELIZED_FINANCIAL_RETURN_RATE,
    # --- Accumulated costs ---
    "total_import_cost": CONF_ACCUMULATE_COST_RATES,              # grid
    "total_operating_cost": CONF_ACCUMULATE_COST_RATES,
    "combined_total_charging_cost": CONF_ACCUMULATE_COST_RATES,
    "combined_total_consumption_cost": CONF_ACCUMULATE_COST_RATES,
    "total_levelized_operating_cost": CONF_ACCUMULATE_LEVELIZED_COST_RATES,
    "combined_total_levelized_device_operating_cost": CONF_ACCUMULATE_LEVELIZED_COST_RATES,
    # --- Accumulated cost savings ---
    "total_avoided_cost": CONF_ACCUMULATE_COST_SAVING_RATES,        # pv / storage / consumer
    "total_cost_savings": CONF_ACCUMULATE_COST_SAVING_RATES,
    "combined_total_cost_savings": CONF_ACCUMULATE_COST_SAVING_RATES,
    "total_levelized_cost_savings": CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
    "combined_total_levelized_cost_savings": CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
    # --- Accumulated financial return ---
    "total_financial_return": CONF_ACCUMULATE_FINANCIAL_RETURN,
    "combined_total_financial_return": CONF_ACCUMULATE_FINANCIAL_RETURN,
    "total_levelized_financial_return": CONF_ACCUMULATE_LEVELIZED_FINANCIAL_RETURN,
    "combined_total_levelized_financial_return": CONF_ACCUMULATE_LEVELIZED_FINANCIAL_RETURN,
}


def _option_gated_out(description, options: OptionsWrapper, scope: str) -> bool:
    """Return True if *description* is gated off for *scope* by the options."""
    gate = _SENSOR_OPTION_GATE.get(description.key)
    return gate is not None and not options.check(gate, scope)


def _all_prod_adapters_have_lcoe(power_insight: PowerInsight) -> bool:
    """Return True if there is at least one prod adapter and all have lcoe configured."""
    adapters = power_insight.prod_adapters
    return bool(adapters) and all(a.lcoe is not None for a in adapters)


def _provider_is_charge_source(power_insight: PowerInsight, uid: str) -> bool:
    """Return True if any battery is configured to charge from this provider.

    Charging-channel sensors (``charge_gated``) are only meaningful for a
    provider that actually feeds a battery; otherwise they would always read
    0 %. This is checked in ``async_setup_entry`` rather than via ``exists_fn``
    because ``exists_fn`` receives only the OptionsWrapper (grid) or a single
    adapter (pv/battery) — neither can see the battery set.
    """
    return any(
        uid in battery.charge_from_adapters
        for battery in power_insight.storage_adapters
    )


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
    # Evaluated once; shared by the three loops below.
    _prod_lcoe_available = _all_prod_adapters_have_lcoe(power_insight)
    # Ledger sensors should also survive after all prod adapters are removed, as
    # long as their retired-adapter frozen totals are still stored on the entry.
    _has_retired_lcoe = bool(entry.data.get(CONF_RETIRED_ADAPTERS, []))
    for description in POWER_INSIGHT_SENSORS:
        if not description.exists_fn(options_wrapped):
            continue
        if _option_gated_out(description, options_wrapped, SCOPE_COMBINED):
            continue
        if description.lcoe_gated and not _prod_lcoe_available:
            continue
        entities.append(PowerInsightSensor(
            description=description,
            config_entry=entry,
            source_entities=description.entities_fn(power_insight),
            power_insight=power_insight,
        ))

    for description in POWER_INSIGHT_HOME_BASE_LOAD_SENSORS:
        if _option_gated_out(description, options_wrapped, SCOPE_COMBINED):
            continue
        entities.append(PowerInsightHomeBaseLoadSensor(
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
        if description.lcoe_gated and not (_prod_lcoe_available or _has_retired_lcoe):
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
        if description.charge_gated and not _provider_is_charge_source(
            power_insight, grid_adapter.uid
        ):
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
            if description.charge_gated and not _provider_is_charge_source(
                power_insight, adapter.uid
            ):
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
            if description.charge_gated and not _provider_is_charge_source(
                power_insight, adapter.uid
            ):
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
                dynamic_description = PowerInsightSensorDescription(
                    # Keyed by the source's subentry id, never its name: a
                    # renamed device must not orphan this sensor's history.
                    key=f"charging_share_from_{source_adapter.uid}",
                    translation_key="charging_share_from",
                    icon="mdi:percent",
                    native_unit_of_measurement=PERCENTAGE,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=0,
                    entities_fn=lambda obj: obj.source_entities_power,
                    value_fn=lambda obj: obj.sink_adapters_source_shares,
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
        # adapter. Named "Power share from {Source}" to mirror the battery's
        # "Charging share from {Source}" sensors; both report this device's
        # current draw from that source as a share (%). Gate on the power-share
        # option.
        if options_wrapped.check(CONF_ENABLE_POWER_SOURCE_SHARES, "consumer"):
            for source_adapter in power_insight.gross_power_adapters:
                dynamic_description = PowerInsightSensorDescription(
                    key=f"power_share_from_{source_adapter.uid}",
                    translation_key="power_share_from",
                    icon="mdi:percent",
                    native_unit_of_measurement=PERCENTAGE,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=0,
                    entities_fn=lambda obj: obj.source_entities_power,
                    value_fn=lambda obj: obj.sink_adapters_source_shares,
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

        # The watts behind those shares, and their running energy: "Power
        # from {Source}" (W) and "Energy from {Source}" (kWh). One of each per
        # power-providing adapter, not only the consumer's allowed sources — a
        # restriction the meters contradict is relaxed, so a "PV only"
        # consumer can really draw from the grid. Keyed by the source's
        # subentry id, never its name, so a rename keeps the history.
        energy_sensors: dict[str, PowerInsightDynamicAdapterIntegrationSensor] = {}
        for source_adapter in power_insight.gross_power_adapters:
            if options_wrapped.check(CONF_ENABLE_POWER_SOURCE_POWER, "consumer"):
                power_description = PowerInsightSensorDescription(
                    key=f"power_from_{source_adapter.uid}",
                    translation_key="power_from",
                    native_unit_of_measurement=UnitOfPower.WATT,
                    device_class=SensorDeviceClass.POWER,
                    state_class=SensorStateClass.MEASUREMENT,
                    suggested_display_precision=0,
                    entities_fn=lambda obj: obj.source_entities_power,
                    value_fn=lambda obj: obj.sink_adapters_source_power,
                )
                entities.append(PowerInsightDynamicAdapterSensor(
                    description=power_description,
                    config_entry=entry,
                    source_entities=power_description.entities_fn(power_insight),
                    power_insight=power_insight,
                    device_adapter=adapter,
                    dynamic_adapter=source_adapter,
                ))
            if options_wrapped.check(CONF_ACCUMULATE_POWER_SOURCE_ENERGY, "consumer"):
                energy_description = PowerInsightIntegrationSensorDescription(
                    key=f"energy_from_{source_adapter.uid}",
                    translation_key="energy_from",
                    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                    device_class=SensorDeviceClass.ENERGY,
                    state_class=SensorStateClass.TOTAL,
                    suggested_display_precision=2,
                    entities_fn=lambda obj: obj.source_entities_power,
                    integration_value_fn=lambda obj: obj.sink_adapters_source_power,
                    unit_prefix="k",
                    retired_source_key=RETIRED_ENERGY_FROM,
                )
                energy_sensor = PowerInsightDynamicAdapterIntegrationSensor(
                    description=energy_description,
                    config_entry=entry,
                    source_entities=energy_description.entities_fn(power_insight),
                    power_insight=power_insight,
                    device_adapter=adapter,
                    dynamic_adapter=source_adapter,
                )
                energy_sensors[source_adapter.uid] = energy_sensor
                entities.append(energy_sensor)

        # The energy from sources that have since been removed, frozen when
        # they were: so the per-source totals still add up to everything this
        # consumer drew. Only once there is something to show.
        removed = retired_source_totals(entry, adapter.uid, RETIRED_ENERGY_FROM)
        if energy_sensors and removed:
            entities.append(PowerInsightRemovedSourcesSensor(
                description=ENERGY_FROM_REMOVED_DEVICES,
                config_entry=entry,
                device_adapter=adapter,
                removed=removed,
            ))

        # Lifetime shares of those totals: "Energy share from {Source}", plus
        # one for the removed devices so that together they make 100 %. Added
        # after the totals they read, so those exist by the time they listen.
        if energy_sensors and options_wrapped.check(
            CONF_ENABLE_ENERGY_SOURCE_SHARES, "consumer"
        ):
            frozen = sum(value for _, value in removed.values())
            for source_uid in energy_sensors:
                entities.append(PowerInsightEnergyShareSensor(
                    description=ENERGY_SHARE_FROM,
                    config_entry=entry,
                    device_adapter=adapter,
                    totals=energy_sensors,
                    removed_total=frozen,
                    share_of=source_uid,
                ))
            if removed:
                entities.append(PowerInsightEnergyShareSensor(
                    description=ENERGY_SHARE_FROM_REMOVED_DEVICES,
                    config_entry=entry,
                    device_adapter=adapter,
                    totals=energy_sensors,
                    removed_total=frozen,
                    share_of=None,
                ))

        _add(entities, config_subentry_id=adapter.uid)

    # Disable entities whose controlling option is now off (keeping their
    # history), and re-enable any we previously disabled that are wanted again.
    _sync_entity_enabled_state(hass, entry, created_unique_ids)


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
            name=f"{self.config_entry.title or 'PowerInsight'} Combined",
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        value = self.entity_description.value_fn(self.power_insight)
        if value is not None:
            value = self.entity_description.transform_fn(value)
        return value


class PowerInsightHomeBaseLoadSensor(BasePowerInsightSensor):
    """A sensor on the synthetic home base load device.

    The home base load has no adapter and no config subentry — it is the
    residual the solve leaves behind — so its device is created here rather
    than from a subentry. It is kept as a device of its own, and never as a
    row in the per-adapter results, because a dict key would need a uid and
    any readable one can collide with a user's slugified device name.
    """

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
            identifiers={(DOMAIN, f"{self.config_entry.entry_id}_home_base_load")},
            name=f"{self.config_entry.title or 'PowerInsight'} Home base load",
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        value = self.entity_description.value_fn(self.power_insight)
        if value is not None:
            value = self.entity_description.transform_fn(value)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, float] | None:
        """Expose where the unmetered load's power came from."""
        attributes_fn = self.entity_description.attributes_fn
        if attributes_fn is None:
            return None

        return attributes_fn(self.power_insight) or None


class PowerInsightCombinedLedgerSensor(PowerInsightSensor):
    """Combined accumulated levelized sensor derived from per-adapter totals.

    Recomputes on every source event as the sum of the active per-adapter base
    accumulated totals (each already scaled by its adapter's correction factor
    for display) plus the frozen contributions of removed end-of-life adapters.
    It stores no running total itself, so there is no reload double-count, and
    a lifetime-value correction is reflected retroactively and consistently in
    both the per-adapter and the combined totals.

    It is unavailable while any *enabled* per-device total is unknown or
    unavailable — at startup before its value is restored, or while its meter
    is down — because a partial sum would record a false drop and rise in the
    long-term statistics. A *disabled* per-device total is skipped: it is not
    accumulating, so that device is simply not part of the combined total.
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

    def _ledger_total(self) -> float | None:
        """Return the per-adapter totals plus the retired ledger, or ``None``.

        ``None`` while an enabled part has no value to add.
        """
        ent_reg = er.async_get(self.hass)
        total = 0.0
        for uid in self.power_insight.levelized_correction_factors:
            unique_id = (
                f"{self.config_entry.entry_id}_{uid}_{self._per_adapter_key}"
            )
            entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id is None:
                continue
            registry_entry = ent_reg.async_get(entity_id)
            if registry_entry is not None and registry_entry.disabled:
                continue
            state = self.hass.states.get(entity_id)
            try:
                total += float(state.state)
            except (AttributeError, ValueError, TypeError):
                return None  # not restored yet, unknown or unavailable

        return total + _retired_ledger_sum(self.config_entry, self._per_adapter_key)

    @property
    def available(self) -> bool:
        """Unavailable while an enabled per-device total has no value."""
        return self._ledger_total() is not None

    @property
    def native_value(self) -> float | None:
        """Return the summed per-adapter totals plus the retired ledger."""
        return self._ledger_total()


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
        """Return the state of the sensor.

        Every per-device map is keyed by the device's whole family, so an idle
        device reads its idle value from the map itself. The value is unknown
        when the whole map is ``None`` (an inflow meter down, so gross power is
        unknowable), when this adapter's own reading is ``None``, or when the
        engine publishes ``None`` for it (a price with nothing delivered).
        """
        mapping = self.entity_description.value_fn(self.power_insight)
        if mapping is None or self.device_adapter.power is None:
            return None
        value = mapping.get(self.device_adapter.uid, 0.0)
        if value is None:
            return None
        value = self.entity_description.transform_fn(value)
        if self.entity_description.apply_correction_factor:
            value = value * self.device_adapter.correction_factor
        return value

    @property
    def extra_state_attributes(self) -> dict[str, float] | None:
        """Return the description's extra attributes for this adapter."""
        attributes_fn = self.entity_description.attributes_fn
        if attributes_fn is None or not self.device_adapter.power_source_uids:
            # Only meaningful for a device restricted to specific sources.
            return None

        values = attributes_fn(self.power_insight) or {}
        deficit = values.get(self.device_adapter.uid)

        return {
            "restriction_deficit": None if deficit is None else round(deficit, 1)
        }


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
        # The name names the other device: "Charging share from Roof PV".
        self._attr_translation_placeholders = {"source": dynamic_adapter.verbose_name}

        uid = f"{self.config_entry.entry_id}_{self.device_adapter.uid}"
        self._attr_unique_id = f"{uid}_{self.entity_description.key}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.device_adapter.uid)},
            name=f"{self.config_entry.title} {self.device_adapter.verbose_name}",
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor.

        As :meth:`PowerInsightAdapterSensor.native_value`, but over the nested
        ``{device_uid: {dynamic_uid: value}}`` map: a device or source absent
        from an otherwise-present map contributed 0 to this pairing, so it reads
        0 rather than unavailable. It goes unavailable only when the whole map is
        None (gross power unknowable) or this device's own reading is None.
        """
        mapping = self.entity_description.value_fn(self.power_insight)
        if mapping is None or self.device_adapter.power is None:
            return None
        row = mapping.get(self.device_adapter.uid)
        value = 0.0 if row is None else row.get(self.dynamic_adapter.uid, 0.0)
        if value is None:
            return None
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
        self._unit_prefix = UNIT_PREFIXES[description.unit_prefix]

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Substitute the HA-configured currency for the EUR placeholder."""
        return _resolve_currency_unit(
            self.entity_description.native_unit_of_measurement, self.hass
        )

    # ------------------------------------------------------------------
    # History carried over from the devices' apps
    # ------------------------------------------------------------------

    @property
    def _accumulated(self) -> Decimal | None:
        """What this sensor counted itself: the running total, as displayed."""
        return self._state

    def _carried_over(self) -> tuple[float | None, dict]:
        """What this total carries over, and its attributes; none by default."""
        return None, {}

    @cached_property
    def _history(self) -> tuple[float | None, dict]:
        """``_carried_over``, once: the history only changes with a reload."""
        if self.entity_description.history_key is None:
            return None, {}
        return self._carried_over()

    @property
    def native_value(self) -> Decimal | None:
        """The counted total plus what it carries over from the devices' apps.

        Added here and nowhere else: the restored total, its breakdown and
        the engine hold only what was counted. Until the sensor has counted
        anything there is nothing to add it to.
        """
        accumulated = self._accumulated
        carried, _ = self._history
        if accumulated is None or carried is None:
            return accumulated
        return accumulated + Decimal(str(carried))

    @property
    def extra_state_attributes(self) -> dict | None:
        """The carried-over part next to the counted one, or why there is none."""
        _, attributes = self._history
        if not attributes:
            return None
        accumulated = self._accumulated
        return {
            **attributes,
            ATTR_TRACKED: None if accumulated is None else round(float(accumulated), 2),
        }


def _runtime_history(entry: ConfigEntry) -> dict[str, DeviceHistory]:
    """The entry's priced history, or none before it is set up."""
    return getattr(getattr(entry, "runtime_data", None), "history", None) or {}


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
            name=f"{self.config_entry.title or 'PowerInsight'} Combined",
        )

    @property
    def integration_value(self) -> float | None:
        """Return the current rate value to integrate."""
        value = self.entity_description.integration_value_fn(self.power_insight)
        if value is not None:
            value = self.entity_description.transform_fn(value)
        return value

    def _carried_over(self) -> tuple[float | None, dict]:
        """Every device's history for this total, removed devices included."""
        return summed_carried_over(
            self.config_entry,
            _runtime_history(self.config_entry),
            self.entity_description.history_key,
        )


class PowerInsightDynamicAdapterIntegrationSensor(BasePowerInsightIntegrationSensor):
    """Per-adapter integration sensor over a nested uid-keyed dict.

    The accumulating twin of :class:`PowerInsightDynamicAdapterSensor`:
    ``integration_value_fn`` returns ``{device_uid: {dynamic_uid: value}}`` and
    this sensor integrates one pairing, e.g. the energy a consumer drew from
    one source. It carries no price, so there is nothing to correct.
    """

    def __init__(
            self,
            description: PowerInsightIntegrationSensorDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
            device_adapter: AbstractBaseAdapter,
            dynamic_adapter: AbstractBaseAdapter,
    ) -> None:
        """Initialize the dynamic adapter integration sensor entity."""
        super().__init__(description, config_entry, source_entities, power_insight)
        self.device_adapter = device_adapter
        self.dynamic_adapter = dynamic_adapter
        # The name names the other device: "Energy from Roof PV".
        self._attr_translation_placeholders = {"source": dynamic_adapter.verbose_name}

        uid = f"{self.config_entry.entry_id}_{self.device_adapter.uid}"
        self._attr_unique_id = f"{uid}_{self.entity_description.key}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.device_adapter.uid)},
            name=f"{self.config_entry.title} {self.device_adapter.verbose_name}",
        )

    @property
    def integration_value(self) -> float | None:
        """Return this pairing's current rate, as the dynamic sensor reads it.

        ``None`` — so the total pauses — when the whole map is ``None`` or this
        device's own reading is unavailable.
        """
        mapping = self.entity_description.integration_value_fn(self.power_insight)
        if mapping is None or self.device_adapter.power is None:
            return None
        row = mapping.get(self.device_adapter.uid)
        value = 0.0 if row is None else row.get(self.dynamic_adapter.uid, 0.0)
        if value is None:
            return None
        return self.entity_description.transform_fn(value)

    async def async_will_remove_from_hass(self) -> None:
        """Freeze this total into the source ledger when its source is removed.

        The consumer's sensor outlives the source it names in the config entry
        but not on the next setup, which no longer creates it. As for the
        retired-device ledger, its own teardown is the only reliable moment to
        read its final value: a removed source's subentry is gone by then,
        while an ordinary reload leaves it in place. A consumer removed along
        with it keeps nothing — its sensors are gone too.
        """
        await super().async_will_remove_from_hass()

        key = self.entity_description.retired_source_key
        subentries = self.config_entry.subentries
        if (
            key is None
            or self.dynamic_adapter.uid in subentries
            or self.device_adapter.uid not in subentries
        ):
            return

        value = self.native_value
        if value is None:
            return

        record_retired_source(
            self.hass,
            self.config_entry,
            source_uid=self.dynamic_adapter.uid,
            title=self.dynamic_adapter.verbose_name,
            consumer_uid=self.device_adapter.uid,
            key=key,
            value=float(value),
        )


class PowerInsightRemovedSourcesSensor(SensorEntity):
    """A consumer's frozen total from sources that have been removed.

    The sum of the source ledger's entries for this consumer, with one
    attribute per removed device. It never changes during a setup: the ledger
    only grows by a removal, and a removal reloads the entry.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
            self,
            description: SensorEntityDescription,
            config_entry: ConfigEntry,
            device_adapter: AbstractBaseAdapter,
            removed: dict[str, tuple[str, float]],
    ) -> None:
        """Initialize the removed-sources sensor."""
        self.entity_description = description
        self.config_entry = config_entry
        self.device_adapter = device_adapter

        uid = f"{config_entry.entry_id}_{device_adapter.uid}"
        self._attr_unique_id = f"{uid}_{description.key}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, device_adapter.uid)},
            name=f"{config_entry.title} {device_adapter.verbose_name}",
        )
        self._attr_native_value = round(sum(v for _, v in removed.values()), 6)
        self._attr_extra_state_attributes = {
            title or source_uid: round(value, 6)
            for source_uid, (title, value) in removed.items()
        }


class PowerInsightEnergyShareSensor(SensorEntity):
    """A consumer's lifetime share of its energy from one source.

    ``Σ energy_from_*`` is the denominator, never a separate total of the
    consumer's energy: it is the same counting, paused and restored together,
    so the shares always add up to 100 %. Energy from removed sources stays in
    the denominator, frozen, and has a share of its own (``share_of=None``).

    Recomputed whenever one of the totals writes a new state. Unavailable
    while a total is disabled: a share of a partial sum would be a wrong
    number, not an approximate one. A total that has counted nothing yet is
    0 kWh — restored values are in place before the shares are added — and
    until anything has been drawn at all the share is unknown: a share of
    nothing is undefined.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
            self,
            description: SensorEntityDescription,
            config_entry: ConfigEntry,
            device_adapter: AbstractBaseAdapter,
            totals: dict[str, PowerInsightDynamicAdapterIntegrationSensor],
            removed_total: float,
            share_of: str | None,
    ) -> None:
        """Initialize the energy share sensor."""
        self.entity_description = description
        self.config_entry = config_entry
        self.device_adapter = device_adapter
        self._totals = totals
        self._removed_total = Decimal(str(removed_total))
        self._share_of = share_of

        key = description.key
        if share_of is not None:
            # Keyed by the source's subentry id, never its name.
            key = f"{key}_{share_of}"
            self._attr_translation_placeholders = {
                "source": totals[share_of].dynamic_adapter.verbose_name
            }
        uid = f"{config_entry.entry_id}_{device_adapter.uid}"
        self._attr_unique_id = f"{uid}_{key}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, device_adapter.uid)},
            name=f"{config_entry.title} {device_adapter.verbose_name}",
        )

    async def async_added_to_hass(self) -> None:
        """Follow every total this share is worked out from."""
        await super().async_added_to_hass()
        entity_ids = [
            total.entity_id for total in self._totals.values()
            if total.hass is not None and total.entity_id
        ]

        @callback
        def _total_changed(_event) -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_track_state_change_event(self.hass, entity_ids, _total_changed)
        )

    def _parts(self) -> dict[str | None, Decimal] | None:
        """Return each total by source uid (``None`` = removed), or ``None``."""
        parts: dict[str | None, Decimal] = {None: self._removed_total}
        for source_uid, total in self._totals.items():
            if total.hass is None:
                return None  # disabled: not counting
            value = total.native_value
            parts[source_uid] = Decimal(0) if value is None else Decimal(str(value))
        return parts

    @property
    def available(self) -> bool:
        """Unavailable while a total it is worked out from is disabled."""
        return self._parts() is not None

    @property
    def native_value(self) -> float | None:
        """Return this source's share of everything drawn so far, in %."""
        parts = self._parts()
        if parts is None:
            return None
        whole = sum(parts.values())
        if whole <= 0:
            return None
        return float(parts[self._share_of] / whole * 100)


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
    def integration_components(self) -> dict[str, float] | None:
        """Return this device's rate split by which correction factor applies."""
        components_fn = self.entity_description.integration_components_fn
        if components_fn is None:
            return None

        return get_value(self.device_adapter.uid, components_fn(self.power_insight))

    def _carried_over(self) -> tuple[float | None, dict]:
        """This device's history for this total.

        The grid's totals are the whole home's (its export compensation is
        everything exported), so they carry every device's.
        """
        history = _runtime_history(self.config_entry)
        key = self.entity_description.history_key
        if self.device_adapter is self.power_insight.grid_adapter:
            return summed_carried_over(self.config_entry, history, key)
        return device_carried_over(
            self.config_entry, history, self.device_adapter.uid, key
        )

    def _component_factors_now(self) -> dict[str, float]:
        """Return the factor that scales each accumulated component.

        A component's adapter that still exists gives its live factor. One that
        has been removed can no longer be edited, so the last factor seen for
        it is final: its share of this total stays as it was displayed when
        the adapter was removed, just as the adapter's own totals are frozen
        into the retired ledger. The grid never scales (1.0).
        """
        live = self.power_insight.levelized_correction_factors
        return {
            uid: live.get(uid, self._component_factors.get(uid, 1.0))
            for uid in self._component_totals
        }

    @property
    def _accumulated(self) -> Decimal | None:
        """Return the accumulated base total, corrected for display if requested.

        Each accumulated component is scaled by *its own* adapter's correction
        factor, so editing one device's lifetime cost rescales exactly the
        share of history that came from it. Anything without a breakdown — a
        total accumulated before the breakdown existed — has no attribution
        left to correct by, so it is carried through unscaled rather than
        guessed at. That holds whether or not anything has been accumulated on
        top of it yet.
        """
        base = self._state
        if base is None or not self.entity_description.apply_correction_factor:
            return base

        factors = self._component_factors_now()
        corrected = Decimal(0)
        for uid, total in self._component_totals.items():
            corrected += total * Decimal(str(factors[uid]))

        # Whatever predates the breakdown stays as it was recorded.
        return corrected + (base - sum(self._component_totals.values()))

    @property
    def extra_restore_state_data(self) -> IntegrationSensorExtraStoredData:
        """Persist the BASE running total (not the corrected display).

        The factors go with it: this is written when the entity is removed
        for the reload that follows a device's removal, while the engine still
        holds that device, so its last factor survives into the next setup.
        """
        return IntegrationSensorExtraStoredData(
            self._state,
            self.native_unit_of_measurement,
            self._last_valid_state,
            dict(self._component_totals) or None,
            self._component_factors_now() or None,
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
        # Only PV and battery totals belong to the device ledger: a consumer's
        # levelized operating cost shares the key but is not a device cost.
        if (
            not self.entity_description.apply_correction_factor
            or key not in LEVELIZED_TOTAL_KEYS
            or not isinstance(self.device_adapter, BaseProductionAdapter)
        ):
            return

        uid = self.device_adapter.uid
        # Subentry still present -> this is a reload/unload, not a removal.
        if uid in self.config_entry.subentries:
            return

        # Corrected (base * factor), with the carried-over history: frozen as
        # it was displayed, like everything else about a removed device.
        value = self.native_value
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
