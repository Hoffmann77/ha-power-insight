"""Class-per-scenario engine tests, built on the shared device/entity layer.

Each scenario is a *class* that pins exactly one device configuration and one
set of entity readings; every ``test_`` method asserts one engine property with
a hand-written expected value. This mirrors the ``TestFullScenario`` style in
``test_power_insight_calculations.py`` but reuses the reusable ``DeviceConfig``
/ preset / ``build_engine_for`` machinery, so no adapter plumbing is repeated.

One class = one (device, entity-state) edge case. To test a different set of
readings, write another class — a class never sweeps several entity-value sets.

Adding a scenario:

    class TestMyEdgeCase:
        DEVICE = PRESET_DEVICES["grid_pv"]        # or a custom DeviceConfig
        ENTITIES = {GRID_POWER: ..., ...}          # exactly one reading set

        @pytest.fixture
        def pi(self):
            return build_engine_for(self.DEVICE, self.ENTITIES)

        def test_some_property(self, pi):
            assert pi.some_property == pytest.approx(expected)
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
