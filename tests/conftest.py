"""Shared fixtures for PowerInsight integration tests."""
from __future__ import annotations

import pathlib
import sys
import types

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Patch sys.modules so HA's custom component discovery finds our package,
# not the testing_config version that gets cached at pytest startup.
_project_root = pathlib.Path(__file__).parent.parent
_cc_path = str(_project_root / "custom_components")
_cc_mod = types.ModuleType("custom_components")
_cc_mod.__path__ = [_cc_path]
_cc_mod.__package__ = "custom_components"
_cc_mod.__spec__ = None
sys.modules["custom_components"] = _cc_mod

DOMAIN = "power_insight"

GRID_SUB_ID = "01GRID00000000000000000001"
PV_SUB_ID = "01PV0000000000000000000001"
BAT_SUB_ID = "01BAT00000000000000000001A"

BASE_OPTIONS = {
    "calculate_instantaneous_rates": [],
    "calculate_instantaneous_saving_rates": [],
    "calculate_accumulated_entities": [],
}


def make_grid_subentry_data(
    subentry_id: str = GRID_SUB_ID,
    power_entity: str = "sensor.grid_power",
) -> dict:
    """Return subentry data for a grid adapter."""
    return {
        "subentry_id": subentry_id,
        "subentry_type": "adapter",
        "title": "Grid",
        "unique_id": None,
        "data": {
            "adapter": {
                "adapter_type": "grid",
                "key": "grid",
                "config": {
                    "power_entity": power_entity,
                    "power_entity_inverted": False,
                },
            },
        },
    }


def make_pv_subentry_data(
    subentry_id: str = PV_SUB_ID,
    power_entity: str = "sensor.pv_power",
) -> dict:
    """Return subentry data for a PV system adapter."""
    return {
        "subentry_id": subentry_id,
        "subentry_type": "adapter",
        "title": "Solar PV",
        "unique_id": None,
        "data": {
            "adapter": {
                "adapter_type": "pv_system",
                "key": "solar_pv",
                "config": {
                    "power_entity": power_entity,
                    "power_entity_inverted": False,
                    "default_lcoe": 0.10,
                    "current_lcoe": 0.10,
                    "default_co2_intensity": 50.0,
                    "current_co2_intensity": 50.0,
                    "exports_power": True,
                    "export_compensation": 0.08,
                },
            },
            "lifetime_production": 10000.0,
            "lifetime_cost": 1000.0,
            "co2_footprint": 500.0,
        },
    }


def make_battery_subentry_data(
    subentry_id: str = BAT_SUB_ID,
    power_entity: str = "sensor.battery_power",
    charge_from_adapters: list[str] | None = None,
) -> dict:
    """Return subentry data for a battery adapter."""
    return {
        "subentry_id": subentry_id,
        "subentry_type": "adapter",
        "title": "Battery",
        "unique_id": None,
        "data": {
            "adapter": {
                "adapter_type": "battery",
                "key": "battery",
                "config": {
                    "power_entity": power_entity,
                    "power_entity_inverted": False,
                    "default_lcos": 0.15,
                    "current_lcos": 0.15,
                    "default_co2_intensity": 100.0,
                    "current_co2_intensity": 100.0,
                    "exports_power": False,
                    "export_compensation": 0.0,
                    "charge_from_grid": True,
                    "charge_from_adapters": charge_from_adapters or [],
                },
            },
            "lifetime_production": 5000.0,
            "lifetime_cost": 2000.0,
            "co2_footprint": 500.0,
        },
    }


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Config entry with a single grid adapter."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data()],
    )


@pytest.fixture
def mock_config_entry_no_grid() -> MockConfigEntry:
    """Config entry with no adapters configured."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
    )


@pytest.fixture
def mock_config_entry_with_pv() -> MockConfigEntry:
    """Config entry with grid + PV adapter."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data(), make_pv_subentry_data()],
    )


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add entry to hass and load the integration."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
