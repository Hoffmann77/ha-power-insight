"""Sensor entities for the PowerInsight integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
# from operator import attrgetter

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.const import (
    PERCENTAGE,
    CURRENCY_EURO,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.components.integration.const import (
    METHOD_LEFT,
)
from homeassistant.helpers.device import async_device_info_to_link_from_entity
from homeassistant.components.integration.sensor import (
    IntegrationSensor,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)

from .entity import BaseEventSensorEntity, BaseEventIntegrationSensorEntity
from .utils import get_value
from .power_insight import PowerInsight
from . import MyConfigEntry
from .const import (
    DOMAIN,
    CONF_ENABLE_DEBUG_ENTITIES,
    CONF_CALCULATE_COST_RATES,
    CONF_CALCULATE_LEVELIZED_COST_RATES,
    CONF_CALCULATE_COST_SAVING_RATES,
    CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES,

    CONF_ACCUMULATE_COST_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_RATES,
    CONF_ACCUMULATE_COST_SAVING_RATES,
    CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PowerInsightSensorDescription(SensorEntityDescription):
    """Provide the description of a Power insight sensor."""

    entities_fn: Callable[[dict], float | None]
    exists_fn: Callable[[dict], bool] = lambda value: True
    value_fn: Callable[[dict], float | None]
    transform_fn: Callable = lambda value: value


@dataclass(frozen=True, kw_only=True)
class PowerInsightIntegrationSensorDescription(SensorEntityDescription):
    """Provide a description of a Heat pump Signal sensor."""

    entities_fn: Callable[[dict], float | None]
    exists_fn: Callable[[dict], bool] = lambda value: True
    integration_value_fn: Callable[[dict], float | None]
    transform_fn: Callable = lambda value: value


#
# PowerInsight sensors
#

POWER_INSIGHT_SENSORS = (
    PowerInsightSensorDescription(
        key="available_power",
        name="Available power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda options: options.check(CONF_ENABLE_DEBUG_ENTITIES),
        value_fn=lambda obj: obj.total_power,
    ),
    PowerInsightSensorDescription(
        key="combined_export_ratio",
        name="Combined export ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        # exists_fn=lambda options: options.check(),
        value_fn=lambda obj: obj.export_share,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorDescription(
        key="combined_export_compensation_rate",
        name="Combined export compensation rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda options: options.check(CONF_CALCULATE_COST_RATES),
        value_fn=lambda obj: obj.total_export_compensation_rate,
    ),
    PowerInsightSensorDescription(
        key="combined_self_consumption_power",
        name="Combined self-consumption power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        # exists_fn=lambda options: adapter.exports_power,
        value_fn=lambda obj: obj.self_consumption,
    ),
    PowerInsightSensorDescription(
        key="combined_self_consumption_ratio",
        name="Combined self-consumption ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        # exists_fn=lambda options: adapter.exports_power,
        value_fn=lambda obj: obj.self_consumption_share,
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
        exists_fn=lambda options: options.check(CONF_CALCULATE_COST_SAVING_RATES),
        value_fn=lambda obj: obj.total_self_cons_saving_rate,
    ),
    PowerInsightSensorDescription(
        key="combined_utilization_power",
        name="Combined utilization power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        # exists_fn=lambda options: adapter.exports_power,
        value_fn=lambda obj: obj.utilization,
    ),
    PowerInsightSensorDescription(
        key="combined_utilization_ratio",
        name="Combined utilization ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        # exists_fn=lambda options: adapter.exports_power,
        value_fn=lambda obj: obj.utilization_share,
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
        # exists_fn=lambda options: adapter.exports_power,
        value_fn=lambda obj: obj.coe,
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
        # exists_fn=lambda options: adapter.exports_power,
        value_fn=lambda obj: obj.lcoe,
    ),
    PowerInsightSensorDescription(
        key="combined_cost_rate",
        name="Combined cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda options: options.check(CONF_CALCULATE_COST_RATES),
        value_fn=lambda obj: obj.coe_rate,
    ),

    PowerInsightSensorDescription(
        key="combined_levelized_cost_rate",
        name="Combined levelized cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda options: options.check(CONF_CALCULATE_LEVELIZED_COST_RATES),
        value_fn=lambda obj: obj.lcoe_rate,
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
        exists_fn=lambda options: options.check(CONF_CALCULATE_COST_RATES),
        value_fn=lambda obj: obj.total_coo_rate,
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
        exists_fn=lambda options: options.check(CONF_CALCULATE_LEVELIZED_COST_RATES),
        value_fn=lambda obj: obj.total_lcoo_rate,
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
        exists_fn=lambda options: options.check(CONF_CALCULATE_COST_SAVING_RATES),
        value_fn=lambda obj: obj.total_saving_rate,
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
        exists_fn=lambda options: options.check(CONF_CALCULATE_LEVELIZED_COST_SAVING_RATES),
        value_fn=lambda obj: obj.total_levelized_saving_rate,
    ),
)


POWER_INSIGHT_INTEGRATION_SENSORS = (
    PowerInsightIntegrationSensorDescription(
        key="combined_total_export_compensation",
        name="Combined total export compensation",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda options: options.check(CONF_ACCUMULATE_COST_RATES),
        integration_value_fn=lambda obj: obj.total_export_compensation_rate,
    ),
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
        exists_fn=lambda options: options.check(CONF_ACCUMULATE_COST_RATES),
        integration_value_fn=lambda obj: obj.total_coo_rate,
    ),
    PowerInsightIntegrationSensorDescription(
        key="combined_total_levelized_operating_costs",
        name="Combined total levelized operating costs",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda options: options.check(CONF_ACCUMULATE_LEVELIZED_COST_RATES),
        integration_value_fn=lambda obj: obj.total_lcoo_rate,
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
        exists_fn=lambda options: options.check(CONF_ACCUMULATE_COST_SAVING_RATES),
        integration_value_fn=lambda obj: obj.total_self_cons_saving_rate,
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
        exists_fn=lambda options: options.check(CONF_ACCUMULATE_COST_SAVING_RATES),
        integration_value_fn=lambda obj: obj.total_saving_rate,
    ),
    PowerInsightIntegrationSensorDescription(
        key="combined_total_levelized_cost_savings",
        name="Combined total levelized cost savings",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        exists_fn=lambda options: options.check(CONF_ACCUMULATE_LEVELIZED_COST_SAVING_RATES),
        integration_value_fn=lambda obj: obj.total_levelized_saving_rate,
    ),
)



POWER_INSIGHT_GRID_ADAPTER_SENSORS = (
    # PowerInsightSensorDescription(
    #     key="self_consumption_rate",
    #     name="Self consumption rate",
    #     icon="mdi:percent",
    #     native_unit_of_measurement=PERCENTAGE,
    #     state_class=SensorStateClass.MEASUREMENT,
    #     suggested_display_precision=0,
    #     entities_fn=lambda obj: obj.source_entities_power,
    #     value_fn=lambda obj: obj.grid_adapter_self_cons_rates,
    #     transform_fn=lambda val: val * 100,
    # ),
)



#
# PowerInsight production adapter sensors
#

POWER_INSIGHT_PROD_ADAPTER_SENSORS = (
    PowerInsightSensorDescription(
        key="export_power",
        name="Export power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_unit_of_measurement=UnitOfPower.WATT,
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
        value_fn=lambda obj: obj.prod_adapters_export_rates,
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
        suggested_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.prod_adapters_self_cons_power,
    ),
    PowerInsightSensorDescription(
        key="self_consumption_ratio",
        name="Self-consumption ratio",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.prod_adapters_self_cons_rates,
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
        value_fn=lambda obj: obj.prod_adapters_self_cons_shares,
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
        value_fn=lambda obj: obj.prod_adapters_self_cons_saving_rates,
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
        value_fn=lambda obj: obj.prod_adapters_lcoo_rates,
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
        value_fn=lambda obj: obj.prod_adapters_saving_rates,
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
        value_fn=lambda obj: obj.prod_adapters_levelized_saving_rates,
    ),
)


POWER_INSIGHT_PROD_ADAPTER_INTEGRATION_SENSORS = (
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
        integration_value_fn=lambda obj: obj.prod_adapters_lcoo_rates,
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
        integration_value_fn=lambda obj: obj.prod_adapters_self_cons_saving_rates,
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
        integration_value_fn=lambda obj: obj.prod_adapters_saving_rates,
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
        integration_value_fn=lambda obj: obj.prod_adapters_levelized_saving_rates,
    ),
)


#
# PowerInsight consumption adapter sensors
#

# consumption
# Power from grid, pv, ...
# total power from grid, pv, ...

# total consumption
# grid, pv,... shares


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
        key="operating_cost_rate_levelized",
        name="Operating cost rate levelized",
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


POWER_INSIGHT_CONS_ADAPTER_INTEGRATION_SENSORS = ()






class OptionsWrapper:
    """Wrapper around the raw options dict providing a unified check interface."""

    def __init__(self, options: dict) -> None:
        self._options = options
        self._selected: set = set()
        for key, value in options.items():
            if isinstance(value, list):
                self._selected.update(value)

    def check(self, key: str) -> bool:
        """Return True if the key is enabled, either as a boolean or a selected list item."""
        if key in self._selected:
            return True
        return bool(self._options.get(key, False))




async def async_setup_entry(
        hass: HomeAssistant,
        entry: MyConfigEntry,
        async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform."""
    power_insight = entry.runtime_data.power_insight
    entities = []

    options_wrapped = OptionsWrapper(entry.options)

    for description in POWER_INSIGHT_SENSORS:
        if not description.exists_fn(options_wrapped):
            continue
        
        entity = PowerInsightSensor(
            description=description,
            config_entry=entry,
            source_entities=description.entities_fn(power_insight),
            power_insight=power_insight,
        )
        entities.append(entity)

    for description in POWER_INSIGHT_INTEGRATION_SENSORS:
        if not description.exists_fn(options_wrapped):
            continue

        entity = PowerInsightIntegrationSensor(
            description=description,
            config_entry=entry,
            source_entities=description.entities_fn(power_insight),
            power_insight=power_insight,
        )
        entities.append(entity)

    async_add_entities(entities)


    grid_adapter = power_insight.grid_adapter
    entities = []
    for description in POWER_INSIGHT_GRID_ADAPTER_SENSORS:
        entity = PowerInsightAdapterSensor(
            description=description,
            config_entry=entry,
            source_entities=description.entities_fn(power_insight),
            power_insight=power_insight,
            device_adapter=grid_adapter,
        )
        entities.append(entity)
    
    async_add_entities(entities, config_subentry_id=grid_adapter.uid)


    for adapter in power_insight.prod_adapters:
        entities = []
        for description in POWER_INSIGHT_PROD_ADAPTER_SENSORS:
            if not description.exists_fn(adapter):
                continue

            entity = PowerInsightAdapterSensor(
                description=description,
                config_entry=entry,
                source_entities=description.entities_fn(power_insight),
                power_insight=power_insight,
                device_adapter=adapter,
            )
            entities.append(entity)

        for description in POWER_INSIGHT_PROD_ADAPTER_INTEGRATION_SENSORS:
            if not description.exists_fn(adapter):
                continue

            entity = PowerInsightAdapterIntegrationSensor(
                description=description,
                config_entry=entry,
                source_entities=description.entities_fn(power_insight),
                power_insight=power_insight,
                device_adapter=adapter,
            )
            entities.append(entity)

        async_add_entities(entities, config_subentry_id=adapter.uid)

    for adapter in power_insight.cons_adapters:
        entities = []
        for description in POWER_INSIGHT_CONS_ADAPTER_SENSORS:
            if not description.exists_fn(adapter):
                continue

            entity = PowerInsightAdapterSensor(
                description=description,
                config_entry=entry,
                source_entities=description.entities_fn(power_insight),
                power_insight=power_insight,
                device_adapter=adapter,
            )
            entities.append(entity)

        for description in POWER_INSIGHT_CONS_ADAPTER_INTEGRATION_SENSORS:
            if not description.exists_fn(adapter):
                continue

            entity = PowerInsightAdapterIntegrationSensor(
                description=description,
                config_entry=entry,
                source_entities=description.entities_fn(power_insight),
                power_insight=power_insight,
                device_adapter=adapter,
            )
            entities.append(entity)


        for power_adapter in power_insight.power_providing_adapters:

            name = power_adapter.verbose_name


            dynamic_description = PowerInsightSensorDescription(
                key=f"{name}_ratio",
                name=f"{name} Ratio",
                icon="mdi:percent",
                native_unit_of_measurement=PERCENTAGE,
                state_class=SensorStateClass.MEASUREMENT,
                suggested_display_precision=0,
                entities_fn=lambda obj: (
                    obj.source_entities_power
                ),
                value_fn=lambda obj: obj.cons_adapters_source_shares,
                transform_fn=lambda val: val * 100,
            )

            if not description.exists_fn(adapter):
                continue

            entity = PowerInsightDynamicAdapterSensor(
                description=dynamic_description,
                config_entry=entry,
                source_entities=dynamic_description.entities_fn(power_insight),
                power_insight=power_insight,
                device_adapter=adapter,
                dynamic_adapter=power_adapter,
            )
            entities.append(entity)

        async_add_entities(entities, config_subentry_id=adapter.uid)


class BasePowerInsightSensor(BaseEventSensorEntity):
    """Base sensor entity."""

    entity_description: PowerInsightSensorDescription

    _attr_has_entity_name = True

    def __init__(
            self,
            description: SensorEntityDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
    ) -> None:
        """Initialize the base sensor entity."""
        super().__init__(source_entities, power_insight)
        self.entity_description = description
        self.config_entry = config_entry


class PowerInsightSensor(BasePowerInsightSensor):
    """Sensor entity with access to the `PowerInsight` instance."""

    def __init__(
            self,
            description: SensorEntityDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
    ) -> None:
        """Initialize sensor entity."""
        super().__init__(
            description, config_entry, source_entities, power_insight
        )
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
        data = self.power_insight
        assert data is not None
        value = self.entity_description.value_fn(data)
        if value is not None:
            value = self.entity_description.transform_fn(value)

        return value


class PowerInsightAdapterSensor(BasePowerInsightSensor):
    """Sensor entity with access to the `Adapter` instance.

    Used for adapter sensors entities that require
    additional access to the `PowerInsight` instance.

    """

    def __init__(
            self,
            description: SensorEntityDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
            device_adapter,
    ) -> None:
        """Initialize device sensor entity."""
        super().__init__(
            description, config_entry, source_entities, power_insight
        )
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
        assert self.power_insight is not None
        value = self.entity_description.value_fn(self.power_insight)
        value = get_value(self.device_adapter.uid, value)
        if value is not None:
            value = self.entity_description.transform_fn(value)

        return value



class PowerInsightDynamicAdapterSensor(BasePowerInsightSensor):
    """Sensor entity with access to the `Adapter` instance.

    Used for adapter sensors entities that require
    additional access to the `PowerInsight` instance.

    """

    def __init__(
            self,
            description: SensorEntityDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
            device_adapter,
            dynamic_adapter
    ) -> None:
        """Initialize device sensor entity."""
        super().__init__(
            description, config_entry, source_entities, power_insight
        )
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
        assert self.power_insight is not None
        value = self.entity_description.value_fn(self.power_insight)
        value = get_value(self.device_adapter.uid, value)
        value = get_value(self.dynamic_adapter.uid, value)
        if value is not None:
            value = self.entity_description.transform_fn(value)

        return value




class BasePowerInsightIntegrationSensor(BaseEventIntegrationSensorEntity):
    """Integration sensor entity with access to the `PowerInsight` instance."""

    entity_description: PowerInsightIntegrationSensorDescription

    _attr_has_entity_name = True

    def __init__(
            self,
            description: SensorEntityDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
    ) -> None:
        """Initialize the base sensor entity."""
        super().__init__(source_entities, power_insight)
        self.entity_description = description
        self.config_entry = config_entry


class PowerInsightIntegrationSensor(BasePowerInsightIntegrationSensor):
    """Integration sensor entity with access to the `PowerInsight` instance."""

    def __init__(
            self,
            description: SensorEntityDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
    ) -> None:

        super().__init__(
            description, config_entry, source_entities, power_insight
        )

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
        """Return the state of the sensor."""
        data = self.power_insight
        assert data is not None
        value = self.entity_description.integration_value_fn(data)
        if value is not None:
            value = self.entity_description.transform_fn(value)

        return value


class PowerInsightAdapterIntegrationSensor(BasePowerInsightIntegrationSensor):
    """Integration sensor entity with access to the `PowerInsight` instance."""

    def __init__(
            self,
            description: SensorEntityDescription,
            config_entry: ConfigEntry,
            source_entities: list[str],
            power_insight: PowerInsight,
            device_adapter,
    ) -> None:

        super().__init__(
            description, config_entry, source_entities, power_insight
        )
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
        """Return the state of the sensor."""
        data = self.power_insight
        assert data is not None
        value = self.entity_description.integration_value_fn(data)
        value = get_value(self.device_adapter.uid, value)
        if value is not None:
            value = self.entity_description.transform_fn(value)

        return value
