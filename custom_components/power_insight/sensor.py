"""Sensor entities for the PowerInsight integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
# from operator import attrgetter

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.const import PERCENTAGE  # , CURRENCY_EURO
from homeassistant.components.sensor import (
    # SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)

from .entity import BaseEventSensorEntity
from .const import DOMAIN  # , CONF_PV_SIGNAL, CONF_BATTERY, CONF_HEATPUMP
from .utils import get_value
from . import MyConfigEntry


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class UpdateSensorEntityDescription(SensorEntityDescription):
    """Provide a description of a Heat pump Signal sensor."""

    # Possible arguments:
    # device_class: SensorDeviceClass | None = None
    # last_reset: datetime | None = None
    # native_unit_of_measurement: str | None = None
    # options: list[str] | None = None
    # state_class: SensorStateClass | str | None = None
    # suggested_display_precision: int | None = None
    # suggested_unit_of_measurement: str | None = None
    # unit_of_measurement: None = None  # Type override, use native_unit_of_measurement



    value_fn: Callable[[dict], float | None]
    exists_fn: Callable[[dict], bool] = lambda _: True



TOTAL_POWER_SENSORS = (
    UpdateSensorEntityDescription(
        key="total_input",
        name="Total power input",
        # native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        # suggested_display_precision=0,
        # value_fn=attrgetter("power_threshold"),
        value_fn=lambda resp: get_value("grid", resp, multiply=100),
        exists_fn=lambda entry: bool("grid" in entry),
    ),
    UpdateSensorEntityDescription(
        key="total_ouput",
        name="Total power output",
        # native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        # suggested_display_precision=0,
        # value_fn=attrgetter("power_threshold"),
        value_fn=lambda resp: get_value("grid", resp, multiply=100),
        exists_fn=lambda entry: bool("grid" in entry),
    ),

)


@dataclass(frozen=True, kw_only=True)
class ShareSensorEntityDescription(SensorEntityDescription):
    """Provide a description of a Heat pump Signal sensor."""

    depending_on: list[str]
    value_fn: Callable[[dict], float | None] = None


SHARE_SENSOR = ShareSensorEntityDescription(
    # key="grid_share",
    # name="Grid share",
    native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=0,
    depending_on=["total_input", "total_output"],
    # value_fn=lambda resp: get_value("grid", resp, multiply=100),
)



# SHARE_SENSORS = (
#     ShareSensorEntityDescription(
#         key="grid_share",
#         name="Grid share",
#         native_unit_of_measurement=PERCENTAGE,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=0,
#         # value_fn=attrgetter("power_threshold"),
#         source_entites=["total_input", "total_output"],
#         value_fn=lambda resp: get_value("grid", resp, multiply=100),
#         # exists_fn=lambda entry: bool("grid" in entry),
#     ),
#     ShareSensorEntityDescription(
#         key="pv_share",
#         name="PV share",
#         native_unit_of_measurement=PERCENTAGE,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=0,
#         # value_fn=attrgetter("power_threshold"),
#         source_entites=["total_input", "total_output"],
#         value_fn=lambda resp: get_value("pv_system", resp, multiply=100),
#         # exists_fn=lambda entry: bool("pv_system" in entry),
#     ),
# )


# @dataclass(frozen=True, kw_only=True)
# class PriceSensorEntityDescription(SensorEntityDescription):
#     """Provide a description of a Heat pump Signal sensor."""

#     value_fn: Callable[[dict], float | None]
#     exists_fn: Callable[[dict], bool] = lambda _: True


# PRICE_SENSORS = (
#     PriceSensorEntityDescription(
#         key="cost_of_energy",
#         name="Costs of energy",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["write_off"],
#         exists_fn=lambda entry: bool("write_off" in entry),
#     ),
#     PriceSensorEntityDescription(
#         key="levelized_costs_of_energy",
#         name="Levelized costs of energy",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["lifetime"],
#         exists_fn=lambda entry: bool("lifetime" in entry),
#     ),
# )


# @dataclass(frozen=True, kw_only=True)
# class Co2IntensitySensorEntityDescription(SensorEntityDescription):
#     """Provide a description of a Heat pump Signal sensor."""

#     value_fn: Callable[[dict], float | None]
#     exists_fn: Callable[[dict], bool] = lambda _: True


# CO2_INTENSITY_SENSORS = (
#     Co2IntensitySensorEntityDescription(
#         key="co2_intensity_write_off",
#         name="Co2 intensity write off",
#         native_unit_of_measurement="gco2/kWh",
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=1,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["write_off"],
#         exists_fn=lambda entry: bool("write_off" in entry),
#     ),
#     Co2IntensitySensorEntityDescription(
#         key="co2_intensity_lifetime",
#         name="Co2 intensity lifetime",
#         native_unit_of_measurement="gco2/kWh",
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=1,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["lifetime"],
#         exists_fn=lambda entry: bool("lifetime" in entry),
#     ),
# )


# @dataclass(frozen=True, kw_only=True)
# class SavingsSensorEntityDescription(SensorEntityDescription):
#     """Provide a description of a Heat pump Signal sensor."""

#     value_fn: Callable[[dict], float | None]
#     exists_fn: Callable[[dict], bool] = lambda _: True


# CURRENT_COSTS_SAVINGS_SENSORS = (
#     SavingsSensorEntityDescription(
#         key="pv_current_costs_savings",
#         name="PV system current savings",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["pv_system"]["write_off"],
#         exists_fn=lambda entry: bool("write_off" in entry.get("pv_system", {})),
#     ),
#     SavingsSensorEntityDescription(
#         key="pv_current_costs_savings_lcoe",
#         name="PV system current savings lcoe",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["pv_system"]["lifetime"],
#         exists_fn=lambda entry: bool("lifetime" in entry.get("pv_system", {})),
#     ),
#     SavingsSensorEntityDescription(
#         key="bat_current_costs_savings",
#         name="Battery current savings",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["battery"]["write_off"],
#         exists_fn=lambda entry: bool("write_off" in entry.get("battery", {})),
#     ),
#     SavingsSensorEntityDescription(
#         key="bat_current_costs_savings_lcoe",
#         name="Battery current savings lcoe",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["battery"]["lifetime"],
#         exists_fn=lambda entry: bool("lifetime" in entry.get("battery", {})),
#     ),
# )


# CURRENT_CO2_SAVINGS_SENSORS = (
#     SavingsSensorEntityDescription(
#         key="pv_current_co2_savings",
#         name="PV system current savings",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["write_off"],
#         exists_fn=lambda entry: bool("write_off" in entry),
#     ),
#     SavingsSensorEntityDescription(
#         key="pv_current_co2_savings_lcoe",
#         name="PV system current savings lcoe",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["lifetime"],
#         exists_fn=lambda entry: bool("lifetime" in entry),
#     ),
#     SavingsSensorEntityDescription(
#         key="bat_current_co2_savings",
#         name="Battery current savings",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["write_off"],
#         exists_fn=lambda entry: bool("write_off" in entry),
#     ),
#     SavingsSensorEntityDescription(
#         key="bat_current_co2_savings_lcoe",
#         name="Battery current savings lcoe",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["lifetime"],
#         exists_fn=lambda entry: bool("lifetime" in entry),
#     ),
# )


# TOTAL_COSTS_SAVINGS_SENSORS = (
#     SavingsSensorEntityDescription(
#         key="pv_total_costs_savings",
#         name="PV system total savings",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["write_off"],
#         exists_fn=lambda entry: bool("write_off" in entry),
#     ),
#     SavingsSensorEntityDescription(
#         key="pv_total_costs_savings_lcoe",
#         name="PV system total savings lcoe",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["lifetime"],
#         exists_fn=lambda entry: bool("lifetime" in entry),
#     ),
#     SavingsSensorEntityDescription(
#         key="bat_total_costs_savings",
#         name="Battery total savings",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["write_off"],
#         exists_fn=lambda entry: bool("write_off" in entry),
#     ),
#     SavingsSensorEntityDescription(
#         key="bat_total_costs_savings_lcoe",
#         name="Battery total savings lcoe",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["lifetime"],
#         exists_fn=lambda entry: bool("lifetime" in entry),
#     ),
# )


# TOTAL_CO2_SAVINGS_SENSORS = (
#     SavingsSensorEntityDescription(
#         key="pv_total_co2_savings",
#         name="PV system total savings",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["write_off"],
#         exists_fn=lambda entry: bool("write_off" in entry),
#     ),
#     SavingsSensorEntityDescription(
#         key="pv_total_co2_savings_lcoe",
#         name="PV system total savings lcoe",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["lifetime"],
#         exists_fn=lambda entry: bool("lifetime" in entry),
#     ),
#     SavingsSensorEntityDescription(
#         key="bat_total_co2_savings",
#         name="Battery total savings",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["write_off"],
#         exists_fn=lambda entry: bool("write_off" in entry),
#     ),
#     SavingsSensorEntityDescription(
#         key="bat_total_co2_savings_lcoe",
#         name="Battery total savings lcoe",
#         native_unit_of_measurement=CURRENCY_EURO,
#         state_class=SensorStateClass.MEASUREMENT,
#         suggested_display_precision=2,
#         # value_fn=attrgetter("power_threshold"),
#         value_fn=lambda resp: resp["lifetime"],
#         exists_fn=lambda entry: bool("lifetime" in entry),
#     ),
# )

# Savings, total savings, costs, co2 intensity


SENSORS = TOTAL_POWER_SENSORS


async def async_setup_entry(
        hass: HomeAssistant,
        entry: MyConfigEntry,
        async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform."""
    # Access the runtime data form the config entry
    power_insight = entry.runtime_data.power_insight
    entry_id = entry.entry_id

    entities: list = []
    key_entity_mapping = {}

    # Add the total power sensors
    for description in TOTAL_POWER_SENSORS:
        source_entities = power_insight.source_entities_power
        entity = EventSensorEntity(
            description, entry, source_entities, power_insight
        )
        key_entity_mapping[description.key] = entity.unique_id
        entities.append(entity)

    # Add the share sensors
    for adapter in power_insight.power_providing_adapters:
        description = SHARE_SENSOR
        description.key = f"{adapter.name}_share"
        description.name = f"{" ".join(adapter.name.split("_")).title()} Share"
        description.value_fn = lambda obj: get_value(
            description.key, obj.shares, multiply=100
        ),
        source_entities = [
            key_entity_mapping[val] for val in description.depending_on
        ]
        entity = EventSensorEntity(
            description, entry, source_entities, power_insight
        )
        key_entity_mapping[description.key] = entity.unique_id
        entities.append(entity)

    _LOGGER.debug(f"Adding the following entities: {entities}")

    async_add_entities(entities)


class EventSensorEntity(BaseEventSensorEntity):

    entity_description: UpdateSensorEntityDescription

    def __init__(
            self,
            description: UpdateSensorEntityDescription,
            config_entry,
            source_entities,
            power_insight,
    ) -> None:
        """Initialize sensor entity."""
        super().__init__(source_entities, power_insight)
        self.entity_description = description
        self._config_entry = config_entry

        self._attr_unique_id = (
            f"{self._config_entry.entry_id}_{self.entity_description.key}"
        )
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            name=self._config_entry.title or "PowerInsight",
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        data = self.data.electricity_price
        assert data is not None
        return self.entity_description.value_fn(data)
