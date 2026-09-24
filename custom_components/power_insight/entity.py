"""Base sensor entities for the PowerInsight integration.

Two base classes are provided:

- ``BaseEventSensorEntity`` — a plain measurement sensor that re-reads its
  value from the shared ``PowerInsight`` engine whenever the engine takes a
  new reading from any of its source entities.

- ``BaseEventIntegrationSensorEntity`` — a ``TOTAL`` sensor that accumulates
  a rate quantity (e.g. EUR/h) over time.  Integration is triggered both by
  source-entity readings *and* by a periodic timer (``max_sub_interval``) so
  that steady-state periods — where source entities fire no events — are
  captured correctly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import logging
from typing import Any, Self

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorEntity,
    SensorExtraStoredData,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .event_handler import async_track_source_updates
from .power_insight import PowerInsight, UNIT_PREFIXES


_LOGGER = logging.getLogger(__name__)

# Seconds per time unit — used to convert the integration area to the target
# time unit (default: hours, giving Wh or EUR from W or EUR/h respectively).
UNIT_TIME = {
    UnitOfTime.SECONDS: 1,
    UnitOfTime.MINUTES: 60,
    UnitOfTime.HOURS: 60 * 60,
    UnitOfTime.DAYS: 24 * 60 * 60,
}


# ---------------------------------------------------------------------------
# BaseEventSensorEntity
# ---------------------------------------------------------------------------


class BaseEventSensorEntity(SensorEntity):
    """Measurement sensor that stays in sync with the shared PowerInsight engine.

    All sensor subclasses in this integration share a single ``PowerInsight``
    instance.  The ``EventHandler`` updates that instance with fresh W-values
    whenever any tracked source entity changes or reports, then sends that
    entity's dispatcher signal (``source_signal``).

    This class listens for the signals of its source entities and calls
    ``async_write_ha_state()`` in response, which causes HA to pull the new
    value via the subclass's ``native_value`` property.  No state is stored
    here — calculation is fully delegated to ``PowerInsight``.

    Write coalescing
    ----------------
    When several source entities change in the same event-loop tick (common at
    HA startup or with multi-channel energy meters), each sends its own
    signal.  Without coalescing every signal would produce a separate
    ``async_write_ha_state()`` call, each computing the same final
    ``PowerInsight`` result.  Instead, the first event sets a ``_pending_write``
    flag and schedules a single ``_flush_write`` with ``call_soon``; subsequent
    signals in the same tick see the flag is already set and do nothing.  The
    flush runs in the next iteration when ``PowerInsight`` holds all updates.
    """

    _attr_should_poll = False

    def __init__(
        self,
        source_entities: list[str],
        power_insight: PowerInsight,
    ) -> None:
        """Initialise the sensor.

        Args:
            source_entities: Entity IDs whose readings should trigger a
                state write.  Typically the power/price/co2 entities feeding this
                sensor's calculation.
            power_insight: Shared calculation engine.  Already holds the
                current values when a signal reaches this callback.

        """
        self._source_entities = source_entities
        self.power_insight = power_insight
        self._pending_write = False

    async def async_added_to_hass(self) -> None:
        """Listen for source readings once the entity is part of HA."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_source_updates(
                self.hass,
                self.config_entry.entry_id,
                self._source_entities,
                self._on_source_update,
            )
        )

    def _schedule_write(self) -> None:
        """Schedule a single state write for the current event-loop tick.

        Safe to call from any number of callbacks in the same tick — only the
        first call schedules the flush; the rest are no-ops.
        """
        if not self._pending_write:
            self._pending_write = True
            self.hass.loop.call_soon(self._flush_write)

    def _flush_write(self) -> None:
        """Write state to HA once all same-tick events have been processed."""
        self._pending_write = False
        self.async_write_ha_state()

    @callback
    def _on_source_update(self, timestamp: datetime) -> None:
        """Schedule a coalesced state write on a new source reading."""
        self._schedule_write()


# ---------------------------------------------------------------------------
# Integration method helpers
# ---------------------------------------------------------------------------

METHOD_TRAPEZOIDAL = "trapezoidal"
METHOD_LEFT = "left"
METHOD_RIGHT = "right"
INTEGRATION_METHODS = [METHOD_TRAPEZOIDAL, METHOD_LEFT, METHOD_RIGHT]


class _IntegrationMethod(ABC):
    """Abstract base for numerical integration strategies."""

    @staticmethod
    def from_name(method_name: str) -> _IntegrationMethod:
        """Return the integration method instance for the given name."""
        return _NAME_TO_INTEGRATION_METHOD[method_name]()

    @abstractmethod
    def validate_states(
        self, left: float | str, right: float | str
    ) -> tuple[Decimal, Decimal] | None:
        """Parse and validate the left/right endpoint values.

        Returns a ``(left_dec, right_dec)`` tuple if both values are numeric,
        or ``None`` if either value cannot be converted to a ``Decimal``.
        """

    @abstractmethod
    def calculate_area_with_two_states(
        self, elapsed_time: Decimal, left: Decimal, right: Decimal
    ) -> Decimal:
        """Return the area of one integration slice given two endpoint values."""

    def calculate_area_with_one_state(
        self, elapsed_time: Decimal, constant_state: Decimal
    ) -> Decimal:
        """Return the area when the integrand is assumed constant."""
        return constant_state * elapsed_time


class _Trapezoidal(_IntegrationMethod):
    """Trapezoidal rule — averages the left and right endpoint values."""

    def calculate_area_with_two_states(
        self, elapsed_time: Decimal, left: Decimal, right: Decimal
    ) -> Decimal:
        return elapsed_time * (left + right) / 2

    def validate_states(
        self, left: float | str, right: float | str
    ) -> tuple[Decimal, Decimal] | None:
        if (left_dec := _decimal_state(left)) is None or (
            right_dec := _decimal_state(right)
        ) is None:
            return None
        return (left_dec, right_dec)


class _Left(_IntegrationMethod):
    """Left-rectangle rule — uses the value at the start of each interval."""

    def calculate_area_with_two_states(
        self, elapsed_time: Decimal, left: Decimal, right: Decimal
    ) -> Decimal:
        return self.calculate_area_with_one_state(elapsed_time, left)

    def validate_states(
        self, left: float | str, right: float | str
    ) -> tuple[Decimal, Decimal] | None:
        if (left_dec := _decimal_state(left)) is None:
            return None
        return (left_dec, left_dec)


class _Right(_IntegrationMethod):
    """Right-rectangle rule — uses the value at the end of each interval."""

    def calculate_area_with_two_states(
        self, elapsed_time: Decimal, left: Decimal, right: Decimal
    ) -> Decimal:
        return self.calculate_area_with_one_state(elapsed_time, right)

    def validate_states(
        self, left: float | str, right: float | str
    ) -> tuple[Decimal, Decimal] | None:
        if (right_dec := _decimal_state(right)) is None:
            return None
        return (right_dec, right_dec)


def _decimal_state(state: float | str) -> Decimal | None:
    """Convert a numeric state value to ``Decimal``, returning ``None`` on failure."""
    try:
        return Decimal(state)
    except (InvalidOperation, TypeError):
        return None


_NAME_TO_INTEGRATION_METHOD: dict[str, type[_IntegrationMethod]] = {
    METHOD_LEFT: _Left,
    METHOD_RIGHT: _Right,
    METHOD_TRAPEZOIDAL: _Trapezoidal,
}


# ---------------------------------------------------------------------------
# Extra stored data for state restoration
# ---------------------------------------------------------------------------


@dataclass
class IntegrationSensorExtraStoredData(SensorExtraStoredData):
    """Persistent data stored alongside the sensor's native value.

    ``last_valid_state`` allows the running total to be recovered after an HA
    restart even if the sensor's ``native_value`` was ``None`` at shutdown.
    """

    last_valid_state: Decimal | None
    #: The running total split by which adapter's correction factor scales it.
    #: ``None`` for a total accumulated before the split existed, which can
    #: therefore no longer be corrected — see the class docstring.
    component_totals: dict[str, Decimal] | None = None
    #: The last correction factor seen for each component's adapter, so a part
    #: whose adapter has since been removed keeps the factor it had then.
    component_factors: dict[str, float] | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        data = super().as_dict()
        data["last_valid_state"] = (
            str(self.last_valid_state) if self.last_valid_state is not None else None
        )
        data["component_totals"] = (
            {key: str(value) for key, value in self.component_totals.items()}
            if self.component_totals is not None else None
        )
        data["component_factors"] = (
            dict(self.component_factors)
            if self.component_factors is not None else None
        )
        return data

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> Self | None:
        """Deserialise from a previously stored dict."""
        extra = SensorExtraStoredData.from_dict(restored)
        if extra is None:
            return None

        try:
            last_valid_state = (
                Decimal(str(restored["last_valid_state"]))
                if restored.get("last_valid_state") is not None
                else None
            )
        except InvalidOperation:
            _LOGGER.error("Could not restore last_valid_state — value was corrupted")
            return None

        if last_valid_state is None:
            return None

        component_totals: dict[str, Decimal] | None = None
        raw_components = restored.get("component_totals")
        if isinstance(raw_components, dict):
            try:
                component_totals = {
                    key: Decimal(str(value)) for key, value in raw_components.items()
                }
            except InvalidOperation:
                _LOGGER.error("Could not restore component_totals — value corrupted")
                component_totals = None

        component_factors: dict[str, float] | None = None
        raw_factors = restored.get("component_factors")
        if isinstance(raw_factors, dict):
            try:
                component_factors = {
                    key: float(value) for key, value in raw_factors.items()
                }
            except (TypeError, ValueError):
                _LOGGER.error("Could not restore component_factors — value corrupted")
                component_factors = None

        return cls(
            extra.native_value,
            extra.native_unit_of_measurement,
            last_valid_state,
            component_totals,
            component_factors,
        )


# ---------------------------------------------------------------------------
# BaseEventIntegrationSensorEntity
# ---------------------------------------------------------------------------


class BaseEventIntegrationSensorEntity(RestoreSensor, ABC):
    """Accumulation sensor that integrates a computed rate over time.

    Unlike a standard HA ``IntegrationSensor`` which integrates a single
    source entity directly, this class integrates the value returned by the
    abstract ``integration_value`` property — a derived quantity computed by
    the shared ``PowerInsight`` engine (e.g. EUR/h, Wh).

    **Event-driven integration**

    ``EventHandler`` updates ``PowerInsight`` before sending the source
    entity's dispatcher signal.  The signal carries the reading's own
    timestamp (rather than wall-clock time) to avoid adding processing-delay
    error to the elapsed-time calculation.

    **Left-Riemann method**

    Every input to the engine is a held value between two events — a meter's
    reading stands until it reports again — so every rate the engine computes
    is a step function, constant from one event to the next. The left-Riemann
    rule is exact for a step function: each slice is ``elapsed_time × left``,
    the rate that held over it. A trapezoid would smear each step back over
    the interval before it.

    **Unavailability**

    A rate that becomes unavailable is integrated up to the moment it did —
    the old rate held until then — and the total pauses until a rate is
    known again. There is no staleness timeout: a sensor that is still
    available is trusted, because sensors that only report on change are
    legitimately silent for hours.

    **max_sub_interval**

    Power meters frequently hold a constant output for extended periods without
    firing any state-change events.  Without a fallback, those periods would
    contribute nothing to the running total.  ``max_sub_interval`` schedules a
    recurring timer: if no event arrives within the interval, the timer fires
    and integrates the last known rate as a constant, then reschedules itself.
    The timer is cancelled and rescheduled whenever a real event arrives, so
    there is no double-counting.  Defaults to 1 minute.

    **State restoration**

    The running total survives HA restarts via ``RestoreSensor`` /
    ``IntegrationSensorExtraStoredData``.
    """

    _attr_state_class = SensorStateClass.TOTAL
    _attr_should_poll = False

    def __init__(
        self,
        source_entities: list[str],
        power_insight: PowerInsight,
        max_sub_interval: timedelta | None = timedelta(minutes=1),
    ) -> None:
        """Initialise the integration sensor.

        Args:
            source_entities: Entity IDs that trigger integration whenever the
                engine takes a new reading from them.
            power_insight: Shared calculation engine.
            max_sub_interval: How often to force an integration step when no
                source event arrives.  Set to ``None`` to disable.  Defaults
                to 1 minute, which keeps accumulation error under ~1/60th of
                the hourly rate for any steady-state period.

        """
        self._source_entities = source_entities
        self.power_insight = power_insight

        # Running total; None until the first integration step completes.
        self._state: Decimal | None = None
        # Last non-None total — used to survive unavailability windows and
        # to restore state when native_value is None at shutdown.
        self._last_valid_state: Decimal | None = None

        # The running total split by correction target; parallel to _state and
        # summing to it. Empty until the first step with a breakdown available.
        self._component_totals: dict[str, Decimal] = {}
        # The last correction factor seen per component key, as restored; a
        # subclass that corrects its display keeps it current.
        self._component_factors: dict[str, float] = {}

        # Left-endpoint anchor: the integration_value at the end of the
        # previous interval.  None until the first event is received.
        self._last_integration_value: float | None = None
        # The matching anchor for the per-component breakdown.
        self._last_integration_components: dict[str, float] | None = None
        # Timestamp of the previous integration step (or the first event).
        # None until the first event is received.
        self._last_integration_time: datetime | None = None

        self._method = _IntegrationMethod.from_name(METHOD_LEFT)

        # Unit scaling: dividing the raw area (value × seconds) by
        # (prefix × time_unit_in_seconds) converts to the target unit.
        # Defaults: no prefix (×1), time unit = hours (÷3600) → EUR/h → EUR.
        self._unit_prefix = UNIT_PREFIXES[None]
        self._unit_time = UNIT_TIME[UnitOfTime.HOURS]

        self._max_sub_interval = max_sub_interval
        # Cancellation handle for the pending max_sub_interval timer.
        self._cancel_max_sub_interval: CALLBACK_TYPE | None = None

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    def integration_components(self) -> dict[str, float] | None:
        """Return ``integration_value`` split by correction target, if it splits.

        ``None`` (the default) means this sensor accumulates an undivided
        value. When a breakdown is returned its parts must sum to
        ``integration_value``, and each key names the adapter whose correction
        factor scales that part — so the accumulated total can be re-corrected
        exactly, however long afterwards the lifetime cost is edited.
        """
        return None

    @property
    @abstractmethod
    def integration_value(self) -> float | None:
        """Return the current rate value to integrate (e.g. EUR/h).

        Called after ``PowerInsight`` has been updated with the latest source
        entity values, so the returned value already reflects the new state.
        Must return ``None`` when any required input is unavailable.
        """

    # ------------------------------------------------------------------
    # Integration helpers
    # ------------------------------------------------------------------

    def _update_component_integrals(
        self,
        elapsed_seconds: Decimal,
        left: dict[str, float],
        right: dict[str, float],
    ) -> None:
        """Integrate each component over the same interval as the total.

        Every integration method is linear in the value, so integrating the
        parts and integrating the whole agree exactly — the components stay a
        true decomposition of ``_state`` rather than drifting from it.
        """
        for key in set(left) | set(right):
            states = self._method.validate_states(
                left.get(key, 0.0), right.get(key, 0.0)
            )
            if not states:
                continue
            area = self._method.calculate_area_with_two_states(
                elapsed_seconds, *states
            )
            scaled = area / (self._unit_prefix * self._unit_time)
            self._component_totals[key] = (
                self._component_totals.get(key, Decimal(0)) + scaled
            )

    def _update_integral(self, area: Decimal) -> None:
        """Add one area slice to the running total.

        ``area`` is in (value × seconds).  Dividing by ``_unit_prefix ×
        _unit_time`` converts to the sensor's native unit (e.g. EUR/h × s
        ÷ 3600 s/h = EUR).
        """
        area_scaled = area / (self._unit_prefix * self._unit_time)
        if isinstance(self._state, Decimal):
            self._state += area_scaled
        else:
            self._state = area_scaled
        self._last_valid_state = self._state
        _LOGGER.debug(
            "Integrated area=%s scaled=%s running_total=%s",
            area, area_scaled, self._state,
        )

    # ------------------------------------------------------------------
    # max_sub_interval timer
    # ------------------------------------------------------------------

    def _schedule_max_sub_interval(self) -> None:
        """Schedule a one-shot timer to integrate if no event arrives in time.

        Does nothing if max_sub_interval is disabled or if no first event has
        arrived yet (nothing to integrate from).
        """
        if self._max_sub_interval is None or self._last_integration_value is None:
            return

        @callback
        def _on_max_sub_interval_exceeded(now: datetime) -> None:
            """Integrate the last known rate as a constant, then reschedule."""
            if self._last_integration_time is None or self._last_integration_value is None:
                return

            elapsed = Decimal((now - self._last_integration_time).total_seconds())
            if elapsed > 0 and (
                value_dec := _decimal_state(self._last_integration_value)
            ) is not None:
                area = self._method.calculate_area_with_one_state(elapsed, value_dec)
                self._update_integral(area)
                # The breakdown must follow the total through steady periods
                # too, or those slices escape a later correction.
                if (components := self._last_integration_components) is not None:
                    self._update_component_integrals(elapsed, components, components)
                self._last_integration_time = now
            self.async_write_ha_state()

            # Reschedule for the next sub-interval.
            self._cancel_max_sub_interval = async_call_later(
                self.hass, self._max_sub_interval, _on_max_sub_interval_exceeded
            )

        self._cancel_max_sub_interval = async_call_later(
            self.hass, self._max_sub_interval, _on_max_sub_interval_exceeded
        )

    def _cancel_and_reschedule_max_sub_interval(self) -> None:
        """Cancel the pending timer and start a fresh one.

        Called after each real integration event so the timer always measures
        from the most recent event, preventing double-counting.
        """
        if self._cancel_max_sub_interval is not None:
            self._cancel_max_sub_interval()
            self._cancel_max_sub_interval = None
        self._schedule_max_sub_interval()

    def _cancel_pending_max_sub_interval(self) -> None:
        """Cancel the pending timer without rescheduling (used on removal)."""
        if self._cancel_max_sub_interval is not None:
            self._cancel_max_sub_interval()
            self._cancel_max_sub_interval = None

    # ------------------------------------------------------------------
    # HA lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Restore persisted state and listen for source readings."""
        await super().async_added_to_hass()

        # --- State restoration ---
        # Attempt to recover the running total from the last HA session.
        if (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            # Prefer native_value; fall back to last_valid_state if native_value
            # was None at shutdown (e.g. sensor had never integrated anything).
            self._state = (
                Decimal(str(last_sensor_data.native_value))
                if last_sensor_data.native_value is not None
                else last_sensor_data.last_valid_state
            )
            self._attr_native_value = last_sensor_data.native_value
            self._last_valid_state = last_sensor_data.last_valid_state
            self._component_totals = dict(last_sensor_data.component_totals or {})
            self._component_factors = dict(last_sensor_data.component_factors or {})
            _LOGGER.debug(
                "Restored state=%s last_valid_state=%s",
                self._state, self._last_valid_state,
            )

        # Ensure the timer is cancelled cleanly when the entity is removed.
        self.async_on_remove(self._cancel_pending_max_sub_interval)

        # Start the total now if the engine already holds every reading it
        # needs (loaded at setup), rather than at the first source event — a
        # sensor that only reports on change could keep that waiting for hours.
        if self.integration_value is not None:
            self._last_integration_value = self.integration_value
            self._last_integration_components = self.integration_components
            self._last_integration_time = dt_util.utcnow()
            self._schedule_max_sub_interval()

        # --- Source readings ---
        self.async_on_remove(
            async_track_source_updates(
                self.hass,
                self.config_entry.entry_id,
                self._source_entities,
                self._handle_integration_event,
            )
        )

    # ------------------------------------------------------------------
    # Core integration logic
    # ------------------------------------------------------------------

    @callback
    def _handle_integration_event(self, timestamp: datetime) -> None:
        """Integrate the slice since the last step and update HA state.

        Called with the reading's own timestamp — ``last_updated`` for a
        change, ``last_reported`` for a report — so the elapsed time reflects
        when the physical value was read, not when this callback ran.
        ``PowerInsight`` is updated by ``EventHandler`` before this callback
        runs, so ``self.integration_value`` already reflects the new source
        entity state.

        1. Integrate the rate that held since the last step (the left value)
           up to ``timestamp`` — including when the new rate is unavailable,
           since the old one held until the moment it went.
        2. Hold the new rate from here on; if it is unavailable, the total
           pauses until an event brings a known rate back.
        3. Reset the max_sub_interval timer.

        Time never moves backwards: an event stamped before the last step
        (the timer runs on the wall clock, events on the source's own
        timestamps) adds nothing and does not rewind the anchor, so no slice
        is counted twice.
        """
        right_value = self.integration_value
        right_components = self.integration_components
        left_value = self._last_integration_value
        left_components = self._last_integration_components
        last_time = self._last_integration_time

        if last_time is not None and left_value is not None:
            elapsed_seconds = Decimal((timestamp - last_time).total_seconds())
            _LOGGER.debug(
                "Integration step: left=%s right=%s elapsed=%.3fs",
                left_value, right_value, float(elapsed_seconds),
            )
            if elapsed_seconds > 0 and (
                states := self._method.validate_states(left_value, right_value)
            ):
                area = self._method.calculate_area_with_two_states(elapsed_seconds, *states)
                self._update_integral(area)
                if left_components is not None:
                    self._update_component_integrals(
                        elapsed_seconds, left_components, right_components or {},
                    )

        # Hold the new rate from here on, never rewinding the clock.
        if last_time is None or timestamp > last_time:
            self._last_integration_time = timestamp
        self._last_integration_value = right_value
        self._last_integration_components = right_components

        # Cancel old timer and start a fresh one from this step.
        self._cancel_and_reschedule_max_sub_interval()

        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # HA state properties
    # ------------------------------------------------------------------

    @property
    def native_value(self) -> Decimal | None:
        """Return the accumulated total."""
        return self._state

    async def async_set_value(self, value: float) -> None:
        """Seed the running total to *value* (backs the ``set_value`` service).

        Lets the user set an accumulated sensor to a known starting figure —
        e.g. to carry over historical totals when adopting the integration.
        The new total persists across restarts via the existing restore path.

        The seeded figure replaces the history, so its breakdown goes too: the
        total then reads exactly *value*, which a later correction leaves at
        face value, like any total with no attribution to correct it by.
        """
        self._state = Decimal(str(value))
        self._last_valid_state = self._state
        self._component_totals = {}
        self._component_factors = {}
        self.async_write_ha_state()

    @property
    def extra_restore_state_data(self) -> IntegrationSensorExtraStoredData:
        """Return the extra data to persist across HA restarts."""
        return IntegrationSensorExtraStoredData(
            self.native_value,
            self.native_unit_of_measurement,
            self._last_valid_state,
            dict(self._component_totals) or None,
            dict(self._component_factors) or None,
        )

    async def async_get_last_sensor_data(
        self,
    ) -> IntegrationSensorExtraStoredData | None:
        """Load the previously persisted extra sensor data."""
        if (restored_last_extra_data := await self.async_get_last_extra_data()) is None:
            return None
        return IntegrationSensorExtraStoredData.from_dict(
            restored_last_extra_data.as_dict()
        )
