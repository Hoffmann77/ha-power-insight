"""Tests for PowerInsight core calculation logic.

Three scenarios of increasing complexity:
  1. Grid + PV  (excess production → exporting)
  2. Grid + PV + Battery  (all consumed, no export)
  3. Grid + PV + Battery + Consumer  (consumer cost allocation)
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

# Import power_insight.py directly (bypassing the package __init__.py
# which depends on Home Assistant).
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

def build_power_insight(adapters, values):
    """Create a PowerInsight instance, register adapters, and set values."""
    pi = PowerInsight()
    for adapter in adapters:
        pi.register_adapter(adapter)
    for entity_id, value in values.items():
        pi.set_value(entity_id, value)
    return pi


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

# Entity IDs (arbitrary strings – only need to be consistent)
GRID_POWER = "sensor.grid_power"
GRID_PRICE = "sensor.grid_price"
PV_POWER = "sensor.pv_power"
BAT_POWER = "sensor.bat_power"
CONS_POWER = "sensor.consumer_power"

# Config constants
GRID_PRICE_VALUE = 0.30   # EUR/kWh
PV_LCOE = 0.08            # EUR/kWh
PV_EXPORT_COMP = 0.08     # EUR/kWh
BAT_LCOS = 0.12           # EUR/kWh


def _make_grid(power_value, price_value=GRID_PRICE_VALUE):
    adapter = GridAdapter(
        unique_id="grid",
        verbose_name="Grid",
        power_entity=GRID_POWER,
        price_entity=GRID_PRICE,
    )
    return adapter, {GRID_POWER: power_value, GRID_PRICE: price_value}


def _make_pv(power_value, lcoe=PV_LCOE, exports=True, compensation=PV_EXPORT_COMP):
    adapter = PvAdapter(
        unique_id="pv",
        verbose_name="PV",
        power_entity=PV_POWER,
        power_entity_inverted=False,
        lcoe=lcoe,
        lco2_intensity=0.0,
        exports_power=exports,
        export_compensation=compensation,
    )
    return adapter, {PV_POWER: power_value}


def _make_battery(power_value, lcos=BAT_LCOS, exports=False, compensation=0.0):
    adapter = BatteryAdapter(
        unique_id="bat",
        verbose_name="Battery",
        power_entity=BAT_POWER,
        power_entity_inverted=False,
        lcos=lcos,
        lco2_intensity=0.0,
        exports_power=exports,
        export_compensation=compensation,
    )
    return adapter, {BAT_POWER: power_value}


def _make_consumer(power_value):
    adapter = ConsumerAdapter(
        unique_id="cons",
        verbose_name="Consumer",
        power_entity=CONS_POWER,
    )
    return adapter, {CONS_POWER: power_value}


def _build_scenario(adapter_specs):
    """Build PowerInsight from a list of (adapter, values_dict) tuples."""
    adapters = []
    values = {}
    for adapter, vals in adapter_specs:
        adapters.append(adapter)
        values.update(vals)
    return build_power_insight(adapters, values)


# ===================================================================
# Scenario 1 — Grid + PV  (PV overproducing → exporting to grid)
# ===================================================================
# Grid power: -1000 W  (negative = exporting)
# PV power:    3000 W  (producing)
# Grid price:  0.30 EUR/kWh
# PV LCOE:     0.08 EUR/kWh
# PV exports:  True, compensation = 0.08 EUR/kWh
# ===================================================================

class TestScenario1GridPv:
    """Grid + PV with excess production (exporting)."""

    @pytest.fixture()
    def pi(self):
        return _build_scenario([
            _make_grid(-1000),
            _make_pv(3000),
        ])

    # -- Power flows --

    def test_grid_import(self, pi):
        # grid power = -1000 → import = max(power, 0) = 0
        assert pi.grid_import == pytest.approx(0.0)

    def test_grid_export(self, pi):
        # grid power = -1000 → export = -power = 1000
        assert pi.grid_export == pytest.approx(1000.0)

    def test_production(self, pi):
        # PV produces 3000
        assert pi.production == pytest.approx(3000.0)

    def test_utilization(self, pi):
        # PV consumption = max(-power, 0) = 0 (producing, not consuming)
        assert pi.utilization == pytest.approx(0.0)

    def test_total_power(self, pi):
        # grid_import + production = 0 + 3000
        assert pi.total_power == pytest.approx(0 + 3000)

    def test_self_consumption(self, pi):
        # total_power - grid_export - utilization = 3000 - 1000 - 0
        assert pi.self_consumption == pytest.approx(3000 - 1000 - 0)

    # -- Shares --

    def test_export_share(self, pi):
        # grid_export / total_power = 1000 / 3000
        assert pi.export_share == pytest.approx(1000 / 3000)

    def test_utilization_share(self, pi):
        # utilization / total_power = 0 / 3000
        assert pi.utilization_share == pytest.approx(0.0)

    def test_self_consumption_share(self, pi):
        # self_consumption / total_power = 2000 / 3000
        assert pi.self_consumption_share == pytest.approx(2000 / 3000)

    def test_applicable_utilization_share(self, pi):
        # utilization_share / (1 - export_share) = 0 / (1 - 1/3)
        assert pi.applicable_utilization_share == pytest.approx(0.0)

    def test_applicable_self_consumption_share(self, pi):
        # self_cons_share / (1 - export_share) = (2/3) / (2/3) = 1.0
        assert pi.applicable_self_consumption_share == pytest.approx(
            (2000 / 3000) / (1 - 1000 / 3000)
        )

    # -- Cost rates --

    def test_coe_rate(self, pi):
        # grid_coe_rate + pv_coe_rate
        # grid: import=0 → coe_rate=0
        # pv: coe=0.0 (base prod adapter) → coe_rate = (3000/1000)*0 = 0
        assert pi.coe_rate == pytest.approx(0.0)

    def test_coe(self, pi):
        # coe_rate / total_power_kW = 0 / 3 = 0
        assert pi.coe == pytest.approx(0.0)

    def test_lcoe_rate(self, pi):
        # grid: import=0 → lcoe_rate=0
        # pv: lcoe=0.08 → lcoe_rate = (3000/1000) * 0.08 = 0.24
        assert pi.lcoe_rate == pytest.approx(0 + (3000 / 1000) * PV_LCOE)

    def test_lcoe(self, pi):
        # lcoe_rate / total_power_kW = 0.24 / 3.0
        lcoe_rate = (3000 / 1000) * PV_LCOE
        assert pi.lcoe == pytest.approx(lcoe_rate / (3000 / 1000))

    # -- Grid adapter properties --

    def test_grid_adapter_total_power_shares(self, pi):
        # grid_import / total_power = 0 / 3000
        assert pi.grid_adapter_total_power_shares["grid"] == pytest.approx(0.0)

    def test_grid_adapter_self_cons_rates(self, pi):
        # applicable_self_consumption_share (same for all providers)
        assert pi.grid_adapter_self_cons_rates["grid"] == pytest.approx(
            (2000 / 3000) / (1 - 1000 / 3000)
        )

    def test_grid_adapter_self_cons_shares(self, pi):
        # (self_cons_rate * power_share) / self_cons_share
        # = (1.0 * 0.0) / (2/3) = 0
        assert pi.grid_adapter_self_cons_shares["grid"] == pytest.approx(0.0)

    # -- Production adapter properties --

    def test_prod_adapters_total_power_shares(self, pi):
        # pv production / total_power = 3000 / 3000
        assert pi.prod_adapters_total_power_shares["pv"] == pytest.approx(
            3000 / 3000
        )

    def test_prod_adapters_export_shares(self, pi):
        # PV is the only exporter → 100%
        assert pi.prod_adapters_export_shares["pv"] == pytest.approx(1.0)

    def test_prod_adapters_export_rates(self, pi):
        # export_share_pv * total_export_share / power_share_pv
        # = 1.0 * (1/3) / 1.0 = 1/3
        assert pi.prod_adapters_export_rates["pv"] == pytest.approx(
            1.0 * (1000 / 3000) / (3000 / 3000)
        )

    def test_prod_adapters_export_power(self, pi):
        # grid_export * export_share = 1000 * 1.0
        assert pi.prod_adapters_export_power["pv"] == pytest.approx(
            1000 * 1.0
        )

    def test_prod_adapters_export_compensation_rates(self, pi):
        # export_power_kW * compensation = (1000/1000) * 0.08
        assert pi.prod_adapters_export_compensation_rates["pv"] == pytest.approx(
            (1000 / 1000) * PV_EXPORT_COMP
        )

    def test_prod_adapters_self_cons_rates(self, pi):
        # (1 - export_rate) * applicable_self_cons_share
        # export_rate_pv = 1/3
        # applicable_self_cons_share = 1.0
        # = (1 - 1/3) * 1.0 = 2/3
        export_rate_pv = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        assert pi.prod_adapters_self_cons_rates["pv"] == pytest.approx(
            (1 - export_rate_pv) * applicable
        )

    def test_prod_adapters_self_cons_power(self, pi):
        # production * self_cons_rate = 3000 * 2/3
        export_rate_pv = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate_pv) * applicable
        assert pi.prod_adapters_self_cons_power["pv"] == pytest.approx(
            3000 * self_cons_rate
        )

    def test_prod_adapters_self_cons_saving_rates(self, pi):
        # self_cons_power_kW * grid_coe
        # grid_coe = 0.30 (price entity value)
        export_rate_pv = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate_pv) * applicable
        self_cons_power = 3000 * self_cons_rate
        assert pi.prod_adapters_self_cons_saving_rates["pv"] == pytest.approx(
            (self_cons_power / 1000) * GRID_PRICE_VALUE
        )

    def test_prod_adapters_coo_rates(self, pi):
        # consumption_kW * coe (blended)
        # PV consumption = 0, so coo_rate = 0
        assert pi.prod_adapters_coo_rates["pv"] == pytest.approx(0.0)

    def test_prod_adapters_lcoo_rates(self, pi):
        # consumption_kW * lcoe (blended)
        # PV consumption = 0, so lcoo_rate = 0
        assert pi.prod_adapters_lcoo_rates["pv"] == pytest.approx(0.0)

    def test_prod_adapters_saving_rates(self, pi):
        # export_compensation + self_cons_savings - coo_rate - coe_rate
        # coe_rate for PV = (3000/1000) * 0.0 = 0 (BaseProductionAdapter.coe = 0)
        export_comp = (1000 / 1000) * PV_EXPORT_COMP
        export_rate_pv = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate_pv) * applicable
        self_cons_power = 3000 * self_cons_rate
        self_cons_savings = (self_cons_power / 1000) * GRID_PRICE_VALUE
        coo_rate = 0.0  # PV consumption = 0
        coe_rate = 0.0  # BaseProductionAdapter.coe = 0
        assert pi.prod_adapters_saving_rates["pv"] == pytest.approx(
            export_comp + self_cons_savings - coo_rate - coe_rate
        )

    def test_prod_adapters_levelized_saving_rates(self, pi):
        # Same as saving_rates but uses lcoe_rate and lcoo_rate
        export_comp = (1000 / 1000) * PV_EXPORT_COMP
        export_rate_pv = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate_pv) * applicable
        self_cons_power = 3000 * self_cons_rate
        self_cons_savings = (self_cons_power / 1000) * GRID_PRICE_VALUE
        lcoo_rate = 0.0  # PV consumption = 0
        lcoe_rate = (3000 / 1000) * PV_LCOE  # PV lcoe_rate
        assert pi.prod_adapters_levelized_saving_rates["pv"] == pytest.approx(
            export_comp + self_cons_savings - lcoo_rate - lcoe_rate
        )

    # -- Totals --

    def test_total_export_compensation_rate(self, pi):
        assert pi.total_export_compensation_rate == pytest.approx(
            (1000 / 1000) * PV_EXPORT_COMP
        )

    def test_total_self_cons_saving_rate(self, pi):
        export_rate_pv = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate_pv) * applicable
        self_cons_power = 3000 * self_cons_rate
        assert pi.total_self_cons_saving_rate == pytest.approx(
            (self_cons_power / 1000) * GRID_PRICE_VALUE
        )

    def test_total_coo_rate(self, pi):
        assert pi.total_coo_rate == pytest.approx(0.0)

    def test_total_saving_rate(self, pi):
        export_comp = (1000 / 1000) * PV_EXPORT_COMP
        export_rate_pv = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate_pv) * applicable
        self_cons_power = 3000 * self_cons_rate
        self_cons_savings = (self_cons_power / 1000) * GRID_PRICE_VALUE
        assert pi.total_saving_rate == pytest.approx(
            export_comp + self_cons_savings - 0 - 0
        )


# ===================================================================
# Scenario 2 — Grid + PV + Battery  (all consumed, no export)
# ===================================================================
# Grid power:  500 W   (importing)
# PV power:   2000 W   (producing)
# Bat power:  1000 W   (discharging)
# Grid price:  0.30 EUR/kWh
# PV LCOE:     0.08, exports_power=True, compensation=0.08
# Bat LCOS:    0.12, exports_power=False
# ===================================================================

class TestScenario2GridPvBattery:
    """Grid + PV + Battery, all power consumed (no export)."""

    @pytest.fixture()
    def pi(self):
        return _build_scenario([
            _make_grid(500),
            _make_pv(2000),
            _make_battery(1000),
        ])

    # -- Power flows --

    def test_grid_import(self, pi):
        assert pi.grid_import == pytest.approx(500.0)

    def test_grid_export(self, pi):
        assert pi.grid_export == pytest.approx(0.0)

    def test_production(self, pi):
        # PV + Battery = 2000 + 1000
        assert pi.production == pytest.approx(2000 + 1000)

    def test_utilization(self, pi):
        # Both PV and battery consumption = 0 (both producing)
        assert pi.utilization == pytest.approx(0.0)

    def test_total_power(self, pi):
        # grid_import + production = 500 + 3000
        assert pi.total_power == pytest.approx(500 + 2000 + 1000)

    def test_self_consumption(self, pi):
        # total_power - export - utilization = 3500 - 0 - 0
        assert pi.self_consumption == pytest.approx(3500 - 0 - 0)

    # -- Shares --

    def test_export_share(self, pi):
        assert pi.export_share == pytest.approx(0.0)

    def test_self_consumption_share(self, pi):
        # All power is self-consumed
        assert pi.self_consumption_share == pytest.approx(3500 / 3500)

    def test_applicable_self_consumption_share(self, pi):
        # self_cons_share / (1 - 0) = 1.0
        assert pi.applicable_self_consumption_share == pytest.approx(1.0)

    # -- Cost rates --

    def test_coe_rate(self, pi):
        # grid: (500/1000) * 0.30 = 0.15
        # pv: (2000/1000) * 0.0 = 0
        # bat: (1000/1000) * 0.0 = 0
        assert pi.coe_rate == pytest.approx(
            (500 / 1000) * GRID_PRICE_VALUE + 0 + 0
        )

    def test_coe(self, pi):
        # coe_rate / total_power_kW
        grid_coe_rate = (500 / 1000) * GRID_PRICE_VALUE
        assert pi.coe == pytest.approx(grid_coe_rate / (3500 / 1000))

    def test_lcoe_rate(self, pi):
        # grid: (500/1000) * 0.30
        # pv: (2000/1000) * 0.08
        # bat: (1000/1000) * 0.12  (BatteryAdapter.lcoe returns lcos)
        assert pi.lcoe_rate == pytest.approx(
            (500 / 1000) * GRID_PRICE_VALUE
            + (2000 / 1000) * PV_LCOE
            + (1000 / 1000) * BAT_LCOS
        )

    def test_lcoe(self, pi):
        lcoe_rate = (
            (500 / 1000) * GRID_PRICE_VALUE
            + (2000 / 1000) * PV_LCOE
            + (1000 / 1000) * BAT_LCOS
        )
        assert pi.lcoe == pytest.approx(lcoe_rate / (3500 / 1000))

    # -- Grid adapter properties --

    def test_grid_adapter_total_power_shares(self, pi):
        assert pi.grid_adapter_total_power_shares["grid"] == pytest.approx(
            500 / 3500
        )

    # -- Production adapter share distribution --

    def test_prod_adapters_total_power_shares(self, pi):
        assert pi.prod_adapters_total_power_shares["pv"] == pytest.approx(
            2000 / 3500
        )
        assert pi.prod_adapters_total_power_shares["bat"] == pytest.approx(
            1000 / 3500
        )

    def test_prod_adapters_export_shares(self, pi):
        # PV exports_power=True, battery exports_power=False
        # But export_share=0 (no actual export), so export_shares
        # are based on power_shares of exporters only
        # PV is the only exporter → 100%
        assert pi.prod_adapters_export_shares["pv"] == pytest.approx(1.0)
        assert pi.prod_adapters_export_shares["bat"] == pytest.approx(0.0)

    def test_prod_adapters_export_rates(self, pi):
        # export_share_adapter * total_export_share / power_share_adapter
        # total_export_share = 0, so numerator = 0
        assert pi.prod_adapters_export_rates["pv"] == pytest.approx(0.0)
        assert pi.prod_adapters_export_rates["bat"] == pytest.approx(0.0)

    def test_prod_adapters_export_power(self, pi):
        # grid_export * export_share = 0 * anything
        assert pi.prod_adapters_export_power["pv"] == pytest.approx(0.0)
        assert pi.prod_adapters_export_power["bat"] == pytest.approx(0.0)

    def test_prod_adapters_export_compensation_rates(self, pi):
        assert pi.prod_adapters_export_compensation_rates["pv"] == pytest.approx(0.0)
        assert pi.prod_adapters_export_compensation_rates["bat"] == pytest.approx(0.0)

    def test_prod_adapters_self_cons_rates(self, pi):
        # (1 - export_rate) * applicable_self_cons_share
        # export_rate = 0 for both, applicable = 1.0
        assert pi.prod_adapters_self_cons_rates["pv"] == pytest.approx(
            (1 - 0) * 1.0
        )
        assert pi.prod_adapters_self_cons_rates["bat"] == pytest.approx(
            (1 - 0) * 1.0
        )

    def test_prod_adapters_self_cons_shares(self, pi):
        # (self_cons_rate * power_share) / self_cons_share
        # self_cons_rate=1.0 for both, self_cons_share=1.0
        assert pi.prod_adapters_self_cons_shares["pv"] == pytest.approx(
            (1.0 * (2000 / 3500)) / 1.0
        )
        assert pi.prod_adapters_self_cons_shares["bat"] == pytest.approx(
            (1.0 * (1000 / 3500)) / 1.0
        )

    def test_prod_adapters_self_cons_power(self, pi):
        # production * self_cons_rate
        assert pi.prod_adapters_self_cons_power["pv"] == pytest.approx(
            2000 * 1.0
        )
        assert pi.prod_adapters_self_cons_power["bat"] == pytest.approx(
            1000 * 1.0
        )

    def test_prod_adapters_self_cons_saving_rates(self, pi):
        # self_cons_power_kW * grid_coe
        assert pi.prod_adapters_self_cons_saving_rates["pv"] == pytest.approx(
            (2000 / 1000) * GRID_PRICE_VALUE
        )
        assert pi.prod_adapters_self_cons_saving_rates["bat"] == pytest.approx(
            (1000 / 1000) * GRID_PRICE_VALUE
        )

    def test_prod_adapters_coo_rates(self, pi):
        # Both have consumption=0 → coo=0
        assert pi.prod_adapters_coo_rates["pv"] == pytest.approx(0.0)
        assert pi.prod_adapters_coo_rates["bat"] == pytest.approx(0.0)

    def test_prod_adapters_saving_rates(self, pi):
        # export_comp + self_cons_savings - coo - coe_rate
        # PV: 0 + (2000/1000)*0.30 - 0 - 0 = 0.60
        assert pi.prod_adapters_saving_rates["pv"] == pytest.approx(
            0 + (2000 / 1000) * GRID_PRICE_VALUE - 0 - 0
        )
        # Battery: 0 + (1000/1000)*0.30 - 0 - 0 = 0.30
        assert pi.prod_adapters_saving_rates["bat"] == pytest.approx(
            0 + (1000 / 1000) * GRID_PRICE_VALUE - 0 - 0
        )

    def test_prod_adapters_levelized_saving_rates(self, pi):
        # Same but subtracts lcoe_rate and lcoo_rate
        # PV: 0 + (2000/1000)*0.30 - 0 - (2000/1000)*0.08
        pv_self_cons_savings = (2000 / 1000) * GRID_PRICE_VALUE
        pv_lcoe_rate = (2000 / 1000) * PV_LCOE
        assert pi.prod_adapters_levelized_saving_rates["pv"] == pytest.approx(
            0 + pv_self_cons_savings - 0 - pv_lcoe_rate
        )
        # Battery: 0 + (1000/1000)*0.30 - 0 - (1000/1000)*0.12
        bat_self_cons_savings = (1000 / 1000) * GRID_PRICE_VALUE
        bat_lcoe_rate = (1000 / 1000) * BAT_LCOS
        assert pi.prod_adapters_levelized_saving_rates["bat"] == pytest.approx(
            0 + bat_self_cons_savings - 0 - bat_lcoe_rate
        )

    # -- Totals --

    def test_total_export_compensation_rate(self, pi):
        assert pi.total_export_compensation_rate == pytest.approx(0.0)

    def test_total_self_cons_saving_rate(self, pi):
        assert pi.total_self_cons_saving_rate == pytest.approx(
            (2000 / 1000) * GRID_PRICE_VALUE
            + (1000 / 1000) * GRID_PRICE_VALUE
        )

    def test_total_coo_rate(self, pi):
        assert pi.total_coo_rate == pytest.approx(0.0)

    def test_total_lcoo_rate(self, pi):
        assert pi.total_lcoo_rate == pytest.approx(0.0)

    def test_total_saving_rate(self, pi):
        pv_saving = 0 + (2000 / 1000) * GRID_PRICE_VALUE - 0 - 0
        bat_saving = 0 + (1000 / 1000) * GRID_PRICE_VALUE - 0 - 0
        assert pi.total_saving_rate == pytest.approx(pv_saving + bat_saving)

    def test_total_levelized_saving_rate(self, pi):
        pv_saving = (
            0
            + (2000 / 1000) * GRID_PRICE_VALUE
            - 0
            - (2000 / 1000) * PV_LCOE
        )
        bat_saving = (
            0
            + (1000 / 1000) * GRID_PRICE_VALUE
            - 0
            - (1000 / 1000) * BAT_LCOS
        )
        assert pi.total_levelized_saving_rate == pytest.approx(
            pv_saving + bat_saving
        )


# ===================================================================
# Scenario 3 — Grid + PV + Battery + Consumer
# ===================================================================
# Same power setup as scenario 2, plus a consumer at -800 W
# Consumer power is negative (consuming).
# ===================================================================

class TestScenario3GridPvBatteryConsumer:
    """Grid + PV + Battery + Consumer."""

    @pytest.fixture()
    def pi(self):
        return _build_scenario([
            _make_grid(500),
            _make_pv(2000),
            _make_battery(1000),
            _make_consumer(-800),
        ])

    # -- Power flows are same as scenario 2 (consumer doesn't affect them) --

    def test_total_power(self, pi):
        # Consumer doesn't contribute to total_power (not a prod adapter)
        assert pi.total_power == pytest.approx(500 + 2000 + 1000)

    def test_self_consumption(self, pi):
        assert pi.self_consumption == pytest.approx(3500.0)

    # -- Consumer adapter properties --

    def test_cons_adapter_total_power_shares(self, pi):
        # consumer consumption / total_power
        # ConsumerAdapter.consumption: power * -1 if power < 0 else 0
        # power = -800 → consumption = 800
        assert pi.cons_adapter_total_power_shares["cons"] == pytest.approx(
            800 / 3500
        )

    def test_cons_adapters_self_cons_share(self, pi):
        # power_share / self_cons_share
        # = (800/3500) / (3500/3500) = 800/3500
        assert pi.cons_adapters_self_cons_share["cons"] == pytest.approx(
            (800 / 3500) / 1.0
        )

    def test_cons_adapters_source_shares(self, pi):
        # Each power provider's self_cons_share is the same for all consumers
        # Grid self_cons_share = (applicable_sc * grid_power_share) / sc_share
        #   = (1.0 * 500/3500) / 1.0 = 500/3500
        # PV self_cons_share = (1.0 * 2000/3500) / 1.0 = 2000/3500
        # Bat self_cons_share = (1.0 * 1000/3500) / 1.0 = 1000/3500
        shares = pi.cons_adapters_source_shares["cons"]
        assert shares["grid"] == pytest.approx(
            (1.0 * (500 / 3500)) / 1.0
        )
        assert shares["pv"] == pytest.approx(
            (1.0 * (2000 / 3500)) / 1.0
        )
        assert shares["bat"] == pytest.approx(
            (1.0 * (1000 / 3500)) / 1.0
        )

    def test_cons_adapters_coo_rates(self, pi):
        # consumption_kW * coe (blended)
        coe = ((500 / 1000) * GRID_PRICE_VALUE) / (3500 / 1000)
        assert pi.cons_adapters_coo_rates["cons"] == pytest.approx(
            (800 / 1000) * coe
        )

    def test_cons_adapters_lcoo_rates(self, pi):
        # consumption_kW * lcoe (blended)
        lcoe_rate = (
            (500 / 1000) * GRID_PRICE_VALUE
            + (2000 / 1000) * PV_LCOE
            + (1000 / 1000) * BAT_LCOS
        )
        lcoe = lcoe_rate / (3500 / 1000)
        assert pi.cons_adapters_lcoo_rates["cons"] == pytest.approx(
            (800 / 1000) * lcoe
        )

    # -- Verify production adapters are unaffected by consumer --

    def test_prod_adapters_saving_rates_unchanged(self, pi):
        # Should be same as scenario 2
        assert pi.prod_adapters_saving_rates["pv"] == pytest.approx(
            0 + (2000 / 1000) * GRID_PRICE_VALUE - 0 - 0
        )
        assert pi.prod_adapters_saving_rates["bat"] == pytest.approx(
            0 + (1000 / 1000) * GRID_PRICE_VALUE - 0 - 0
        )
