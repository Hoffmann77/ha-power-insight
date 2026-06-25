"""Tests for PowerInsight sensor entity creation and state updates."""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    DOMAIN,
    GRID_SUB_ID,
    PV_SUB_ID,
    BAT_SUB_ID,
    BASE_OPTIONS,
    make_grid_subentry_data,
    make_pv_subentry_data,
    make_battery_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_entry_entities(
    hass: HomeAssistant, entry: MockConfigEntry
) -> list[er.RegistryEntry]:
    """Return all entity registry entries belonging to *entry*."""
    ent_reg = er.async_get(hass)
    return er.async_entries_for_config_entry(ent_reg, entry.entry_id)


def get_sensor_state(
    hass: HomeAssistant, entry: MockConfigEntry, key_suffix: str
) -> str | None:
    """Return the HA state string of the sensor whose unique_id ends with *key_suffix*."""
    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    for ent in entries:
        if ent.unique_id and ent.unique_id.endswith(key_suffix):
            return hass.states.get(ent.entity_id)
    return None


# ---------------------------------------------------------------------------
# Entity creation tests
# ---------------------------------------------------------------------------


async def test_hub_sensors_created_for_grid_only_setup(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Hub-level sensors should be registered after loading with a grid adapter."""
    hass.states.async_set(
        "sensor.grid_power", "0", {"unit_of_measurement": "W"}
    )
    await setup_integration(hass, mock_config_entry)

    entries = get_entry_entities(hass, mock_config_entry)
    unique_ids = {e.unique_id for e in entries}
    entry_id = mock_config_entry.entry_id

    assert f"{entry_id}_combined_self_consumption_power" in unique_ids
    assert f"{entry_id}_combined_self_consumption_ratio" in unique_ids
    assert f"{entry_id}_combined_export_ratio" in unique_ids


async def test_grid_adapter_sensors_created(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Grid-specific sensors should be registered under the grid subentry."""
    hass.states.async_set(
        "sensor.grid_power", "0", {"unit_of_measurement": "W"}
    )
    await setup_integration(hass, mock_config_entry)

    entries = get_entry_entities(hass, mock_config_entry)
    unique_ids = {e.unique_id for e in entries}

    # Grid adapter unique_id is the subentry_id
    from .conftest import GRID_SUB_ID
    grid_prefix = f"{mock_config_entry.entry_id}_{GRID_SUB_ID}"
    grid_sensors = [uid for uid in unique_ids if uid and uid.startswith(grid_prefix)]
    assert len(grid_sensors) > 0, "Expected at least one grid adapter sensor"


async def test_pv_adapter_sensors_created(
    hass: HomeAssistant, mock_config_entry_with_pv: MockConfigEntry
) -> None:
    """PV adapter sensors should be registered when a PV subentry is configured."""
    hass.states.async_set(
        "sensor.grid_power", "0", {"unit_of_measurement": "W"}
    )
    hass.states.async_set(
        "sensor.pv_power", "0", {"unit_of_measurement": "W"}
    )
    await setup_integration(hass, mock_config_entry_with_pv)

    entries = get_entry_entities(hass, mock_config_entry_with_pv)
    unique_ids = {e.unique_id for e in entries}

    from .conftest import PV_SUB_ID
    pv_prefix = f"{mock_config_entry_with_pv.entry_id}_{PV_SUB_ID}"
    pv_sensors = [uid for uid in unique_ids if uid and uid.startswith(pv_prefix)]
    assert len(pv_sensors) > 0, "Expected at least one PV adapter sensor"


async def test_battery_charging_share_sensors_only_for_selected_sources(
    hass: HomeAssistant,
) -> None:
    """A battery should only get a "charging share from X" sensor for each
    source it is actually configured to charge from.

    Here the battery may charge from the grid but NOT from the PV system, so
    only the grid charging-share sensor should exist.
    """
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[
            make_grid_subentry_data(),
            make_pv_subentry_data(),
            make_battery_subentry_data(charge_from_adapters=[GRID_SUB_ID]),
        ],
    )
    for ent in ("grid_power", "pv_power", "battery_power"):
        hass.states.async_set(f"sensor.{ent}", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    entries = get_entry_entities(hass, entry)
    keys = {e.unique_id for e in entries if e.unique_id}

    bat_prefix = f"{entry.entry_id}_{BAT_SUB_ID}_charging_share_from_"
    charging_share_keys = {k for k in keys if k.startswith(bat_prefix)}

    # Exactly one charging-share sensor (Grid), none for the unselected PV.
    assert charging_share_keys == {f"{bat_prefix}Grid"}


# ---------------------------------------------------------------------------
# State update tests
# ---------------------------------------------------------------------------


async def test_grid_import_sensor_reflects_initial_state(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The grid import sensor should read 500 W when grid_power starts at 500."""
    hass.states.async_set(
        "sensor.grid_power", "500", {"unit_of_measurement": "W"}
    )
    await setup_integration(hass, mock_config_entry)
    await hass.async_block_till_done()

    pi = mock_config_entry.runtime_data.power_insight
    assert pi.combined_grid_import == pytest.approx(500.0)
    assert pi.combined_grid_export == pytest.approx(0.0)


async def test_grid_export_sensor_reflects_negative_power(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Negative grid power (export) should be reflected correctly in PowerInsight."""
    hass.states.async_set(
        "sensor.grid_power", "-300", {"unit_of_measurement": "W"}
    )
    await setup_integration(hass, mock_config_entry)

    pi = mock_config_entry.runtime_data.power_insight
    assert pi.combined_grid_import == pytest.approx(0.0)
    assert pi.combined_grid_export == pytest.approx(300.0)


async def test_sensor_state_updates_on_state_change(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """HA sensor state should update when the source entity changes."""
    hass.states.async_set(
        "sensor.grid_power", "0", {"unit_of_measurement": "W"}
    )
    await setup_integration(hass, mock_config_entry)
    await hass.async_block_till_done()

    # Find the self-consumption power sensor before the update
    entry_id = mock_config_entry.entry_id
    sensor_state_before = get_sensor_state(
        hass, mock_config_entry, f"{entry_id}_combined_self_consumption_power"
    )
    assert sensor_state_before is not None

    # Trigger a state change
    hass.states.async_set(
        "sensor.grid_power", "800", {"unit_of_measurement": "W"}
    )
    await hass.async_block_till_done()

    pi = mock_config_entry.runtime_data.power_insight
    assert pi.combined_grid_import == pytest.approx(800.0)


async def test_sensor_reflects_unavailable_after_source_goes_unavailable(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """When a source entity becomes unavailable, PowerInsight should store None."""
    hass.states.async_set(
        "sensor.grid_power", "500", {"unit_of_measurement": "W"}
    )
    await setup_integration(hass, mock_config_entry)

    # Source entity goes unavailable
    hass.states.async_set("sensor.grid_power", "unavailable", {})
    await hass.async_block_till_done()

    pi = mock_config_entry.runtime_data.power_insight
    assert pi.grid_adapter.power is None


async def test_sensor_recovers_after_unavailable(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """After recovering from unavailable, sensor should reflect the new value."""
    hass.states.async_set("sensor.grid_power", "unavailable", {})
    await setup_integration(hass, mock_config_entry)

    hass.states.async_set(
        "sensor.grid_power", "200", {"unit_of_measurement": "W"}
    )
    await hass.async_block_till_done()

    pi = mock_config_entry.runtime_data.power_insight
    assert pi.combined_grid_import == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# Grid + PV combined value test
# ---------------------------------------------------------------------------


async def test_gross_power_with_grid_and_pv(
    hass: HomeAssistant, mock_config_entry_with_pv: MockConfigEntry
) -> None:
    """gross_power should sum grid import + PV production when both are set."""
    hass.states.async_set(
        "sensor.grid_power", "200", {"unit_of_measurement": "W"}
    )
    hass.states.async_set(
        "sensor.pv_power", "1000", {"unit_of_measurement": "W"}
    )
    await setup_integration(hass, mock_config_entry_with_pv)

    pi = mock_config_entry_with_pv.runtime_data.power_insight
    # grid import (200) + pv production (1000) + battery discharge (0) = 1200
    assert pi.gross_power == pytest.approx(1200.0)
