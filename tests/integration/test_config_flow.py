"""Tests for the PowerInsight config flow and subentry flows."""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import DOMAIN, GRID_SUB_ID, BASE_OPTIONS, make_grid_subentry_data

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


# ---------------------------------------------------------------------------
# Main config flow
# ---------------------------------------------------------------------------


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    """The initial user step should display a configuration form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_empty_name_returns_error(hass: HomeAssistant) -> None:
    """Submitting an empty name should return a form with a validation error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": ""},
    )
    assert result["type"] == FlowResultType.FORM
    assert "name" in result["errors"]


async def test_user_step_creates_entry(hass: HomeAssistant) -> None:
    """Name step advances to preset step; completing both creates the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Test PowerInsight"},
    )
    # Name step should advance to the preset step, not create the entry yet.
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "preset"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"preset": "recommended"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test PowerInsight"
    # Recommended preset seeds sensible per-scope defaults.
    options = result["options"]
    assert options["schema"] == 2
    combined = options["scopes"]["combined"]
    assert "accumulate_cost_saving_rates" in combined
    assert "enable_distribution_power" in combined
    # Grid has no savings sensors, so they are absent from its scope.
    assert "accumulate_cost_saving_rates" not in options["scopes"]["grid"]


# ---------------------------------------------------------------------------
# Subentry flow — menu
# ---------------------------------------------------------------------------


async def test_subentry_menu_includes_grid_when_none_configured(
    hass: HomeAssistant,
) -> None:
    """The subentry menu should include 'grid' when no grid adapter exists yet."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"), context={"source": "user"}
    )
    assert result["type"] == FlowResultType.MENU
    assert "grid" in result["menu_options"]


async def test_subentry_menu_excludes_grid_when_already_configured(
    hass: HomeAssistant,
) -> None:
    """The subentry menu should omit 'grid' when a grid adapter already exists."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data()],
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"), context={"source": "user"}
    )
    assert result["type"] == FlowResultType.MENU
    assert "grid" not in result["menu_options"]


# ---------------------------------------------------------------------------
# Subentry flow — grid adapter
# ---------------------------------------------------------------------------


async def test_subentry_grid_creates_subentry(hass: HomeAssistant) -> None:
    """Completing the grid subentry flow should create a grid adapter subentry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
    )
    entry.add_to_hass(hass)

    hass.states.async_set(
        "sensor.grid_power", "100", {"unit_of_measurement": "W"}
    )

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input={"next_step_id": "grid"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "configure"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            "power_entity": "sensor.grid_power",
            "power_entity_inverted": False,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Grid"

    subentries = list(entry.subentries.values())
    assert len(subentries) == 1
    adapter = subentries[0].data["adapter"]
    assert adapter["adapter_type"] == "grid"
    assert adapter["config"]["power_entity"] == "sensor.grid_power"


# ---------------------------------------------------------------------------
# Subentry flow — consumer adapter
# ---------------------------------------------------------------------------


async def test_subentry_consumer_creates_subentry(hass: HomeAssistant) -> None:
    """Completing the consumer subentry flow should create a consumer adapter."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
    )
    entry.add_to_hass(hass)

    hass.states.async_set(
        "sensor.dishwasher_power", "1500", {"unit_of_measurement": "W"}
    )

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input={"next_step_id": "consumer"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "configure"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            "name": "Dishwasher",
            "power_entity": "sensor.dishwasher_power",
            "power_entity_inverted": False,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Dishwasher"

    subentries = list(entry.subentries.values())
    assert len(subentries) == 1
    adapter = subentries[0].data["adapter"]
    assert adapter["adapter_type"] == "consumer"
    assert adapter["config"]["power_entity"] == "sensor.dishwasher_power"


async def test_subentry_consumer_rejects_duplicate_name(
    hass: HomeAssistant,
) -> None:
    """Two consumer subentries with the same name should fail with a slug conflict error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[
            {
                "subentry_id": "01CONSUMER000000000000001A",
                "subentry_type": "adapter",
                "title": "Heat pump",
                "unique_id": None,
                "data": {
                    "adapter": {
                        "adapter_type": "consumer",
                        "key": "heat_pump",
                        "config": {
                            "power_entity": "sensor.heat_pump_power",
                            "power_entity_inverted": False,
                        },
                    },
                },
            }
        ],
    )
    entry.add_to_hass(hass)

    hass.states.async_set(
        "sensor.other_power", "100", {"unit_of_measurement": "W"}
    )

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input={"next_step_id": "consumer"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            "name": "Heat pump",  # duplicate slug
            "power_entity": "sensor.other_power",
            "power_entity_inverted": False,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"].get("base") == "name_not_unique"


# ---------------------------------------------------------------------------
# Subentry flow — PV system adapter
# ---------------------------------------------------------------------------


async def test_subentry_pv_creates_subentry(hass: HomeAssistant) -> None:
    """Completing the PV system subentry flow should create a PV adapter."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
    )
    entry.add_to_hass(hass)

    hass.states.async_set(
        "sensor.solar_power", "2000", {"unit_of_measurement": "W"}
    )

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input={"next_step_id": "pv_system"}
    )
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            "name": "Rooftop Solar",
            "power_entity": "sensor.solar_power",
            "power_entity_inverted": False,
            "exports_power": True,
            "export_compensation": 0.08,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Rooftop Solar"

    subentries = list(entry.subentries.values())
    assert len(subentries) == 1
    adapter = subentries[0].data["adapter"]
    assert adapter["adapter_type"] == "pv_system"
    assert adapter["config"]["exports_power"] is True


# ---------------------------------------------------------------------------
# Subentry flow — battery adapter
# ---------------------------------------------------------------------------


async def test_subentry_battery_rejects_empty_charge_source(
    hass: HomeAssistant,
) -> None:
    """A battery submitted with no charge source is rejected with an error.

    An empty charge_from is a misconfiguration (a battery with no source cannot
    charge), so the flow re-shows the form instead of creating the subentry.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data()],
    )
    entry.add_to_hass(hass)

    hass.states.async_set(
        "sensor.battery_power", "0", {"unit_of_measurement": "W"}
    )

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input={"next_step_id": "battery"}
    )
    assert result["step_id"] == "configure"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            "name": "Home Battery",
            "power_entity": "sensor.battery_power",
            "power_entity_inverted": False,
            "charge_from_adapters": [],  # no charge source selected
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"].get("charge_from_adapters") == "charge_sources_required"


async def test_subentry_battery_creates_subentry_with_charge_source(
    hass: HomeAssistant,
) -> None:
    """Selecting at least one charge source lets the battery subentry be created."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data()],
    )
    entry.add_to_hass(hass)

    hass.states.async_set(
        "sensor.battery_power", "0", {"unit_of_measurement": "W"}
    )

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input={"next_step_id": "battery"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            "name": "Home Battery",
            "power_entity": "sensor.battery_power",
            "power_entity_inverted": False,
            "charge_from_adapters": [GRID_SUB_ID],
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    adapter = list(entry.subentries.values())[-1].data["adapter"]
    assert adapter["adapter_type"] == "battery"
    assert adapter["config"]["charge_from_adapters"] == [GRID_SUB_ID]


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


async def test_options_flow_shows_single_form(hass: HomeAssistant) -> None:
    """The options flow init shows a preset selector and debug toggle."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data()],
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    keys = {str(getattr(k, "schema", k)) for k in result["data_schema"].schema}
    assert "preset" in keys
    assert "debug_power_entities" in keys
    # Old section keys must not appear in the simplified init form.
    assert "grid" not in keys
    assert "diagnostics" not in keys
    assert "distribution_power" not in keys


async def test_options_flow_submit_saves_everything(hass: HomeAssistant) -> None:
    """Choosing a non-custom preset on the init step saves immediately."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data()],
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"preset": "minimal", "debug_power_entities": True},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    # Minimal preset: distribution ratios + financial-return sensors.
    combined = entry.options["scopes"]["combined"]
    assert "enable_distribution_ratios" in combined
    assert "calculate_financial_return_rate" in combined
    assert entry.options["debug_power_entities"] is True


async def test_options_flow_blocks_under_configured(hass: HomeAssistant) -> None:
    """Enabling a cost rate when no price entity is set re-shows the last scope with an error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data()],
    )
    entry.add_to_hass(hass)

    # Start custom flow.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"preset": "custom", "debug_power_entities": False},
    )
    assert result["step_id"] == "combined"

    # Combined: nothing enabled.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "power_sensors": {"distribution_power": False, "distribution_ratios": False},
            "costs": {"cost_method": "none", "accumulate_costs": False},
            "savings": {"savings_method": "none", "accumulate_savings": False},
            "financial_return": {
                "financial_return_method": "none",
                "accumulate_financial_return": False,
            },
        },
    )
    assert result["step_id"] == "grid"

    # Grid: enable cost — but the grid adapter has no price entity.
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
            "costs": {"cost_method": "standard", "accumulate_costs": False},
        },
    )
    # Grid has no price entity → blocked; last scope form re-shown with an error.
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "grid"
    assert result["errors"]["base"] == "reconfigure_adapters_first"
