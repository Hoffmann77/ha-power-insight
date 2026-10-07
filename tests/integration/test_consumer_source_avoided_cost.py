"""A consumer's avoided cost, split by the source that served it.

"Avoided cost from Solar PV" is what the PV system's power kept off this
consumer's grid bill; together they add up to the consumer's avoided cost.
The grid gets none: it is the alternative being priced against.
"""

from __future__ import annotations

import copy
from datetime import timedelta

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    CONS_SUB_ID,
    DOMAIN,
    GRID_SUB_ID,
    PV_SUB_ID,
    make_consumer_subentry_data,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

RATES = ["calculate_cost_saving_rates", "enable_source_avoided_cost"]
TOTALS = RATES + ["accumulate_cost_saving_rates"]


def _entry(consumer_options: list[str]) -> MockConfigEntry:
    grid = copy.deepcopy(make_grid_subentry_data())
    grid["data"]["adapter"]["config"]["grid_electricity_price_entity"] = "sensor.grid_price"
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={"schema": 2, "scopes": {"consumer": consumer_options}},
        subentries_data=[grid, make_pv_subentry_data(), make_consumer_subentry_data()],
    )


def _state(hass: HomeAssistant, entry: MockConfigEntry, key: str):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{CONS_SUB_ID}_{key}"
    )
    return None if entity_id is None else hass.states.get(entity_id)


def _float(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> float:
    state = _state(hass, entry, key)
    assert state is not None, f"{key} was not created"
    assert state.state not in ("unknown", "unavailable"), f"{key} is {state.state}"
    return float(state.state)


def _set(hass: HomeAssistant, entity: str, value: float, unit: str = "W") -> None:
    hass.states.async_set(f"sensor.{entity}", str(value), {"unit_of_measurement": unit})


def _readings(hass: HomeAssistant) -> None:
    """Grid 500 W, PV 500 W, the unrestricted consumer draws 400 W, at 0.30.

    Half of everything comes from each source, so 200 W of the draw is PV:
    0.2 kW × 0.30 = 0.06 EUR/h avoided.
    """
    _set(hass, "grid_power", 500)
    _set(hass, "pv_power", 500)
    _set(hass, "consumer_power", -400)
    _set(hass, "grid_price", 0.30, unit="EUR/kWh")


async def _settle(hass: HomeAssistant) -> None:
    for _ in range(4):
        await hass.async_block_till_done()


async def test_one_rate_per_local_source_adding_up_to_the_avoided_cost(
    hass: HomeAssistant,
) -> None:
    """The PV's 200 W avoided 0.06 EUR/h, which is the whole avoided cost.

    There is no sensor for the grid: its watts avoid nothing.
    """
    entry = _entry(RATES)
    _readings(hass)
    await setup_integration(hass, entry)
    await _settle(hass)

    from_pv = _float(hass, entry, f"avoided_cost_from_{PV_SUB_ID}")
    assert from_pv == pytest.approx(0.06)
    assert from_pv == pytest.approx(_float(hass, entry, "avoided_cost_rate"))
    assert _state(hass, entry, f"avoided_cost_from_{GRID_SUB_ID}") is None
    # The rates alone, without Total savings.
    assert _state(hass, entry, f"total_avoided_cost_from_{PV_SUB_ID}") is None


async def test_a_removed_source_keeps_its_avoided_cost(hass: HomeAssistant) -> None:
    """An hour at 0.06 EUR/h is 0.06 EUR from the PV system; removing it
    freezes that into "Total avoided cost from removed devices".
    """
    entry = _entry(TOTALS)
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _readings(hass)
        await setup_integration(hass, entry)
        _set(hass, "grid_power", 500)
        await _settle(hass)
        frozen.move_to(t0 + timedelta(hours=1))
        _set(hass, "grid_power", 500)
        await _settle(hass)

    total = _float(hass, entry, f"total_avoided_cost_from_{PV_SUB_ID}")
    assert total == pytest.approx(0.06, abs=1e-3)
    assert total == pytest.approx(_float(hass, entry, "total_avoided_cost"), abs=1e-6)

    hass.config_entries.async_remove_subentry(entry, PV_SUB_ID)
    await _settle(hass)

    [retired] = entry.data["retired_sources"]
    assert retired["totals"][CONS_SUB_ID]["total_avoided_cost_from"] == pytest.approx(total)
    removed = _state(hass, entry, "total_avoided_cost_from_removed_devices")
    assert float(removed.state) == pytest.approx(total)
    assert removed.attributes["device_class"] == "monetary"
    assert "state_class" not in removed.attributes


def test_the_split_needs_the_standard_method() -> None:
    """It splits the standard avoided cost, so it needs that method."""
    from custom_components.power_insight.config_flow import scope_ui_to_leaves

    chosen = {"avoided_cost_by_source": True}
    assert "enable_source_avoided_cost" in scope_ui_to_leaves(
        "consumer", {**chosen, "savings_method": "standard"}
    )
    assert "enable_source_avoided_cost" not in scope_ui_to_leaves(
        "consumer", {**chosen, "savings_method": "none"}
    )
