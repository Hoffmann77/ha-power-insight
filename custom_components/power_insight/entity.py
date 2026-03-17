"""Numeric integration of data coming from a source sensor over time."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
import logging
from typing import TYPE_CHECKING, Any, Final, Self

import logging
# from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from homeassistant.components.sensor import (
    DEVICE_CLASS_UNITS,
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
    SensorEntity,
    RestoreSensor,
    SensorDeviceClass,
    SensorExtraStoredData,
    SensorStateClass,
)
from homeassistant.components.integration.sensor import (
    IntegrationSensor,
)
from homeassistant.const import (
    STATE_UNAVAILABLE,
    UnitOfTime,
)
from homeassistant.core import (
    Event,
    EventStateChangedData,
    EventStateReportedData,
    State,
    callback,
    HomeAssistant,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_state_report_event,
)

from .event import (
    async_track_power_insight_state_change_event,
    async_track_power_insight_state_report_event,
)
from .power_insight import PowerInsight



_LOGGER = logging.getLogger(__name__)

# SI Metric prefixes
UNIT_PREFIXES = {None: 1, "k": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}

# SI Time prefixes
UNIT_TIME = {
    UnitOfTime.SECONDS: 1,
    UnitOfTime.MINUTES: 60,
    UnitOfTime.HOURS: 60 * 60,
    UnitOfTime.DAYS: 24 * 60 * 60,
}


class BaseEventSensorEntity(SensorEntity):
    """Sensor entity that updates the power insight instance.

    This entity updates the underlying instance of `PowerInsight`
    when the state changed or state reported events for any of the
    source entities is fired.

    This allows us to pass data from the any source entity to a single
    underlying instance of `PowerInsight` which can perform calculations
    using all necessary values.

    """

    _attr_should_poll = False

    def __init__(
        self,
        source_entities: list[str],
        power_insight: PowerInsight,
    ) -> None:
        """Initialize the sensor entity."""
        self._source_entities = source_entities
        self.power_insight = power_insight
        self._state: float | None = None

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added to hass."""
        await super().async_added_to_hass()

        handle_state_change = self._update_on_state_change_callback
        handle_state_report = self._update_on_state_report_callback

        self.async_on_remove(
            async_track_power_insight_state_change_event(
                self.hass,
                self.config_entry.entry_id,
                self._source_entities,
                handle_state_change,
            )
        )
        self.async_on_remove(
            async_track_power_insight_state_report_event(
                self.hass,
                self.config_entry.entry_id,
                self._source_entities,
                handle_state_report,
            )
        )

    @callback
    def _update_on_state_change_callback(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle sensor state change."""
        self.async_write_ha_state()

    @callback
    def _update_on_state_report_callback(
        self, event: Event[EventStateReportedData]
    ) -> None:
        """Handle sensor state report."""
        self.async_write_ha_state()

    # def _update_on_state_change(
    #     self,
    #     entity_id: str,
    #     new_state: State | None,
    #     old_state: State | None,
    #     old_last_reported: datetime | None,
    # ) -> None:
    #     """Update the data on state change.

    #     Ref: https://www.home-assistant.io/docs/configuration/events/#state_changed  #noqa

    #     """
    #     if new_state is None:
    #         return

    #     helper = "state_obj None" if old_state is None else f"{old_state.state}"
    #     _LOGGER.debug(f"Update on state change entity: {entity_id} old: {helper}: new: {new_state.state}")

    #     if new_state.state == STATE_UNAVAILABLE:
    #         # The entity is currently not available.
    #         if self._keep_alive and old_state:
    #             cancel = self._schedule_freeze_cancellation(
    #                 self._keep_alive, entity_id, None
    #             )
    #             self.async_on_remove(cancel)
    #             self._freeze_callbacks[entity_id] = cancel
    #         else:
    #             self._attr_available = False
    #             self.async_write_ha_state()

    #         return

    #     if old_state and old_state.state == STATE_UNAVAILABLE:
    #         # The state changed from state_unavailable to usable data
    #         # https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/entity.py LN 1332  # noqa
    #         cancel = self._freeze_callbacks.pop(entity_id, False)
    #         if cancel:
    #             self._on_remove.remove(cancel)
    #             cancel()

    #     # Remove the entity from the report event listener
    #     # as soon as we get the initial data.
    #     if entity_id in self._cancel_report_listener_callbacks:
    #         cancel = self.report_cancel_callbacks[entity_id]
    #         self._on_remove.remove(cancel)
    #         cancel()

    #     self._attr_available = True

    #     # Pass the value of the state to the `PowerInsight` instance.
    #     value = self._state_to_value(new_state)
    #     self.power_insight.set_value(entity_id, value)

    #     self.async_write_ha_state()

    # def _state_to_value(self, state_obj: State) -> float | None:
    #     """Return the state of the given state object as float."""
    #     try:
    #         value = float(state_obj.state)
    #     except ValueError:
    #         return None

    #     if unit := state_obj.attributes.get("unit_of_measurement"):
    #         unit = unit[0]

    #     return value * UNIT_PREFIXES.get(unit, 1.0)


METHOD_TRAPEZOIDAL = "trapezoidal"
METHOD_LEFT = "left"
METHOD_RIGHT = "right"
INTEGRATION_METHODS = [METHOD_TRAPEZOIDAL, METHOD_LEFT, METHOD_RIGHT]


class _IntegrationMethod(ABC):
    @staticmethod
    def from_name(method_name: str) -> _IntegrationMethod:
        return _NAME_TO_INTEGRATION_METHOD[method_name]()

    @abstractmethod
    def validate_states(self, left: str, right: str) -> tuple[Decimal, Decimal] | None:
        """Check state requirements for integration."""

    @abstractmethod
    def calculate_area_with_two_states(
        self, elapsed_time: Decimal, left: Decimal, right: Decimal
    ) -> Decimal:
        """Calculate area given two states."""

    def calculate_area_with_one_state(
        self, elapsed_time: Decimal, constant_state: Decimal
    ) -> Decimal:
        return constant_state * elapsed_time


class _Trapezoidal(_IntegrationMethod):
    def calculate_area_with_two_states(
        self, elapsed_time: Decimal, left: Decimal, right: Decimal
    ) -> Decimal:
        return elapsed_time * (left + right) / 2

    def validate_states(self, left: str, right: str) -> tuple[Decimal, Decimal] | None:
        if (left_dec := _decimal_state(left)) is None or (
            right_dec := _decimal_state(right)
        ) is None:
            return None
        return (left_dec, right_dec)


class _Left(_IntegrationMethod):
    def calculate_area_with_two_states(
        self, elapsed_time: Decimal, left: Decimal, right: Decimal
    ) -> Decimal:
        return self.calculate_area_with_one_state(elapsed_time, left)

    def validate_states(self, left: str, right: str) -> tuple[Decimal, Decimal] | None:
        if (left_dec := _decimal_state(left)) is None:
            return None
        return (left_dec, left_dec)


class _Right(_IntegrationMethod):
    def calculate_area_with_two_states(
        self, elapsed_time: Decimal, left: Decimal, right: Decimal
    ) -> Decimal:
        return self.calculate_area_with_one_state(elapsed_time, right)

    def validate_states(self, left: str, right: str) -> tuple[Decimal, Decimal] | None:
        if (right_dec := _decimal_state(right)) is None:
            return None
        return (right_dec, right_dec)


def _decimal_state(state: str) -> Decimal | None:
    try:
        return Decimal(state)
    except (InvalidOperation, TypeError):
        return None


_NAME_TO_INTEGRATION_METHOD: dict[str, type[_IntegrationMethod]] = {
    METHOD_LEFT: _Left,
    METHOD_RIGHT: _Right,
    METHOD_TRAPEZOIDAL: _Trapezoidal,
}




@dataclass
class IntegrationSensorExtraStoredData(SensorExtraStoredData):
    """Object to hold extra stored data."""

    # source_entity: str | None
    last_valid_state: Decimal | None

    def as_dict(self) -> dict[str, Any]:
        """Return a dict representation of the utility sensor data."""
        data = super().as_dict()
        # data["source_entity"] = self.source_entity
        data["last_valid_state"] = (
            str(self.last_valid_state) if self.last_valid_state else None
        )
        return data

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> Self | None:
        """Initialize a stored sensor state from a dict."""
        extra = SensorExtraStoredData.from_dict(restored)
        if extra is None:
            return None

        # source_entity = restored.get(ATTR_SOURCE_ID)

        try:
            last_valid_state = (
                Decimal(str(restored.get("last_valid_state")))
                if restored.get("last_valid_state")
                else None
            )
        except InvalidOperation:
            # last_period is corrupted
            _LOGGER.error("Could not use last_valid_state")
            return None

        if last_valid_state is None:
            return None

        return cls(
            extra.native_value,
            extra.native_unit_of_measurement,
            # source_entity,
            last_valid_state,
        )




class BaseEventIntegrationSensorEntity(RestoreSensor):
    """Representation of an integration sensor."""

    _attr_state_class = SensorStateClass.TOTAL
    _attr_should_poll = False

    def __init__(
        self,
        # hass: HomeAssistant,
        # *,
        source_entities: list[str],
        power_insight: PowerInsight,
        
        
        # integration_method: str,
        # name: str | None,
        # round_digits: int | None,
        # source_entity: str,
        # unique_id: str | None,
        # unit_prefix: str | None,
        # unit_time: UnitOfTime,
        # max_sub_interval: timedelta | None,
    ) -> None:
        """Initialize the integration sensor."""
        self._source_entities = source_entities
        self.power_insight = power_insight
        
        self._last_integration_value = None
        # self._last_valid_integration_value = None
        
        self._state: Decimal | None = None
        self._last_valid_state: Decimal | None = None
        
        self._last_integration_time: datetime = datetime.now(tz=UTC)
        
        
        # self._attr_unique_id = unique_id
        # self._sensor_source_id = source_entity
        # self._round_digits = round_digits
        
        self._method = _IntegrationMethod.from_name("left") # (integration_method)

        # self._attr_name = name if name is not None else f"{source_entity} integral"
        # self._unit_prefix_string = "" if unit_prefix is None else unit_prefix
        # self._unit_of_measurement: str | None = None
        self._unit_prefix = UNIT_PREFIXES[None]
        
        self._unit_time = UNIT_TIME[UnitOfTime.HOURS]
        
        # self._unit_time_str = unit_time
        # self._attr_icon = "mdi:chart-histogram"
        # self._source_entity: str = source_entity
        
        # self.device_entry = async_entity_id_to_device(
        #     hass,
        #     source_entity,
        # )
        # self._max_sub_interval: timedelta | None = (
        #     None  # disable time based integration
        #     if max_sub_interval is None or max_sub_interval.total_seconds() == 0
        #     else max_sub_interval
        # )
        # self._max_sub_interval_exceeded_callback: CALLBACK_TYPE = lambda *args: None
        # self._last_integration_trigger = _IntegrationTrigger.StateEvent
        # self._attr_suggested_display_precision = round_digits or 2

    # def _calculate_unit(self, source_unit: str) -> str:
    #     """Multiply source_unit with time unit of the integral.

    #     Possibly cancelling out a time unit in the denominator of the source_unit.
    #     Note that this is a heuristic string manipulation method and might not
    #     transform all source units in a sensible way.

    #     Examples:
    #     - Speed to distance: 'km/h' and 'h' will be transformed to 'km'
    #     - Power to energy: 'W' and 'h' will be transformed to 'Wh'

    #     """
    #     unit_time = self._unit_time_str
    #     if source_unit.endswith(f"/{unit_time}"):
    #         integral_unit = source_unit[0 : (-(1 + len(unit_time)))]
    #     else:
    #         integral_unit = f"{source_unit}{unit_time}"

    #     return f"{self._unit_prefix_string}{integral_unit}"



    # def _derive_and_set_attributes_from_state(self, source_state: State) -> None:
    #     source_unit = source_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        
    #     if source_unit is not None:
    #         self._unit_of_measurement = self._calculate_unit(source_unit)
    #     else:
    #         # If the source has no defined unit we cannot derive a unit for the integral
    #         self._unit_of_measurement = None

    #     self._attr_device_class = self._calculate_device_class(
    #         source_state.attributes.get(ATTR_DEVICE_CLASS), self.unit_of_measurement
    #     )
    #     if self._attr_device_class:
    #         self._attr_icon = None  # Remove this sensors icon default and allow to fallback to the device class default
    #     else:
    #         self._attr_icon = "mdi:chart-histogram"

    def _update_integral(self, area: Decimal) -> None:
        area_scaled = area / (self._unit_prefix * self._unit_time)
        if isinstance(self._state, Decimal):
            self._state += area_scaled
        else:
            self._state = area_scaled
        
        _LOGGER.debug(
            "area = %s, area_scaled = %s new state = %s", area, area_scaled, self._state
        )
        
        self._last_valid_state = self._state
        
    

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        #
        # Restore the state state of the integration sensor.
        #
        
        if (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._state = (
                Decimal(str(last_sensor_data.native_value))
                if last_sensor_data.native_value
                else last_sensor_data.last_valid_state
            )
            self._attr_native_value = last_sensor_data.native_value
            # self._unit_of_measurement = last_sensor_data.native_unit_of_measurement
            self._last_valid_state = last_sensor_data.last_valid_state

            _LOGGER.debug(
                "Restored state %s and last_valid_state %s",
                self._state,
                self._last_valid_state,
            )
        
        # if self._max_sub_interval is not None:
        #     source_state = self.hass.states.get(self._sensor_source_id)
        #     self._schedule_max_sub_interval_exceeded_if_state_is_numeric(source_state)
        #     self.async_on_remove(self._cancel_max_sub_interval_exceeded_callback)
        #     handle_state_change = self._integrate_on_state_change_with_max_sub_interval
        #     handle_state_report = self._integrate_on_state_report_with_max_sub_interval
        # else:
            
        handle_state_change = self._integrate_on_state_change_callback
        handle_state_report = self._integrate_on_state_report_callback

        self.async_on_remove(
            async_track_power_insight_state_change_event(
                self.hass,
                self.config_entry.entry_id,
                self._source_entities,
                handle_state_change,
            )
        )
        self.async_on_remove(
            async_track_power_insight_state_report_event(
                self.hass,
                self.config_entry.entry_id,
                self._source_entities,
                handle_state_report,
            )
        )

    # @callback
    # def _integrate_on_state_change_with_max_sub_interval(
    #     self, event: Event[EventStateChangedData]
    # ) -> None:
    #     """Handle sensor state update when sub interval is configured."""
    #     self._integrate_on_state_update_with_max_sub_interval(
    #         None, None, event.data["old_state"], event.data["new_state"]
    #     )

    # @callback
    # def _integrate_on_state_report_with_max_sub_interval(
    #     self, event: Event[EventStateReportedData]
    # ) -> None:
    #     """Handle sensor state report when sub interval is configured."""
    #     self._integrate_on_state_update_with_max_sub_interval(
    #         event.data["old_last_reported"],
    #         event.data["last_reported"],
    #         None,
    #         event.data["new_state"],
    #     )

    # @callback
    # def _integrate_on_state_update_with_max_sub_interval(
    #     self,
    #     old_timestamp: datetime | None,
    #     new_timestamp: datetime | None,
    #     old_state: State | None,
    #     new_state: State | None,
    # ) -> None:
    #     """Integrate based on state change and time.

    #     Next to doing the integration based on state change this method cancels and
    #     reschedules time based integration.
    #     """
    #     self._cancel_max_sub_interval_exceeded_callback()
    #     try:
    #         self._integrate_on_state_change(
    #             old_timestamp, new_timestamp, old_state, new_state
    #         )
    #         self._last_integration_trigger = _IntegrationTrigger.StateEvent
    #         self._last_integration_time = datetime.now(tz=UTC)
    #     finally:
    #         # When max_sub_interval exceeds without state change the source is assumed
    #         # constant with the last known state (new_state).
    #         self._schedule_max_sub_interval_exceeded_if_state_is_numeric(new_state)

    @callback
    def _integrate_on_state_change_callback(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle sensor state change."""
        return self._integrate_on_state_change(
            event.data["entity_id"],
            event.data["old_state"],
            event.data["new_state"],
            None,
        )
        
        # return self._integrate_on_state_change(
            
        #     None, None, event.data["old_state"], event.data["new_state"]
        # )

    @callback
    def _integrate_on_state_report_callback(
        self, event: Event[EventStateReportedData]
    ) -> None:
        """Handle sensor state report."""
        return self._integrate_on_state_change(
            event.data["entity_id"],
            None,
            None,
            event.data["new_state"],
        )

    def _integrate_on_state_change(
        self,
        entity_id: str,
        old_state: State | None,
        new_state: State | None,
        curr_state: State | None,
    ) -> None:
        """Integrate on state change."""
        
        now = datetime.now(tz=UTC)
        
        right_value = self.integration_value
        _LOGGER.debug(f"right value {right_value}")
        
        if self._last_integration_value is not None:
            left_value = self._last_integration_value
            _LOGGER.debug(f"set left value {left_value}")
        else:
            self._last_integration_value = right_value
            _LOGGER.debug(f"set right value {right_value}")
            self.async_write_ha_state()
            return
        
        if not (
            states := self._method.validate_states(left_value, right_value)
        ):
            self.async_write_ha_state()
            return
        
        # HINT: maybe use the timestamp of new_state.
        elapsed_seconds = Decimal(
            (now - self._last_integration_time).total_seconds()
        )
        _LOGGER.debug(f"elapsed seconds: {elapsed_seconds}")
        
        _LOGGER.debug(f"values: {left_value} {right_value}")
        
        area = self._method.calculate_area_with_two_states(
            elapsed_seconds, *states,
        )
        _LOGGER.debug(f"area: {area}")

        self._update_integral(area)
        
        self._last_integration_time = now
        
        _LOGGER.debug(f"_state: {self._state}")
        
        
        self._last_integration_value = right_value
        

        self.async_write_ha_state()
        




    # def _integrate_on_state_change(
    #     self,
    #     old_timestamp: datetime | None,
    #     new_timestamp: datetime | None,
    #     old_state: State | None,
    #     new_state: State | None,
    # ) -> None:
    #     if new_state is None:
    #         return

    #     if new_state.state == STATE_UNAVAILABLE:
    #         self._attr_available = False
    #         self.async_write_ha_state()
    #         return

    #     if old_state:
    #         # state has changed, we recover old_state from the event
    #         new_timestamp = new_state.last_updated
    #         old_state_state = old_state.state
    #         old_timestamp = old_state.last_reported
    #     else:
    #         # first state or event state reported without any state change
    #         old_state_state = new_state.state

    #     self._attr_available = True
    #     self._derive_and_set_attributes_from_state(new_state)

    #     if old_timestamp is None and old_state is None:
    #         self.async_write_ha_state()
    #         return

    #     if not (
    #         states := self._method.validate_states(old_state_state, new_state.state)
    #     ):
    #         self.async_write_ha_state()
    #         return

    #     if TYPE_CHECKING:
    #         assert new_timestamp is not None
    #         assert old_timestamp is not None

    #     elapsed_seconds = Decimal(
    #         (new_timestamp - old_timestamp).total_seconds()
    #         if self._last_integration_trigger == _IntegrationTrigger.StateEvent
    #         else (new_timestamp - self._last_integration_time).total_seconds()
    #     )

    #     area = self._method.calculate_area_with_two_states(elapsed_seconds, *states)

    #     self._update_integral(area)
    #     self.async_write_ha_state()

    # def _schedule_max_sub_interval_exceeded_if_state_is_numeric(
    #     self, source_state: State | None
    # ) -> None:
    #     """Schedule possible integration using the source state and max_sub_interval.

    #     The callback reference is stored for possible cancellation if the source state
    #     reports a change before max_sub_interval has passed.

    #     If the callback is executed, meaning there was no state change reported, the
    #     source_state is assumed constant and integration is done using its value.
    #     """
    #     if (
    #         self._max_sub_interval is not None
    #         and source_state is not None
    #         and (source_state_dec := _decimal_state(source_state.state)) is not None
    #     ):

    #         @callback
    #         def _integrate_on_max_sub_interval_exceeded_callback(now: datetime) -> None:
    #             """Integrate based on time and reschedule."""
    #             elapsed_seconds = Decimal(
    #                 (now - self._last_integration_time).total_seconds()
    #             )
    #             self._derive_and_set_attributes_from_state(source_state)
    #             area = self._method.calculate_area_with_one_state(
    #                 elapsed_seconds, source_state_dec
    #             )
    #             self._update_integral(area)
    #             self.async_write_ha_state()

    #             self._last_integration_time = datetime.now(tz=UTC)
    #             self._last_integration_trigger = _IntegrationTrigger.TimeElapsed

    #             self._schedule_max_sub_interval_exceeded_if_state_is_numeric(
    #                 source_state
    #             )

    #         self._max_sub_interval_exceeded_callback = async_call_later(
    #             self.hass,
    #             self._max_sub_interval,
    #             _integrate_on_max_sub_interval_exceeded_callback,
    #         )

    # def _cancel_max_sub_interval_exceeded_callback(self) -> None:
    #     self._max_sub_interval_exceeded_callback()

    @property
    def native_value(self) -> Decimal | None:
        """Return the state of the sensor."""
        # if isinstance(self._state, Decimal) and self._round_digits:
        #     return round(self._state, self._round_digits)

        return self._state

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

    @property
    def extra_restore_state_data(self) -> IntegrationSensorExtraStoredData:
        """Return sensor specific state data to be restored."""
        return IntegrationSensorExtraStoredData(
            self.native_value,
            self.native_unit_of_measurement,
            # self._source_entities,
            self._last_valid_state,
        )
    
    async def async_set_value(self, value):
        """Set the entity to a specific value."""
        self._state = value
        self.async_write_ha_state()

    async def async_get_last_sensor_data(
        self,
    ) -> IntegrationSensorExtraStoredData | None:
        """Restore Utility Meter Sensor Extra Stored Data."""
        if (restored_last_extra_data := await self.async_get_last_extra_data()) is None:
            return None

        return IntegrationSensorExtraStoredData.from_dict(
            restored_last_extra_data.as_dict()
        )