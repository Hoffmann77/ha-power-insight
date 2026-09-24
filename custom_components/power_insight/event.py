"""Per-config-entry state-change/report event tracking.

Forked from ``homeassistant.helpers.event`` so that PowerInsight's scoped
custom events (prefixed per config entry) can be tracked with the same
fast entity-id routing HA uses internally. Changes from the upstream helper
are marked ``# MODIFIED``.
"""

from typing import Iterable, Callable

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
import logging
from typing import Any, Generic, TypeVar

from homeassistant.const import (
    EVENT_STATE_CHANGED,
    EVENT_STATE_REPORTED,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    # Explicit reexport of 'EventStateChangedData' for backwards compatibility
    EventStateChangedData as EventStateChangedData,  # noqa: PLC0414
    EventStateEventData,
    EventStateReportedData,
    HassJob,
    HassJobType,
    HomeAssistant,
    State,
    callback,
)
# from homeassistant.loader import bind_hass
from homeassistant.util.event_type import EventType
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


_TypedDictT = TypeVar("_TypedDictT", bound=Mapping[str, Any])


# power_insight_source_state_changed
# power_insight_source_state_reported


@dataclass(slots=True, frozen=True)
class _KeyedEventData(Generic[_TypedDictT]):
    """Class to track data for events by key."""

    listener: CALLBACK_TYPE
    callbacks: defaultdict[str, list[HassJob[[Event[_TypedDictT]], Any]]]


_TRACK_STATE_CHANGE_DATA: HassKey[_KeyedEventData[EventStateChangedData]] = HassKey(
    "track_state_change_data"
)

_TRACK_STATE_REPORT_DATA: HassKey[_KeyedEventData[EventStateReportedData]] = HassKey(
    "track_state_report_data"
)


@dataclass(slots=True, frozen=True)
class _KeyedEventTracker(Generic[_TypedDictT]):
    """Class to track events by key."""

    key: HassKey[_KeyedEventData[_TypedDictT]]
    event_type: EventType[_TypedDictT] | str
    dispatcher_callable: Callable[
        [
            HomeAssistant,
            dict[str, list[HassJob[[Event[_TypedDictT]], Any]]],
            Event[_TypedDictT],
        ],
        None,
    ]
    filter_callable: Callable[
        [
            HomeAssistant,
            dict[str, list[HassJob[[Event[_TypedDictT]], Any]]],
            _TypedDictT,
        ],
        bool,
    ]


@callback
def _async_dispatch_entity_id_event_soon[_StateEventDataT: EventStateEventData](
    hass: HomeAssistant,
    callbacks: dict[str, list[HassJob[[Event[_StateEventDataT]], Any]]],
    event: Event[_StateEventDataT],
) -> None:
    """Dispatch to listeners soon to ensure one event loop runs before dispatch."""
    hass.loop.call_soon(_async_dispatch_entity_id_event, hass, callbacks, event)


@callback
def _async_dispatch_entity_id_event[_StateEventDataT: EventStateEventData](
    hass: HomeAssistant,
    callbacks: dict[str, list[HassJob[[Event[_StateEventDataT]], Any]]],
    event: Event[_StateEventDataT],
) -> None:
    """Dispatch to listeners."""
    if not (callbacks_list := callbacks.get(event.data["entity_id"])):
        return
    for job in callbacks_list.copy():
        try:
            hass.async_run_hass_job(job, event)
        except Exception:
            _LOGGER.exception(
                "Error while dispatching event for %s to %s",
                event.data["entity_id"],
                job,
            )


@callback
def _async_state_filter[_StateEventDataT: EventStateEventData](
    hass: HomeAssistant,
    callbacks: dict[str, list[HassJob[[Event[_StateEventDataT]], Any]]],
    event_data: _StateEventDataT,
) -> bool:
    """Filter state changes by entity_id."""
    return event_data["entity_id"] in callbacks


_KEYED_TRACK_STATE_CHANGE = _KeyedEventTracker(
    key=_TRACK_STATE_CHANGE_DATA,
    event_type=EVENT_STATE_CHANGED,
    dispatcher_callable=_async_dispatch_entity_id_event_soon,
    filter_callable=_async_state_filter,
)


def async_track_power_insight_state_change_event(
    hass: HomeAssistant,
    entry_id: str,  # MODIFIED: added entry_id
    entity_ids: str | Iterable[str],
    action: Callable[[Event[EventStateChangedData]], Any],
    job_type: HassJobType | None = None,
) -> CALLBACK_TYPE:
    """Track specific state change events indexed by entity_id.

    Unlike async_track_state_change, async_track_state_change_event
    passes the full event to the callback.

    The action will not be called immediately, but will be scheduled to run
    in the next event loop iteration, even if the action is decorated with
    @callback.

    In order to avoid having to iterate a long list
    of EVENT_STATE_CHANGED and fire and create a job
    for each one, we keep a dict of entity ids that
    care about the state change events so we can
    do a fast dict lookup to route events.
    The passed in entity_ids will be automatically lower cased.

    EVENT_STATE_CHANGED is fired on each occasion the state is updated
    and changed, opposite of EVENT_STATE_REPORTED.
    """
    if not (entity_ids := _async_string_to_lower_list(entity_ids)):
        return _remove_empty_listener
    return _async_track_power_insight_state_change_event(
        hass, entry_id, entity_ids, action, job_type
    )


def _async_track_power_insight_state_change_event(
    hass: HomeAssistant,
    entry_id: str,  # MODIFIED: added entry_id
    entity_ids: str | Iterable[str],
    action: Callable[[Event[EventStateChangedData]], Any],
    job_type: HassJobType | None,
) -> CALLBACK_TYPE:
    """Faster version of async_track_state_change_event.

    The passed in entity_ids will not be automatically lower cased.
    """
    return _async_track_event(
        _KEYED_TRACK_STATE_CHANGE, hass, entry_id, entity_ids, action, job_type
    )


_KEYED_TRACK_STATE_REPORT = _KeyedEventTracker(
    key=_TRACK_STATE_REPORT_DATA,
    event_type=EVENT_STATE_REPORTED,
    dispatcher_callable=_async_dispatch_entity_id_event_soon,
    filter_callable=_async_state_filter,
)


def async_track_power_insight_state_report_event(
    hass: HomeAssistant,
    entry_id: str,  # MODIFIED: added entry_id
    entity_ids: str | Iterable[str],
    action: Callable[[Event[EventStateReportedData]], Any],
    job_type: HassJobType | None = None,
) -> CALLBACK_TYPE:
    """Track EVENT_STATE_REPORTED by entity_ids.

    EVENT_STATE_REPORTED is fired on each occasion the state is updated
    but not changed, opposite of EVENT_STATE_CHANGED.
    """
    return _async_track_event(
        _KEYED_TRACK_STATE_REPORT, hass, entry_id, entity_ids, action, job_type
    )


@callback
def _remove_empty_listener() -> None:
    """Remove a listener that does nothing."""


@callback
def _remove_listener(
    hass: HomeAssistant,
    entry_id: str,  # MODIFIED: added entry_id
    tracker: _KeyedEventTracker[_TypedDictT],
    keys: Iterable[str],
    job: HassJob[[Event[_TypedDictT]], Any],
    callbacks: dict[str, list[HassJob[[Event[_TypedDictT]], Any]]],
) -> None:
    """Remove listener."""
    for key in keys:
        callbacks[key].remove(job)
        if not callbacks[key]:
            del callbacks[key]

    if not callbacks:
        prefix = f"{DOMAIN}_{entry_id}_"  # MODIFIED: created prefix
        key = f"{prefix}{tracker.key}"
        hass.data.pop(key).listener()
        # hass.data[DOMAIN][entry_id].pop(prefix + tracker.key).listener()  # MODIFIED: added DOMAIN, entry_id and prefix


def _async_track_event(
    tracker: _KeyedEventTracker[_TypedDictT],
    hass: HomeAssistant,
    entry_id: str,  # MODIFIED: added entry_id
    keys: str | Iterable[str],
    action: Callable[[Event[_TypedDictT]], None],
    job_type: HassJobType | None,
) -> CALLBACK_TYPE:
    """Track an event by a specific key.

    This function is intended for internal use only.
    """
    if not keys:
        return _remove_empty_listener

    prefix = f"{DOMAIN}_{entry_id}_"  # MODIFIED: created prefix
    hass_data = hass.data # [DOMAIN][entry_id]  # MODIFIED: added DOMAIN and entry_id
    tracker_key = f"{prefix}{tracker.key}" # prefix + tracker.key  # MODIFIED: added prefix
    if tracker_key in hass_data:
        event_data = hass_data[tracker_key]
        callbacks = event_data.callbacks

    else:
        callbacks = defaultdict(list)
        listener = hass.bus.async_listen(
            prefix + tracker.event_type,  # MODIFIED: added prefix
            partial(tracker.dispatcher_callable, hass, callbacks),
            event_filter=partial(tracker.filter_callable, hass, callbacks),
        )
        event_data = _KeyedEventData(listener, callbacks)
        hass_data[tracker_key] = event_data

    job = HassJob(
        action, f"track {prefix + tracker.event_type} event {keys}", job_type=job_type  # MODIFIED: added prefix
    )

    if isinstance(keys, str):
        # Almost all calls to this function use a single key
        # so we optimize for that case. We don't use setdefault
        # here because this function gets called ~20000 times
        # during startup, and we want to avoid the overhead of
        # creating empty lists and throwing them away.
        callbacks[keys].append(job)
        keys = (keys,)
    else:
        for key in keys:
            callbacks[key].append(job)

    return partial(
        _remove_listener, hass, entry_id, tracker, keys, job, callbacks
    )


@callback
def _async_string_to_lower_list(instr: str | Iterable[str]) -> list[str]:
    if isinstance(instr, str):
        return [instr.lower()]

    return [mstr.lower() for mstr in instr]