"""Class-per-scenario edge-case tests for the ``PowerInsight`` engine.

Each scenario is a *class* that pins exactly one device configuration and one
set of entity readings; every ``test_`` method asserts one engine property with
a hand-written expected value (derived from first principles, not read back from
the engine, so a regression flips a test red). This mirrors the
``TestFullScenario`` style in ``test_power_insight_calculations.py`` but reuses
the reusable ``DeviceConfig`` / preset / ``build_engine_for`` machinery in
``engine_property_framework.py``, so no adapter plumbing is repeated.

One class = one (device, entity-state) edge case. To test a different set of
readings, write another class — a class never sweeps several entity-value sets.

    class TestMyEdgeCase:
        DEVICE = PRESET_DEVICES["grid_pv"]        # or a custom DeviceConfig
        ENTITIES = {GRID_POWER: ..., ...}          # exactly one reading set

        @pytest.fixture
        def pi(self):
            return build_engine_for(self.DEVICE, self.ENTITIES)

        def test_some_property(self, pi):
            assert pi.some_property == pytest.approx(expected)

Sign convention: grid + = import / - = export; pv/bat + = produce/discharge
/ - = standby/charge.
"""

from __future__ import annotations

import pytest

from tests.engine_property_framework import (
    BAT1_POWER,
    CONS1_POWER,
    GRID_POWER,
    GRID_PRICE,
    PV1_POWER,
    PRESET_DEVICES,
    ConsumerSpec,
    DeviceConfig,
    GridSpec,
    PvSpec,
    build_engine_for,
)


class TestBatteryChargingSplit:
    """Grid + PV + one battery charging from grid + PV (gross 4000 W).

    Import 1000 W (gross-power share 0.25) and PV 3000 W (share 0.75) feed a
    500 W battery charge, split 125 W / 375 W by those shares.
    """

    DEVICE = PRESET_DEVICES["grid_pv_battery"]
    ENTITIES = {
        GRID_POWER: 1000.0,
        GRID_PRICE: 0.30,
        PV1_POWER: 3000.0,
        BAT1_POWER: -500.0,   # charging 500 W
        CONS1_POWER: -800.0,
    }

    @pytest.fixture
    def pi(self):
        return build_engine_for(self.DEVICE, self.ENTITIES)

    def test_gross_power(self, pi):
        assert pi.gross_power == pytest.approx(4000.0)

    def test_combined_charging_power(self, pi):
        assert pi.combined_charging_power == pytest.approx(500.0)

    def test_charging_source_shares(self, pi):
        assert pi.storage_adapters_charging_source_shares == {
            "bat1": {"grid": pytest.approx(0.25), "pv1": pytest.approx(0.75)}
        }

    def test_grid_charging_power(self, pi):
        assert pi.grid_adapters_charging_power == {"grid": pytest.approx(125.0)}

    def test_dynamic_lcoe_blend(self, pi):
        # grid coe (= price 0.30) * 0.25 + pv1 lcoe 0.10 * 0.75 = 0.15
        assert pi.storage_adapters_dynamic_lcoe == {"bat1": pytest.approx(0.15)}


class TestFullExport:
    """Grid + PV at midday: import 0, all 3000 W of PV exported."""

    DEVICE = PRESET_DEVICES["grid_pv"]
    ENTITIES = {GRID_POWER: -3000.0, GRID_PRICE: 0.30, PV1_POWER: 3000.0}

    @pytest.fixture
    def pi(self):
        return build_engine_for(self.DEVICE, self.ENTITIES)

    def test_gross_power(self, pi):
        assert pi.gross_power == pytest.approx(3000.0)

    def test_combined_grid_export(self, pi):
        assert pi.combined_grid_export == pytest.approx(3000.0)

    def test_export_ratio_is_one(self, pi):
        assert pi.gross_power_export_ratio == pytest.approx(1.0)

    def test_combined_consumption_is_zero(self, pi):
        assert pi.combined_consumption == pytest.approx(0.0)

    def test_export_power(self, pi):
        assert pi.prod_adapters_export_power == {"pv1": pytest.approx(3000.0)}

    def test_export_compensation_rate(self, pi):
        # (3000 W / 1000) * 0.08 EUR/kWh = 0.24 EUR/h
        assert pi.combined_export_compensation_rate == pytest.approx(0.24)


class TestDaytimeSelfConsumption:
    """Grid + PV: 200 W import + 1000 W PV, all self-consumed (gross 1200 W)."""

    DEVICE = PRESET_DEVICES["grid_pv"]
    ENTITIES = {GRID_POWER: 200.0, GRID_PRICE: 0.30, PV1_POWER: 1000.0}

    @pytest.fixture
    def pi(self):
        return build_engine_for(self.DEVICE, self.ENTITIES)

    def test_gross_power(self, pi):
        assert pi.gross_power == pytest.approx(1200.0)

    def test_combined_consumption(self, pi):
        assert pi.combined_consumption == pytest.approx(1200.0)

    def test_no_export(self, pi):
        assert pi.gross_power_export_ratio == pytest.approx(0.0)

    def test_full_consumption_ratio(self, pi):
        assert pi.gross_power_consumption_ratio == pytest.approx(1.0)
        assert pi.gross_power_applicable_consumption_ratio == pytest.approx(1.0)

    def test_gross_power_shares(self, pi):
        assert pi.prod_adapters_gross_power_shares == {"pv1": pytest.approx(1000.0 / 1200.0)}
        assert pi.grid_adapters_gross_power_shares == {"grid": pytest.approx(200.0 / 1200.0)}

    def test_pv_consumption_power(self, pi):
        assert pi.prod_adapters_consumption_ratios == {"pv1": pytest.approx(1.0)}
        assert pi.prod_adapters_consumption_power == {"pv1": pytest.approx(1000.0)}

    def test_pv_avoided_cost_rate(self, pi):
        # (1000 W / 1000) * 0.30 EUR/kWh = 0.30 EUR/h
        assert pi.prod_adapters_avoided_cost_rates == {"pv1": pytest.approx(0.30)}


class TestNightStandby:
    """Grid + PV at night: 700 W import, PV drawing 20 W standby."""

    DEVICE = PRESET_DEVICES["grid_pv"]
    ENTITIES = {GRID_POWER: 700.0, GRID_PRICE: 0.25, PV1_POWER: -20.0}

    @pytest.fixture
    def pi(self):
        return build_engine_for(self.DEVICE, self.ENTITIES)

    def test_gross_power(self, pi):
        assert pi.gross_power == pytest.approx(700.0)

    def test_combined_production_is_zero(self, pi):
        assert pi.combined_production == pytest.approx(0.0)

    def test_combined_standby_power(self, pi):
        assert pi.combined_standby_power == pytest.approx(20.0)

    def test_combined_consumption(self, pi):
        # 700 W import - 20 W PV standby = 680 W self-consumed
        assert pi.combined_consumption == pytest.approx(680.0)

    def test_standby_ratio(self, pi):
        assert pi.gross_power_standby_ratio == pytest.approx(20.0 / 700.0)

    def test_combined_coe_equals_grid_price(self, pi):
        # PV produces nothing, so only the grid contributes cost -> coe == price
        assert pi.combined_coe == pytest.approx(0.25)


class TestAllZero:
    """Every reading is zero — gross power 0, ratios and coe must guard to 0."""

    DEVICE = PRESET_DEVICES["grid_pv_battery"]
    ENTITIES = {
        GRID_POWER: 0.0,
        GRID_PRICE: 0.30,
        PV1_POWER: 0.0,
        BAT1_POWER: 0.0,
        CONS1_POWER: 0.0,
    }

    @pytest.fixture
    def pi(self):
        return build_engine_for(self.DEVICE, self.ENTITIES)

    def test_gross_power(self, pi):
        assert pi.gross_power == pytest.approx(0.0)

    def test_combined_consumption(self, pi):
        assert pi.combined_consumption == pytest.approx(0.0)

    def test_ratios_guard_to_zero(self, pi):
        assert pi.gross_power_export_ratio == pytest.approx(0.0)
        assert pi.gross_power_consumption_ratio == pytest.approx(0.0)

    def test_combined_coe_guards_to_zero(self, pi):
        assert pi.combined_coe == pytest.approx(0.0)


class TestPureGridExportDegenerate:
    """Export 500 W with no production: gross power 0, export_ratio must not
    divide by zero, and consumption goes negative (a documented degenerate)."""

    DEVICE = PRESET_DEVICES["grid_only"]
    ENTITIES = {GRID_POWER: -500.0, GRID_PRICE: 0.30}

    @pytest.fixture
    def pi(self):
        return build_engine_for(self.DEVICE, self.ENTITIES)

    def test_combined_grid_import(self, pi):
        assert pi.combined_grid_import == pytest.approx(0.0)

    def test_combined_grid_export(self, pi):
        assert pi.combined_grid_export == pytest.approx(500.0)

    def test_gross_power_is_zero(self, pi):
        assert pi.gross_power == pytest.approx(0.0)

    def test_export_ratio_guards_to_zero(self, pi):
        # _divide(500, 0) must return 0.0 rather than raise.
        assert pi.gross_power_export_ratio == pytest.approx(0.0)

    def test_consumption_goes_negative(self, pi):
        assert pi.combined_consumption == pytest.approx(-500.0)


class TestGridUnavailable:
    """Grid power sensor unavailable -> scalars None, per-adapter dicts {}."""

    DEVICE = PRESET_DEVICES["grid_pv_battery"]
    ENTITIES = {
        GRID_POWER: None,
        GRID_PRICE: 0.30,
        PV1_POWER: 1000.0,
        BAT1_POWER: 0.0,
        CONS1_POWER: -200.0,
    }

    @pytest.fixture
    def pi(self):
        return build_engine_for(self.DEVICE, self.ENTITIES)

    def test_scalars_are_none(self, pi):
        assert pi.combined_grid_import is None
        assert pi.combined_grid_export is None
        assert pi.gross_power is None
        assert pi.combined_consumption is None
        assert pi.gross_power_export_ratio is None

    def test_gross_power_derived_dicts_are_empty(self, pi):
        # These gate on gross_power, which is None -> empty dict.
        assert pi.prod_adapters_gross_power_shares == {}
        assert pi.grid_adapters_gross_power_shares == {}

    def test_charging_source_shares_degrade_to_zero(self, pi):
        # Charging source shares are NOT gross-power gated: with every source
        # weight unknown they collapse to 0.0 (not {} and not None).
        assert pi.storage_adapters_charging_source_shares == {
            "bat1": {"grid": pytest.approx(0.0), "pv1": pytest.approx(0.0)}
        }


class TestCustomInvertedGrid:
    """Custom device: inverted grid sensor, no price entity, one PV + consumer.

    ``power_entity_inverted`` flips the sign, so a +600 reading is 600 W export.
    """

    DEVICE = DeviceConfig(
        grid=GridSpec(
            power_entity="sensor.custom_grid",
            price_entity=None,
            power_entity_inverted=True,
        ),
        pv=(PvSpec(uid="pvx", power_entity="sensor.custom_pv", lcoe=0.11),),
        consumers=(ConsumerSpec(uid="cx", power_entity="sensor.custom_cons"),),
    )
    ENTITIES = {
        "sensor.custom_grid": 600.0,    # inverted -> 600 W export
        "sensor.custom_pv": 2000.0,
        "sensor.custom_cons": -1400.0,
    }

    @pytest.fixture
    def pi(self):
        return build_engine_for(self.DEVICE, self.ENTITIES)

    def test_inverted_sign(self, pi):
        assert pi.combined_grid_import == pytest.approx(0.0)
        assert pi.combined_grid_export == pytest.approx(600.0)

    def test_gross_power(self, pi):
        assert pi.gross_power == pytest.approx(2000.0)

    def test_combined_consumption(self, pi):
        # gross 2000 - export 600 = 1400 W self-consumed
        assert pi.combined_consumption == pytest.approx(1400.0)

    def test_no_price_means_no_coe(self, pi):
        assert pi.combined_coe is None


# ---------------------------------------------------------------------------
# build_engine_for validation: entity ids must be routable for the device.
# ---------------------------------------------------------------------------


def test_build_engine_for_rejects_unknown_entity() -> None:
    with pytest.raises(ValueError, match="unknown entity id"):
        build_engine_for("grid_only", {"sensor.grid_powr": 1000.0})  # typo


def test_build_engine_for_rejects_nonroutable_entity() -> None:
    # A battery reading on a grid_pv device (no battery adapter) is a mismatch.
    with pytest.raises(ValueError, match="unknown entity id"):
        build_engine_for("grid_pv", {GRID_POWER: 100.0, BAT1_POWER: -100.0})


def test_build_engine_for_unknown_preset_device() -> None:
    with pytest.raises(KeyError, match="Unknown preset device"):
        build_engine_for("does_not_exist", {GRID_POWER: 100.0})
