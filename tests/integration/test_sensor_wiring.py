"""Structural tests for the sensor platform's wiring.

Sensor descriptions reach the engine through lambdas (``value_fn``,
``entities_fn``, ``attributes_fn``) and reach the user through
``_SENSOR_OPTION_GATE``. Neither link is visible to a type checker, so a
property renamed in the engine or an option added to a scope's menu breaks
quietly: the first shows up as an ``AttributeError`` at state-write time, the
second as a checkbox that creates nothing.

These tests hold both links closed. They assert structure, not values — what a
sensor *reads* is the engine tests' business.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.power_insight import sensor as sensor_mod
from custom_components.power_insight.const import (
    CONF_ENABLE_CHARGING_SOURCE_SHARES,
    CONF_ENABLE_DEBUG_ENTITIES,
    CONF_ENABLE_POWER_SOURCE_SHARES,
    SCOPE_SUPPORTED_OPTIONS,
)
from .conftest import (
    DOMAIN,
    FULL_OPTIONS,
    PV_SUB_ID,
    make_battery_subentry_data,
    make_consumer_subentry_data,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

#: Which description tuples make up each option scope's sensor set.
SCOPE_GROUPS: dict[str, tuple[str, ...]] = {
    "combined": (
        "POWER_INSIGHT_SENSORS",
        "POWER_INSIGHT_HOME_BASE_LOAD_SENSORS",
        "POWER_INSIGHT_INTEGRATION_SENSORS",
        "POWER_INSIGHT_COMBINED_LEDGER_SENSORS",
    ),
    "grid": (
        "POWER_INSIGHT_GRID_ADAPTER_SENSORS",
        "POWER_INSIGHT_GRID_ADAPTER_INTEGRATION_SENSORS",
    ),
    "pv_system": (
        "POWER_INSIGHT_PV_ADAPTER_SENSORS",
        "POWER_INSIGHT_PV_ADAPTER_INTEGRATION_SENSORS",
    ),
    "battery": (
        "POWER_INSIGHT_STORAGE_ADAPTER_SENSORS",
        "POWER_INSIGHT_STORAGE_ADAPTER_INTEGRATION_SENSORS",
    ),
    "consumer": (
        "POWER_INSIGHT_CONS_ADAPTER_SENSORS",
        "POWER_INSIGHT_CONS_ADAPTER_INTEGRATION_SENSORS",
    ),
}

#: Options whose sensors are built inline in ``async_setup_entry`` — one per
#: source adapter, so there is no static description to gate.
DYNAMICALLY_BUILT = {
    CONF_ENABLE_CHARGING_SOURCE_SHARES,
    CONF_ENABLE_POWER_SOURCE_SHARES,
}


def _descriptions(scope: str):
    for group in SCOPE_GROUPS[scope]:
        yield from getattr(sensor_mod, group)


def _all_descriptions():
    for scope in SCOPE_GROUPS:
        for description in _descriptions(scope):
            yield scope, description


@pytest.fixture
async def loaded_engine(hass: HomeAssistant):
    """A live engine behind a full topology, every reading available."""
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
    return entry.runtime_data.power_insight


# ---------------------------------------------------------------------------
# Descriptions -> engine
# ---------------------------------------------------------------------------


def test_every_scope_has_a_description_group() -> None:
    """A new option scope must bring its sensor group, or it gates nothing."""
    assert set(SCOPE_GROUPS) == set(SCOPE_SUPPORTED_OPTIONS)


async def test_every_description_lambda_resolves(loaded_engine) -> None:
    """No description may reach for an engine property that no longer exists."""
    failures = []
    for scope, description in _all_descriptions():
        for attribute in (
            "value_fn",
            "integration_value_fn",
            "entities_fn",
            "attributes_fn",
            "integration_components_fn",
        ):
            fn = getattr(description, attribute, None)
            if fn is None:
                continue
            try:
                fn(loaded_engine)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{scope}/{description.key}.{attribute}: {exc!r}")

    assert not failures, "sensor lambdas that no longer resolve:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# Descriptions <-> the options menu
# ---------------------------------------------------------------------------


def test_every_offered_option_creates_at_least_one_sensor() -> None:
    """An option a scope's menu offers must actually gate a sensor in it.

    Otherwise the user ticks a box and nothing appears.
    """
    orphans = []
    for scope, supported in SCOPE_SUPPORTED_OPTIONS.items():
        gated_keys = {
            sensor_mod._SENSOR_OPTION_GATE.get(d.key) for d in _descriptions(scope)
        }
        for option in sorted(supported - DYNAMICALLY_BUILT):
            if option not in gated_keys:
                orphans.append(f"{scope}: {option}")

    assert not orphans, "options that create no sensor:\n" + "\n".join(orphans)


def test_no_sensor_is_gated_on_an_option_its_scope_never_offers() -> None:
    """The mirror image: a sensor nothing can ever switch on."""
    unreachable = []
    for scope, description in _all_descriptions():
        gate = sensor_mod._SENSOR_OPTION_GATE.get(description.key)
        if gate is None or gate == CONF_ENABLE_DEBUG_ENTITIES:
            continue
        if gate not in SCOPE_SUPPORTED_OPTIONS[scope]:
            unreachable.append(f"{scope}/{description.key} gated on {gate}")

    assert not unreachable, "sensors that can never be created:\n" + "\n".join(
        unreachable
    )


def test_every_sensor_carries_an_option_gate() -> None:
    """An ungated sensor ignores the user's preset and is always created."""
    ungated = [
        f"{scope}/{description.key}"
        for scope, description in _all_descriptions()
        if description.key not in sensor_mod._SENSOR_OPTION_GATE
    ]

    assert not ungated, "sensors with no entry in _SENSOR_OPTION_GATE:\n" + "\n".join(
        ungated
    )


# ---------------------------------------------------------------------------
# ... and the gate honoured end to end.
# ---------------------------------------------------------------------------


async def test_power_sensors_are_absent_when_distribution_power_is_off(
    hass: HomeAssistant,
) -> None:
    """Turning the distribution-power option off must remove *every* W sensor.

    ``charging_power`` and ``standby_power`` were previously missing from the
    gate map and got created regardless of the option.
    """
    options = {
        "schema": 2,
        "scopes": {
            "combined": ["enable_distribution_ratios"],
            "grid": ["enable_distribution_ratios", "enable_distribution_shares"],
            "pv_system": ["enable_distribution_ratios", "enable_distribution_shares"],
            "battery": ["enable_distribution_ratios", "enable_distribution_shares"],
            "consumer": [],
        },
        "debug_power_entities": False,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=options,
        subentries_data=[
            make_grid_subentry_data(),
            make_pv_subentry_data(),
            make_battery_subentry_data(charge_from_adapters=[PV_SUB_ID]),
        ],
    )
    for entity_id in ("sensor.grid_power", "sensor.pv_power", "sensor.battery_power"):
        hass.states.async_set(entity_id, "100", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    registry = er.async_get(hass)
    power_suffixes = (
        "import_power",
        "export_power",
        "consumption_power",
        "self_consumption_power",
        "charging_power",
        "standby_power",
    )
    created = [
        entity.unique_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
        if entity.unique_id.endswith(power_suffixes)
    ]

    assert created == []
