"""Edge-case tests for the ``PowerInsight`` engine, driven declaratively.

Each :class:`EngineCase` pairs a device configuration and a set of entity
readings (preset or custom) with a block of hand-computed expected property
values. See ``engine_property_framework.py`` for the full API.

To add an edge case, append an :class:`EngineCase` to ``CASES`` — no new test
method is needed. The last section verifies the framework's own matching
behaviour (numbers/None/dicts/subset/predicate and entity-id validation).
"""

from __future__ import annotations

import pytest

from tests.engine_property_framework import (
    BAT1_POWER,
    CONS1_POWER,
    GRID_POWER,
    GRID_PRICE,
    PV1_POWER,
    BatterySpec,
    ConsumerSpec,
    DeviceConfig,
    EngineCase,
    GridSpec,
    PvSpec,
    assert_engine_case,
    build_engine,
    evaluate_case,
    subset,
)


# ---------------------------------------------------------------------------
# Edge cases. Expected values are derived from first principles (the documented
# model), not read back from the engine, so a regression flips a test red.
#
# Sign convention: grid + = import / - = export; pv/bat + = produce/discharge
# / - = standby/charge.
# ---------------------------------------------------------------------------

CASES: list[EngineCase] = [
    # --- Unavailability: a single None sensor collapses derived values. ------
    EngineCase(
        name="grid_unavailable_propagates_none",
        device="grid_pv_battery",
        entities={
            GRID_POWER: None,
            GRID_PRICE: 0.30,
            PV1_POWER: 1000.0,
            BAT1_POWER: 0.0,
            CONS1_POWER: -200.0,
        },
        notes="Grid power None -> scalars None, per-adapter dicts {}.",
        expected={
            "combined_grid_import": None,
            "combined_grid_export": None,
            "gross_power": None,
            "combined_consumption": None,
            "gross_power_export_ratio": None,
            "prod_adapters_gross_power_shares": {},
            "storage_adapters_charging_source_shares": subset({}),
        },
    ),
    # --- Everything idle: gross power 0, ratios guard to 0.0. ----------------
    EngineCase(
        name="all_zero_readings",
        device="grid_pv_battery",
        entities="all_zero",
        notes="Zero gross power must not raise; ratios and coe guard to 0.0.",
        expected={
            "combined_grid_import": 0.0,
            "combined_grid_export": 0.0,
            "combined_production": 0.0,
            "combined_discharging_power": 0.0,
            "combined_charging_power": 0.0,
            "gross_power": 0.0,
            "combined_consumption": 0.0,
            "gross_power_export_ratio": 0.0,
            "gross_power_consumption_ratio": 0.0,
            "combined_coe": 0.0,
        },
    ),
    # --- Pure grid export with no production: the degenerate _divide guard. --
    EngineCase(
        name="pure_grid_export_zero_gross",
        device="grid_only",
        entities={GRID_POWER: -500.0, GRID_PRICE: 0.30},
        notes=(
            "Export 500 W but gross power 0 (no import/production). "
            "export_ratio must guard to 0.0 rather than divide by zero; "
            "consumption goes negative (documented degenerate)."
        ),
        expected={
            "combined_grid_import": 0.0,
            "combined_grid_export": 500.0,
            "combined_production": 0.0,
            "gross_power": 0.0,
            "combined_consumption": -500.0,
            "gross_power_export_ratio": 0.0,
            "gross_power_consumption_ratio": 0.0,
        },
    ),
    # --- Full-export midday: all production leaves via the grid. ------------
    EngineCase(
        name="full_export_single_pv",
        device="grid_pv",
        entities={GRID_POWER: -3000.0, GRID_PRICE: 0.30, PV1_POWER: 3000.0},
        notes="Import 0, all 3000 W PV exported. export_ratio == 1.0.",
        expected={
            "combined_grid_export": 3000.0,
            "combined_production": 3000.0,
            "gross_power": 3000.0,
            "combined_consumption": 0.0,
            "gross_power_export_ratio": 1.0,
            "gross_power_consumption_ratio": 0.0,
            "prod_adapters_gross_power_shares": {"pv1": 1.0},
            "prod_adapters_export_shares": {"pv1": 1.0},
            "prod_adapters_export_power": {"pv1": 3000.0},
            # (3000 W * 1.0 / 1000) * 0.08 EUR/kWh = 0.24 EUR/h
            "combined_export_compensation_rate": 0.24,
        },
    ),
    # --- Night standby: only the grid feeds the house + PV standby draw. ----
    EngineCase(
        name="night_import_with_pv_standby",
        device="grid_pv",
        entities={GRID_POWER: 700.0, GRID_PRICE: 0.25, PV1_POWER: -20.0},
        notes="Import 700 W, PV drawing 20 W standby. Consumption = 680 W.",
        expected={
            "combined_grid_import": 700.0,
            "combined_production": 0.0,
            "combined_standby_power": 20.0,
            "gross_power": 700.0,
            "combined_consumption": 680.0,
            "gross_power_standby_ratio": 20.0 / 700.0,
            "gross_power_consumption_ratio": 680.0 / 700.0,
            # Only the grid contributes cost, PV produces nothing -> coe == price
            "combined_coe": 0.25,
        },
    ),
    # --- Daytime self-consumption: import + PV, nothing exported/charged. ----
    EngineCase(
        name="daytime_full_self_consumption",
        device="grid_pv",
        entities={GRID_POWER: 200.0, GRID_PRICE: 0.30, PV1_POWER: 1000.0},
        notes="Import 200 W + PV 1000 W, all self-consumed (gross 1200 W).",
        expected={
            "gross_power": 1200.0,
            "combined_consumption": 1200.0,
            "gross_power_export_ratio": 0.0,
            "gross_power_consumption_ratio": 1.0,
            "gross_power_applicable_consumption_ratio": 1.0,
            "prod_adapters_gross_power_shares": {"pv1": 1000.0 / 1200.0},
            "grid_adapters_gross_power_shares": {"grid": 200.0 / 1200.0},
            "prod_adapters_consumption_ratios": {"pv1": 1.0},
            "prod_adapters_consumption_power": {"pv1": 1000.0},
            # avoided cost = (1000 W / 1000) * 0.30 EUR/kWh = 0.30 EUR/h
            "prod_adapters_avoided_cost_rates": {"pv1": 0.30},
        },
    ),
    # --- Battery charging routed across grid + PV by gross-power weight. -----
    EngineCase(
        name="battery_charging_source_split",
        device="grid_pv_battery",
        entities={
            GRID_POWER: 1000.0,
            GRID_PRICE: 0.30,
            PV1_POWER: 3000.0,
            BAT1_POWER: -500.0,
            CONS1_POWER: -800.0,
        },
        notes=(
            "gross 4000 W (grid 0.25, pv1 0.75). Battery charges 500 W from "
            "grid+pv1, split 125 W / 375 W. dynamic_lcoe blends grid coe (=price "
            "0.30) and pv1 lcoe 0.10 -> 0.15."
        ),
        expected={
            "gross_power": 4000.0,
            "combined_charging_power": 500.0,
            "grid_adapters_gross_power_shares": {"grid": 0.25},
            # prod_adapters spans PV + storage; the charging battery produces
            # nothing, so its gross-power share is 0.0 (present, not absent).
            "prod_adapters_gross_power_shares": {"pv1": 0.75, "bat1": 0.0},
            "storage_adapters_charging_source_shares": {
                "bat1": {"grid": 0.25, "pv1": 0.75}
            },
            "grid_adapters_charging_power": {"grid": 125.0},
            "prod_adapters_charging_power": subset({"pv1": 375.0}),
            "storage_adapters_dynamic_lcoe": {"bat1": 0.30 * 0.25 + 0.10 * 0.75},
            "storage_adapters_dynamic_coe": {"bat1": 0.30 * 0.25 + 0.0 * 0.75},
        },
    ),
    # --- Custom device + custom entities: inverted grid sensor, no price. ----
    EngineCase(
        name="custom_inverted_grid_no_price",
        device=DeviceConfig(
            grid=GridSpec(
                power_entity="sensor.custom_grid",
                price_entity=None,
                power_entity_inverted=True,
            ),
            pv=(PvSpec(uid="pvx", power_entity="sensor.custom_pv", lcoe=0.11),),
            consumers=(ConsumerSpec(uid="cx", power_entity="sensor.custom_cons"),),
        ),
        entities={
            # Inverted: a +600 reading means 600 W export in engine convention.
            "sensor.custom_grid": 600.0,
            "sensor.custom_pv": 2000.0,
            "sensor.custom_cons": -1400.0,
        },
        notes="power_entity_inverted flips the sign: +600 -> 600 W export.",
        expected={
            "combined_grid_import": 0.0,
            "combined_grid_export": 600.0,
            "combined_production": 2000.0,
            "gross_power": 2000.0,
            "combined_consumption": 1400.0,
            # No grid price entity -> cost of electricity undefined.
            "combined_coe": None,
        },
    ),
    # --- Preset device + preset entities + one override. --------------------
    EngineCase(
        name="full_midday_but_grid_sensor_unavailable",
        device="full",
        entities="midday",
        entity_overrides={GRID_POWER: None},
        notes="Reuses the midday preset but knocks out the grid sensor.",
        expected={
            "gross_power": None,
            "combined_grid_export": None,
            "prod_adapters_gross_power_shares": {},
        },
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_engine_property_case(case: EngineCase) -> None:
    assert_engine_case(case)


# ---------------------------------------------------------------------------
# Framework self-tests: the harness must catch mismatches and typos, and its
# resolution/validation must behave as documented.
# ---------------------------------------------------------------------------


def _passing_probe() -> EngineCase:
    return EngineCase(
        name="probe",
        device="grid_only",
        entities={GRID_POWER: 1000.0, GRID_PRICE: 0.30},
        expected={"combined_grid_import": 1000.0},
    )


def test_framework_flags_number_mismatch() -> None:
    case = EngineCase(
        name="wrong_number",
        device="grid_only",
        entities={GRID_POWER: 1000.0, GRID_PRICE: 0.30},
        expected={"combined_grid_import": 999.0},
    )
    _, failures = evaluate_case(case)
    assert len(failures) == 1
    assert "combined_grid_import" in failures[0]


def test_framework_flags_none_mismatch() -> None:
    case = EngineCase(
        name="expected_none_got_value",
        device="grid_only",
        entities={GRID_POWER: 1000.0, GRID_PRICE: 0.30},
        expected={"combined_grid_import": None},
    )
    _, failures = evaluate_case(case)
    assert failures and "expected None" in failures[0]


def test_framework_flags_unknown_property() -> None:
    case = EngineCase(
        name="typo_property",
        device="grid_only",
        entities={GRID_POWER: 1000.0, GRID_PRICE: 0.30},
        expected={"combined_grid_imprt": 1000.0},
    )
    _, failures = evaluate_case(case)
    assert failures and "no such property" in failures[0]


def test_framework_dict_key_mismatch_is_caught() -> None:
    case = EngineCase(
        name="extra_dict_key",
        device="grid_pv",
        entities={GRID_POWER: 200.0, GRID_PRICE: 0.30, PV1_POWER: 1000.0},
        # Real result only has "pv1"; expecting a ghost uid must fail.
        expected={"prod_adapters_gross_power_shares": {"pv1": 1000.0 / 1200.0,
                                                       "ghost": 0.0}},
    )
    _, failures = evaluate_case(case)
    assert failures and "key mismatch" in failures[0]


def test_framework_subset_ignores_extra_keys() -> None:
    # subset() checks only pv1 even though the real dict has more entries.
    case = EngineCase(
        name="subset_ok",
        device="full",
        entities="midday",
        expected={"prod_adapters_gross_power_shares": subset({"pv1": 3000.0 / 6500.0})},
    )
    assert_engine_case(case)  # must not raise


def test_framework_predicate_matching() -> None:
    case = EngineCase(
        name="predicate",
        device="grid_only",
        entities={GRID_POWER: 1000.0, GRID_PRICE: 0.30},
        expected={"combined_grid_import": lambda v: v > 0},
    )
    assert_engine_case(case)


def test_framework_rejects_unknown_entity_id() -> None:
    case = EngineCase(
        name="typo_entity",
        device="grid_only",
        entities={"sensor.grid_powr": 1000.0},  # typo, not canonical/routable
        expected={},
    )
    with pytest.raises(ValueError, match="unknown entity id"):
        build_engine(case)


def test_framework_ignores_absent_canonical_entities() -> None:
    # A battery reading is canonical but not routable on grid_pv -> skipped,
    # not an error, so shared entity presets work on smaller devices.
    case = EngineCase(
        name="canonical_absent_ok",
        device="grid_pv",
        entities="midday",  # includes bat/pv2/pv3 readings the device lacks
        expected={"combined_grid_export": 3000.0},
    )
    assert_engine_case(case)


def test_assert_engine_case_returns_engine() -> None:
    pi = assert_engine_case(_passing_probe())
    # The returned engine supports ad-hoc assertions beyond `expected`.
    assert pi.combined_grid_import == 1000.0
