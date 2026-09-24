"""Tests for PowerInsight integration setup (__init__.py)."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    DOMAIN,
    GRID_SUB_ID,
    BAT_SUB_ID,
    BASE_OPTIONS,
    make_grid_subentry_data,
    make_battery_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_setup_standby_without_grid(
    hass: HomeAssistant, mock_config_entry_no_grid: MockConfigEntry
) -> None:
    """Entry should load successfully (standby) when no grid adapter is configured."""
    await setup_integration(hass, mock_config_entry_no_grid)
    assert mock_config_entry_no_grid.state == ConfigEntryState.LOADED


async def test_migrate_flat_options_to_scopes(hass: HomeAssistant) -> None:
    """A v1 entry with flat options is migrated to the v2 per-scope schema."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        version=1,
        minor_version=1,
        options={
            "calculate_instantaneous_rates": ["calculate_cost_rates"],
            "calculate_instantaneous_saving_rates": [],
            "calculate_accumulated_entities": ["accumulate_cost_rates"],
            "enable_power_shares": True,
            "debug_power_entities": True,
        },
        subentries_data=[make_grid_subentry_data()],
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    # Every migration step runs, so the entry lands on the current minor version.
    assert entry.minor_version == 4
    assert entry.options["schema"] == 2
    grid = set(entry.options["scopes"]["grid"])
    # Cost rate + its accumulation carried over to the grid scope.
    assert "calculate_cost_rates" in grid
    assert "accumulate_cost_rates" in grid
    # Power shares expanded into the grid distribution categories.
    assert "enable_distribution_ratios" in grid
    assert "enable_distribution_shares" in grid
    # Watt sensors kept (were always-on before).
    assert "enable_distribution_power" in grid
    assert entry.options["debug_power_entities"] is True
    # Levelized was not enabled, so it must not appear anywhere.
    all_leaves = {l for s in entry.options["scopes"].values() for l in s}
    assert not any("levelized" in leaf for leaf in all_leaves)


async def test_no_grid_creates_repair_issue(
    hass: HomeAssistant, mock_config_entry_no_grid: MockConfigEntry
) -> None:
    """No grid adapter should create a 'no_grid_configured' repair issue."""
    await setup_integration(hass, mock_config_entry_no_grid)
    issue_reg = ir.async_get(hass)
    assert issue_reg.async_get_issue(DOMAIN, "no_grid_configured") is not None


async def test_setup_succeeds_with_grid(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Entry should load successfully when a grid adapter is configured."""
    hass.states.async_set("sensor.grid_power", "500", {"unit_of_measurement": "W"})
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state == ConfigEntryState.LOADED


async def test_grid_issue_dismissed_on_successful_setup(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A prior 'no_grid_configured' issue should be absent after a successful setup."""
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, mock_config_entry)
    issue_reg = ir.async_get(hass)
    assert issue_reg.async_get_issue(DOMAIN, "no_grid_configured") is None


async def test_powerinsight_bootstrapped_from_ha_state(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """PowerInsight should be seeded with current HA state values at startup."""
    hass.states.async_set("sensor.grid_power", "750", {"unit_of_measurement": "W"})
    await setup_integration(hass, mock_config_entry)

    pi = mock_config_entry.runtime_data.power_insight
    assert pi.combined_grid_import == pytest.approx(750.0)


async def test_powerinsight_unavailable_state_yields_none(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """An 'unavailable' source entity should seed PowerInsight with None."""
    hass.states.async_set("sensor.grid_power", "unavailable", {})
    await setup_integration(hass, mock_config_entry)

    pi = mock_config_entry.runtime_data.power_insight
    assert pi.grid_adapter.power is None


async def test_powerinsight_kw_unit_scaled_to_watts(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A state expressed in kW should be scaled to Watts in PowerInsight."""
    hass.states.async_set("sensor.grid_power", "1.5", {"unit_of_measurement": "kW"})
    await setup_integration(hass, mock_config_entry)

    pi = mock_config_entry.runtime_data.power_insight
    assert pi.combined_grid_import == pytest.approx(1500.0)


async def test_unload_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Unloading should leave the entry in NOT_LOADED state."""
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state == ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state == ConfigEntryState.NOT_LOADED


async def test_stale_battery_charge_source_creates_repair_issue(
    hass: HomeAssistant,
) -> None:
    """A battery referencing a removed charge-source adapter creates a repair issue."""
    NONEXISTENT_PV_ID = "nonexistent_pv_00000000000001"

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[
            make_grid_subentry_data(),
            make_battery_subentry_data(charge_from_adapters=[NONEXISTENT_PV_ID]),
        ],
    )

    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    issue_reg = ir.async_get(hass)
    assert (
        issue_reg.async_get_issue(DOMAIN, f"reconfigure_battery_{BAT_SUB_ID}")
        is not None
    )


async def test_valid_battery_charge_source_no_repair_issue(
    hass: HomeAssistant,
) -> None:
    """A battery with a valid charge_from_adapters reference should not raise a repair issue."""
    from .conftest import PV_SUB_ID, make_pv_subentry_data

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[
            make_grid_subentry_data(),
            make_pv_subentry_data(),
            make_battery_subentry_data(charge_from_adapters=[PV_SUB_ID]),
        ],
    )

    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    issue_reg = ir.async_get(hass)
    assert (
        issue_reg.async_get_issue(DOMAIN, f"reconfigure_battery_{BAT_SUB_ID}") is None
    )


async def test_migrate_drops_stored_battery_efficiency(hass: HomeAssistant) -> None:
    """The retired round-trip efficiency is stripped from battery subentries.

    Nothing ever read it, so leaving the key behind would keep implying it
    feeds a calculation somewhere.
    """
    import copy

    from .conftest import BAT_SUB_ID, make_battery_subentry_data

    battery = copy.deepcopy(make_battery_subentry_data())
    battery["data"]["adapter"]["config"]["battery_efficiency"] = 95

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        version=1,
        minor_version=2,
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data(), battery],
    )
    for name in ("grid_power", "battery_power"):
        hass.states.async_set(f"sensor.{name}", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    config = entry.subentries[BAT_SUB_ID].data["adapter"]["config"]
    assert "battery_efficiency" not in config
    # Everything else the battery was configured with survives untouched.
    assert config["default_lcos"] == 0.15
    assert config["charge_from_adapters"] == []
    assert entry.minor_version == 4


async def test_migrate_rekeys_share_sensors_by_subentry_id(hass: HomeAssistant) -> None:
    """A share sensor keyed by its source's name is re-keyed by the source's
    subentry id in place, so its history survives and a rename cannot orphan it.
    """
    from homeassistant.helpers import entity_registry as er

    from .conftest import make_battery_subentry_data

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        version=1,
        minor_version=3,
        options=BASE_OPTIONS,
        subentries_data=[
            make_grid_subentry_data(),
            make_battery_subentry_data(charge_from_adapters=[GRID_SUB_ID]),
        ],
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_{BAT_SUB_ID}_charging_share_from_Grid",
        config_entry=entry,
    )
    for name in ("grid_power", "battery_power"):
        hass.states.async_set(f"sensor.{name}", "0", {"unit_of_measurement": "W"})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    migrated = registry.async_get(old.entity_id)
    assert migrated is not None
    assert migrated.unique_id == (
        f"{entry.entry_id}_{BAT_SUB_ID}_charging_share_from_{GRID_SUB_ID}"
    )
    assert entry.minor_version == 4


async def test_an_entry_from_a_newer_version_is_refused(hass: HomeAssistant) -> None:
    """A downgrade is refused rather than loading data it cannot understand."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        version=2,
        minor_version=1,
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data()],
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.MIGRATION_ERROR


def _grid_with_price() -> dict:
    import copy

    grid = copy.deepcopy(make_grid_subentry_data())
    grid["data"]["adapter"]["config"]["grid_electricity_price_entity"] = (
        "sensor.grid_price"
    )
    return grid


@pytest.mark.parametrize(
    ("unit", "issue"),
    [("EUR", "price_unit"), ("GBP/kWh", "price_currency"), ("ct/kWh", None)],
)
async def test_a_price_that_cannot_be_used_raises_a_repair_issue(
    hass: HomeAssistant, unit: str, issue: str | None
) -> None:
    """An unknown price unit, or a foreign currency, needs the user; ct/kWh does not."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="My PowerInsight", options=BASE_OPTIONS,
        subentries_data=[_grid_with_price()],
    )
    hass.states.async_set("sensor.grid_power", "100", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.grid_price", "30", {"unit_of_measurement": unit})
    await setup_integration(hass, entry)

    registry = ir.async_get(hass)
    raised = {
        kind for kind in ("price_unit", "price_currency")
        if registry.async_get_issue(DOMAIN, f"{kind}_{entry.entry_id}")
    }
    assert raised == ({issue} if issue else set())


async def test_ct_per_kwh_prices_are_converted(hass: HomeAssistant) -> None:
    """A 30 ct/kWh tariff is 0.30 EUR/kWh: 1 kW imported costs 0.30 EUR/h."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="My PowerInsight", options=BASE_OPTIONS,
        subentries_data=[_grid_with_price()],
    )
    hass.states.async_set("sensor.grid_power", "1000", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.grid_price", "30", {"unit_of_measurement": "ct/kWh"})
    await setup_integration(hass, entry)

    assert entry.runtime_data.power_insight.combined_coe_rate == pytest.approx(0.30)


async def test_two_devices_on_one_power_sensor_raise_a_repair_issue(
    hass: HomeAssistant,
) -> None:
    """An entry from before the flow refused it gets told, not silently miscounted."""
    import copy

    from .conftest import make_consumer_subentry_data

    twin = copy.deepcopy(make_consumer_subentry_data())
    twin["data"]["adapter"]["config"]["power_entity"] = "sensor.grid_power"
    entry = MockConfigEntry(
        domain=DOMAIN, title="My PowerInsight", options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data(), twin],
    )
    hass.states.async_set("sensor.grid_power", "100", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    assert ir.async_get(hass).async_get_issue(
        DOMAIN, f"shared_power_entity_{entry.entry_id}"
    )
