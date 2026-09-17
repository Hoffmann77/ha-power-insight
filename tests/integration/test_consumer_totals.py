"""Accumulated totals for a consumer.

A consumer could report what it costs right now and never what it had cost:
the rate sensors existed, the integration sensors behind them did not.
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

from .conftest import (
    CONS_SUB_ID,
    DOMAIN,
    make_consumer_subentry_data,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

TOTALS = (
    "total_operating_cost",
    "total_levelized_operating_cost",
    "total_avoided_cost",
)


def _state(hass: HomeAssistant, entry: MockConfigEntry, suffix: str):
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id and entity.unique_id.endswith(suffix):
            return hass.states.get(entity.entity_id)
    return None


def _float(hass: HomeAssistant, entry: MockConfigEntry, suffix: str) -> float:
    state = _state(hass, entry, suffix)
    assert state is not None, f"sensor *{suffix} was not created"
    assert state.state not in ("unknown", "unavailable"), f"*{suffix} is {state.state}"
    return float(state.state)


def _set(hass: HomeAssistant, entity_id: str, value, unit: str | None = "W") -> None:
    hass.states.async_set(
        entity_id, str(value), {"unit_of_measurement": unit} if unit else {}
    )


async def _settle(hass: HomeAssistant) -> None:
    for _ in range(4):
        await hass.async_block_till_done()


def _grid_with_price() -> dict:
    grid = copy.deepcopy(make_grid_subentry_data())
    grid["data"]["adapter"]["config"]["grid_electricity_price_entity"] = (
        "sensor.grid_price"
    )
    return grid


@pytest.mark.parametrize("key", TOTALS)
async def test_consumer_totals_are_created(hass: HomeAssistant, key: str) -> None:
    """Each consumer rate sensor now has an accumulating counterpart."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={
            "schema": 2,
            "scopes": {
                "consumer": [
                    "calculate_cost_rates",
                    "calculate_levelized_cost_rates",
                    "calculate_cost_saving_rates",
                    "accumulate_cost_rates",
                    "accumulate_levelized_cost_rates",
                    "accumulate_cost_saving_rates",
                ],
            },
        },
        subentries_data=[
            _grid_with_price(),
            make_pv_subentry_data(),
            make_consumer_subentry_data(),
        ],
    )
    _set(hass, "sensor.grid_power", 1000)
    _set(hass, "sensor.grid_price", 0.30, unit="EUR/kWh")
    _set(hass, "sensor.pv_power", 2000)
    _set(hass, "sensor.consumer_power", -800)
    await setup_integration(hass, entry)
    await _settle(hass)

    state = _state(hass, entry, f"{CONS_SUB_ID}_{key}")
    assert state is not None, f"{key} was not created"
    assert state.attributes["state_class"] == "total"
    assert state.attributes["device_class"] == "monetary"


async def test_consumer_totals_are_absent_without_the_option(
    hass: HomeAssistant,
) -> None:
    """They are opt-in like every other accumulation sensor."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={
            "schema": 2,
            "scopes": {
                "consumer": [
                    "calculate_cost_rates",
                    "calculate_levelized_cost_rates",
                    "calculate_cost_saving_rates",
                ],
            },
        },
        subentries_data=[
            _grid_with_price(),
            make_pv_subentry_data(),
            make_consumer_subentry_data(),
        ],
    )
    _set(hass, "sensor.grid_power", 1000)
    _set(hass, "sensor.grid_price", 0.30, unit="EUR/kWh")
    _set(hass, "sensor.pv_power", 2000)
    _set(hass, "sensor.consumer_power", -800)
    await setup_integration(hass, entry)
    await _settle(hass)

    for key in TOTALS:
        assert _state(hass, entry, f"{CONS_SUB_ID}_{key}") is None, key


async def test_consumer_operating_cost_accumulates_its_rate(
    hass: HomeAssistant,
) -> None:
    """Held for an hour, the total equals the rate — the point of the sensor.

    Grid imports 1000 W at 0.30 EUR/kWh with no local generation, so the only
    source is the grid and the consumer's 800 W draw is priced entirely at the
    tariff: 0.8 kW x 0.30 = 0.24 EUR/h.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={
            "schema": 2,
            "scopes": {
                "consumer": ["calculate_cost_rates", "accumulate_cost_rates"],
            },
        },
        subentries_data=[_grid_with_price(), make_consumer_subentry_data()],
    )
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _set(hass, "sensor.grid_power", 1000)
        _set(hass, "sensor.grid_price", 0.30, unit="EUR/kWh")
        _set(hass, "sensor.consumer_power", -800)
        await setup_integration(hass, entry)

        # Anchor the integral at t0, then hold the rate for an hour.
        _set(hass, "sensor.grid_power", 1000)
        await _settle(hass)
        frozen.move_to(t0 + timedelta(hours=1))
        _set(hass, "sensor.grid_power", 1000)
        await _settle(hass)

    rate = _float(hass, entry, f"{CONS_SUB_ID}_operating_cost_rate")
    total = _float(hass, entry, f"{CONS_SUB_ID}_total_operating_cost")

    assert rate == pytest.approx(0.24, abs=1e-3)
    assert total == pytest.approx(0.24, abs=1e-3)
