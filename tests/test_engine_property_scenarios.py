"""Class-per-scenario engine tests, built on the shared device/entity layer.

This is the alternative authoring style to ``test_engine_property_cases.py``
(the declarative ``EngineCase`` list). Here a scenario is a *class*: it names a
device configuration and entity readings, and each ``test_`` method asserts one
engine property. It mirrors the ``TestFullScenario`` style in
``test_power_insight_calculations.py`` but reuses the reusable
``DeviceConfig`` / preset / ``build_engine_for`` machinery, so no adapter
plumbing is repeated.

Two shapes are shown:

* :class:`TestBatteryChargingSplit` — one class = one (device, entity-state)
  edge case, with per-property assertions carrying inline literal expected
  values. Cleanest when you want granular, individually-named property tests
  for a single interesting state.

* :class:`TestGridPvAcrossStates` — one device explored across several named
  entity states via a parametrized fixture, with the hand-written expected
  values co-located in a per-state table. Use this when you want "a number of
  entity values to test for" in a single class.

Pick whichever reads better for the scenario; both share the same foundation
as the declarative cases, so devices, presets and validation behave identically.
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

    One entity state; each property is its own named test with an inline
    expected value derived from first principles.
    """

    DEVICE = PRESET_DEVICES["grid_pv_battery"]
    ENTITIES = {
        GRID_POWER: 1000.0,   # import -> gross-power share 0.25
        GRID_PRICE: 0.30,
        PV1_POWER: 3000.0,    # produce -> gross-power share 0.75
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
        # Sources weighted by gross-power share: grid 0.25, pv1 0.75.
        assert pi.storage_adapters_charging_source_shares == {
            "bat1": {"grid": pytest.approx(0.25), "pv1": pytest.approx(0.75)}
        }

    def test_grid_charging_power(self, pi):
        # 500 W split 0.25/0.75 -> grid feeds 125 W of the charging.
        assert pi.grid_adapters_charging_power == {"grid": pytest.approx(125.0)}

    def test_dynamic_lcoe_blend(self, pi):
        # grid coe (= price 0.30) * 0.25 + pv1 lcoe 0.10 * 0.75 = 0.15
        assert pi.storage_adapters_dynamic_lcoe == {"bat1": pytest.approx(0.15)}


class TestGridPvAcrossStates:
    """One grid + PV device explored across several entity states.

    The device is fixed; ``STATES`` maps a state name to its entity readings
    and the hand-written expected values for the properties under test. The
    parametrized ``pi`` fixture builds a fresh engine per state, and each
    ``test_`` method looks up that state's expected value.
    """

    DEVICE = PRESET_DEVICES["grid_pv"]

    # state -> {"entities": {...}, "expected": {property: value}}
    STATES = {
        "full_export": {
            "entities": {GRID_POWER: -3000.0, GRID_PRICE: 0.30, PV1_POWER: 3000.0},
            "expected": {
                "gross_power": 3000.0,
                "combined_grid_export": 3000.0,
                "gross_power_export_ratio": 1.0,
                "combined_consumption": 0.0,
            },
        },
        "self_consumption": {
            "entities": {GRID_POWER: 200.0, GRID_PRICE: 0.30, PV1_POWER: 1000.0},
            "expected": {
                "gross_power": 1200.0,
                "combined_grid_export": 0.0,
                "gross_power_export_ratio": 0.0,
                "combined_consumption": 1200.0,
            },
        },
        "night_standby": {
            "entities": {GRID_POWER: 700.0, GRID_PRICE: 0.25, PV1_POWER: -20.0},
            "expected": {
                "gross_power": 700.0,
                "combined_grid_export": 0.0,
                "gross_power_export_ratio": 0.0,
                "combined_consumption": 680.0,  # 700 import - 20 PV standby
            },
        },
    }

    @pytest.fixture(params=list(STATES), ids=list(STATES))
    def state(self, request):
        return self.STATES[request.param]

    @pytest.fixture
    def pi(self, state):
        return build_engine_for(self.DEVICE, state["entities"])

    def test_gross_power(self, pi, state):
        assert pi.gross_power == pytest.approx(state["expected"]["gross_power"])

    def test_combined_grid_export(self, pi, state):
        assert pi.combined_grid_export == pytest.approx(
            state["expected"]["combined_grid_export"]
        )

    def test_gross_power_export_ratio(self, pi, state):
        assert pi.gross_power_export_ratio == pytest.approx(
            state["expected"]["gross_power_export_ratio"]
        )

    def test_combined_consumption(self, pi, state):
        assert pi.combined_consumption == pytest.approx(
            state["expected"]["combined_consumption"]
        )
