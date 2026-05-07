"""Base sensor entities for the PowerInsight integration.

Two base classes are provided:

- ``BaseEventSensorEntity`` — a plain measurement sensor that re-reads its
  value from the shared ``PowerInsight`` engine whenever any of its source
  entities fire a state-change or state-report event.

- ``BaseEventIntegrationSensorEntity`` — a ``TOTAL`` sensor that accumulates
  a rate quantity (e.g. EUR/h) over time.  Integration is triggered both by
  source-entity events *and* by a periodic timer (``max_sub_interval``) so
  that steady-state periods — where source entities fire no events — are
  captured correctly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    EventStateReportedData,
    State,
    callback,
)
from homeassistant.helpers.event import async_call_later

from .event import (
    async_track_power_insight_state_change_event,
    async_track_power_insight_state_report_event,
)
from .power_insight import PowerInsight


_LOGGER = logging.getLogger(__name__)

# Scaling factors for SI unit prefixes used on power/energy entities.
UNIT_PREFIXES = {None: 1, "k": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}

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
    whenever any tracked source entity changes, then fires a scoped custom
    event on the HA bus.

    This class listens for those events and calls ``async_write_ha_state()``
    in response, which causes HA to pull the new value via the subclass's
    ``native_value`` property.  No state is stored here — calculation is
    fully delegated to ``PowerInsight``.

    Both ``state_changed`` and ``state_reported`` events are tracked so that
    the first known value is picked up via a state-report even before any
    actual state change occurs.
    """

    _attr_should_poll = False

    def __init__(
        self,
        source_entities: list[str],
        power_insight: PowerInsight,
    ) -> None:
        """Initialise the sensor.

        Args:
            source_entities: Entity IDs whose events should trigger a state
                write.  Typically the power/price/co2 entities feeding this
                sensor's calculation.
            power_insight: Shared calculation engine.  Already holds the
                current values when an event reaches this callback.

        """
        self._source_entities = source_entities
        self.power_insight = power_insight

    async def async_added_to_hass(self) -> None:
        """Register event listeners once the entity is part of HA."""
        await super().async_added_to_hass()

        # Track both event types for each source entity.
        # state_changed  — source value actually changed.
        # state_reported — source value was re-reported without changing (gives
        #                  us the initial value on startup before any change).
        self.async_on_remove(
            async_track_power_insight_state_change_event(
                self.hass,
                self.config_entry.entry_id,
                self._source_entities,
                self._update_on_state_change_callback,
            )
        )
        self.async_on_remove(
            async_track_power_insight_state_report_event(
                self.hass,
                self.config_entry.entry_id,
                self._source_entities,
                self._update_on_state_report_callback,
            )
        )

    @callback
    def _update_on_state_change_callback(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Push the current PowerInsight value to HA.

        EventHandler has already updated PowerInsight before this event fires,
        so native_value will return the freshly computed result.
        """
        self.async_write_ha_state()

    @callback
    def _update_on_state_report_callback(
        self, event: Event[EventStateReportedData]
    ) -> None:
        """Push the current PowerInsight value to HA (state-report variant)."""
        self.async_write_ha_state()


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

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        data = super().as_dict()
        data["last_valid_state"] = (
            str(self.last_valid_state) if self.last_valid_state is not None else None
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

        return cls(
            extra.native_value,
            extra.native_unit_of_measurement,
            last_valid_state,
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

    ``EventHandler`` updates ``PowerInsight`` before firing a scoped custom
    event.  Each event callback extracts the actual state-change timestamp
    from the event data (rather than using wall-clock time) to avoid adding
    processing-delay error to the elapsed-time calculation.

    **Trapezoidal method**

    The default integration method is trapezoidal: the area of each slice is
    ``elapsed_time × (left + right) / 2``.  Because both endpoints are fully
    computed ``PowerInsight`` values (left = previous calculation result,
    right = current calculation result), trapezoidal averaging is appropriate
    and more accurate than left- or right-rectangle rules for smoothly varying
    rate values.

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
            source_entities: Entity IDs that trigger integration when they
                fire a state-change or state-report event.
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

        # Left-endpoint anchor: the integration_value at the end of the
        # previous interval.  None until the first event is received.
        self._last_integration_value: float | None = None
        # Timestamp of the previous integration step (or the first event).
        # None until the first event is received.
        self._last_integration_time: datetime | None = None

        self._method = _IntegrationMethod.from_name(METHOD_TRAPEZOIDAL)

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
            if (value_dec := _decimal_state(self._last_integration_value)) is not None:
                area = self._method.calculate_area_with_one_state(elapsed, value_dec)
                self._update_integral(area)

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
        """Restore persisted state and register event listeners."""
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
            _LOGGER.debug(
                "Restored state=%s last_valid_state=%s",
                self._state, self._last_valid_state,
            )

        # Ensure the timer is cancelled cleanly when the entity is removed.
        self.async_on_remove(self._cancel_pending_max_sub_interval)

        # --- Event listeners ---
        self.async_on_remove(
            async_track_power_insight_state_change_event(
                self.hass,
                self.config_entry.entry_id,
                self._source_entities,
                self._integrate_on_state_change_callback,
            )
        )
        self.async_on_remove(
            async_track_power_insight_state_report_event(
                self.hass,
                self.config_entry.entry_id,
                self._source_entities,
                self._integrate_on_state_report_callback,
            )
        )

    # ------------------------------------------------------------------
    # Event callbacks
    # ------------------------------------------------------------------

    @callback
    def _integrate_on_state_change_callback(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle a source state-change event.

        Uses the new state's ``last_updated`` timestamp so that the elapsed
        time reflects when the physical value changed, not when this callback
        ran.
        """
        new_state: State | None = event.data["new_state"]
        # Fall back to wall-clock if the state object is unexpectedly absent.
        timestamp = new_state.last_updated if new_state is not None else datetime.now(tz=UTC)
        self._handle_integration_event(timestamp)

    @callback
    def _integrate_on_state_report_callback(
        self, event: Event[EventStateReportedData]
    ) -> None:
        """Handle a source state-report event (value unchanged, re-reported).

        Uses ``last_reported`` from the event data for the same accuracy
        reason as the state-change handler.
        """
        self._handle_integration_event(event.data["last_reported"])

    # ------------------------------------------------------------------
    # Core integration logic
    # ------------------------------------------------------------------

    def _handle_integration_event(self, timestamp: datetime) -> None:
        """Integrate one time slice and update HA state.

        ``PowerInsight`` is updated by ``EventHandler`` before this callback
        fires, so ``self.integration_value`` already reflects the new source
        entity state.

        On the first call the method initialises the left-endpoint anchor and
        schedules the max_sub_interval timer; no area is accumulated yet
        because there is no previous timestamp to measure from.

        On subsequent calls:
        1. Compute elapsed time from the previous event's timestamp.
        2. Integrate using (left=previous rate, right=current rate).
        3. Advance the left-endpoint anchor to the current values.
        4. Reset the max_sub_interval timer.
        """
        right_value = self.integration_value

        if self._last_integration_value is None:
            # First event: record the initial anchor; nothing to integrate yet.
            self._last_integration_value = right_value
            self._last_integration_time = timestamp
            self.async_write_ha_state()
            self._schedule_max_sub_interval()
            return

        left_value = self._last_integration_value

        # Use the actual event timestamps for accuracy.
        elapsed_seconds = Decimal((timestamp - self._last_integration_time).total_seconds())

        _LOGGER.debug(
            "Integration step: left=%s right=%s elapsed=%.3fs",
            left_value, right_value, float(elapsed_seconds),
        )

        if elapsed_seconds > 0 and left_value is not None and right_value is not None:
            if states := self._method.validate_states(left_value, right_value):
                area = self._method.calculate_area_with_two_states(elapsed_seconds, *states)
                self._update_integral(area)

        # Advance the left-endpoint anchor.
        self._last_integration_time = timestamp
        self._last_integration_value = right_value

        # Cancel old timer and start a fresh one from this event's timestamp.
        self._cancel_and_reschedule_max_sub_interval()

        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # HA state properties
    # ------------------------------------------------------------------

    @property
    def native_value(self) -> Decimal | None:
        """Return the accumulated total."""
        return self._state

    @property
    def extra_restore_state_data(self) -> IntegrationSensorExtraStoredData:
        """Return the extra data to persist across HA restarts."""
        return IntegrationSensorExtraStoredData(
            self.native_value,
            self.native_unit_of_measurement,
            self._last_valid_state,
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
