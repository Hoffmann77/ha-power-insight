"""Tests for PowerInsight — Grid + 3 PV + 3 Battery + 1 Consumer.

Each test method derives its expected value directly from entity_values using
the same formulas that the production code implements.  Adding a new scenario
case requires only a new ENTITY_VALUES entry; no test methods change.

Sign convention (matches power_insight.py):
  Grid   : positive = import, negative = export
  PV/Bat : positive = producing/discharging, negative = standby/charging
"""

from __future__ import annotations

import importlib.util
import os

import pytest

_MODULE_PATH = os.path.join(
    os.path.dirname(__file__),
    os.pardir,
    "custom_components",
    "power_insight",
    "power_insight.py",
)
_spec = importlib.util.spec_from_file_location("power_insight", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

PowerInsight = _mod.PowerInsight
GridAdapter = _mod.GridAdapter
PvAdapter = _mod.PvAdapter
BatteryAdapter = _mod.BatteryAdapter
ConsumerAdapter = _mod.ConsumerAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_power_insight(adapters, entity_values):
    pi = PowerInsight()
    for adapter in adapters:
        pi.register_adapter(adapter)
    for entity_id, value in entity_values.items():
        pi.set_value(entity_id, value)
    return pi


def _divide(a, b):
    if a == 0.0:
        return 0.0
    return a / b


# ---------------------------------------------------------------------------
# Scenario: Grid-1 + PV-1 + PV-2 + PV-3 + Bat-1 + Bat-2 + Bat-3 + Cons-1
#
# PV-1, PV-2  : exports_power=True,  export_compensation=0.08 €/kWh, lcoe=0.10/0.12
# PV-3        : exports_power=False, export_compensation=0.00,        lcoe=0.15
# Bat-1..3    : exports_power=False, charge_from_adapters=[] (no source tracking)
# Cons-1      : plain consumer
# ---------------------------------------------------------------------------

class TestFullScenario:
    """Full adapter set — formula-derived expected values."""

    # --- entity IDs ---
    GRID_POWER   = "sensor.grid_power"
    GRID_PRICE   = "sensor.grid_price"
    PV1_POWER    = "sensor.pv1_power"
    PV2_POWER    = "sensor.pv2_power"
    PV3_POWER    = "sensor.pv3_power"
    BAT1_POWER   = "sensor.bat1_power"
    BAT2_POWER   = "sensor.bat2_power"
    BAT3_POWER   = "sensor.bat3_power"
    CONS1_POWER  = "sensor.cons1_power"

    PV1_LCOE = 0.10
    PV2_LCOE = 0.12
    PV3_LCOE = 0.15
    PV1_EXPORT_COMP = 0.08
    PV2_EXPORT_COMP = 0.08

    ENTITY_VALUES = {
        # Morning: grid imports, PV-1 producing, PV-3 in standby,
        #          Bat-1 discharging, consumer on.
        "morning": {
            GRID_POWER:  1000.0,
            GRID_PRICE:  0.30,
            PV1_POWER:   2000.0,
            PV2_POWER:      0.0,
            PV3_POWER:    -30.0,   # standby draw
            BAT1_POWER:   500.0,   # discharging
            BAT2_POWER:     0.0,
            BAT3_POWER:     0.0,
            CONS1_POWER:  800.0,
        },
        # Midday: grid exporting, all PV at peak, all batteries charging.
        "midday": {
            GRID_POWER:  -3000.0,
            GRID_PRICE:   0.30,
            PV1_POWER:   3000.0,
            PV2_POWER:   2000.0,
            PV3_POWER:   1500.0,
            BAT1_POWER:  -800.0,   # charging
            BAT2_POWER:  -600.0,   # charging
            BAT3_POWER:  -400.0,   # charging
            CONS1_POWER:    0.0,
        },
        # Evening: grid neutral, PV-1 in standby, batteries discharging,
        #          consumer on.
        "evening": {
            GRID_POWER:     0.0,
            GRID_PRICE:   0.30,
            PV1_POWER:    -25.0,   # standby draw
            PV2_POWER:      0.0,
            PV3_POWER:      0.0,
            BAT1_POWER:   800.0,   # discharging
            BAT2_POWER:   600.0,   # discharging
            BAT3_POWER:   200.0,   # discharging
            CONS1_POWER:  800.0,
        },
        # Nighttime: grid imports, all PV in standby, no battery activity.
        "nighttime": {
            GRID_POWER:   700.0,
            GRID_PRICE:   0.25,
            PV1_POWER:    -20.0,
            PV2_POWER:    -10.0,
            PV3_POWER:      0.0,
            BAT1_POWER:     0.0,
            BAT2_POWER:     0.0,
            BAT3_POWER:     0.0,
            CONS1_POWER:  300.0,
        },
        # None: one sensor unavailable → all derived properties return None.
        "none": {
            GRID_POWER:  None,
            GRID_PRICE:  0.30,
            PV1_POWER:   1000.0,
            PV2_POWER:      0.0,
            PV3_POWER:      0.0,
            BAT1_POWER:     0.0,
            BAT2_POWER:     0.0,
            BAT3_POWER:     0.0,
            CONS1_POWER:  500.0,
        },
    }

    ADAPTERS = (
        GridAdapter(
            unique_id="grid",
            verbose_name="Grid",
            power_entity=GRID_POWER,
            price_entity=GRID_PRICE,
        ),
        PvAdapter(
            unique_id="pv1",
            verbose_name="PV-1",
            power_entity=PV1_POWER,
            power_entity_inverted=False,
            lcoe=PV1_LCOE,
            lco2_intensity=35.0,
            exports_power=True,
            export_compensation=PV1_EXPORT_COMP,
        ),
        PvAdapter(
            unique_id="pv2",
            verbose_name="PV-2",
            power_entity=PV2_POWER,
            power_entity_inverted=False,
            lcoe=PV2_LCOE,
            lco2_intensity=40.0,
            exports_power=True,
            export_compensation=PV2_EXPORT_COMP,
        ),
        PvAdapter(
            unique_id="pv3",
            verbose_name="PV-3",
            power_entity=PV3_POWER,
            power_entity_inverted=False,
            lcoe=PV3_LCOE,
            lco2_intensity=50.0,
            exports_power=False,
            export_compensation=0.0,
        ),
        BatteryAdapter(
            unique_id="bat1",
            verbose_name="Battery-1",
            power_entity=BAT1_POWER,
            power_entity_inverted=False,
            lcos=0.15,
            lco2_intensity=50.0,
            exports_power=False,
            export_compensation=0.0,
            charge_from_grid=False,
            charge_from_adapters=[],
        ),
        BatteryAdapter(
            unique_id="bat2",
            verbose_name="Battery-2",
            power_entity=BAT2_POWER,
            power_entity_inverted=False,
            lcos=0.15,
            lco2_intensity=50.0,
            exports_power=False,
            export_compensation=0.0,
            charge_from_grid=False,
            charge_from_adapters=[],
        ),
        BatteryAdapter(
            unique_id="bat3",
            verbose_name="Battery-3",
            power_entity=BAT3_POWER,
            power_entity_inverted=False,
            lcos=0.15,
            lco2_intensity=50.0,
            exports_power=False,
            export_compensation=0.0,
            charge_from_grid=False,
            charge_from_adapters=[],
        ),
        ConsumerAdapter(
            unique_id="cons1",
            verbose_name="Consumer-1",
            power_entity=CONS1_POWER,
        ),
    )

    @pytest.fixture(params=list(ENTITY_VALUES))
    def entity_values(self, request):
        return self.ENTITY_VALUES[request.param]

    @pytest.fixture()
    def test_case(self, request):
        return request.node.callspec.params["entity_values"]

    @pytest.fixture()
    def power_insight(self, entity_values):
        return build_power_insight(self.ADAPTERS, entity_values)

    # ------------------------------------------------------------------
    # Helpers: derive primitive quantities from raw entity_values.
    # All returned values are floats; None inputs propagate naturally.
    # ------------------------------------------------------------------

    def _ev(self, ev):
        """Unpack the seven power readings from entity_values."""
        grid  = ev[self.GRID_POWER]
        pv1   = ev[self.PV1_POWER]
        pv2   = ev[self.PV2_POWER]
        pv3   = ev[self.PV3_POWER]
        bat1  = ev[self.BAT1_POWER]
        bat2  = ev[self.BAT2_POWER]
        bat3  = ev[self.BAT3_POWER]
        return grid, pv1, pv2, pv3, bat1, bat2, bat3

    def _base(self, ev):
        """Return the fundamental derived scalars used across many tests."""
        grid, pv1, pv2, pv3, bat1, bat2, bat3 = self._ev(ev)
        if grid is None:
            return None, None, None, None, None, None, None, None

        grid_import   = max(grid, 0.0)
        grid_export   = max(-grid, 0.0)
        pv_prod       = max(pv1, 0.0) + max(pv2, 0.0) + max(pv3, 0.0)
        pv_standby    = max(-pv1, 0.0) + max(-pv2, 0.0) + max(-pv3, 0.0)
        bat_discharge = max(bat1, 0.0) + max(bat2, 0.0) + max(bat3, 0.0)
        bat_charging  = max(-bat1, 0.0) + max(-bat2, 0.0) + max(-bat3, 0.0)
        gross         = grid_import + pv_prod + bat_discharge
        consumption   = gross - grid_export - bat_charging - pv_standby
        return (grid_import, grid_export, pv_prod, pv_standby,
                bat_discharge, bat_charging, gross, consumption)

    # ------------------------------------------------------------------
    # Layer 1 — direct power readings
    # ------------------------------------------------------------------

    def test_combined_grid_import(self, power_insight, entity_values, test_case):
        grid = entity_values[self.GRID_POWER]
        expected = None if grid is None else max(grid, 0.0)
        assert power_insight.combined_grid_import == expected

    def test_combined_grid_export(self, power_insight, entity_values, test_case):
        grid = entity_values[self.GRID_POWER]
        expected = None if grid is None else max(-grid, 0.0)
        assert power_insight.combined_grid_export == expected

    def test_combined_production(self, power_insight, entity_values, test_case):
        pv1 = entity_values[self.PV1_POWER]
        pv2 = entity_values[self.PV2_POWER]
        pv3 = entity_values[self.PV3_POWER]
        expected = max(pv1, 0.0) + max(pv2, 0.0) + max(pv3, 0.0)
        assert power_insight.combined_production == expected

    def test_combined_standby_power(self, power_insight, entity_values, test_case):
        pv1 = entity_values[self.PV1_POWER]
        pv2 = entity_values[self.PV2_POWER]
        pv3 = entity_values[self.PV3_POWER]
        expected = max(-pv1, 0.0) + max(-pv2, 0.0) + max(-pv3, 0.0)
        assert power_insight.combined_standby_power == expected

    def test_combined_discharging_power(self, power_insight, entity_values, test_case):
        bat1 = entity_values[self.BAT1_POWER]
        bat2 = entity_values[self.BAT2_POWER]
        bat3 = entity_values[self.BAT3_POWER]
        expected = max(bat1, 0.0) + max(bat2, 0.0) + max(bat3, 0.0)
        assert power_insight.combined_discharging_power == expected

    def test_combined_charging_power(self, power_insight, entity_values, test_case):
        bat1 = entity_values[self.BAT1_POWER]
        bat2 = entity_values[self.BAT2_POWER]
        bat3 = entity_values[self.BAT3_POWER]
        expected = max(-bat1, 0.0) + max(-bat2, 0.0) + max(-bat3, 0.0)
        assert power_insight.combined_charging_power == expected

    # ------------------------------------------------------------------
    # Layer 2 — derived scalars
    # ------------------------------------------------------------------

    def test_gross_power(self, power_insight, entity_values, test_case):
        b = self._base(entity_values)
        expected = None if b[0] is None else b[6]  # gross
        assert power_insight.gross_power == expected

    def test_combined_consumption(self, power_insight, entity_values, test_case):
        b = self._base(entity_values)
        expected = None if b[0] is None else b[7]  # consumption
        assert power_insight.combined_consumption == expected

    # ------------------------------------------------------------------
    # Layer 3 — gross power ratios
    # ------------------------------------------------------------------

    def test_gross_power_export_ratio(self, power_insight, entity_values, test_case):
        b = self._base(entity_values)
        if b[0] is None:
            assert power_insight.gross_power_export_ratio is None
            return
        _, grid_export, _, _, _, _, gross, _ = b
        expected = _divide(grid_export, gross)
        assert power_insight.gross_power_export_ratio == pytest.approx(expected)

    def test_gross_power_consumption_ratio(self, power_insight, entity_values, test_case):
        b = self._base(entity_values)
        if b[0] is None:
            assert power_insight.gross_power_consumption_ratio is None
            return
        _, _, _, _, _, _, gross, consumption = b
        expected = _divide(consumption, gross)
        assert power_insight.gross_power_consumption_ratio == pytest.approx(expected)

    def test_gross_power_standby_ratio(self, power_insight, entity_values, test_case):
        b = self._base(entity_values)
        if b[0] is None:
            assert power_insight.gross_power_standby_ratio is None
            return
        _, _, _, pv_standby, _, _, gross, _ = b
        expected = _divide(pv_standby, gross)
        assert power_insight.gross_power_standby_ratio == pytest.approx(expected)

    def test_gross_power_charging_ratio(self, power_insight, entity_values, test_case):
        b = self._base(entity_values)
        if b[0] is None:
            assert power_insight.gross_power_charging_ratio is None
            return
        _, _, _, _, _, bat_charging, gross, _ = b
        expected = _divide(bat_charging, gross)
        assert power_insight.gross_power_charging_ratio == pytest.approx(expected)

    def test_gross_power_applicable_consumption_ratio(self, power_insight, entity_values, test_case):
        b = self._base(entity_values)
        if b[0] is None:
            assert power_insight.gross_power_applicable_consumption_ratio is None
            return
        _, grid_export, _, _, _, bat_charging, gross, consumption = b
        export_ratio   = _divide(grid_export, gross)
        charging_ratio = _divide(bat_charging, gross)
        cons_ratio     = _divide(consumption, gross)
        denom = 1.0 - export_ratio - charging_ratio
        expected = _divide(cons_ratio, denom)
        assert power_insight.gross_power_applicable_consumption_ratio == pytest.approx(expected)

    # ------------------------------------------------------------------
    # Layer 4 — per-adapter allocation (PV adapters only; batteries have
    # exports_power=False and charge_from_adapters=[], simplifying shares)
    # ------------------------------------------------------------------

    def _pv_export_shares(self, ev):
        """
        Compute prod_adapters_export_shares for pv1/pv2 (the only exporters).
        pv3, bat1..3 have exports_power=False → share = 0.
        """
        b = self._base(ev)
        if b[0] is None:
            return {}
        grid_import, _, _, _, bat_discharge, _, gross, _ = b
        pv1 = max(ev[self.PV1_POWER], 0.0)
        pv2 = max(ev[self.PV2_POWER], 0.0)
        # gross_power_shares for pv1, pv2
        s1 = _divide(pv1, gross)
        s2 = _divide(pv2, gross)
        total_exportable = s1 + s2
        return {
            "pv1": _divide(s1, total_exportable),
            "pv2": _divide(s2, total_exportable),
            "pv3": 0.0,
        }

    def test_prod_adapters_gross_power_shares(self, power_insight, entity_values, test_case):
        b = self._base(entity_values)
        if b[0] is None:
            assert power_insight.prod_adapters_gross_power_shares == {}
            return
        _, _, _, _, _, _, gross, _ = b
        pv1 = max(entity_values[self.PV1_POWER], 0.0)
        pv2 = max(entity_values[self.PV2_POWER], 0.0)
        pv3 = max(entity_values[self.PV3_POWER], 0.0)
        bat1 = max(entity_values[self.BAT1_POWER], 0.0)
        bat2 = max(entity_values[self.BAT2_POWER], 0.0)
        bat3 = max(entity_values[self.BAT3_POWER], 0.0)
        expected = {
            "pv1":  _divide(pv1,  gross),
            "pv2":  _divide(pv2,  gross),
            "pv3":  _divide(pv3,  gross),
            "bat1": _divide(bat1, gross),
            "bat2": _divide(bat2, gross),
            "bat3": _divide(bat3, gross),
        }
        assert power_insight.prod_adapters_gross_power_shares == pytest.approx(expected)

    def test_prod_adapters_export_shares(self, power_insight, entity_values, test_case):
        b = self._base(entity_values)
        if b[0] is None:
            assert power_insight.prod_adapters_export_shares == {}
            return
        expected_pv = self._pv_export_shares(entity_values)
        result = power_insight.prod_adapters_export_shares
        assert result.get("pv1", 0.0) == pytest.approx(expected_pv["pv1"])
        assert result.get("pv2", 0.0) == pytest.approx(expected_pv["pv2"])
        assert result.get("pv3", 0.0) == pytest.approx(expected_pv["pv3"])
        # batteries do not export
        for uid in ("bat1", "bat2", "bat3"):
            assert result.get(uid, 0.0) == pytest.approx(0.0)

    def test_prod_adapters_export_power(self, power_insight, entity_values, test_case):
        b = self._base(entity_values)
        if b[0] is None:
            assert power_insight.prod_adapters_export_power == {}
            return
        _, grid_export, _, _, _, _, _, _ = b
        export_shares = self._pv_export_shares(entity_values)
        expected = {uid: grid_export * s for uid, s in export_shares.items()}
        # batteries: export_share=0 → export_power=0
        for uid in ("bat1", "bat2", "bat3"):
            expected[uid] = 0.0
        result = power_insight.prod_adapters_export_power
        assert result == pytest.approx(expected)

    def test_prod_adapters_export_compensation_rates(self, power_insight, entity_values, test_case):
        b = self._base(entity_values)
        if b[0] is None:
            result = power_insight.prod_adapters_export_compensation_rates
            assert all(v is None for v in result.values())
            return
        _, grid_export, _, _, _, _, _, _ = b
        export_shares = self._pv_export_shares(entity_values)
        expected = {
            "pv1":  (grid_export * export_shares["pv1"]  / 1000) * self.PV1_EXPORT_COMP,
            "pv2":  (grid_export * export_shares["pv2"]  / 1000) * self.PV2_EXPORT_COMP,
            "pv3":  0.0,
            "bat1": 0.0,
            "bat2": 0.0,
            "bat3": 0.0,
        }
        result = power_insight.prod_adapters_export_compensation_rates
        assert result == pytest.approx(expected)

    def test_prod_adapters_avoided_cost_rates(self, power_insight, entity_values, test_case):
        """
        avoided_cost_rate[uid] = (consumption_power[uid] / 1000) * grid_coe
        consumption_power[uid] = production[uid] * consumption_ratio[uid]

        For adapters with exports_power=False and no charging tracking,
        consumption_ratio = (1 - 0 - 0) * applicable_ratio = applicable_ratio.
        For exporting PV adapters:
        consumption_ratio = (1 - export_ratio_adapter - 0) * applicable_ratio
        """
        b = self._base(entity_values)
        if b[0] is None:
            result = power_insight.prod_adapters_avoided_cost_rates
            assert all(v is None for v in result.values())
            return
        grid_import, grid_export, _, _, _, bat_charging, gross, consumption = b
        grid_coe = entity_values[self.GRID_PRICE]

        export_ratio   = _divide(grid_export, gross)
        charging_ratio = _divide(bat_charging, gross)
        cons_ratio     = _divide(consumption, gross)
        denom          = 1.0 - export_ratio - charging_ratio
        applicable     = _divide(cons_ratio, denom)

        export_shares = self._pv_export_shares(entity_values)

        def _avoided(prod, exp_share):
            if not prod:
                return 0.0
            power_share = _divide(prod, gross)
            # adapter export_ratio = exp_share * total_export_ratio / power_share
            adapter_exp_ratio = _divide(exp_share * export_ratio, power_share)
            cons_r = (1.0 - adapter_exp_ratio) * applicable
            return (prod * cons_r / 1000) * grid_coe

        pv1 = max(entity_values[self.PV1_POWER], 0.0)
        pv2 = max(entity_values[self.PV2_POWER], 0.0)
        pv3 = max(entity_values[self.PV3_POWER], 0.0)
        bat1 = max(entity_values[self.BAT1_POWER], 0.0)
        bat2 = max(entity_values[self.BAT2_POWER], 0.0)
        bat3 = max(entity_values[self.BAT3_POWER], 0.0)

        expected = {
            "pv1":  _avoided(pv1,  export_shares["pv1"]),
            "pv2":  _avoided(pv2,  export_shares["pv2"]),
            "pv3":  _avoided(pv3,  0.0),
            "bat1": _avoided(bat1, 0.0),
            "bat2": _avoided(bat2, 0.0),
            "bat3": _avoided(bat3, 0.0),
        }
        result = power_insight.prod_adapters_avoided_cost_rates
        assert result == pytest.approx(expected)

    # ------------------------------------------------------------------
    # Layer 5 — combined monetary rates
    # ------------------------------------------------------------------

    def test_combined_export_compensation_rate(self, power_insight, entity_values, test_case):
        b = self._base(entity_values)
        if b[0] is None:
            assert power_insight.combined_export_compensation_rate is None
            return
        _, grid_export, _, _, _, _, _, _ = b
        export_shares = self._pv_export_shares(entity_values)
        expected = (
            (grid_export * export_shares["pv1"] / 1000) * self.PV1_EXPORT_COMP
            + (grid_export * export_shares["pv2"] / 1000) * self.PV2_EXPORT_COMP
        )
        assert power_insight.combined_export_compensation_rate == pytest.approx(expected)

    def test_combined_avoided_cost_rate(self, power_insight, entity_values, test_case):
        b = self._base(entity_values)
        if b[0] is None:
            assert power_insight.combined_avoided_cost_rate is None
            return
        # combined_avoided_cost_rate = sum of prod_adapters_avoided_cost_rates
        avoided = power_insight.prod_adapters_avoided_cost_rates
        expected = sum(avoided.values())
        assert power_insight.combined_avoided_cost_rate == pytest.approx(expected)
