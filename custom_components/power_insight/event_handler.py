"""Event handler for the PowerInsight integration."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Callable, Iterable

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    EventStateReportedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_state_report_event,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.signal_type import SignalType

from .const import DOMAIN
from .utils import price_to_value, state_to_value


_LOGGER = logging.getLogger(__name__)

_INVALID_STATES = frozenset({STATE_UNAVAILABLE, STATE_UNKNOWN})


def source_signal(entry_id: str, entity_id: str) -> SignalType[datetime]:
    """Return the dispatcher signal for one source entity of one config entry.

    It is sent once the engine holds the entity's new reading, carrying the
    time of the reading. A dispatcher signal rather than a bus event: the
    recorder writes every bus event to the database, and nothing outside this
    config entry needs to see these.
    """
    return SignalType(f"{DOMAIN}_{entry_id}_{entity_id}")


@callback
def async_track_source_updates(
    hass: HomeAssistant,
    entry_id: str,
    entity_ids: Iterable[str],
    action: Callable[[datetime], None],
) -> CALLBACK_TYPE:
    """Call ``action`` with the reading's time whenever a source is updated.

    ``action`` runs once the engine already holds the new reading. Entity ids
    are lower-cased like HA's own state trackers, and a repeated one is
    connected once (the dispatcher keys its listeners by callable).
    """
    unsubs = [
        async_dispatcher_connect(hass, source_signal(entry_id, entity_id), action)
        for entity_id in dict.fromkeys(entity_id.lower() for entity_id in entity_ids)
    ]

    @callback
    def _unsubscribe() -> None:
        for unsub in unsubs:
            unsub()

    return _unsubscribe


class EventHandler:
    """Bridge between the HA event bus and the PowerInsight calculation engine.

    Responsibilities
    ----------------
    - Track ``state_changed`` and ``state_reported`` events for all source
      entities registered across all adapters.
    - Translate raw HA state strings to numeric Watt values (applying SI prefix
      scaling) and store them on the shared ``PowerInsight`` instance.
    - Send the entity's ``source_signal`` once the engine holds the reading, so
      that sensor entities belonging to *this* config entry — and only those
      that read this entity — update, and never before the engine does.

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
        self._entry_id = entry_id
        self._unsub_listeners: list = []
        #: Called after every stored reading, once the engine holds it.
        self.on_update: Callable[[], None] | None = None

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
                    else self._to_value(entity_id, state)
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

    def _to_value(self, entity_id: str, state) -> float | None:
        """Return a tracked state as the engine stores it.

        A price is normalised to currency per kWh (``ct/kWh`` and ``EUR/MWh``
        included) and is ``None`` in a unit that is not a price per energy;
        everything else is a power, normalised to W.
        """
        if entity_id in self.power_insight.source_entities_price:
            return price_to_value(state)
        return state_to_value(state)

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
        new_state = event.data["new_state"]
        self._update(
            event.data["entity_id"],
            new_state,
            # The removed entity has no state to date the change by.
            new_state.last_updated if new_state is not None else dt_util.utcnow(),
            is_report=False,
        )

    @callback
    def _update_on_state_report_callback(
        self, event: Event[EventStateReportedData]
    ) -> None:
        """Handle a source entity state report (same value, updated timestamp)."""
        self._update(
            event.data["entity_id"],
            event.data["new_state"],
            event.data["last_reported"],
            is_report=True,
        )

    def _update(
        self,
        entity_id: str,
        new_state: State | None,
        timestamp: datetime,
        *,
        is_report: bool,
    ) -> None:
        """Store the updated value on PowerInsight and notify sensor entities.

        Translates the new HA state to a numeric value and writes it to the
        ``PowerInsight`` engine, then sends the entity's ``source_signal`` with
        the reading's time so downstream sensors re-read their values. The
        timestamp is the source's own (``last_updated`` for a change,
        ``last_reported`` for a report), so running totals measure elapsed
        time without this callback's processing delay.

        Args:
            entity_id:  The entity whose state changed or was reported.
            new_state:  Its state now (``None`` once the entity is removed).
            timestamp:  When the reading was taken.
            is_report:  ``True`` for ``state_reported``, ``False`` for
                ``state_changed``.

        """
        if new_state is None:
            # Entity was removed from HA; mark as unavailable.
            value = None
        elif new_state.state in _INVALID_STATES:
            value = None
        else:
            value = self._to_value(entity_id, new_state)

        value_changed = self.power_insight.set_value(entity_id, value)
        if self.on_update is not None:
            self.on_update()

        # state_reported: always send — running totals need the new timestamp
        # to advance their accumulation even if the rate is unchanged.
        # state_changed: only send when the stored numeric value actually
        # changed; if the HA state string changed but the float is identical
        # there is nothing for sensors to recalculate.
        if is_report or value_changed:
            async_dispatcher_send(
                self.hass, source_signal(self._entry_id, entity_id), timestamp
            )
