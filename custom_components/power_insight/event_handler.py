"""Event handler for the PowerInsight integration."""

from __future__ import annotations

import logging
from typing import Iterable

from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EVENT_STATE_CHANGED,
    EVENT_STATE_REPORTED,
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
)

from .const import DOMAIN
from .power_insight import UNIT_PREFIXES


_LOGGER = logging.getLogger(__name__)


class EventHandler:
    """Handle the communication between power_insight and the event bus."""

    def __init__(self, hass, entry_id, power_insight) -> None:
        self.hass = hass
        self.power_insight = power_insight

        self._event_prefix = f"{DOMAIN}_{entry_id}_"

        self._unsub_state_change_listener = []


    def track_entities(self, entity_ids: Iterable[str]) -> None:

        handle_state_change = self._update_on_state_change_callback
        handle_state_report = self._update_on_state_report_callback

        unsub = (
            async_track_state_change_event(
                self.hass,
                entity_ids,
                handle_state_change,
            ),
            async_track_state_change_event(
                self.hass,
                entity_ids,
                handle_state_report,
            ),
        )
        self._unsub_state_change_listener.extend(unsub)

    def untrack_entities(self) -> None:
        for unsub in self._unsub_state_change_listener:
            unsub()


    @callback
    def _update_on_state_change_callback(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle sensor state change."""
        return self._update_on_state_change(
            event.data,
            event.data["entity_id"],
            event.data["old_state"],
            event.data["new_state"],
            None,
        )

    @callback
    def _update_on_state_report_callback(
        self, event: Event[EventStateReportedData]
    ) -> None:
        """Handle sensor state report."""
        return self._update_on_state_change(
            event.data,
            event.data["entity_id"],
            None,
            None,
            event.data["new_state"],
        )

    def _update_on_state_change(
        self,
        event_data: EventStateChangedData | EventStateReportedData,
        entity_id: str,
        old_state: State | None,
        new_state: State | None,
        curr_state: State | None,
        # old_timestamp: datetime | None,
        # new_timestamp: datetime | None,
    ) -> None:
        """Update the data on state change.

        Ref: https://www.home-assistant.io/docs/configuration/events/#state_changed  #noqa

        """
        INVALID_STATES = (STATE_UNAVAILABLE, STATE_UNKNOWN)

        if curr_state:
            new_state = curr_state

        # Entity was removed from Home Assistant.
        if new_state is None:
            value = None

        # Entity does not provide valid data.
        elif new_state.state in INVALID_STATES:

            # The old state was a valid value.
            if old_state and old_state not in INVALID_STATES:
                # TODO: implement a short keep alive period for the value.
                # cancel = self._schedule_freeze_cancellation(
                #     self._keep_alive, entity_id, None
                # )
                # self.async_on_remove(cancel)
                # self._freeze_callbacks[entity_id] = cancel
                value = None
            else:
                value = None

        # We expect a valid state value
        else:
            value = self._state_to_value(new_state)


        # Unfreeze the value as soon we have a new valid value.
        # https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/entity.py LN 1332  # noqa
        # if value and entity_id in self._freeze_callbacks:
        #     cancel = self._freeze_callbacks.pop(entity_id)
        #     cancel()

        # Set the value of the entity in power_insight.
        self.power_insight.set_value(entity_id, value)

        # Fire an event to notify all entities that depend on this entity_id.
        # We send a custom event to ensure that the instance is updated
        # before the entities retrieve the signal to update.
        if curr_state is not None:
            event_type = self._event_prefix + EVENT_STATE_REPORTED
        else:
            event_type = self._event_prefix + EVENT_STATE_CHANGED

        self.hass.bus.async_fire(event_type, event_data)

    def _state_to_value(self, state_obj: State) -> float | None:
        """Return the state of the given state object as float."""
        try:
            value = float(state_obj.state)
        except ValueError:
            return None

        if unit := state_obj.attributes.get("unit_of_measurement"):
            unit = unit[0]

        return value * UNIT_PREFIXES.get(unit, 1.0)
