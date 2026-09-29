"""Power and energy per source for a consumer.

The consumer's "Power share from {source}" sensors said where its power came
from as a percentage; these say it in watts, and add up the energy over time.
"""

from __future__ import annotations

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
    GRID_SUB_ID,
    PV_SUB_ID,
    make_consumer_subentry_data,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

BOTH = ["enable_power_source_power", "accumulate_power_source_energy"]


def _entry(consumer_options: list[str], power_from: list[str] | None = None):
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={"schema": 2, "scopes": {"consumer": consumer_options}},
        subentries_data=[
            make_grid_subentry_data(),
            make_pv_subentry_data(),
            make_consumer_subentry_data(power_from_adapters=power_from or []),
        ],
    )


def _state(hass: HomeAssistant, entry: MockConfigEntry, key: str):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{CONS_SUB_ID}_{key}"
    )
    return None if entity_id is None else hass.states.get(entity_id)


def _float(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> float:
    state = _state(hass, entry, key)
    assert state is not None, f"{key} was not created"
    assert state.state not in ("unknown", "unavailable"), f"{key} is {state.state}"
    return float(state.state)


def _set(hass: HomeAssistant, entity: str, watts: float) -> None:
    hass.states.async_set(f"sensor.{entity}", str(watts), {"unit_of_measurement": "W"})


def _readings(hass: HomeAssistant) -> None:
    """Grid imports 500 W, PV makes 500 W, the consumer draws 400 W."""
    _set(hass, "grid_power", 500)
    _set(hass, "pv_power", 500)
    _set(hass, "consumer_power", -400)


async def _settle(hass: HomeAssistant) -> None:
    for _ in range(4):
        await hass.async_block_till_done()


async def test_one_of_each_per_source(hass: HomeAssistant) -> None:
    """Every source that can supply power gets a watt and a kWh sensor.

    The grid is included even though it is a balancing node: it is where most
    of a consumer's energy comes from at night.
    """
    entry = _entry(BOTH)
    _readings(hass)
    await setup_integration(hass, entry)
    await _settle(hass)

    for source in (GRID_SUB_ID, PV_SUB_ID):
        power = _state(hass, entry, f"power_from_{source}")
        assert power is not None
        assert power.attributes["unit_of_measurement"] == "W"
        assert power.attributes["device_class"] == "power"
        assert power.attributes["state_class"] == "measurement"

        energy = _state(hass, entry, f"energy_from_{source}")
        assert energy is not None
        assert energy.attributes["unit_of_measurement"] == "kWh"
        assert energy.attributes["device_class"] == "energy"
        assert energy.attributes["state_class"] == "total"


async def test_absent_without_the_options(hass: HomeAssistant) -> None:
    """They are opt-in: a consumer with only its power shares gets neither."""
    entry = _entry(["enable_power_source_shares"])
    _readings(hass)
    await setup_integration(hass, entry)
    await _settle(hass)

    assert _state(hass, entry, f"power_share_from_{PV_SUB_ID}") is not None
    for source in (GRID_SUB_ID, PV_SUB_ID):
        assert _state(hass, entry, f"power_from_{source}") is None
        assert _state(hass, entry, f"energy_from_{source}") is None


@pytest.mark.parametrize(
    ("power_from", "from_grid", "from_pv"),
    [([], 200.0, 200.0), ([PV_SUB_ID], 0.0, 400.0)],
    ids=["whole_mix", "pv_only"],
)
async def test_power_from_each_source(
    hass: HomeAssistant, power_from: list[str], from_grid: float, from_pv: float
) -> None:
    """The watts behind the power shares, summing to the consumer's draw.

    With 500 W from each source and 1000 W consumed, the whole mix is half and
    half, so the 400 W draw is 200 W from each. Restricted to PV, the consumer
    is served first and PV covers all 400 W.
    """
    entry = _entry(["enable_power_source_power"], power_from)
    _readings(hass)
    await setup_integration(hass, entry)
    await _settle(hass)

    assert _float(hass, entry, f"power_from_{GRID_SUB_ID}") == pytest.approx(from_grid)
    assert _float(hass, entry, f"power_from_{PV_SUB_ID}") == pytest.approx(from_pv)


async def test_energy_from_each_source_accumulates_its_power(
    hass: HomeAssistant,
) -> None:
    """Held for an hour, each total in kWh equals its power in kW.

    Restricted to PV, the 400 W draw comes entirely from PV: 0.4 kWh from PV
    after an hour, and nothing from the grid.
    """
    entry = _entry(BOTH, [PV_SUB_ID])
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _readings(hass)
        await setup_integration(hass, entry)

        # Anchor the integral at t0, then hold the readings for an hour.
        _set(hass, "grid_power", 500)
        await _settle(hass)
        frozen.move_to(t0 + timedelta(hours=1))
        _set(hass, "grid_power", 500)
        await _settle(hass)

    assert _float(hass, entry, f"energy_from_{PV_SUB_ID}") == pytest.approx(0.4, abs=1e-3)
    assert _float(hass, entry, f"energy_from_{GRID_SUB_ID}") == pytest.approx(0.0, abs=1e-6)
