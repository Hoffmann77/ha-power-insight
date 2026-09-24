"""The persistent-imbalance repair issue: raised for a lasting gap, not a brief one.

Meters sampled at different moments make the metered devices briefly read more
than the sources supply, and the engine evens that out. A gap that persists for
the whole 15-minute window — above 10 % of gross power — means a misconfigured
meter, and the user is told; it is cleared once the gap stays under 5 %.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.power_insight.imbalance import ImbalanceMonitor

from .conftest import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@dataclass
class _Engine:
    """Stands in for the engine: just the two figures the monitor reads."""

    metering_imbalance: float | None = 0.0
    gross_power: float | None = 1000.0


def _monitor(hass: HomeAssistant) -> tuple[ImbalanceMonitor, _Engine, MockConfigEntry]:
    entry = MockConfigEntry(domain=DOMAIN, title="My PowerInsight")
    entry.add_to_hass(hass)
    engine = _Engine()
    return ImbalanceMonitor(hass, entry, engine), engine, entry


def _raised(hass: HomeAssistant, entry: MockConfigEntry) -> bool:
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"metering_imbalance_{entry.entry_id}"
    )
    return issue is not None


def _hold(monitor, engine, start, minutes: int, imbalance: float) -> None:
    """Hold ``imbalance`` W against 1000 W gross for ``minutes``, one sample a minute."""
    engine.metering_imbalance = imbalance
    for minute in range(minutes + 1):
        monitor.update(start + timedelta(minutes=minute))


async def test_a_lasting_imbalance_raises_the_issue(hass: HomeAssistant) -> None:
    """200 W against 1000 W gross — 20 % — for the whole window is raised."""
    monitor, engine, entry = _monitor(hass)
    _hold(monitor, engine, dt_util.utcnow(), 16, 200.0)
    assert _raised(hass, entry)


async def test_a_brief_imbalance_does_not(hass: HomeAssistant) -> None:
    """A two-minute gap averages to under 10 % over 15 minutes: normal jitter."""
    monitor, engine, entry = _monitor(hass)
    t0 = dt_util.utcnow()
    _hold(monitor, engine, t0, 2, 300.0)
    _hold(monitor, engine, t0 + timedelta(minutes=2), 14, 0.0)
    assert not _raised(hass, entry)


async def test_nothing_is_judged_before_a_whole_window(hass: HomeAssistant) -> None:
    """Ten minutes of a large gap are not yet a persistent one."""
    monitor, engine, entry = _monitor(hass)
    _hold(monitor, engine, dt_util.utcnow(), 10, 500.0)
    assert not _raised(hass, entry)


async def test_the_issue_clears_once_the_meters_agree(hass: HomeAssistant) -> None:
    """Raised at 20 %, cleared after a whole window with no gap at all."""
    monitor, engine, entry = _monitor(hass)
    t0 = dt_util.utcnow()
    _hold(monitor, engine, t0, 16, 200.0)
    assert _raised(hass, entry)
    _hold(monitor, engine, t0 + timedelta(minutes=16), 16, 0.0)
    assert not _raised(hass, entry)


async def test_a_meter_dropping_out_starts_the_window_over(hass: HomeAssistant) -> None:
    """With gross power unknowable nothing can be judged, so the window restarts."""
    monitor, engine, entry = _monitor(hass)
    t0 = dt_util.utcnow()
    _hold(monitor, engine, t0, 10, 200.0)
    engine.metering_imbalance = engine.gross_power = None
    monitor.update(t0 + timedelta(minutes=11))
    engine.gross_power = 1000.0
    _hold(monitor, engine, t0 + timedelta(minutes=12), 10, 200.0)
    assert not _raised(hass, entry)


async def test_the_imbalance_sensor_shows_the_gap(hass: HomeAssistant) -> None:
    """With the debug sensors on, the diagnostic sensor shows the balanced gap.

    PV reads 1000 W while the export (200 W), the battery (500 W) and the plug
    (600 W) read 1300 W: a 300 W imbalance.
    """
    from homeassistant.const import EntityCategory
    from homeassistant.helpers import entity_registry as er

    from .conftest import (
        BASE_OPTIONS,
        make_battery_subentry_data,
        make_consumer_subentry_data,
        make_grid_subentry_data,
        make_pv_subentry_data,
        setup_integration,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={**BASE_OPTIONS, "debug_power_entities": True},
        subentries_data=[
            make_grid_subentry_data(),
            make_pv_subentry_data(),
            make_battery_subentry_data(),
            make_consumer_subentry_data(),
        ],
    )
    for name, watts in (("grid_power", -200), ("pv_power", 1000),
                        ("battery_power", -500), ("consumer_power", -600)):
        hass.states.async_set(f"sensor.{name}", str(watts), {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)
    hass.states.async_set("sensor.consumer_power", "-600", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_metering_imbalance"
    )
    assert entity_id is not None
    assert registry.async_get(entity_id).entity_category is EntityCategory.DIAGNOSTIC
    assert float(hass.states.get(entity_id).state) == pytest.approx(300.0)
