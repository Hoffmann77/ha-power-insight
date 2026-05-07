"""Event handler for the PowerInsight integration."""

from __future__ import annotations

import logging
from typing import Iterable

from homeassistant.const import (
    EVENT_STATE_CHANGED,
    EVENT_STATE_REPORTED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
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

from .const import DOMAIN
from .power_insight import UNIT_PREFIXES


_LOGGER = logging.getLogger(__name__)

_INVALID_STATES = frozenset({STATE_UNAVAILABLE, STATE_UNKNOWN})


class EventHandler:
    """Bridge between the HA event bus and the PowerInsight calculation engine.

    Responsibilities
    ----------------
    - Track ``state_changed`` and ``state_reported`` events for all source
      entities registered across all adapters.
    - Translate raw HA state strings to numeric Watt values (applying SI prefix
      scaling) and store them on the shared ``PowerInsight`` instance.
    - Fire scoped custom events — prefixed with ``"{DOMAIN}_{entry_id}_"`` — so
      that sensor entities belonging to *this* config entry update without
      interfering with other PowerInsight instances.

    Initialisation
    --------------
    ``track_entities`` reads the current HA state for every entity immediately
    on registration, bootstrapping ``PowerInsight`` before any event arrives.
    This means sensors display correct values as soon as the integration loads,
    rather than showing ``None`` until each source entity next changes.
    """

    def __init__(self, hass, entry_id, power_insight) -> None:
        """Initialise the event handler."""
        self.hass = hass
        self.power_insight = power_insight
        # Prefix isolates custom events for this config entry from all others.
        self._event_prefix = f"{DOMAIN}_{entry_id}_"
        self._unsub_listeners: list = []

    def track_entities(self, entity_ids: Iterable[str]) -> None:
        """Start tracking source entities and bootstrap PowerInsight immediately.

        For each entity, reads the current HA state synchronously so that
        ``PowerInsight`` is populated before any event fires.  This avoids a
        startup gap where all sensor values are ``None`` while waiting for the
        first ``state_changed`` event.

        Registers two persistent listeners per entity set:
        - ``state_changed``: fired when the numeric value changes.
        - ``state_reported``: fired when the value is re-reported without
          changing (advances the clock for integration sensors).
        """
        entity_ids = list(entity_ids)

        # Bootstrap: populate PowerInsight with whatever states HA already has.
        for entity_id in entity_ids:
            if (state := self.hass.states.get(entity_id)) is not None:
                value = (
                    None
                    if state.state in _INVALID_STATES
                    else self._state_to_value(state)
                )
                self.power_insight.set_value(entity_id, value)

        # Register persistent listeners for ongoing updates.
        self._unsub_listeners.extend([
            async_track_state_change_event(
                self.hass,
                entity_ids,
                self._update_on_state_change_callback,
            ),
            async_track_state_report_event(
                self.hass,
                entity_ids,
                self._update_on_state_report_callback,
            ),
        ])

    def untrack_entities(self) -> None:
        """Cancel all active event listeners."""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    @callback
    def _update_on_state_change_callback(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle a source entity state change."""
        self._update_on_state_change(
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
        """Handle a source entity state report (same value, updated timestamp)."""
        self._update_on_state_change(
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
    ) -> None:
        """Store the updated value on PowerInsight and notify sensor entities.

        Translates the new HA state to a numeric Watts value and writes it to
        the ``PowerInsight`` engine.  Then fires the appropriate scoped custom
        event so downstream sensor entities know to re-read their calculated
        values.

        The custom event is always fired — even for ``state_reported`` where the
        numeric value is unchanged — because integration sensors need to
        accumulate the elapsed time regardless of whether the rate has changed.

        Args:
            event_data: Raw event data forwarded verbatim to the custom event.
            entity_id:  The entity whose state changed or was reported.
            old_state:  Previous state (``state_changed`` only, else ``None``).
            new_state:  New state (``state_changed`` only, else ``None``).
            curr_state: Current state (``state_reported`` only, else ``None``).

        """
        # Unify the two event paths: curr_state is set for state_reported,
        # new_state for state_changed.
        if curr_state is not None:
            new_state = curr_state

        if new_state is None:
            # Entity was removed from HA; mark as unavailable.
            value = None
        elif new_state.state in _INVALID_STATES:
            value = None
        else:
            value = self._state_to_value(new_state)

        value_changed = self.power_insight.set_value(entity_id, value)

        is_report = curr_state is not None
        event_type = (
            self._event_prefix + EVENT_STATE_REPORTED
            if is_report
            else self._event_prefix + EVENT_STATE_CHANGED
        )

        # state_reported: always fire — integration sensors need the new
        # timestamp to advance their accumulation even if the rate is unchanged.
        # state_changed: only fire when the stored numeric value actually
        # changed; if the HA state string changed but the float is identical
        # there is nothing for sensors to recalculate.
        if is_report or value_changed:
            self.hass.bus.async_fire(event_type, event_data)

    def _state_to_value(self, state_obj: State) -> float | None:
        """Convert a HA state object to a numeric Watts value.

        Reads the ``unit_of_measurement`` attribute to apply SI prefix scaling
        so that kW, MW, etc. are all stored as Watts internally.  An unknown
        prefix is treated as ×1 (no scaling).
        """
        try:
            value = float(state_obj.state)
        except ValueError:
            return None

        # Apply SI prefix (k=10³, M=10⁶, …) based on the first character of
        # the unit string.  None key matches plain "W" or any unrecognised unit.
        if unit := state_obj.attributes.get("unit_of_measurement"):
            unit = unit[0]

        return value * UNIT_PREFIXES.get(unit, 1.0)
