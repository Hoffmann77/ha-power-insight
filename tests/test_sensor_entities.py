"""Tests for PowerInsight sensor entity creation and state updates."""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    DOMAIN,
    GRID_SUB_ID,
    PV_SUB_ID,
    BAT_SUB_ID,
    BASE_OPTIONS,
    FULL_OPTIONS,
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


async def test_disabling_option_disables_entity_but_keeps_it(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Turning an option off should disable (not delete) the matching sensors,
    and turning it back on should re-enable them.

    Power-share sensors are gated on ``enable_power_shares``; toggling it must
    therefore take effect on the registered entities.
    """
    hass.states.async_set(
        "sensor.grid_power", "0", {"unit_of_measurement": "W"}
    )
    await setup_integration(hass, mock_config_entry)
    ent_reg = er.async_get(hass)

    uid = f"{mock_config_entry.entry_id}_combined_export_ratio"
    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, uid)
    assert entity_id is not None
    assert ent_reg.async_get(entity_id).disabled_by is None

    def _with_combined(leaves: list[str]) -> dict:
        opts = {**mock_config_entry.options}
        opts["scopes"] = {**opts["scopes"], "combined": leaves}
        return opts

    # Drop distribution ratios from the combined scope → the entity is kept
    # but disabled by the integration.
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options=_with_combined(["enable_distribution_power"]),
    )
    await hass.async_block_till_done()

    reg_entry = ent_reg.async_get(entity_id)
    assert reg_entry is not None, "entity should be kept, not deleted"
    assert reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    # Re-enable → the integration re-enables the entity.
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options=_with_combined(
            ["enable_distribution_power", "enable_distribution_ratios"]
        ),
    )
    await hass.async_block_till_done()

    assert ent_reg.async_get(entity_id).disabled_by is None


async def test_grid_owns_import_export_and_compensation_sensors(
    hass: HomeAssistant,
) -> None:
    """Import/export power and export compensation live on the grid device,
    and the combined export-compensation sensors are gone from the hub."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=FULL_OPTIONS,
        subentries_data=[make_grid_subentry_data(), make_pv_subentry_data()],
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    entries = get_entry_entities(hass, entry)
    uids = {e.unique_id for e in entries if e.unique_id}
    grid = f"{entry.entry_id}_{GRID_SUB_ID}"

    assert f"{grid}_import_power" in uids
    assert f"{grid}_export_power" in uids
    assert f"{grid}_export_compensation_rate" in uids
    assert f"{grid}_total_export_compensation" in uids

    # Export compensation no longer exists at the combined/hub level.
    assert f"{entry.entry_id}_combined_export_compensation_rate" not in uids
    assert f"{entry.entry_id}_combined_total_export_compensation" not in uids


async def test_options_form_submit_reloads_and_applies(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Submitting the single options form reloads the entry and applies it."""
    hass.states.async_set(
        "sensor.grid_power", "0", {"unit_of_measurement": "W"}
    )
    await setup_integration(hass, mock_config_entry)
    ent_reg = er.async_get(hass)
    uid = f"{mock_config_entry.entry_id}_combined_export_ratio"
    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, uid)
    assert entity_id is not None
    assert ent_reg.async_get(entity_id).disabled_by is None

    result = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "combined": {
                "distribution_power": True,
                "distribution_ratios": False,  # drop ratios → export ratio off
                "cost_rates": [],
                "cost_savings_rates": [],
                "accumulated_costs": [],
                "accumulated_cost_savings": [],
            },
            "grid": {},
            "diagnostics": {"debug_power_entities": False},
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    # The save reloaded the entry and applied the change.
    assert (
        ent_reg.async_get(entity_id).disabled_by
        is er.RegistryEntryDisabler.INTEGRATION
    )


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
