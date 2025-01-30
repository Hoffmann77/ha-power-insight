"""Numeric integration of data coming from a source sensor over time."""

from __future__ import annotations

import logging
# from abc import ABC, abstractmethod
from datetime import datetime

from homeassistant.components.sensor import (
    SensorEntity,
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
                self.power_insight.set_value(entity_id, state.state)

        handle_state_change = self._update_on_state_change_callback
        handle_state_report = self._update_on_state_report_callback

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._source_entities,
                handle_state_change,
            )
        )
        self.async_on_remove(
            async_track_state_report_event(
                self.hass,
                self._source_entities,
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
        self.power_insight.set_value(entity_id, new_state.state)

        self.async_write_ha_state()


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

