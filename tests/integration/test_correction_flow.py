"""Tests for the correction-factor reconfigure flow and sensor display (item C)."""

from __future__ import annotations

import copy
from datetime import timedelta

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    DOMAIN,
    BASE_OPTIONS,
    BAT_SUB_ID,
    FULL_OPTIONS,
    PV_SUB_ID,
    GRID_SUB_ID,
    make_battery_subentry_data,
    make_grid_subentry_data,
    make_pv_subentry_data,
    setup_integration,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _pv_state(hass: HomeAssistant, entry: MockConfigEntry, suffix: str):
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.unique_id and ent.unique_id.endswith(suffix):
            return hass.states.get(ent.entity_id)
    return None


# ---------------------------------------------------------------------------
# C2 — reconfigure recomputes the correction factor
# ---------------------------------------------------------------------------


async def test_reconfigure_pv_computes_correction_factor(
    hass: HomeAssistant,
) -> None:
    """Editing lifetime cost yields current_lcoe and a correction factor.

    The immutable base (default_lcoe) is left unchanged and the lifetime
    values are written back to the subentry top level.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data(), make_pv_subentry_data()],
    )
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "adapter"),
        context={"source": "reconfigure", "subentry_id": PV_SUB_ID},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    # Double the lifetime cost (production unchanged): lcoe 0.10 -> 0.20.
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            "power_entity": "sensor.pv_power",
            "power_entity_inverted": False,
            "lifetime_production": 10000.0,
            "lifetime_cost": 2000.0,
        },
    )
    assert result["type"] == FlowResultType.ABORT  # update_reload_and_abort

    subentry = entry.subentries[PV_SUB_ID]
    config = subentry.data["adapter"]["config"]
    assert config["default_lcoe"] == 0.10  # base unchanged
    assert config["current_lcoe"] == pytest.approx(0.20)
    assert config["correction_factor"] == pytest.approx(2.0)
    # Lifetime values are persisted at the subentry top level.
    assert subentry.data["lifetime_cost"] == 2000.0


# ---------------------------------------------------------------------------
# A3 — per-adapter levelized sensors gated on adapter.lcoe
# ---------------------------------------------------------------------------


async def test_levelized_sensors_absent_without_lcoe(hass: HomeAssistant) -> None:
    """A PV adapter without a configured LCOE gets no levelized sensors."""
    pv_data = copy.deepcopy(make_pv_subentry_data())
    # Remove the levelized cost so adapter.lcoe is None.
    pv_data["data"]["adapter"]["config"].pop("default_lcoe")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=[make_grid_subentry_data(), pv_data],
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    ent_reg = er.async_get(hass)
    uids = {
        e.unique_id for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    }
    assert f"{entry.entry_id}_{PV_SUB_ID}_levelized_operating_cost_rate" not in uids


async def test_levelized_sensors_present_with_lcoe(hass: HomeAssistant) -> None:
    """A PV adapter with a configured LCOE gets levelized sensors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=FULL_OPTIONS,
        subentries_data=[make_grid_subentry_data(), make_pv_subentry_data()],
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    ent_reg = er.async_get(hass)
    uids = {
        e.unique_id for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    }
    assert f"{entry.entry_id}_{PV_SUB_ID}_levelized_operating_cost_rate" in uids


# ---------------------------------------------------------------------------
# C4 — per-adapter levelized display is scaled by the correction factor
# ---------------------------------------------------------------------------


async def test_levelized_measurement_applies_factor_to_the_price(
    hass: HomeAssistant,
) -> None:
    """A correction scales the device's *price*, not its finished saving.

    The saving is ``served × (tariff − lcoe)``. Scaling that product by the
    correction factor moves it the wrong way — doubling a PV's lifetime cost
    would double its reported saving, when a dearer kWh can only save less.
    The factor belongs on the lcoe inside the bracket.
    """
    grid_data = copy.deepcopy(make_grid_subentry_data())
    grid_data["data"]["adapter"]["config"]["grid_electricity_price_entity"] = (
        "sensor.grid_price"
    )
    pv_data = copy.deepcopy(make_pv_subentry_data())
    pv_data["data"]["adapter"]["config"]["correction_factor"] = 2.0
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=FULL_OPTIONS,
        subentries_data=[grid_data, pv_data],
    )
    hass.states.async_set("sensor.grid_power", "1000", {"unit_of_measurement": "W"})
    hass.states.async_set(
        "sensor.grid_price", "0.30", {"unit_of_measurement": "EUR/kWh"}
    )
    hass.states.async_set("sensor.pv_power", "2000", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)
    await hass.async_block_till_done()

    pi = entry.runtime_data.power_insight
    base = pi.adapters_levelized_saving_rates.get(PV_SUB_ID)
    corrected = pi.adapters_levelized_saving_rates_corrected.get(PV_SUB_ID)
    state = _pv_state(hass, entry, f"{PV_SUB_ID}_levelized_cost_savings_rate")
    assert state is not None
    assert base is not None and corrected is not None

    # 2 kW served at a 0.30 tariff, lcoe 0.10 doubled to 0.20.
    assert base == pytest.approx(2.0 * (0.30 - 0.10))
    assert corrected == pytest.approx(2.0 * (0.30 - 0.10 * 2.0))
    assert float(state.state) == pytest.approx(corrected, rel=1e-6)
    # Costlier energy saves less. The old behaviour returned base * 2.0.
    assert corrected < base


# ---------------------------------------------------------------------------
# C5b — combined derived sensor reads the retired-adapter ledger
#
# The full removal lifecycle (accumulate -> remove -> snapshot -> reload) is
# covered end-to-end in tests/test_end_to_end.py; here we only check the read
# side: a pre-seeded ledger is reflected in the combined derived sensor.
# ---------------------------------------------------------------------------


async def test_combined_ledger_sensor_includes_retired_totals(
    hass: HomeAssistant,
) -> None:
    """The combined derived sensor adds the frozen retired-adapter totals."""
    from custom_components.power_insight.const import CONF_RETIRED_ADAPTERS

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={
            "schema": 2,
            "scopes": {"combined": ["accumulate_levelized_cost_rates"]},
        },
        data={
            CONF_RETIRED_ADAPTERS: [
                {
                    "subentry_id": "01OLDPV0000000000000000001",
                    "adapter_type": "pv_system",
                    "title": "Old PV",
                    "retired_at": "2026-01-01T00:00:00+00:00",
                    "totals": {"total_levelized_operating_cost": 42.0},
                }
            ],
        },
        subentries_data=[make_grid_subentry_data()],
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
    await setup_integration(hass, entry)

    ent_reg = er.async_get(hass)
    uid = f"{entry.entry_id}_combined_total_levelized_device_operating_cost"
    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, uid)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    # No active levelized adapters; the value is just the frozen ledger sum.
    assert float(state.state) == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# C6 — the accumulated breakdown survives a restart
#
# A total accumulated from a blend of source prices can only be re-corrected
# if the blend is persisted with it. These cover the storage contract itself;
# the arithmetic it enables is pinned in tests/engine/test_full_topology.py.
# ---------------------------------------------------------------------------


def test_stored_data_round_trips_the_component_breakdown() -> None:
    """Components survive serialisation, as Decimals."""
    from decimal import Decimal

    from custom_components.power_insight.entity import (
        IntegrationSensorExtraStoredData,
    )

    stored = IntegrationSensorExtraStoredData(
        Decimal("1.50"),
        "EUR",
        Decimal("1.50"),
        {"pv": Decimal("1.00"), "grid": Decimal("0.50")},
    )
    restored = IntegrationSensorExtraStoredData.from_dict(stored.as_dict())

    assert restored is not None
    assert restored.component_totals == {
        "pv": Decimal("1.00"),
        "grid": Decimal("0.50"),
    }
    # The parts still add up to the total they were split from.
    assert sum(restored.component_totals.values()) == restored.native_value


def test_stored_data_round_trips_the_last_factors() -> None:
    """The last factor seen per component survives serialisation.

    It is what a removed device's share of the total is corrected by once the
    device is no longer there to ask.
    """
    from decimal import Decimal

    from custom_components.power_insight.entity import (
        IntegrationSensorExtraStoredData,
    )

    stored = IntegrationSensorExtraStoredData(
        Decimal("1.50"),
        "EUR",
        Decimal("1.50"),
        {"pv": Decimal("1.00"), "grid": Decimal("0.50")},
        {"pv": 1.5, "grid": 1.0},
    )
    restored = IntegrationSensorExtraStoredData.from_dict(stored.as_dict())

    assert restored is not None
    assert restored.component_factors == {"pv": 1.5, "grid": 1.0}


def test_stored_data_without_components_restores_cleanly() -> None:
    """A total written before the breakdown existed still restores.

    It comes back with no attribution, which is the honest answer — there is
    nothing to correct it by, so the display carries it through unscaled
    rather than inventing a factor for it.
    """
    from decimal import Decimal

    from custom_components.power_insight.entity import (
        IntegrationSensorExtraStoredData,
    )

    legacy = IntegrationSensorExtraStoredData(
        Decimal("2.00"),
        "EUR",
        Decimal("2.00"),
    ).as_dict()
    del legacy["component_totals"]

    restored = IntegrationSensorExtraStoredData.from_dict(legacy)

    assert restored is not None
    assert restored.native_value == Decimal("2.00")
    assert restored.component_totals is None
    assert restored.component_factors is None


# ---------------------------------------------------------------------------
# C7 — a removed device's correction is final
# ---------------------------------------------------------------------------


async def test_removing_a_source_keeps_its_share_corrected(
    hass: HomeAssistant,
) -> None:
    """A removed PV's share of the battery's total keeps the PV's last factor.

    The battery charges 1 kW from the PV for one hour. The PV's lcoe is 0.10
    corrected by 1.5, so the battery's levelized operating cost is 0.10 EUR at
    base and 0.15 EUR displayed. Removing the PV must not move that history:
    the PV can never be edited again, so 1.5 is final. Falling back to 1.0
    would drop the battery's total (and the combined total) to 0.10 EUR — a
    fall the long-term statistics would record — while the PV's own totals
    stay frozen, corrected, in the retired ledger.
    """
    pv = copy.deepcopy(make_pv_subentry_data())
    pv["data"]["adapter"]["config"]["correction_factor"] = 1.5
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options={
            "schema": 2,
            "scopes": {
                "combined": ["accumulate_levelized_cost_rates"],
                "pv_system": ["accumulate_levelized_cost_rates"],
                "battery": ["accumulate_levelized_cost_rates"],
            },
        },
        subentries_data=[
            make_grid_subentry_data(),
            pv,
            make_battery_subentry_data(charge_from_adapters=[PV_SUB_ID]),
        ],
    )
    battery_total = f"{BAT_SUB_ID}_total_levelized_operating_cost"
    combined_total = "combined_total_levelized_device_operating_cost"

    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
        hass.states.async_set("sensor.pv_power", "1000", {"unit_of_measurement": "W"})
        hass.states.async_set(
            "sensor.battery_power", "-1000", {"unit_of_measurement": "W"}
        )
        await setup_integration(hass, entry)

        # Hold the 1 kW charge for one hour, re-reported so the step is exact.
        frozen.move_to(t0 + timedelta(hours=1))
        hass.states.async_set(
            "sensor.battery_power", "-1000", {"unit_of_measurement": "W"}
        )
        for _ in range(4):
            await hass.async_block_till_done()

        before = float(_pv_state(hass, entry, battery_total).state)
        combined_before = float(_pv_state(hass, entry, combined_total).state)
        assert before == pytest.approx(0.15, abs=1e-6)
        assert combined_before == pytest.approx(0.15, abs=1e-6)

        hass.config_entries.async_remove_subentry(entry, PV_SUB_ID)
        for _ in range(4):
            await hass.async_block_till_done()
        # Refresh the derived combined sensor, and prove a second reload (a
        # restart) keeps the factor too.
        await hass.config_entries.async_reload(entry.entry_id)
        hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": "W"})
        for _ in range(4):
            await hass.async_block_till_done()

        assert PV_SUB_ID not in entry.runtime_data.power_insight.levelized_correction_factors
        after = float(_pv_state(hass, entry, battery_total).state)
        combined_after = float(_pv_state(hass, entry, combined_total).state)

    assert after == pytest.approx(before, abs=1e-6)
    assert combined_after == pytest.approx(combined_before, abs=1e-6)


# ---------------------------------------------------------------------------
# C8 — a total with no breakdown is carried at face value
# ---------------------------------------------------------------------------

_SAVINGS_OPTIONS = {
    "schema": 2,
    "scopes": {"pv_system": ["accumulate_levelized_cost_saving_rates"]},
}


def _corrected_pv_entry() -> MockConfigEntry:
    """A PV with lcoe 0.10 corrected by 1.5, behind a priced grid."""
    grid = copy.deepcopy(make_grid_subentry_data())
    grid["data"]["adapter"]["config"]["grid_electricity_price_entity"] = (
        "sensor.grid_price"
    )
    pv = copy.deepcopy(make_pv_subentry_data())
    pv["data"]["adapter"]["config"]["correction_factor"] = 1.5
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=_SAVINGS_OPTIONS,
        subentries_data=[grid, pv],
    )


def _set_pv_home(hass: HomeAssistant) -> None:
    """1 kW imported at 0.30 and 2 kW of PV, all used in the house.

    The PV's levelized saving is 2 kW × (0.30 − 0.10) = 0.40 EUR/h at base,
    and 2 kW × (0.30 − 0.15) = 0.30 EUR/h corrected.
    """
    hass.states.async_set("sensor.grid_power", "1000", {"unit_of_measurement": "W"})
    hass.states.async_set(
        "sensor.grid_price", "0.30", {"unit_of_measurement": "EUR/kWh"}
    )
    hass.states.async_set("sensor.pv_power", "2000", {"unit_of_measurement": "W"})


async def test_a_total_restored_without_a_breakdown_stays_at_face_value(
    hass: HomeAssistant,
) -> None:
    """History with no attribution is never scaled, before or after new slices.

    A total saved before the breakdown existed restores as 10 EUR with no
    components. It must read 10 EUR — not 15 EUR by the PV's own factor, which
    would also scale a saving the wrong way — and must not jump when the first
    component accumulates: after an hour at the corrected 0.30 EUR/h it reads
    10.30 EUR.
    """
    from pytest_homeassistant_custom_component.common import (
        mock_restore_cache_with_extra_data,
    )
    from homeassistant.core import State

    entry = _corrected_pv_entry()
    entry.add_to_hass(hass)
    unique_id = f"{entry.entry_id}_{PV_SUB_ID}_total_levelized_cost_savings"
    entity_id = "sensor.pv_total_levelized_cost_savings"
    er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, unique_id,
        config_entry=entry, config_subentry_id=PV_SUB_ID,
        suggested_object_id="pv_total_levelized_cost_savings",
    )
    mock_restore_cache_with_extra_data(hass, [(
        State(entity_id, "10.0"),
        {
            "native_value": {"__type": "<class 'decimal.Decimal'>", "decimal_str": "10.0"},
            "native_unit_of_measurement": "EUR",
            "last_valid_state": "10.0",
        },
    )])

    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _set_pv_home(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        for _ in range(4):
            await hass.async_block_till_done()
        restored = float(hass.states.get(entity_id).state)

        frozen.move_to(t0 + timedelta(hours=1))
        hass.states.async_set("sensor.pv_power", "2000", {"unit_of_measurement": "W"})
        for _ in range(4):
            await hass.async_block_till_done()
        after_an_hour = float(hass.states.get(entity_id).state)

    assert restored == pytest.approx(10.0, abs=1e-6)
    assert after_an_hour == pytest.approx(10.30, abs=1e-6)


async def test_a_seeded_total_reads_exactly_what_was_set(
    hass: HomeAssistant,
) -> None:
    """``set_value`` replaces the history, breakdown included.

    After an hour the total holds a corrected breakdown. Seeding 5 EUR must
    then read 5 EUR; a breakdown left behind would still be corrected on top
    of the seed and read 4.90 EUR. The seed is then carried at face value.
    """
    entry = _corrected_pv_entry()
    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _set_pv_home(hass)
        await setup_integration(hass, entry)
        frozen.move_to(t0 + timedelta(hours=1))
        hass.states.async_set("sensor.pv_power", "2000", {"unit_of_measurement": "W"})
        for _ in range(4):
            await hass.async_block_till_done()

        suffix = f"{PV_SUB_ID}_total_levelized_cost_savings"
        state = _pv_state(hass, entry, suffix)
        assert float(state.state) == pytest.approx(0.30, abs=1e-6)

        await hass.services.async_call(
            DOMAIN, "set_value", {"value": 5.0},
            target={"entity_id": state.entity_id}, blocking=True,
        )
        for _ in range(4):
            await hass.async_block_till_done()

    assert float(_pv_state(hass, entry, suffix).state) == pytest.approx(5.0, abs=1e-6)


# ---------------------------------------------------------------------------
# C9 — an edit restates the device's whole history
# ---------------------------------------------------------------------------


async def test_an_edit_restates_the_whole_history(hass: HomeAssistant) -> None:
    """Raising the lifetime cost re-prices every kWh already recorded.

    LCOE is a lifetime average, so a revised lifetime cost is the right price
    for past energy too. An hour at 2 kW, 0.30 tariff and lcoe 0.10 saves
    0.40 EUR. Raising the lifetime cost from 1000 to 1500 EUR makes the lcoe
    0.15 (factor 1.5); after the reload the same hour reads
    2 × (0.30 − 0.15) = 0.30 EUR, with nothing accumulated since.
    """
    grid = copy.deepcopy(make_grid_subentry_data())
    grid["data"]["adapter"]["config"]["grid_electricity_price_entity"] = (
        "sensor.grid_price"
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=_SAVINGS_OPTIONS,
        subentries_data=[grid, make_pv_subentry_data()],
    )
    suffix = f"{PV_SUB_ID}_total_levelized_cost_savings"

    t0 = dt_util.utcnow()
    with freeze_time(t0) as frozen:
        _set_pv_home(hass)
        await setup_integration(hass, entry)
        frozen.move_to(t0 + timedelta(hours=1))
        hass.states.async_set("sensor.pv_power", "2000", {"unit_of_measurement": "W"})
        for _ in range(4):
            await hass.async_block_till_done()
        before = float(_pv_state(hass, entry, suffix).state)

        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, "adapter"),
            context={"source": "reconfigure", "subentry_id": PV_SUB_ID},
        )
        await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            user_input={
                "power_entity": "sensor.pv_power",
                "power_entity_inverted": False,
                "lifetime_production": 10000.0,
                "lifetime_cost": 1500.0,
            },
        )
        for _ in range(4):
            await hass.async_block_till_done()
        after = float(_pv_state(hass, entry, suffix).state)

    assert entry.subentries[PV_SUB_ID].data["adapter"]["config"][
        "correction_factor"
    ] == pytest.approx(1.5)
    assert before == pytest.approx(0.40, abs=1e-6)
    assert after == pytest.approx(0.30, abs=1e-6)


def test_reconfigure_without_lifetime_values_keeps_the_base() -> None:
    """Lifetime values missing on reconfigure leave the stored figures alone.

    The form refills emptied fields and rejects 0, so this should not happen
    through the UI; if it ever did, writing None over ``default_lcoe`` would
    make the next lifetime values the new base, and the device's corrected
    history would silently fall back to factor 1.0.
    """
    from custom_components.power_insight.config_flow import (
        BATTERY_FIELDS,
        PV_SYSTEM_FIELDS,
        calculate_fields,
    )

    for fields, price in ((PV_SYSTEM_FIELDS, "lcoe"), (BATTERY_FIELDS, "lcos")):
        stored = {
            f"default_{price}": 0.10,
            f"current_{price}": 0.15,
            "correction_factor": 1.5,
        }
        for missing in ({}, {"lifetime_cost": 0.0, "lifetime_production": 10000.0}):
            result = calculate_fields(
                fields, missing, "reconfigure", existing_data=stored,
            )
            for key, value in stored.items():
                assert result[key] == value, (price, missing, key)
