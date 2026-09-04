"""Tests for the diagnostics download.

Diagnostics reaches for a long list of engine properties and adapter internals
by name, none of which the type checker sees. A property renamed or dropped in
the engine would only show up as an ``AttributeError`` the moment a user hits
*Download diagnostics*, so the point of these tests is to walk every branch —
hub, and one device of each adapter type — on a full topology.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.power_insight.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)
from .conftest import (
    BAT_SUB_ID,
    CONS_SUB_ID,
    DOMAIN,
    FULL_OPTIONS,
    GRID_SUB_ID,
    PV_SUB_ID,
    make_battery_subentry_data,
    make_consumer_subentry_data,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.fixture
async def full_entry(hass: HomeAssistant) -> MockConfigEntry:
    """A loaded entry with a grid (priced), PV, battery and consumer, all live."""
    grid = make_grid_subentry_data()
    grid["data"]["adapter"]["config"]["grid_electricity_price_entity"] = (
        "sensor.grid_price"
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=FULL_OPTIONS,
        subentries_data=[
            grid,
            make_pv_subentry_data(),
            make_battery_subentry_data(charge_from_adapters=[PV_SUB_ID]),
            make_consumer_subentry_data(),
        ],
    )
    hass.states.async_set("sensor.grid_power", "1000", {"unit_of_measurement": "W"})
    hass.states.async_set(
        "sensor.grid_price", "0.30", {"unit_of_measurement": "EUR/kWh"}
    )
    hass.states.async_set("sensor.pv_power", "2000", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.battery_power", "-500", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.consumer_power", "-800", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)
    return entry


def _device(hass: HomeAssistant, entry: MockConfigEntry, identifier: str):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, identifier)})


async def test_entry_diagnostics_dumps_every_adapter(
    hass: HomeAssistant, full_entry: MockConfigEntry
) -> None:
    result = await async_get_config_entry_diagnostics(hass, full_entry)

    assert set(result) == {"options", "data", "adapters", "hub_calculations"}
    adapters = result["adapters"]
    assert adapters["grid"]["adapter_type"] == "grid"
    assert adapters["grid"]["price_entity"] == "sensor.grid_price"
    assert [a["adapter_type"] for a in adapters["pv_systems"]] == ["pv_system"]
    assert [a["adapter_type"] for a in adapters["batteries"]] == ["battery"]
    assert [a["adapter_type"] for a in adapters["consumers"]] == ["consumer"]

    # The live readings made it through the event handler into the engine.
    assert adapters["grid"]["calculated"]["import_power_w"] == 1000
    assert adapters["pv_systems"][0]["calculated"]["production_w"] == 2000
    assert adapters["batteries"][0]["calculated"]["charge_power_w"] == 500
    assert adapters["consumers"][0]["calculated"]["consumption_w"] == 800

    # Every hub calculation resolves — no property was renamed out from under it.
    assert result["hub_calculations"]["gross_power_w"] == 3000
    assert all(
        not isinstance(value, Exception)
        for value in result["hub_calculations"].values()
    )


async def test_battery_dump_resolves_charge_source_names(
    hass: HomeAssistant, full_entry: MockConfigEntry
) -> None:
    result = await async_get_config_entry_diagnostics(hass, full_entry)

    battery = result["adapters"]["batteries"][0]
    assert battery["charge_from_adapter_uids"] == [PV_SUB_ID]
    assert battery["charge_from_adapter_names"] == ["Solar PV"]


@pytest.mark.parametrize(
    ("identifier_fn", "expected_keys"),
    [
        (lambda entry: entry.entry_id, {"options", "data", "hub_calculations"}),
        (lambda entry: GRID_SUB_ID, {"adapter"}),
        (lambda entry: PV_SUB_ID, {"adapter"}),
        (lambda entry: BAT_SUB_ID, {"adapter"}),
        (lambda entry: CONS_SUB_ID, {"adapter"}),
    ],
    ids=["hub", "grid", "pv", "battery", "consumer"],
)
async def test_device_diagnostics_for_every_device(
    hass: HomeAssistant,
    full_entry: MockConfigEntry,
    identifier_fn,
    expected_keys: set[str],
) -> None:
    device = _device(hass, full_entry, identifier_fn(full_entry))
    assert device is not None

    result = await async_get_device_diagnostics(hass, full_entry, device)

    assert set(result) == expected_keys


async def test_diagnostics_without_a_grid(hass: HomeAssistant) -> None:
    """A hub with no grid must still produce a report rather than raising."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=FULL_OPTIONS,
    )
    await setup_integration(hass, entry)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["adapters"] == {"pv_systems": [], "batteries": [], "consumers": []}
    assert result["hub_calculations"] == {"error": "no_grid_configured"}


async def test_diagnostics_with_an_unavailable_meter(
    hass: HomeAssistant, full_entry: MockConfigEntry
) -> None:
    """An unavailable source must read as ``None``, not blow the report up."""
    hass.states.async_set("sensor.battery_power", "unavailable")
    await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, full_entry)

    assert result["adapters"]["batteries"][0]["calculated"]["charge_power_w"] is None
    assert result["hub_calculations"]["gross_power_w"] is None
