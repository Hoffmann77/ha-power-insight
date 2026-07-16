"""Class-per-scenario edge-case tests for the ``PowerInsight`` engine.

Each scenario subclasses :class:`EngineScenario` and sets ``DEVICES`` to a list
of :func:`Add` entries — one adapter per line, carrying its preset, index and
reading. Every ``test_`` method asserts one engine property with a hand-written
expected value (derived from first principles, not read back from the engine, so
a regression flips a test red). See ``engine_property_framework.py`` for the
``Add`` reference.

One class = one (device, entity-state) edge case. To test a different set of
readings, write another class — a class never sweeps several entity-value sets.

    class TestMyEdgeCase(EngineScenario):
        DEVICES = [
            Add("grid", power=200, price=0.30),
            Add("pv_with_export", 1, power=1000),
        ]

        def test_some_property(self, power_insight):
            assert power_insight.some_property == pytest.approx(expected)

Sign convention: grid + = import / - = export; pv/bat + = produce/discharge
/ - = standby/charge; consumer - = load.
"""

from __future__ import annotations

import pytest

from tests.engine_property_framework import Add, EngineScenario, build_engine


class TestBatteryChargingSplit(EngineScenario):
    """Grid + PV + one battery charging from grid + PV (gross 4000 W).

    Import 1000 W (gross-power share 0.25) and PV 3000 W (share 0.75) feed a
    500 W battery charge, split 125 W / 375 W by those shares.
    """

    DEVICES = [
        Add("grid", power=1000, price=0.30),
        Add("pv_with_export", 1, power=3000),
        Add("battery", 1, power=-500, charge_from=["grid", "pv1"]),
        Add("consumer", 1, power=-800),
    ]

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == pytest.approx(4000.0)

    def test_combined_charging_power(self, power_insight):
        assert power_insight.combined_charging_power == pytest.approx(500.0)

    def test_charging_source_shares(self, power_insight):
        assert power_insight.storage_adapters_charging_source_shares == {
            "bat1": {"grid": pytest.approx(0.25), "pv1": pytest.approx(0.75)}
        }

    def test_grid_charging_power(self, power_insight):
        assert power_insight.grid_adapters_charging_power == {"grid": pytest.approx(125.0)}

    def test_dynamic_lcoe_blend(self, power_insight):
        # grid coe (= price 0.30) * 0.25 + pv1 lcoe 0.10 * 0.75 = 0.15
        assert power_insight.storage_adapters_dynamic_lcoe == {"bat1": pytest.approx(0.15)}


class TestFullExport(EngineScenario):
    """Grid + PV at midday: import 0, all 3000 W of PV exported."""

    DEVICES = [
        Add("grid", power=-3000, price=0.30),
        Add("pv_with_export", 1, power=3000),
    ]

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == pytest.approx(3000.0)

    def test_combined_grid_export(self, power_insight):
        assert power_insight.combined_grid_export == pytest.approx(3000.0)

    def test_export_ratio_is_one(self, power_insight):
        assert power_insight.gross_power_export_ratio == pytest.approx(1.0)

    def test_combined_consumption_is_zero(self, power_insight):
        assert power_insight.combined_consumption == pytest.approx(0.0)

    def test_export_power(self, power_insight):
        assert power_insight.prod_adapters_export_power == {"pv1": pytest.approx(3000.0)}

    def test_export_compensation_rate(self, power_insight):
        # (3000 W / 1000) * 0.08 EUR/kWh (pv_with_export export_compensation) = 0.24
        assert power_insight.combined_export_compensation_rate == pytest.approx(0.24)


class TestDaytimeSelfConsumption(EngineScenario):
    """Grid + PV: 200 W import + 1000 W PV, all self-consumed (gross 1200 W)."""

    DEVICES = [
        Add("grid", power=200, price=0.30),
        Add("pv_with_export", 1, power=1000),
    ]

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == pytest.approx(1200.0)

    def test_combined_consumption(self, power_insight):
        assert power_insight.combined_consumption == pytest.approx(1200.0)

    def test_no_export(self, power_insight):
        assert power_insight.gross_power_export_ratio == pytest.approx(0.0)

    def test_full_consumption_ratio(self, power_insight):
        assert power_insight.gross_power_consumption_ratio == pytest.approx(1.0)
        assert power_insight.gross_power_applicable_consumption_ratio == pytest.approx(1.0)

    def test_gross_power_shares(self, power_insight):
        assert power_insight.prod_adapters_gross_power_shares == {"pv1": pytest.approx(1000.0 / 1200.0)}
        assert power_insight.grid_adapters_gross_power_shares == {"grid": pytest.approx(200.0 / 1200.0)}

    def test_pv_consumption_power(self, power_insight):
        assert power_insight.prod_adapters_consumption_ratios == {"pv1": pytest.approx(1.0)}
        assert power_insight.prod_adapters_consumption_power == {"pv1": pytest.approx(1000.0)}

    def test_pv_avoided_cost_rate(self, power_insight):
        # (1000 W / 1000) * 0.30 EUR/kWh (grid price) = 0.30 EUR/h
        assert power_insight.prod_adapters_avoided_cost_rates == {"pv1": pytest.approx(0.30)}


class TestNightStandby(EngineScenario):
    """Grid + PV at night: 700 W import, PV drawing 20 W standby."""

    DEVICES = [
        Add("grid", power=700, price=0.25),
        Add("pv_with_export", 1, power=-20),
    ]

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == pytest.approx(700.0)

    def test_combined_production_is_zero(self, power_insight):
        assert power_insight.combined_production == pytest.approx(0.0)

    def test_combined_standby_power(self, power_insight):
        assert power_insight.combined_standby_power == pytest.approx(20.0)

    def test_combined_consumption(self, power_insight):
        # 700 W import - 20 W PV standby = 680 W self-consumed
        assert power_insight.combined_consumption == pytest.approx(680.0)

    def test_standby_ratio(self, power_insight):
        assert power_insight.gross_power_standby_ratio == pytest.approx(20.0 / 700.0)

    def test_combined_coe_equals_grid_price(self, power_insight):
        # PV produces nothing, so only the grid contributes cost -> coe == price
        assert power_insight.combined_coe == pytest.approx(0.25)


class TestAllZero(EngineScenario):
    """Every reading is zero — gross power 0, ratios and coe must guard to 0."""

    DEVICES = [
        Add("grid", power=0, price=0.30),
        Add("pv_with_export", 1, power=0),
        Add("battery", 1, power=0, charge_from=["grid", "pv1"]),
        Add("consumer", 1, power=0),
    ]

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == pytest.approx(0.0)

    def test_combined_consumption(self, power_insight):
        assert power_insight.combined_consumption == pytest.approx(0.0)

    def test_ratios_guard_to_zero(self, power_insight):
        assert power_insight.gross_power_export_ratio == pytest.approx(0.0)
        assert power_insight.gross_power_consumption_ratio == pytest.approx(0.0)

    def test_combined_coe_guards_to_zero(self, power_insight):
        assert power_insight.combined_coe == pytest.approx(0.0)


class TestPureGridExportDegenerate(EngineScenario):
    """Export 500 W with no production: gross power 0, export_ratio must not
    divide by zero, and consumption goes negative (a documented degenerate)."""

    DEVICES = [
        Add("grid", power=-500, price=0.30),
    ]

    def test_combined_grid_import(self, power_insight):
        assert power_insight.combined_grid_import == pytest.approx(0.0)

    def test_combined_grid_export(self, power_insight):
        assert power_insight.combined_grid_export == pytest.approx(500.0)

    def test_gross_power_is_zero(self, power_insight):
        assert power_insight.gross_power == pytest.approx(0.0)

    def test_export_ratio_guards_to_zero(self, power_insight):
        # _divide(500, 0) must return 0.0 rather than raise.
        assert power_insight.gross_power_export_ratio == pytest.approx(0.0)

    def test_consumption_goes_negative(self, power_insight):
        assert power_insight.combined_consumption == pytest.approx(-500.0)


class TestGridUnavailable(EngineScenario):
    """Grid power sensor unavailable -> scalars None, gross-power dicts {}."""

    DEVICES = [
        Add("grid", power=None, price=0.30),
        Add("pv_with_export", 1, power=1000),
        Add("battery", 1, power=0, charge_from=["grid", "pv1"]),
        Add("consumer", 1, power=-200),
    ]

    def test_scalars_are_none(self, power_insight):
        assert power_insight.combined_grid_import is None
        assert power_insight.combined_grid_export is None
        assert power_insight.gross_power is None
        assert power_insight.combined_consumption is None
        assert power_insight.gross_power_export_ratio is None

    def test_gross_power_derived_dicts_are_empty(self, power_insight):
        # These gate on gross_power, which is None -> empty dict.
        assert power_insight.prod_adapters_gross_power_shares == {}
        assert power_insight.grid_adapters_gross_power_shares == {}

    def test_charging_source_shares_degrade_to_zero(self, power_insight):
        # Charging source shares are NOT gross-power gated: with every source
        # weight unknown they collapse to 0.0 (not {} and not None).
        assert power_insight.storage_adapters_charging_source_shares == {
            "bat1": {"grid": pytest.approx(0.0), "pv1": pytest.approx(0.0)}
        }


class TestInvertedGrid(EngineScenario):
    """Inverted grid sensor, no price entity reading, one PV + consumer.

    ``inverted=True`` flips the sign, so a +600 reading is 600 W export; the
    grid has no price reading, so the cost of electricity is undefined.
    """

    DEVICES = [
        Add("grid", power=600, inverted=True),   # +600 inverted -> 600 W export
        Add("pv_with_export", 1, power=2000),
        Add("consumer", 1, power=-1400),
    ]

    def test_inverted_sign(self, power_insight):
        assert power_insight.combined_grid_import == pytest.approx(0.0)
        assert power_insight.combined_grid_export == pytest.approx(600.0)

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == pytest.approx(2000.0)

    def test_combined_consumption(self, power_insight):
        # gross 2000 - export 600 = 1400 W self-consumed
        assert power_insight.combined_consumption == pytest.approx(1400.0)

    def test_no_price_means_no_coe(self, power_insight):
        assert power_insight.combined_coe is None


# ---------------------------------------------------------------------------
# build_engine / Add validation.
# ---------------------------------------------------------------------------


def test_add_rejects_unknown_preset() -> None:
    with pytest.raises(ValueError, match="Unknown adapter preset"):
        Add("pv_with_exprt", 1, power=1000)  # typo


def test_add_rejects_misused_kwarg() -> None:
    with pytest.raises(ValueError, match="'price' is only valid for a grid"):
        Add("pv_with_export", 1, power=1000, price=0.30)


def test_add_rejects_unknown_override() -> None:
    with pytest.raises(ValueError, match="Unknown override"):
        Add("pv_with_export", 1, power=1000, lcox=0.10)  # typo for lcoe


def test_build_engine_requires_exactly_one_grid() -> None:
    with pytest.raises(ValueError, match="exactly one grid"):
        build_engine([Add("pv_with_export", 1, power=1000)])


def test_build_engine_rejects_duplicate_index() -> None:
    with pytest.raises(ValueError, match="duplicate adapter uid"):
        build_engine([
            Add("grid", power=100, price=0.30),
            Add("pv_with_export", 1, power=1000),
            Add("pv_no_export", 1, power=500),  # collides on pv1
        ])


def test_build_engine_rejects_unknown_charge_source() -> None:
    with pytest.raises(ValueError, match="unknown"):
        build_engine([
            Add("grid", power=100, price=0.30),
            Add("battery", 1, power=-100, charge_from=["pv9"]),  # no pv9
        ])


def test_overrides_are_visible_at_call_site() -> None:
    # An expected value that hinges on a config number can state it inline.
    power_insight = build_engine([
        Add("grid", power=-1000, price=0.30),
        Add("pv_with_export", 1, power=1000, export_compensation=0.05),
    ])
    # All 1000 W exported: (1000 / 1000) * 0.05 = 0.05 EUR/h
    assert power_insight.combined_export_compensation_rate == pytest.approx(0.05)
