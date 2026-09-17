"""Standby power for PV and battery.

Both published ``standby_ratio`` and ``standby_share`` with no watts sensor
behind them, while the grid — the one device that never has a standby draw of
its own — had all three.
"""

from __future__ import annotations

import copy

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    BAT_SUB_ID,
    DOMAIN,
    PV_SUB_ID,
    make_battery_subentry_data,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


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


@pytest.mark.parametrize(
    ("scope", "subentry_id"), [("pv_system", PV_SUB_ID), ("battery", BAT_SUB_ID)]
)
async def test_standby_power_exists_for_pv_and_battery(
    hass: HomeAssistant, scope: str, subentry_id: str
) -> None:
    """Both now publish the watts behind their standby ratio and share."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={
            "schema": 2,
            "scopes": {scope: ["enable_distribution_power"]},
        },
        subentries_data=[
            make_grid_subentry_data(),
            make_pv_subentry_data(),
            make_battery_subentry_data(),
        ],
    )
    _set(hass, "sensor.grid_power", 1000)
    _set(hass, "sensor.pv_power", 2000)
    _set(hass, "sensor.battery_power", 0)
    await setup_integration(hass, entry)
    await _settle(hass)

    state = _state(hass, entry, f"{subentry_id}_standby_power")
    assert state is not None, "standby_power was not created"
    assert state.attributes["unit_of_measurement"] == "W"
    assert state.attributes["device_class"] == "power"


async def test_standby_power_reports_the_supplying_sources_watts(
    hass: HomeAssistant,
) -> None:
    """A PV string in standby is a sink; the watts feeding it are attributed.

    ``pv2`` draws 100 W of standby while ``pv1`` produces and the grid imports,
    so the standby channel carries 100 W split across the two sources. Each
    source's own standby sensor reports its share of that, and the sum is the
    whole channel.
    """
    pv2 = copy.deepcopy(make_pv_subentry_data())
    pv2["subentry_id"] = "01PV0000000000000000000002"
    pv2["title"] = "Solar PV 2"
    pv2["data"]["adapter"]["key"] = "solar_pv_2"
    pv2["data"]["adapter"]["config"]["power_entity"] = "sensor.pv2_power"

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={
            "schema": 2,
            "scopes": {
                "grid": ["enable_distribution_power"],
                "pv_system": ["enable_distribution_power"],
            },
        },
        subentries_data=[make_grid_subentry_data(), make_pv_subentry_data(), pv2],
    )
    _set(hass, "sensor.grid_power", 1000)
    _set(hass, "sensor.pv_power", 2000)
    _set(hass, "sensor.pv2_power", -100)
    await setup_integration(hass, entry)
    await _settle(hass)

    grid_standby = _float(hass, entry, "01GRID00000000000000000001_standby_power")
    pv1_standby = _float(hass, entry, f"{PV_SUB_ID}_standby_power")

    # The channel total is pv2's 100 W draw, shared between the two sources.
    assert grid_standby + pv1_standby == pytest.approx(100.0, abs=1e-3)
    assert grid_standby > 0 and pv1_standby > 0
