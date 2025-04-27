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

from .entity import BaseEventSensorEntity
from .const import DOMAIN  # , CONF_PV_SIGNAL, CONF_BATTERY, CONF_HEATPUMP
from .utils import get_value
from .power_insight import PowerInsight
from . import MyConfigEntry


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PowerInsightSensorEntityDescription(SensorEntityDescription):
    """Provide a description of a Heat pump Signal sensor."""

    entities_fn: Callable[[dict], float | None]
    value_fn: Callable[[dict], float | None]
    transform_fn: Callable = lambda value: value


POWER_INSIGHT_SENSORS = (
    PowerInsightSensorEntityDescription(
        key="available_power",
        name="Available power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.total_power,
    ),
    PowerInsightSensorEntityDescription(
        key="export_share",
        name="Export share",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.export_share,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorEntityDescription(
        key="export_compensation_rate",
        name="Export compensation rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.total_export_compensation_rate,
    ),
    PowerInsightSensorEntityDescription(
        key="self_consumption_power",
        name="Self consumption power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.self_consumption,
    ),
    PowerInsightSensorEntityDescription(
        key="self_consumption_share",
        name="Self consumption share",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.self_consumption_share,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightSensorEntityDescription(
        key="self_consumption_cost_saving_rate",
        name="Self consumption cost saving rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.total_self_cons_saving_rate,
    ),
    PowerInsightSensorEntityDescription(
        key="utilization_power",
        name="Utilization power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.utilization,
    ),
    PowerInsightSensorEntityDescription(
        key="utilization_share",
        name="Utilization share",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.utilization_share,
        transform_fn=lambda val: val * 100,
    ),

    PowerInsightSensorEntityDescription(
        key="electricity_price",
        name="Electricity price",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.coe,
    ),
    PowerInsightSensorEntityDescription(
        key="electricity_price_levelized",
        name="Electricity price levelized",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.lcoe,
    ),
    PowerInsightSensorEntityDescription(
        key="cost_rate",
        name="Cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.coe_rate,
    ),

    PowerInsightSensorEntityDescription(
        key="cost_rate_levelized",
        name="Cost rate levelized",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.lcoe_rate,
    ),
    PowerInsightSensorEntityDescription(
        key="operating_cost_rate",
        name="Operating cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.total_coo_rate,
    ),
    PowerInsightSensorEntityDescription(
        key="operating_cost_rate_levelized",
        name="Operating cost rate levelized",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.total_lcoo_rate,
    ),
    PowerInsightSensorEntityDescription(
        key="cost_savings_rate",
        name="Cost savings rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.total_saving_rate,
    ),
    PowerInsightSensorEntityDescription(
        key="cost_savings_rate_levelized",
        name="Cost savings rate levelized",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.total_levelized_saving_rate,
    ),
)


@dataclass(frozen=True, kw_only=True)
class IntegrationSensorEntityDescription(SensorEntityDescription):
    """Provide a description of a Heat pump Signal sensor."""

    source_entity: str


POWER_INSIGHT_INTEGRATION_SENSORS = (
    IntegrationSensorEntityDescription(
        key="export_compensation",
        name="Export compensation",
        source_entity="export_compensation_rate",
        suggested_display_precision=2,
    ),
    IntegrationSensorEntityDescription(
        key="operating_costs",
        name="Operating costs",
        source_entity="operating_cost_rate",
        suggested_display_precision=2,
    ),
    IntegrationSensorEntityDescription(
        key="operating_costs_levelized",
        name="Operating costs levelized",
        source_entity="operating_cost_rate_levelized",
        suggested_display_precision=2,
    ),
    IntegrationSensorEntityDescription(
        key="self_consumption_cost_savings",
        name="Self consumption cost savings",
        source_entity="self_consumption_cost_saving_rate",
        suggested_display_precision=2,
    ),
    IntegrationSensorEntityDescription(
        key="cost_savings",
        name="Cost savings",
        source_entity="cost_savings_rate",
        suggested_display_precision=2,
    ),
    IntegrationSensorEntityDescription(
        key="cost_savings_levelized",
        name="Cost savings levelized",
        source_entity="cost_savings_rate_levelized",
        suggested_display_precision=2,
    ),
)


@dataclass(frozen=True, kw_only=True)
class AdapterSensorEntityDescription(SensorEntityDescription):
    """Provide a description of a Heat pump Signal sensor."""

    entities_fn: Callable[[dict], float | None] = None
    value_fn: Callable[[dict], float | None] = None
    transform_fn: Callable = lambda value: value


PROD_ADAPTER_SENSORS = ()  # coe_rate, lcoe_rate)


CONS_ADAPTER_SENSORS = ()


@dataclass(frozen=True, kw_only=True)
class PowerInsightAdapterSensorEntityDescription(SensorEntityDescription):
    """Provide a description of a Heat pump Signal sensor."""

    entities_fn: Callable[[dict], float | None] = None
    value_fn: Callable[[dict], float | None] = None
    exists_fn: Callable[[dict], bool] = lambda value: True
    transform_fn: Callable = lambda value: value


POWER_INSIGHT_PROD_ADAPTER_SENSORS = (
    PowerInsightAdapterSensorEntityDescription(
        key="export_power",
        name="Export power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.adapters_export_power,
    ),
    PowerInsightAdapterSensorEntityDescription(
        key="export_rate",
        name="Export rate",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.adapters_export_rates,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightAdapterSensorEntityDescription(
        key="export_share",
        name="Export share",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        exists_fn=lambda adapter: adapter.exports_power,
        value_fn=lambda obj: obj.adapters_export_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightAdapterSensorEntityDescription(
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
        value_fn=lambda obj: obj.adapters_export_compensation_rates,
    ),
    PowerInsightAdapterSensorEntityDescription(
        key="self_consumption_power",
        name="Self consumption power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.adapters_self_cons_power,
    ),
    PowerInsightAdapterSensorEntityDescription(
        key="self_consumption_rate",
        name="Self consumption rate",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.adapters_self_cons_rates,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightAdapterSensorEntityDescription(
        key="self_consumption_share",
        name="Self consumption share",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entities_fn=lambda obj: obj.source_entities_power,
        value_fn=lambda obj: obj.adapters_self_cons_shares,
        transform_fn=lambda val: val * 100,
    ),
    PowerInsightAdapterSensorEntityDescription(
        key="self_consumption_cost_saving_rate",
        name="Self consumption cost saving rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.adapters_self_cons_saving_rates,
    ),
    PowerInsightAdapterSensorEntityDescription(
        key="operating_cost_rate",
        name="Operating cost rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.adapters_coo_rates,
    ),
    PowerInsightAdapterSensorEntityDescription(
        key="operating_cost_rate_levelized",
        name="Operating cost rate levelized",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.adapters_lcoo_rates,
    ),
    PowerInsightAdapterSensorEntityDescription(
        key="cost_savings_rate",
        name="Cost savings rate",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.adapters_saving_rates,
    ),
    PowerInsightAdapterSensorEntityDescription(
        key="cost_savings_rate_levelized",
        name="Cost savings rate levelized",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entities_fn=lambda obj: (
            obj.source_entities_price + obj.source_entities_power
        ),
        value_fn=lambda obj: obj.adapters_levelized_saving_rates,
    ),
)


POWER_INSIGHT_PROD_ADAPTER_INTEGRATION_SENSORS = (
    IntegrationSensorEntityDescription(
        key="export_compensation",
        name="Export compensation",
        source_entity="export_compensation_rate",
        suggested_display_precision=2,
    ),
    IntegrationSensorEntityDescription(
        key="operating_costs",
        name="Operating costs",
        source_entity="operating_cost_rate",
        suggested_display_precision=2,
    ),
    IntegrationSensorEntityDescription(
        key="operating_costs_levelized",
        name="Operating costs levelized",
        source_entity="operating_cost_rate_levelized",
        suggested_display_precision=2,
    ),
    IntegrationSensorEntityDescription(
        key="self_consumption_cost_savings",
        name="Self consumption cost savings",
        source_entity="self_consumption_cost_saving_rate",
        suggested_display_precision=2,
    ),
    IntegrationSensorEntityDescription(
        key="cost_savings",
        name="Cost savings",
        source_entity="cost_savings_rate",
        suggested_display_precision=2,
    ),
    IntegrationSensorEntityDescription(
        key="cost_savings_levelized",
        name="Cost savings levelized",
        source_entity="cost_savings_rate_levelized",
        suggested_display_precision=2,
    ),
)


POWER_INSIGHT_CONS_ADAPTER_SENSORS = ()


async def async_setup_entry(
        hass: HomeAssistant,
        entry: MyConfigEntry,
        async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform."""
    # Access the runtime data form the config entry
    power_insight = entry.runtime_data.power_insight

    integration_sensor_mapping = {}
    for description in POWER_INSIGHT_INTEGRATION_SENSORS:
        integration_sensor_mapping.update(
            {description.source_entity: description}
        )

    adapter_integration_sensor_mapping = {}
    for description in POWER_INSIGHT_PROD_ADAPTER_INTEGRATION_SENSORS:
        adapter_integration_sensor_mapping.update(
            {description.source_entity: description}
        )

    # Add the power insight sensor----------------------------------------->

    _entities = []

    for description in POWER_INSIGHT_SENSORS:
        entity = PowerInsightSensorEntity(
            description=description,
            config_entry=entry,
            source_entities=description.entities_fn(power_insight),
            power_insight=power_insight,
        )
        async_add_entities([entity])

        integration_description = integration_sensor_mapping.get(
            description.key
        )
        if integration_description:
            integration_entity = PowerInsightIntegrationSensorEntity(
                description=integration_description,
                config_entry=entry,
                source_entity=entity.entity_id,
            )
            async_add_entities([integration_entity])


    # TOTAL_POWER_ENTITIES = [entity.entity_id for entity in base_entities]
    # for _entity in base_entities:
    #    key_entity_mapping[_entity.entity_description.key] = _entity.entity_id

    # Add the share sensors ------------------------------------------------->

    # SHARE_SENSOR_SOURCE_ENTITIES = [
    #     key_entity_mapping[val] for val in ("total_input", "total_output")
    # ]
    # _entities: list = []

    # for adapter in power_insight.power_providing_adapters:
    #     # Share sensors
    #     entity = ShareSensorEntity(
    #         description=ShareSensorEntity.get_description(adapter),
    #         config_entry=entry,
    #         source_entities=SHARE_SENSOR_SOURCE_ENTITIES,
    #         power_insight=power_insight,
    #         adapter_key=adapter.key,
    #     )

    #     _entities.append(entity)

    # async_add_entities(_entities)
    # SHARE_SENSOR_ENTITIES = [entity.entity_id for entity in _entities]
    # for _entity in _entities:
    #     key_entity_mapping[_entity.entity_description.key] = _entity.entity_id

    # Add the production adapter sensors----------------------------------->

    _entities: list = []

    for adapter in power_insight.prod_adapters:
        # Add the Adapter sensors
        for description in PROD_ADAPTER_SENSORS:
            entity = AdapterSensorEntity(
                description=description,
                config_entry=entry,
                source_entities=description.entities_fn(adapter),
                power_insight=power_insight,
                adapter=adapter,
            )
            _entities.append(entity)

        # Add the PowerInsight Adapter sensors
        for description in POWER_INSIGHT_PROD_ADAPTER_SENSORS:
            if not description.exists_fn(adapter):
                continue

            entity = PowerInsightAdapterSensorEntity(
                description=description,
                config_entry=entry,
                source_entities=description.entities_fn(power_insight),
                power_insight=power_insight,
                adapter=adapter,
            )
            async_add_entities([entity])

            integration_description = adapter_integration_sensor_mapping.get(
                description.key
            )
            if integration_description:
                integration_entity = PowerInsightAdapterIntegrationSensorEntity(
                    description=integration_description,
                    config_entry=entry,
                    source_entity=entity.entity_id,
                    adapter=adapter,
                )
                async_add_entities([integration_entity])




    # Add the entities
    async_add_entities(_entities)

    # _LOGGER.debug(f"Adding the following entities: {entities}")

    # async_add_entities(entities)


class BaseSensorEntity(BaseEventSensorEntity):
    """Base sensor entity."""

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


class PowerInsightSensorEntity(BaseSensorEntity):
    """Sensor entity with access to the `PowerInsight` instance."""

    entity_description: PowerInsightSensorEntityDescription

    def __init__(
            self,
            description: PowerInsightSensorEntityDescription,
            config_entry,
            source_entities,
            power_insight,
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


class PowerInsightIntegrationSensorEntity(IntegrationSensor):
    """Integration sensor entity with access to the `PowerInsight` instance."""

    _attr_has_entity_name = True

    def __init__(self, description, config_entry, source_entity):
        self.entity_description = description
        self.config_entry = config_entry
        self.source_entity = source_entity

        unique_id = (
            f"{self.config_entry.entry_id}_{self.entity_description.key}"
        )

        device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name=self.config_entry.title or "PowerInsight",
        )

        super().__init__(
            integration_method=METHOD_LEFT,
            name=description.name,
            round_digits=1,
            source_entity=source_entity,
            unique_id=unique_id,
            unit_prefix=None,
            unit_time=UnitOfTime.HOURS,
            device_info=device_info,
            max_sub_interval=None,
        )




class BaseAdapterSensorEntity(BaseSensorEntity):
    """Base adapter sensor entity."""

    def __init__(
            self,
            description: SensorEntityDescription,
            config_entry,
            source_entities,
            power_insight,
            adapter,
    ) -> None:
        """Initialize device sensor entity."""
        super().__init__(
            description, config_entry, source_entities, power_insight
        )
        self.adapter = adapter

        uid = f"{self.config_entry.entry_id}_{self.adapter.key}"

        self._attr_unique_id = f"{uid}_{self.entity_description.key}"

        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, uid)},
            name=f"{self.config_entry.title} {self.adapter.verbose_name}",
            via_device=(DOMAIN, self.config_entry.entry_id)
        )


class PowerInsightAdapterIntegrationSensorEntity(IntegrationSensor):

    _attr_has_entity_name = True

    def __init__(self, description, config_entry, source_entity, adapter):
        self.entity_description = description
        self.config_entry = config_entry
        self.source_entity = source_entity

        self.adapter = adapter

        uid = f"{self.config_entry.entry_id}_{self.adapter.key}"

        unique_id = f"{uid}_{self.entity_description.key}"

        device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, uid)},
            name=f"{self.config_entry.title} {self.adapter.verbose_name}",
            via_device=(DOMAIN, self.config_entry.entry_id)
        )

        super().__init__(
            integration_method=METHOD_LEFT,
            name=description.name,
            round_digits=1,
            source_entity=source_entity,
            unique_id=unique_id,
            unit_prefix=None,
            unit_time=UnitOfTime.HOURS,
            device_info=device_info,
            max_sub_interval=None,
        )


class AdapterSensorEntity(BaseAdapterSensorEntity):
    """Adapter sensor entity with access to the `Adapter` instance.

    Used for adapter sensors entities that only
    require access to the `Adapter` instance itself.

    """

    entity_description: AdapterSensorEntityDescription

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        assert self.adapter is not None
        value = self.entity_description.value_fn(self.adapter)
        if value is not None:
            value = self.entity_description.transform_fn(value)

        return value


class PowerInsightAdapterSensorEntity(BaseAdapterSensorEntity):
    """Adapter sensor entity with access to the `PowerInsight` instance.

    Used for adapter sensors entities that require
    additional access to the `PowerInsight` instance.

    """

    entity_description: PowerInsightAdapterSensorEntityDescription

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        assert self.power_insight is not None
        value = self.entity_description.value_fn(self.power_insight)
        value = get_value(self.adapter.key, value)
        if value is not None:
            value = self.entity_description.transform_fn(value)

        return value
