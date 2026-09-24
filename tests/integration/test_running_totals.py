"""How a running total (EUR) accumulates a rate across steps, dropouts and restarts.

A grid importing 1000 W at 0.30 EUR/kWh is a rate of 0.30 EUR/h. Every rate the
engine computes is a step function — each input is a held reading until its
meter reports again — so a total integrates the rate that *held* over each
slice (left-Riemann), pauses while the rate is unknown, and starts as soon as
the integration is set up with its readings.
"""

from __future__ import annotations

import copy
from datetime import timedelta

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import DOMAIN, GRID_SUB_ID, make_grid_subentry_data, setup_integration

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

TOTAL = f"{GRID_SUB_ID}_total_import_cost"


def _entry() -> MockConfigEntry:
    grid = copy.deepcopy(make_grid_subentry_data())
    grid["data"]["adapter"]["config"]["grid_electricity_price_entity"] = (
        "sensor.grid_price"
    )
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={
            "schema": 2,
            "scopes": {"grid": ["calculate_cost_rates", "accumulate_cost_rates"]},
        },
        subentries_data=[grid],
    )


def _set(hass: HomeAssistant, entity_id: str, value, unit: str = "W") -> None:
    hass.states.async_set(entity_id, str(value), {"unit_of_measurement": unit})


def _total(hass: HomeAssistant, entry: MockConfigEntry) -> float:
    registry = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        if ent.unique_id and ent.unique_id.endswith(TOTAL):
            state = hass.states.get(ent.entity_id)
            assert state is not None and state.state not in ("unknown", "unavailable")
            return float(state.state)
    raise AssertionError(f"no sensor *{TOTAL}")


async def _settle(hass: HomeAssistant) -> None:
    for _ in range(4):
        await hass.async_block_till_done()


async def test_a_total_starts_when_the_integration_is_set_up(hass: HomeAssistant) -> None:
    """The first hour counts even though no reading changed in it.

    The engine has every reading at setup, so the total starts then — not at
    the first source event, which a sensor that only reports on change could
    delay for hours. 0.30 EUR/h held for 1 h is 0.30 EUR.
    """
    entry = _entry()
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _set(hass, "sensor.grid_power", 1000)
        _set(hass, "sensor.grid_price", 0.30, unit="EUR/kWh")
        await setup_integration(hass, entry)
        await _settle(hass)

        frozen.move_to(t0 + timedelta(hours=1))
        _set(hass, "sensor.grid_power", 1000)
        await _settle(hass)

    assert _total(hass, entry) == pytest.approx(0.30, abs=1e-3)


async def test_a_step_is_integrated_at_the_rate_that_held(hass: HomeAssistant) -> None:
    """Each hour is counted at the rate that held through it.

    0.30 EUR/h for the first hour, then the import doubles to 0.60 EUR/h for
    the second: 0.90 EUR. A trapezoid would have averaged the step back over
    the first hour and reported 1.05.
    """
    entry = _entry()
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _set(hass, "sensor.grid_power", 1000)
        _set(hass, "sensor.grid_price", 0.30, unit="EUR/kWh")
        await setup_integration(hass, entry)
        await _settle(hass)

        frozen.move_to(t0 + timedelta(hours=1))
        _set(hass, "sensor.grid_power", 2000)
        await _settle(hass)

        frozen.move_to(t0 + timedelta(hours=2))
        _set(hass, "sensor.grid_power", 2000)
        await _settle(hass)

    assert _total(hass, entry) == pytest.approx(0.90, abs=1e-3)


async def test_a_dropout_counts_up_to_the_moment_it_happened(hass: HomeAssistant) -> None:
    """The rate is counted until the meter drops out, then the total pauses.

    0.30 EUR/h held for the hour before the dropout counts. The two hours the
    meter is unavailable add nothing, and neither does the jump back: the
    total resumes from the reading that returns, and the hour after it adds
    another 0.30 EUR — 0.60 EUR in all.
    """
    entry = _entry()
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _set(hass, "sensor.grid_power", 1000)
        _set(hass, "sensor.grid_price", 0.30, unit="EUR/kWh")
        await setup_integration(hass, entry)
        await _settle(hass)

        frozen.move_to(t0 + timedelta(hours=1))
        hass.states.async_set("sensor.grid_power", "unavailable")
        await _settle(hass)
        assert _total(hass, entry) == pytest.approx(0.30, abs=1e-3)

        frozen.move_to(t0 + timedelta(hours=3))
        _set(hass, "sensor.grid_power", 1000)
        await _settle(hass)
        assert _total(hass, entry) == pytest.approx(0.30, abs=1e-3)

        frozen.move_to(t0 + timedelta(hours=4))
        _set(hass, "sensor.grid_power", 1000)
        await _settle(hass)

    assert _total(hass, entry) == pytest.approx(0.60, abs=1e-3)
