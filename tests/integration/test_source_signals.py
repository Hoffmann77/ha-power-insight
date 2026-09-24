"""How the event handler tells sensors the engine holds a new reading.

Once the engine has stored a source entity's reading, the handler sends that
entity's dispatcher signal with the time of the reading. It is a dispatcher
signal, not a bus event: the recorder writes every bus event to the database,
and nothing outside the config entry needs to see these.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import DATA_DISPATCHER, async_dispatcher_send
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.power_insight.event_handler import (
    async_track_source_updates,
    source_signal,
)

from .conftest import (
    BASE_OPTIONS,
    DOMAIN,
    make_grid_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data()],
    )


def _collect(into: list[datetime]):
    """Return an event-loop callback that appends each timestamp it gets."""

    @callback
    def _append(timestamp: datetime) -> None:
        into.append(timestamp)

    return _append


def _set(hass: HomeAssistant, value) -> None:
    hass.states.async_set(
        "sensor.grid_power", str(value), {"unit_of_measurement": "W"}
    )


async def test_a_signal_carries_the_time_of_the_reading(hass: HomeAssistant) -> None:
    """A change is dated by ``last_updated``, a report by ``last_reported``.

    The running totals measure elapsed time between these timestamps, so each
    must be the source's own: the change at t0 + 1 min, then the unchanged
    re-report at t0 + 2 min (a ``state_reported``, which moves only
    ``last_reported``).
    """
    entry = _entry()
    t0 = dt_util.utcnow()
    received: list[datetime] = []
    with freeze_time(t0) as frozen:
        _set(hass, 100)
        await setup_integration(hass, entry)
        entry.async_on_unload(
            async_track_source_updates(
                hass, entry.entry_id, ["sensor.grid_power"], _collect(received)
            )
        )

        frozen.move_to(t0 + timedelta(minutes=1))
        _set(hass, 200)
        await hass.async_block_till_done()

        frozen.move_to(t0 + timedelta(minutes=2))
        _set(hass, 200)
        await hass.async_block_till_done()

    assert received == [t0 + timedelta(minutes=1), t0 + timedelta(minutes=2)]


async def test_an_unchanged_value_sends_no_change_signal(hass: HomeAssistant) -> None:
    """A state change the engine stores as the same value is not relayed.

    ``100`` W and ``0.1`` kW are different states for HA but the same 100 W
    for the engine, so no sensor has anything to recalculate.
    """
    entry = _entry()
    received: list[datetime] = []
    _set(hass, 100)
    await setup_integration(hass, entry)
    entry.async_on_unload(
        async_track_source_updates(
            hass, entry.entry_id, ["sensor.grid_power"], _collect(received)
        )
    )

    hass.states.async_set(
        "sensor.grid_power", "0.1", {"unit_of_measurement": "kW"}
    )
    await hass.async_block_till_done()

    assert received == []


async def test_no_bus_event_is_fired(hass: HomeAssistant) -> None:
    """A reading reaches the sensors without a single event of this domain.

    Any event the integration fired would be written to the database by the
    recorder, including one per ``state_reported``, which HA itself keeps
    out of it. Here a change and a report are both relayed (the signal
    arrives twice) and no event type starts with the domain.
    """
    entry = _entry()
    received: list[datetime] = []
    fired: list[str] = []
    _set(hass, 100)
    await setup_integration(hass, entry)
    entry.async_on_unload(
        async_track_source_updates(
            hass, entry.entry_id, ["sensor.grid_power"], _collect(received)
        )
    )
    entry.async_on_unload(
        hass.bus.async_listen(
            MATCH_ALL, callback(lambda event: fired.append(event.event_type))
        )
    )

    _set(hass, 200)
    await hass.async_block_till_done()
    _set(hass, 200)
    await hass.async_block_till_done()

    assert len(received) == 2
    assert [kind for kind in fired if kind.startswith(DOMAIN)] == []


async def test_a_repeated_source_is_connected_once(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A source listed twice is one listener, notified once and removed once.

    The dispatcher keys its listeners by callable, so connecting the same one
    twice would leave the second unsubscribe with nothing to remove — and HA
    logs a warning for that.
    """
    received: list[datetime] = []
    now = dt_util.utcnow()
    unsubscribe = async_track_source_updates(
        hass, "entry", ["sensor.a", "Sensor.A"], _collect(received)
    )
    async_dispatcher_send(hass, source_signal("entry", "sensor.a"), now)
    unsubscribe()

    assert received == [now]
    assert "Unable to remove unknown dispatcher" not in caplog.text


async def test_unloading_disconnects_every_signal(hass: HomeAssistant) -> None:
    """No sensor of an unloaded entry stays connected to a source signal."""
    entry = _entry()
    _set(hass, 100)
    await setup_integration(hass, entry)
    prefix = f"{DOMAIN}_{entry.entry_id}_"
    assert any(
        str(signal).startswith(prefix) for signal in hass.data[DATA_DISPATCHER]
    )

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert not any(
        str(signal).startswith(prefix) for signal in hass.data[DATA_DISPATCHER]
    )
