"""Tests for PowerInsight sensor entity creation and state updates."""
from __future__ import annotations

import copy

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
    CONS_SUB_ID,
    BASE_OPTIONS,
    FULL_OPTIONS,
    make_grid_subentry_data,
    make_pv_subentry_data,
    make_battery_subentry_data,
    make_consumer_subentry_data,
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


async def test_grid_charging_sensors_gated_on_charge_source(
    hass: HomeAssistant,
) -> None:
    """Grid CHG sensors appear only when a battery charges from the grid.

    Standby sensors are not charge-gated, so they always appear.
    """
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

    uids = {e.unique_id for e in get_entry_entities(hass, entry) if e.unique_id}
    grid = f"{entry.entry_id}_{GRID_SUB_ID}"

    # Grid charges the battery → grid CHG sensors exist.
    assert f"{grid}_charging_ratio" in uids
    assert f"{grid}_charging_share" in uids
    # Standby is never charge-gated.
    assert f"{grid}_standby_ratio" in uids
    assert f"{grid}_standby_share" in uids


async def test_grid_charging_sensors_absent_without_battery(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """With no battery, grid CHG sensors are gated out but STB sensors remain."""
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, mock_config_entry)

    uids = {e.unique_id for e in get_entry_entities(hass, mock_config_entry) if e.unique_id}
    grid = f"{mock_config_entry.entry_id}_{GRID_SUB_ID}"

    assert f"{grid}_charging_ratio" not in uids
    assert f"{grid}_charging_share" not in uids
    assert f"{grid}_standby_ratio" in uids
    assert f"{grid}_standby_share" in uids


async def test_charging_sensors_follow_the_configured_source(
    hass: HomeAssistant,
) -> None:
    """A battery charging from PV only → PV CHG sensors exist, grid CHG do not."""
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
    for ent in ("grid_power", "pv_power", "battery_power"):
        hass.states.async_set(f"sensor.{ent}", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    uids = {e.unique_id for e in get_entry_entities(hass, entry) if e.unique_id}
    grid = f"{entry.entry_id}_{GRID_SUB_ID}"
    pv = f"{entry.entry_id}_{PV_SUB_ID}"

    assert f"{pv}_charging_ratio" in uids
    assert f"{pv}_charging_share" in uids
    assert f"{grid}_charging_ratio" not in uids
    assert f"{grid}_charging_share" not in uids


async def test_consumer_consumption_share_registered(hass: HomeAssistant) -> None:
    """The consumer gains a consumption_share sensor when shares are enabled."""
    options = {
        **BASE_OPTIONS,
        "scopes": {
            **BASE_OPTIONS["scopes"],
            "consumer": ["enable_distribution_shares", "enable_power_source_shares"],
        },
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=options,
        subentries_data=[make_grid_subentry_data(), make_consumer_subentry_data()],
    )
    for ent in ("grid_power", "consumer_power"):
        hass.states.async_set(f"sensor.{ent}", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    uids = {e.unique_id for e in get_entry_entities(hass, entry) if e.unique_id}
    assert f"{entry.entry_id}_{CONS_SUB_ID}_consumption_share" in uids


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
    """Completing the options flow reloads the entry and applies the changes."""
    hass.states.async_set(
        "sensor.grid_power", "0", {"unit_of_measurement": "W"}
    )
    await setup_integration(hass, mock_config_entry)
    ent_reg = er.async_get(hass)
    uid = f"{mock_config_entry.entry_id}_combined_export_ratio"
    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, uid)
    assert entity_id is not None
    assert ent_reg.async_get(entity_id).disabled_by is None

    # Open options and pick custom to configure per-scope.
    result = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"preset": "custom", "debug_power_entities": False},
    )
    assert result["step_id"] == "combined"

    # Combined: keep distribution_power but drop distribution_ratios.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "power_sensors": {"distribution_power": True, "distribution_ratios": False},
            "costs": {"cost_method": "none", "accumulate_costs": False},
            "savings": {"savings_method": "none", "accumulate_savings": False},
            "financial_return": {"financial_return_method": "none", "accumulate_financial_return": False},
        },
    )
    assert result["step_id"] == "grid"

    # Grid: nothing enabled.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "power_sensors": {
                "distribution_power": False,
                "distribution_ratios": False,
                "distribution_shares": False,
            },
            "export_compensation": {
                "export_compensation_rate": False,
                "export_compensation_total": False,
            },
            "costs": {"cost_method": "none", "accumulate_costs": False},
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    # The save reloaded the entry; dropping distribution_ratios disabled the sensor.
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


# ---------------------------------------------------------------------------
# Channel cost sensors (CON / CHG / STB / EXP)
#
# The combined "operating cost" sensors only ever measured the charging
# channel, so they are renamed to say so, and the other three channels get
# sensors of their own. See docs/dev/engine-calculations.md.
# ---------------------------------------------------------------------------


async def _setup_full_house(hass: HomeAssistant) -> MockConfigEntry:
    """Grid + PV + battery + consumer, importing while the battery charges."""
    grid_data = copy.deepcopy(make_grid_subentry_data())
    grid_data["data"]["adapter"]["config"][
        "grid_electricity_price_entity"
    ] = "sensor.grid_price"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=FULL_OPTIONS,
        subentries_data=[
            grid_data,
            make_pv_subentry_data(),
            make_battery_subentry_data(),
            make_consumer_subentry_data(),
        ],
    )
    readings = {
        "grid_power": "1000",
        "pv_power": "2000",
        "battery_power": "-800",
        "consumer_power": "-400",
    }
    for name, value in readings.items():
        hass.states.async_set(f"sensor.{name}", value, {"unit_of_measurement": "W"})
    hass.states.async_set(
        "sensor.grid_price", "0.30", {"unit_of_measurement": "EUR/kWh"}
    )
    await setup_integration(hass, entry)
    await hass.async_block_till_done()
    return entry


async def test_channel_cost_sensors_registered(hass: HomeAssistant) -> None:
    """The renamed charging sensors exist and the old names are gone."""
    entry = await _setup_full_house(hass)
    keys = {e.unique_id for e in get_entry_entities(hass, entry) if e.unique_id}
    prefix = f"{entry.entry_id}_"

    for key in (
        "combined_charging_cost_rate",
        "combined_levelized_charging_cost_rate",
        "combined_consumption_cost_rate",
        "combined_levelized_consumption_cost_rate",
        "combined_standby_cost_rate",
        "combined_export_cost_rate",
        "combined_total_charging_cost",
        "combined_total_consumption_cost",
    ):
        assert f"{prefix}{key}" in keys, f"missing {key}"

    # The mis-named originals are gone outright — a clean break, so their
    # accumulated history does not silently reappear under a new meaning.
    for key in (
        "combined_operating_cost_rate",
        "combined_levelized_operating_cost_rate",
        "combined_total_operating_cost",
    ):
        assert f"{prefix}{key}" not in keys, f"{key} should have been removed"


async def test_channel_cost_sensors_conserve(hass: HomeAssistant) -> None:
    """The four channel costs partition the cost of gross power.

    The sensor-layer form of the cost-conservation invariant: every watt
    entering the house is bought exactly once, in exactly one channel.
    """
    entry = await _setup_full_house(hass)
    pi = entry.runtime_data.power_insight

    channels = (
        pi.combined_levelized_consumption_cost_rate,
        pi.combined_levelized_charging_cost_rate,
        pi.combined_levelized_standby_cost_rate,
        pi.combined_levelized_export_cost_rate,
    )
    assert None not in channels
    assert sum(channels) == pytest.approx(pi.combined_lcoe_rate)

    # Charging is a strict subset of the whole: with a battery charging off a
    # priced import it is non-zero, and consumption carries the rest.
    assert pi.combined_charging_cost_rate > 0
    assert pi.combined_consumption_cost_rate > 0


async def test_consumer_avoided_cost_sensor(hass: HomeAssistant) -> None:
    """A consumer reports what it did *not* pay the grid, and it is bounded."""
    entry = await _setup_full_house(hass)
    pi = entry.runtime_data.power_insight

    avoided = pi.sink_adapters_avoided_cost_rates
    assert CONS_SUB_ID in avoided

    keys = {e.unique_id for e in get_entry_entities(hass, entry) if e.unique_id}
    assert f"{entry.entry_id}_{CONS_SUB_ID}_avoided_cost_rate" in keys

    # It can never exceed buying the whole draw from the grid.
    draw_kw = 400 / 1000
    assert 0.0 <= avoided[CONS_SUB_ID] <= draw_kw * 0.30 + 1e-9

    # Sink side and source side are two views of one number, never a sum.
    sink_side = sum(avoided.values()) + pi.home_base_load_avoided_cost_rate
    source_side = sum(pi.source_adapters_avoided_cost_rates.values())
    assert sink_side == pytest.approx(source_side)


async def test_device_operating_cost_matches_its_per_device_sensors(
    hass: HomeAssistant,
) -> None:
    """The device view sums the per-device operating costs, exactly.

    This is the pairing that was missing: the ledger total is derived from the
    per-device totals, so the rate it belongs to has to be the per-device sum —
    not the charging channel, which excludes PV standby.
    """
    entry = await _setup_full_house(hass)
    pi = entry.runtime_data.power_insight

    keys = {e.unique_id for e in get_entry_entities(hass, entry) if e.unique_id}
    prefix = f"{entry.entry_id}_"
    assert f"{prefix}combined_device_operating_cost_rate" in keys
    assert f"{prefix}combined_levelized_device_operating_cost_rate" in keys
    assert f"{prefix}combined_total_levelized_device_operating_cost" in keys

    per_device = pi.source_adapters_lcoo_rates
    assert sum(per_device.values()) == pytest.approx(
        pi.combined_levelized_device_operating_cost_rate
    )


async def test_device_view_and_channel_view_diverge_on_standby(
    hass: HomeAssistant,
) -> None:
    """With PV in standby and nothing charging, the two views must differ.

    The charging channel is empty, but the hardware is still costing money —
    which is exactly the case the single old name hid.
    """
    entry = await _setup_full_house(hass)

    # Night: no PV output, PV drawing standby, battery idle, grid covering.
    hass.states.async_set("sensor.pv_power", "-50", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.battery_power", "0", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()

    pi = entry.runtime_data.power_insight
    assert pi.combined_standby_power == pytest.approx(50.0)
    assert pi.combined_charging_power == pytest.approx(0.0)

    # Channel view: nothing charged, so nothing in the CHG bucket.
    assert pi.combined_levelized_charging_cost_rate == pytest.approx(0.0)
    # Device view: the standby draw still costs, and it is the standby bucket.
    device = pi.combined_levelized_device_operating_cost_rate
    assert device > 0.0
    assert device == pytest.approx(pi.combined_levelized_standby_cost_rate)


async def test_per_device_savings_sum_to_the_combined_saving(
    hass: HomeAssistant,
) -> None:
    """Savings additivity, at the sensor layer.

    The per-device sensors read the every-role family, so a device drawing
    (a PV in standby) contributes its negative share and the totals reconcile.
    """
    entry = await _setup_full_house(hass)
    hass.states.async_set("sensor.pv_power", "-50", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()

    pi = entry.runtime_data.power_insight
    assert sum(pi.adapters_levelized_saving_rates.values()) == pytest.approx(
        pi.combined_levelized_saving_rate
    )
    assert sum(pi.adapters_saving_rates.values()) == pytest.approx(
        pi.combined_saving_rate
    )


# ---------------------------------------------------------------------------
# Home base load — a device for the unmetered remainder
# ---------------------------------------------------------------------------


async def test_home_base_load_device_and_sensors(hass: HomeAssistant) -> None:
    """The residual gets a device of its own, gated on the option."""
    from homeassistant.helpers import device_registry as dr

    entry = await _setup_full_house(hass)
    keys = {e.unique_id for e in get_entry_entities(hass, entry) if e.unique_id}
    prefix = f"{entry.entry_id}_"

    assert f"{prefix}home_base_load_power" in keys
    assert f"{prefix}home_base_load_avoided_cost_rate" in keys

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(
        identifiers={(DOMAIN, f"{entry.entry_id}_home_base_load")}
    )
    assert device is not None, "the home base load should have its own device"
    assert "Home base load" in device.name


async def test_home_base_load_absent_when_not_enabled(hass: HomeAssistant) -> None:
    """Without the option the device is never created."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data(), make_consumer_subentry_data()],
    )
    for name in ("grid_power", "consumer_power"):
        hass.states.async_set(f"sensor.{name}", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    keys = {e.unique_id for e in get_entry_entities(hass, entry) if e.unique_id}
    assert f"{entry.entry_id}_home_base_load_power" not in keys


async def test_home_base_load_reports_the_residual_and_its_mix(
    hass: HomeAssistant,
) -> None:
    """Its power is gross minus every metered draw, and it says where it came from."""
    entry = await _setup_full_house(hass)
    pi = entry.runtime_data.power_insight

    # gross 3000 (grid 1000 + pv 2000); metered draws: battery 800 + consumer 400.
    assert pi.gross_power == pytest.approx(3000.0)
    assert pi.home_base_load_power == pytest.approx(3000.0 - 800.0 - 400.0)

    state = get_sensor_state(hass, entry, f"{entry.entry_id}_home_base_load_power")
    assert state is not None
    assert float(state.state) == pytest.approx(1800.0)

    # The provenance row rides along as attributes, and it is a real mix.
    shares = pi.home_base_load_source_shares
    assert sum(shares.values()) == pytest.approx(1.0)
    assert set(shares) == {GRID_SUB_ID, PV_SUB_ID}
