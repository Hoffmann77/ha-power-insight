"""Numeric integration of data coming from a source sensor over time."""

from __future__ import annotations

import logging
# from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.components.integration.sensor import (
    IntegrationSensor,
)
from homeassistant.const import (
    STATE_UNAVAILABLE,
)
from homeassistant.core import (
    Event,
    EventStateChangedData,
    EventStateReportedData,
    State,
    callback,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_state_report_event,
)

# from .const import ()
from .power_insight import PowerInsight


_LOGGER = logging.getLogger(__name__)

# SI Metric prefixes
UNIT_PREFIXES = {None: 1, "k": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}


class BaseEventSensorEntity(SensorEntity):
    """Representation of an integration sensor."""

    _attr_should_poll = False

    def __init__(
        self,
        source_entities: list[str],
        power_insight: PowerInsight,
        allow_freeze: bool = False,
    ) -> None:
        """Initialize the integration sensor."""
        self._source_entities = source_entities
        self.power_insight = power_insight
        self._state: float | None = None
        self._allow_freeze = allow_freeze
        self._freeze_callbacks = {}

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added to hass."""
        await super().async_added_to_hass()

        _LOGGER.debug(f"Added to hass: {self}")
        _LOGGER.debug(f"Source entities: {self._source_entities}")

        # Collect the state of the state obj to provide initial data.
        for entity_id in self._source_entities:
            if (
                state := self.hass.states.get(entity_id)
            ) and state.state != STATE_UNAVAILABLE:
                value = self._state_to_value(state)
                self.power_insight.set_value(entity_id, value)
                _LOGGER.debug(f"Set initial value at startup {entity_id}: {value}")

        handle_state_change = self._update_on_state_change_callback
        handle_state_report = self._update_on_state_report_callback

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._source_entities,
                handle_state_change,
            )
        )
        # self.async_on_remove(
        #     async_track_state_report_event(
        #         self.hass,
        #         self._source_entities,
        #         handle_state_report,
        #     )
        # )

    def _schedule_freeze_cancellation(
        self, freeze_for: timedelta, entity_id, value,
    ) -> None:
        """Schedule possible integration using the source state and max_sub_interval.

        The callback reference is stored for possible cancellation if the source state
        reports a change before max_sub_interval has passed.

        If the callback is executed, meaning there was no state change reported, the
        source_state is assumed constant and integration is done using its value.
        """
        # if (
        #     self._max_sub_interval is not None
        #     and source_state is not None
        #     and (source_state_dec := _decimal_state(source_state.state)) is not None
        # ):

        @callback
        def _cancel_freeze_on_interval_exceeded_callback(now: datetime) -> None:
            """Integrate based on time and reschedule."""

            self._attr_available = False

            self.power_insight.set_value(entity_id, value)

            self.async_write_ha_state()

            # elapsed_seconds = Decimal(
            #     (now - self._last_integration_time).total_seconds()
            # )
            # self._derive_and_set_attributes_from_state(source_state)
            # area = self._method.calculate_area_with_one_state(
            #     elapsed_seconds, source_state_dec
            # )
            # self._update_integral(area)
            # self.async_write_ha_state()

            # self._last_integration_time = datetime.now(tz=UTC)
            # self._last_integration_trigger = _IntegrationTrigger.TimeElapsed

            # self._schedule_max_sub_interval_exceeded_if_state_is_numeric(
            #     source_state
            # )

        # self._freeze_cancellation_callback = async_call_later(
        #     self.hass,
        #     freeze_for,
        #     _cancel_freeze_on_interval_exceeded_callback,
        # )

        return async_call_later(
            self.hass,
            freeze_for,
            _cancel_freeze_on_interval_exceeded_callback,
        )

    # def _cancel_freeze_cancellation_callback(self) -> None:
    #     self._freeze_cancellation_callback()



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
        """Update the data on state change.

        Ref: https://www.home-assistant.io/docs/configuration/events/#state_changed  #noqa

        """
        # The state has been removed.
        if new_state is None:
            _LOGGER.debug("Update on state change new state None")
            return

        helper = "state_obj None" if old_state is None else f"{old_state.state}"
        _LOGGER.debug(f"Update on state change entity: {entity_id} old: {helper}: new: {new_state.state}")

        # Detect unexpected behaviour in future hass updates.
        # if not new_state.state == old_state.state:
        #     raise ValueError("Not expected behaviour detected.")

        # The new state does not provide usable data.
        if new_state.state == STATE_UNAVAILABLE:
            # TODO:
            # Try to use the old data for a short period of time
            # to compensate for short sensor hickups.
            if self._allow_freeze:
                freeze_for = None
                cancel = self._schedule_freeze_cancellation(
                    freeze_for, entity_id, None
                )
                self.async_on_remove(cancel)
                self._freeze_callbacks[entity_id, cancel]

            else:
                self._attr_available = False
                self.async_write_ha_state()

            return

        # The state is set for the first time.
        if old_state is None:
            pass

        elif old_state.state == STATE_UNAVAILABLE:
            # The state changed from state_unavailable to usable data
            # https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/entity.py LN 1332
            cancel = self._freeze_callbacks.pop(entity_id, False)
            if cancel:
                self._on_remove.remove(cancel)
                cancel()

        self._attr_available = True

        # Set new value
        value = self._state_to_value(new_state)
        self.power_insight.set_value(entity_id, value)

        self.async_write_ha_state()

    def _state_to_value(self, state_obj: State) -> float | None:
        """Convert the state obj into a float value."""
        try:
            value = float(state_obj.state)
        except ValueError:
            return None

        if unit := state_obj.attributes.get("unit_of_measurement"):
            unit = unit[0]

        return value * UNIT_PREFIXES.get(unit, 1.0)

    @property
    def native_value(self) -> float | None:
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
