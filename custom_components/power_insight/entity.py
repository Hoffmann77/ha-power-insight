"""Numeric integration of data coming from a source sensor over time."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
import logging
from typing import TYPE_CHECKING, Any, Final, Self

import voluptuous as vol

from homeassistant.components.sensor import (
    DEVICE_CLASS_UNITS,
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
    RestoreSensor,
    SensorEntity,
    SensorDeviceClass,
    SensorExtraStoredData,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_METHOD,
    CONF_NAME,
    CONF_UNIQUE_ID,
    STATE_UNAVAILABLE,
    UnitOfTime,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    EventStateReportedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.device import async_device_info_to_link_from_entity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_state_report_event,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    CONF_MAX_SUB_INTERVAL,
    CONF_ROUND_DIGITS,
    CONF_SOURCE_SENSOR,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_UNIT_PREFIX,
    CONF_UNIT_TIME,
    INTEGRATION_METHODS,
    METHOD_LEFT,
    METHOD_RIGHT,
    METHOD_TRAPEZOIDAL,
)

from .power_insight import PowerInsight

_LOGGER = logging.getLogger(__name__)

ATTR_SOURCE_ID: Final = "source"

# SI Metric prefixes
UNIT_PREFIXES = {None: 1, "k": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}

# SI Time prefixes
UNIT_TIME = {
    UnitOfTime.SECONDS: 1,
    UnitOfTime.MINUTES: 60,
    UnitOfTime.HOURS: 60 * 60,
    UnitOfTime.DAYS: 24 * 60 * 60,
}

DEVICE_CLASS_MAP = {
    SensorDeviceClass.POWER: SensorDeviceClass.ENERGY,
}

DEFAULT_ROUND = 3

PLATFORM_SCHEMA = vol.All(
    cv.removed(CONF_UNIT_OF_MEASUREMENT),
    SENSOR_PLATFORM_SCHEMA.extend(
        {
            vol.Optional(CONF_NAME): cv.string,
            vol.Optional(CONF_UNIQUE_ID): cv.string,
            vol.Required(CONF_SOURCE_SENSOR): cv.entity_id,
            vol.Optional(CONF_ROUND_DIGITS, default=DEFAULT_ROUND): vol.Any(
                None, vol.Coerce(int)
            ),
            vol.Optional(CONF_UNIT_PREFIX): vol.In(UNIT_PREFIXES),
            vol.Optional(CONF_UNIT_TIME, default=UnitOfTime.HOURS): vol.In(UNIT_TIME),
            vol.Remove(CONF_UNIT_OF_MEASUREMENT): cv.string,
            vol.Optional(CONF_MAX_SUB_INTERVAL): cv.positive_time_period,
            vol.Optional(CONF_METHOD, default=METHOD_TRAPEZOIDAL): vol.In(
                INTEGRATION_METHODS
            ),
        }
    ),
)










# async def async_setup_entry(
#     hass: HomeAssistant,
#     config_entry: ConfigEntry,
#     async_add_entities: AddEntitiesCallback,
# ) -> None:
#     """Initialize Integration - Riemann sum integral config entry."""
#     registry = er.async_get(hass)
#     # Validate + resolve entity registry id to entity_id
#     source_entity_id = er.async_validate_entity_id(
#         registry, config_entry.options[CONF_SOURCE_SENSOR]
#     )

#     device_info = async_device_info_to_link_from_entity(
#         hass,
#         source_entity_id,
#     )

#     if (unit_prefix := config_entry.options.get(CONF_UNIT_PREFIX)) == "none":
#         # Before we had support for optional selectors, "none" was used for selecting nothing
#         unit_prefix = None

#     if max_sub_interval_dict := config_entry.options.get(CONF_MAX_SUB_INTERVAL, None):
#         max_sub_interval = cv.time_period(max_sub_interval_dict)
#     else:
#         max_sub_interval = None

#     round_digits = config_entry.options.get(CONF_ROUND_DIGITS)
#     if round_digits:
#         round_digits = int(round_digits)

#     integral = IntegrationSensor(
#         integration_method=config_entry.options[CONF_METHOD],
#         name=config_entry.title,
#         round_digits=round_digits,
#         source_entity=source_entity_id,
#         unique_id=config_entry.entry_id,
#         unit_prefix=unit_prefix,
#         unit_time=config_entry.options[CONF_UNIT_TIME],
#         device_info=device_info,
#         max_sub_interval=max_sub_interval,
#     )

#     async_add_entities([integral])









class BaseEventUpdateSensor(SensorEntity):
    """Representation of an integration sensor."""

    _attr_should_poll = False

    def __init__(
        self,
        source_entities: list[str],
        power_insight: PowerInsight,
    ) -> None:
        """Initialize the integration sensor."""
        self._source_entities = source_entities
        self.power_insight = power_insight
        self._state: float | None = None

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added to hass."""
        await super().async_added_to_hass()

        # Collect the state of the state obj to provide initial data.
        for entity_id in self._source_entities:
            if (
                state := self.hass.states.get(entity_id)
            ) and state.state != STATE_UNAVAILABLE:
                self._grid_insight.set_value(entity_id, state.state)

        handle_state_change = self._update_on_state_change_callback
        handle_state_report = self._update_on_state_report_callback

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._sensor_source_ids,
                handle_state_change,
            )
        )
        self.async_on_remove(
            async_track_state_report_event(
                self.hass,
                self._sensor_source_ids,
                handle_state_report,
            )
        )

    @callback
    def _update_on_state_change_callback(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle sensor state change."""
        return self._update_on_state_change(
            event.data["entity_id"],
            event.data["new_state"],
            event.data["old_state"],
            None,
        )

    @callback
    def _update_on_state_report_callback(
        self, event: Event[EventStateReportedData]
    ) -> None:
        """Handle sensor state report."""
        return self._update_on_state_change(
            event.data["entity_id"],
            event.data["new_state"],
            None,
            event.data["old_last_reported"],
        )

    def _update_on_state_change(
        self,
        entity_id: str,
        new_state: State | None,
        old_state: State | None,
        old_last_reported: datetime | None,
    ) -> None:
        """Update the data on state change."""
        if new_state is None:
            return

        # Changed or reported state as unavailable
        if new_state.state == STATE_UNAVAILABLE:
            self._attr_available = False
            self.async_write_ha_state()
            return

        if old_state:
            # State has changed, we recover old_state from the event
            old_state_state = old_state.state
            old_last_reported = old_state.last_reported
        else:
            # Event state reported without any state change
            old_state_state = new_state.state

        self._attr_available = True
        # self._derive_and_set_attributes_from_state(new_state)

        if old_last_reported is None and old_state is None:
            # State was set for the first time
            self.async_write_ha_state()
            return

        if not (
            states := self._method.validate_states(old_state_state, new_state.state)
        ):
            self.async_write_ha_state()
            return



        # Set new value
        self._grid_insight.set_value(entity_id, new_state.state)

        self.async_write_ha_state()


    @property
    def native_value(self) -> Decimal | None:
        """Return the state of the sensor."""
        # if isinstance(self._state, Decimal) and self._round_digits:
        #     return round(self._state, self._round_digits)
        # return self._state

    # @property
    # def native_unit_of_measurement(self) -> str | None:
    #     """Return the unit the value is expressed in."""
    #     return self._unit_of_measurement

    # @property
    # def extra_state_attributes(self) -> dict[str, str] | None:
    #     """Return the state attributes of the sensor."""
    #     return {
    #         ATTR_SOURCE_ID: self._source_entity,
    #     }

