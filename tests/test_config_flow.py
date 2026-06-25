"""Tests for the PowerInsight config flow and subentry flows."""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import DOMAIN, BASE_OPTIONS, make_grid_subentry_data

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
    """The initial step collects only the name and seeds the default options."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Test PowerInsight"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test PowerInsight"
    # Fresh installs seed the per-scope schema with sensible defaults.
    options = result["options"]
    assert options["schema"] == 2
    combined = options["scopes"]["combined"]
    assert "calculate_cost_saving_rates" in combined
    assert "enable_distribution_power" in combined
    # Grid has no savings sensors, so it only gets its supported defaults.
    assert "calculate_cost_saving_rates" not in options["scopes"]["grid"]


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
# Options flow
# ---------------------------------------------------------------------------


async def test_options_flow_shows_menu(hass: HomeAssistant) -> None:
    """The options flow init step shows the per-scope section menu."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data()],
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"
    # Combined + grid (present) + diagnostics; no pv/battery/consumer, no save.
    assert "combined" in result["menu_options"]
    assert "grid" in result["menu_options"]
    assert "diagnostics" in result["menu_options"]
    assert "done" in result["menu_options"]
    assert "save" not in result["menu_options"]
    assert "battery" not in result["menu_options"]


async def test_options_flow_submit_saves_and_returns_to_menu(
    hass: HomeAssistant,
) -> None:
    """Submitting a section persists immediately and returns to the menu."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data()],
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "combined"}
    )
    assert result["step_id"] == "combined"
    # Only distribution sensors → no data requirements → saves directly.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "cost_rates": [],
            "cost_savings_rates": [],
            "accumulated_costs": [],
            "accumulated_cost_savings": [],
            "distribution_power": True,
            "distribution_ratios": False,
        },
    )
    # Saved immediately, and the flow stays open on the menu.
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"
    assert entry.options["scopes"]["combined"] == ["enable_distribution_power"]

    # "Done" closes the dialog.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "done"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_options_flow_warns_then_saves_under_configured(
    hass: HomeAssistant,
) -> None:
    """Enabling a cost rate with no price entity warns, then saves on confirm."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data()],
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "grid"}
    )
    assert result["step_id"] == "grid"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "cost_rates": ["calculate_cost_rates"],
            "accumulated_costs": [],
            "export_compensation": [],
            "distribution_power": False,
            "distribution_ratios": False,
            "distribution_shares": False,
        },
    )
    # Grid has no price entity → confirm step (save anyway).
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["errors"]["base"] == "reconfigure_adapters_first"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={}
    )
    # Saved (anyway) and back at the menu.
    assert result["type"] == FlowResultType.MENU
    assert entry.options["scopes"]["grid"] == ["calculate_cost_rates"]
