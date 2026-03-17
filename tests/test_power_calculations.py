"""Tests for PowerInsight core calculation logic.

Three scenarios of increasing complexity:
  1. Grid + PV  (excess production → exporting)
  2. Grid + PV + Battery  (all consumed, no export)
  3. Grid + PV + Battery + Consumer  (consumer cost allocation)
"""

from __future__ import annotations

import importlib.util
import os

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
# Factory functions
# All parameters required — constants are defined in the test scenario class.
# Each returns an (adapter, {entity_id: value}) tuple for use in build_scenario.
# ---------------------------------------------------------------------------

def create_grid(uid, power_entity, price_entity, power_value, price_value):
    adapter = GridAdapter(
        unique_id=uid,
        verbose_name=uid,
        power_entity=power_entity,
        price_entity=price_entity,
    )
    return adapter, {power_entity: power_value, price_entity: price_value}


def create_pv(uid, power_entity, power_value, lcoe, lco2_intensity, exports_power, export_compensation):
    adapter = PvAdapter(
        unique_id=uid,
        verbose_name=uid,
        power_entity=power_entity,
        power_entity_inverted=False,
        lcoe=lcoe,
        lco2_intensity=lco2_intensity,
        exports_power=exports_power,
        export_compensation=export_compensation,
    )
    return adapter, {power_entity: power_value}


def create_battery(uid, power_entity, power_value, lcos, lco2_intensity, exports_power, export_compensation, charge_from_grid, charge_from_adapters):
    adapter = BatteryAdapter(
        unique_id=uid,
        verbose_name=uid,
        power_entity=power_entity,
        power_entity_inverted=False,
        lcos=lcos,
        lco2_intensity=lco2_intensity,
        exports_power=exports_power,
        export_compensation=export_compensation,
        charge_from_grid=charge_from_grid,
        charge_from_adapters=charge_from_adapters,
    )
    return adapter, {power_entity: power_value}


def create_consumer(uid, power_entity, power_value):
    adapter = ConsumerAdapter(
        unique_id=uid,
        verbose_name=uid,
        power_entity=power_entity,
    )
    return adapter, {power_entity: power_value}


def build_scenario(adapter_specs):
    """Build a PowerInsight from a list of (adapter, values_dict) tuples."""
    pi = PowerInsight()
    values = {}
    for adapter, vals in adapter_specs:
        pi.register_adapter(adapter)
        values.update(vals)
    for entity_id, value in values.items():
        pi.set_value(entity_id, value)
    return pi


# ===================================================================
# Scenario 1 — Grid + PV  (PV overproducing → exporting to grid)
# ===================================================================
# Grid power: -1000 W  (negative = exporting)
# PV power:    3000 W  (producing)
# Grid price:  0.30 EUR/kWh
# PV LCOE:     0.08 EUR/kWh, exports_power=True, compensation=0.08 EUR/kWh
# ===================================================================

class TestScenario1GridPv:
    """Grid + PV with excess production (exporting)."""

    GRID_UID = "grid"
    PV_UID = "pv"

    GRID_POWER = "sensor.grid_power"
    GRID_PRICE = "sensor.grid_price"
    PV_POWER = "sensor.pv_power"

    GRID_POWER_VALUE = -1000   # W, negative = exporting
    GRID_PRICE_VALUE = 0.30    # EUR/kWh
    PV_POWER_VALUE = 3000      # W
    PV_LCOE = 0.08             # EUR/kWh
    PV_EXPORT_COMP = 0.08      # EUR/kWh

    @pytest.fixture()
    def power_insight(self):
        return build_scenario([
            create_grid(self.GRID_UID, self.GRID_POWER, self.GRID_PRICE, self.GRID_POWER_VALUE, self.GRID_PRICE_VALUE),
            create_pv(self.PV_UID, self.PV_POWER, self.PV_POWER_VALUE, self.PV_LCOE, 0.0, True, self.PV_EXPORT_COMP),
        ])

    # === Combined values ===

    def test_grid_import(self, power_insight):
        # grid power = -1000 → import = max(power, 0) = 0
        assert power_insight.grid_import == pytest.approx(0.0)

    def test_grid_export(self, power_insight):
        # grid power = -1000 → export = -power = 1000
        assert power_insight.grid_export == pytest.approx(1000.0)

    def test_production(self, power_insight):
        assert power_insight.production == pytest.approx(3000.0)

    def test_utilization(self, power_insight):
        # PV only producing, consumption = 0
        assert power_insight.utilization == pytest.approx(0.0)

    def test_total_power(self, power_insight):
        # grid_import + production = 0 + 3000
        assert power_insight.total_power == pytest.approx(0 + 3000)

    def test_export_share(self, power_insight):
        # grid_export / total_power = 1000 / 3000
        assert power_insight.export_share == pytest.approx(1000 / 3000)

    def test_self_consumption(self, power_insight):
        # total_power - grid_export - utilization = 3000 - 1000 - 0
        assert power_insight.self_consumption == pytest.approx(3000 - 1000 - 0)

    def test_self_consumption_share(self, power_insight):
        # self_consumption / total_power = 2000 / 3000
        assert power_insight.self_consumption_share == pytest.approx(2000 / 3000)

    def test_utilization_share(self, power_insight):
        assert power_insight.utilization_share == pytest.approx(0.0)

    def test_applicable_self_consumption_share(self, power_insight):
        # self_cons_share / (1 - export_share) = (2/3) / (2/3) = 1.0
        assert power_insight.applicable_self_consumption_share == pytest.approx(
            (2000 / 3000) / (1 - 1000 / 3000)
        )

    def test_applicable_utilization_share(self, power_insight):
        # utilization_share / (1 - export_share) = 0 / (2/3) = 0
        assert power_insight.applicable_utilization_share == pytest.approx(0.0)

    def test_coe(self, power_insight):
        # coe_rate=0 (import=0), so coe=0
        assert power_insight.coe == pytest.approx(0.0)

    def test_lcoe(self, power_insight):
        # lcoe_rate = (3000/1000) * 0.08 = 0.24
        # lcoe = 0.24 / (3000/1000) = 0.08
        lcoe_rate = (3000 / 1000) * self.PV_LCOE
        assert power_insight.lcoe == pytest.approx(lcoe_rate / (3000 / 1000))

    def test_coe_rate(self, power_insight):
        # grid import=0 → 0; PV base coe=0 → 0
        assert power_insight.coe_rate == pytest.approx(0.0)

    def test_lcoe_rate(self, power_insight):
        # grid: 0; PV: (3000/1000) * 0.08 = 0.24
        assert power_insight.lcoe_rate == pytest.approx((3000 / 1000) * self.PV_LCOE)

    def test_total_export_compensation_rate(self, power_insight):
        # (1000/1000) * 0.08 = 0.08
        assert power_insight.total_export_compensation_rate == pytest.approx(
            (1000 / 1000) * self.PV_EXPORT_COMP
        )

    def test_total_coo_rate(self, power_insight):
        # PV consumption = 0
        assert power_insight.total_coo_rate == pytest.approx(0.0)

    def test_total_self_cons_saving_rate(self, power_insight):
        # self_cons_power_kW * grid_price
        export_rate = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate) * applicable
        self_cons_power = 3000 * self_cons_rate
        assert power_insight.total_self_cons_saving_rate == pytest.approx(
            (self_cons_power / 1000) * self.GRID_PRICE_VALUE
        )

    def test_total_saving_rate(self, power_insight):
        # export_comp + self_cons_savings - coo - coe_rate(=0 base prod)
        export_comp = (1000 / 1000) * self.PV_EXPORT_COMP
        export_rate = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate) * applicable
        self_cons_power = 3000 * self_cons_rate
        self_cons_savings = (self_cons_power / 1000) * self.GRID_PRICE_VALUE
        assert power_insight.total_saving_rate == pytest.approx(
            export_comp + self_cons_savings - 0 - 0
        )

    def test_total_levelized_saving_rate(self, power_insight):
        export_comp = (1000 / 1000) * self.PV_EXPORT_COMP
        export_rate = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate) * applicable
        self_cons_power = 3000 * self_cons_rate
        self_cons_savings = (self_cons_power / 1000) * self.GRID_PRICE_VALUE
        lcoe_rate = (3000 / 1000) * self.PV_LCOE
        assert power_insight.total_levelized_saving_rate == pytest.approx(
            export_comp + self_cons_savings - 0 - lcoe_rate
        )

    # === Grid adapter ===

    def test_grid_adapter_total_power_share(self, power_insight):
        # grid_import / total_power = 0 / 3000
        assert power_insight.grid_adapter_total_power_shares[self.GRID_UID] == pytest.approx(0.0)

    def test_grid_adapter_self_cons_rate(self, power_insight):
        # applicable_self_consumption_share
        assert power_insight.grid_adapter_self_cons_rates[self.GRID_UID] == pytest.approx(
            (2000 / 3000) / (1 - 1000 / 3000)
        )

    def test_grid_adapter_self_cons_share(self, power_insight):
        # (applicable_sc * grid_power_share) / sc_share = (1.0 * 0.0) / (2/3) = 0
        assert power_insight.grid_adapter_self_cons_shares[self.GRID_UID] == pytest.approx(0.0)

    def test_grid_adapter_utilization_rate(self, power_insight):
        assert power_insight.grid_adapter_utilization_rates[self.GRID_UID] == pytest.approx(0.0)

    def test_grid_adapter_utilization_share(self, power_insight):
        assert power_insight.grid_adapter_utilization_shares[self.GRID_UID] == pytest.approx(0.0)

    # === Production adapters ===

    def test_prod_adapter_export_power(self, power_insight):
        # grid_export * export_share_pv = 1000 * 1.0
        assert power_insight.prod_adapters_export_power[self.PV_UID] == pytest.approx(
            1000 * 1.0
        )

    def test_prod_adapter_export_rate(self, power_insight):
        # export_share_pv * total_export_share / power_share_pv = 1.0 * (1/3) / 1.0
        assert power_insight.prod_adapters_export_rates[self.PV_UID] == pytest.approx(
            1.0 * (1000 / 3000) / (3000 / 3000)
        )

    def test_prod_adapter_export_share(self, power_insight):
        # PV is the only exporter → 100%
        assert power_insight.prod_adapters_export_shares[self.PV_UID] == pytest.approx(1.0)

    def test_prod_adapter_export_compensation_rate(self, power_insight):
        # (1000/1000) * 0.08
        assert power_insight.prod_adapters_export_compensation_rates[self.PV_UID] == pytest.approx(
            (1000 / 1000) * self.PV_EXPORT_COMP
        )

    def test_prod_adapter_self_cons_power(self, power_insight):
        # production * self_cons_rate = 3000 * (2/3)
        export_rate = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate) * applicable
        assert power_insight.prod_adapters_self_cons_power[self.PV_UID] == pytest.approx(
            3000 * self_cons_rate
        )

    def test_prod_adapter_self_cons_rate(self, power_insight):
        # (1 - export_rate) * applicable_self_cons_share
        export_rate = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        assert power_insight.prod_adapters_self_cons_rates[self.PV_UID] == pytest.approx(
            (1 - export_rate) * applicable
        )

    def test_prod_adapter_self_cons_share(self, power_insight):
        # (self_cons_rate * power_share) / self_cons_share
        export_rate = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate) * applicable
        assert power_insight.prod_adapters_self_cons_shares[self.PV_UID] == pytest.approx(
            (self_cons_rate * (3000 / 3000)) / (2000 / 3000)
        )

    def test_prod_adapter_self_cons_saving_rate(self, power_insight):
        # self_cons_power_kW * grid_price
        export_rate = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate) * applicable
        self_cons_power = 3000 * self_cons_rate
        assert power_insight.prod_adapters_self_cons_saving_rates[self.PV_UID] == pytest.approx(
            (self_cons_power / 1000) * self.GRID_PRICE_VALUE
        )

    def test_prod_adapter_coo_rate(self, power_insight):
        # PV consumption = 0 → coo = 0
        assert power_insight.prod_adapters_coo_rates[self.PV_UID] == pytest.approx(0.0)

    def test_prod_adapter_lcoo_rate(self, power_insight):
        assert power_insight.prod_adapters_lcoo_rates[self.PV_UID] == pytest.approx(0.0)

    def test_prod_adapter_saving_rate(self, power_insight):
        # export_comp + self_cons_savings - coo - coe_rate(base=0)
        export_comp = (1000 / 1000) * self.PV_EXPORT_COMP
        export_rate = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate) * applicable
        self_cons_power = 3000 * self_cons_rate
        self_cons_savings = (self_cons_power / 1000) * self.GRID_PRICE_VALUE
        assert power_insight.prod_adapters_saving_rates[self.PV_UID] == pytest.approx(
            export_comp + self_cons_savings - 0 - 0
        )

    def test_prod_adapter_levelized_saving_rate(self, power_insight):
        # Same but subtracts lcoe_rate instead of coe_rate
        export_comp = (1000 / 1000) * self.PV_EXPORT_COMP
        export_rate = 1.0 * (1000 / 3000) / (3000 / 3000)
        applicable = (2000 / 3000) / (1 - 1000 / 3000)
        self_cons_rate = (1 - export_rate) * applicable
        self_cons_power = 3000 * self_cons_rate
        self_cons_savings = (self_cons_power / 1000) * self.GRID_PRICE_VALUE
        lcoe_rate = (3000 / 1000) * self.PV_LCOE
        assert power_insight.prod_adapters_levelized_saving_rates[self.PV_UID] == pytest.approx(
            export_comp + self_cons_savings - 0 - lcoe_rate
        )


# ===================================================================
# Scenario 2 — Grid + PV + Battery  (all consumed, no export)
# ===================================================================
# Grid power:  500 W   (importing)
# PV power:   2000 W   (producing)
# Bat power:  1000 W   (discharging, positive = producing)
# Grid price:  0.30 EUR/kWh
# PV  LCOE:    0.08, exports_power=True, compensation=0.08
# Bat LCOS:    0.12, exports_power=False
# ===================================================================

class TestScenario2GridPvBattery:
    """Grid + PV + Battery, all power consumed (no export)."""

    GRID_UID = "grid"
    PV_UID = "pv"
    BAT_UID = "bat"

    GRID_POWER = "sensor.grid_power"
    GRID_PRICE = "sensor.grid_price"
    PV_POWER = "sensor.pv_power"
    BAT_POWER = "sensor.bat_power"

    GRID_POWER_VALUE = 500     # W, positive = importing
    GRID_PRICE_VALUE = 0.30    # EUR/kWh
    PV_POWER_VALUE = 2000      # W
    PV_LCOE = 0.08             # EUR/kWh
    PV_EXPORT_COMP = 0.08      # EUR/kWh
    BAT_POWER_VALUE = 1000     # W, positive = discharging
    BAT_LCOS = 0.12            # EUR/kWh

    @pytest.fixture()
    def power_insight(self):
        return build_scenario([
            create_grid(self.GRID_UID, self.GRID_POWER, self.GRID_PRICE, self.GRID_POWER_VALUE, self.GRID_PRICE_VALUE),
            create_pv(self.PV_UID, self.PV_POWER, self.PV_POWER_VALUE, self.PV_LCOE, 0.0, True, self.PV_EXPORT_COMP),
            create_battery(self.BAT_UID, self.BAT_POWER, self.BAT_POWER_VALUE, self.BAT_LCOS, 0.0, False, 0.0, True, []),
        ])

    # === Combined values ===

    def test_grid_import(self, power_insight):
        assert power_insight.grid_import == pytest.approx(500.0)

    def test_grid_export(self, power_insight):
        assert power_insight.grid_export == pytest.approx(0.0)

    def test_production(self, power_insight):
        # PV + Battery both discharging
        assert power_insight.production == pytest.approx(2000 + 1000)

    def test_utilization(self, power_insight):
        # Both have consumption = 0 (positive power = producing)
        assert power_insight.utilization == pytest.approx(0.0)

    def test_total_power(self, power_insight):
        # grid_import + production = 500 + 3000
        assert power_insight.total_power == pytest.approx(500 + 2000 + 1000)

    def test_export_share(self, power_insight):
        assert power_insight.export_share == pytest.approx(0.0)

    def test_self_consumption(self, power_insight):
        # total_power - export - utilization = 3500 - 0 - 0
        assert power_insight.self_consumption == pytest.approx(3500 - 0 - 0)

    def test_self_consumption_share(self, power_insight):
        assert power_insight.self_consumption_share == pytest.approx(3500 / 3500)

    def test_utilization_share(self, power_insight):
        assert power_insight.utilization_share == pytest.approx(0.0)

    def test_applicable_self_consumption_share(self, power_insight):
        # self_cons_share / (1 - 0) = 1.0
        assert power_insight.applicable_self_consumption_share == pytest.approx(1.0)

    def test_applicable_utilization_share(self, power_insight):
        assert power_insight.applicable_utilization_share == pytest.approx(0.0)

    def test_coe(self, power_insight):
        # coe_rate / total_power_kW
        grid_coe_rate = (500 / 1000) * self.GRID_PRICE_VALUE
        assert power_insight.coe == pytest.approx(grid_coe_rate / (3500 / 1000))

    def test_lcoe(self, power_insight):
        lcoe_rate = (
            (500 / 1000) * self.GRID_PRICE_VALUE
            + (2000 / 1000) * self.PV_LCOE
            + (1000 / 1000) * self.BAT_LCOS
        )
        assert power_insight.lcoe == pytest.approx(lcoe_rate / (3500 / 1000))

    def test_coe_rate(self, power_insight):
        # grid: (500/1000) * 0.30; pv/bat base coe = 0
        assert power_insight.coe_rate == pytest.approx(
            (500 / 1000) * self.GRID_PRICE_VALUE
        )

    def test_lcoe_rate(self, power_insight):
        assert power_insight.lcoe_rate == pytest.approx(
            (500 / 1000) * self.GRID_PRICE_VALUE
            + (2000 / 1000) * self.PV_LCOE
            + (1000 / 1000) * self.BAT_LCOS
        )

    def test_total_export_compensation_rate(self, power_insight):
        assert power_insight.total_export_compensation_rate == pytest.approx(0.0)

    def test_total_coo_rate(self, power_insight):
        # Both PV and battery consumption = 0
        assert power_insight.total_coo_rate == pytest.approx(0.0)

    def test_total_lcoo_rate(self, power_insight):
        assert power_insight.total_lcoo_rate == pytest.approx(0.0)

    def test_total_self_cons_saving_rate(self, power_insight):
        # Each adapter: self_cons_power_kW * grid_price
        # self_cons_rate = 1.0 for both (export_rate=0, applicable=1.0)
        assert power_insight.total_self_cons_saving_rate == pytest.approx(
            (2000 / 1000) * self.GRID_PRICE_VALUE
            + (1000 / 1000) * self.GRID_PRICE_VALUE
        )

    def test_total_saving_rate(self, power_insight):
        pv_saving = 0 + (2000 / 1000) * self.GRID_PRICE_VALUE - 0 - 0
        bat_saving = 0 + (1000 / 1000) * self.GRID_PRICE_VALUE - 0 - 0
        assert power_insight.total_saving_rate == pytest.approx(pv_saving + bat_saving)

    def test_total_levelized_saving_rate(self, power_insight):
        pv_saving = (
            0
            + (2000 / 1000) * self.GRID_PRICE_VALUE
            - 0
            - (2000 / 1000) * self.PV_LCOE
        )
        bat_saving = (
            0
            + (1000 / 1000) * self.GRID_PRICE_VALUE
            - 0
            - (1000 / 1000) * self.BAT_LCOS
        )
        assert power_insight.total_levelized_saving_rate == pytest.approx(
            pv_saving + bat_saving
        )

    # === Grid adapter ===

    def test_grid_adapter_total_power_share(self, power_insight):
        assert power_insight.grid_adapter_total_power_shares[self.GRID_UID] == pytest.approx(
            500 / 3500
        )

    def test_grid_adapter_self_cons_rate(self, power_insight):
        # applicable_self_consumption_share = 1.0
        assert power_insight.grid_adapter_self_cons_rates[self.GRID_UID] == pytest.approx(1.0)

    def test_grid_adapter_self_cons_share(self, power_insight):
        # (1.0 * (500/3500)) / 1.0
        assert power_insight.grid_adapter_self_cons_shares[self.GRID_UID] == pytest.approx(
            (1.0 * (500 / 3500)) / 1.0
        )

    def test_grid_adapter_utilization_rate(self, power_insight):
        assert power_insight.grid_adapter_utilization_rates[self.GRID_UID] == pytest.approx(0.0)

    def test_grid_adapter_utilization_share(self, power_insight):
        assert power_insight.grid_adapter_utilization_shares[self.GRID_UID] == pytest.approx(0.0)

    # === Production adapters ===

    def test_prod_adapters_export_power(self, power_insight):
        # No export → 0 for both
        assert power_insight.prod_adapters_export_power[self.PV_UID] == pytest.approx(0.0)
        assert power_insight.prod_adapters_export_power[self.BAT_UID] == pytest.approx(0.0)

    def test_prod_adapters_export_rates(self, power_insight):
        # total_export_share = 0 → export_rate = 0 for both
        assert power_insight.prod_adapters_export_rates[self.PV_UID] == pytest.approx(0.0)
        assert power_insight.prod_adapters_export_rates[self.BAT_UID] == pytest.approx(0.0)

    def test_prod_adapters_export_shares(self, power_insight):
        # PV exports_power=True but no actual export; battery exports_power=False
        assert power_insight.prod_adapters_export_shares[self.PV_UID] == pytest.approx(1.0)
        assert power_insight.prod_adapters_export_shares[self.BAT_UID] == pytest.approx(0.0)

    def test_prod_adapters_export_compensation_rates(self, power_insight):
        assert power_insight.prod_adapters_export_compensation_rates[self.PV_UID] == pytest.approx(0.0)
        assert power_insight.prod_adapters_export_compensation_rates[self.BAT_UID] == pytest.approx(0.0)

    def test_prod_adapters_self_cons_power(self, power_insight):
        # self_cons_rate = 1.0 for both → power * 1.0
        assert power_insight.prod_adapters_self_cons_power[self.PV_UID] == pytest.approx(2000 * 1.0)
        assert power_insight.prod_adapters_self_cons_power[self.BAT_UID] == pytest.approx(1000 * 1.0)

    def test_prod_adapters_self_cons_rates(self, power_insight):
        # (1 - 0) * 1.0 = 1.0 for both
        assert power_insight.prod_adapters_self_cons_rates[self.PV_UID] == pytest.approx(1.0)
        assert power_insight.prod_adapters_self_cons_rates[self.BAT_UID] == pytest.approx(1.0)

    def test_prod_adapters_self_cons_shares(self, power_insight):
        # (1.0 * power_share) / 1.0 = power_share
        assert power_insight.prod_adapters_self_cons_shares[self.PV_UID] == pytest.approx(
            (1.0 * (2000 / 3500)) / 1.0
        )
        assert power_insight.prod_adapters_self_cons_shares[self.BAT_UID] == pytest.approx(
            (1.0 * (1000 / 3500)) / 1.0
        )

    def test_prod_adapters_self_cons_saving_rates(self, power_insight):
        # self_cons_power_kW * grid_price
        assert power_insight.prod_adapters_self_cons_saving_rates[self.PV_UID] == pytest.approx(
            (2000 / 1000) * self.GRID_PRICE_VALUE
        )
        assert power_insight.prod_adapters_self_cons_saving_rates[self.BAT_UID] == pytest.approx(
            (1000 / 1000) * self.GRID_PRICE_VALUE
        )

    def test_prod_adapters_coo_rates(self, power_insight):
        # Both consumption = 0
        assert power_insight.prod_adapters_coo_rates[self.PV_UID] == pytest.approx(0.0)
        assert power_insight.prod_adapters_coo_rates[self.BAT_UID] == pytest.approx(0.0)

    def test_prod_adapters_lcoo_rates(self, power_insight):
        assert power_insight.prod_adapters_lcoo_rates[self.PV_UID] == pytest.approx(0.0)
        assert power_insight.prod_adapters_lcoo_rates[self.BAT_UID] == pytest.approx(0.0)

    def test_prod_adapters_saving_rates(self, power_insight):
        # export_comp=0 + self_cons_savings - coo=0 - coe_rate(base=0)
        assert power_insight.prod_adapters_saving_rates[self.PV_UID] == pytest.approx(
            0 + (2000 / 1000) * self.GRID_PRICE_VALUE - 0 - 0
        )
        assert power_insight.prod_adapters_saving_rates[self.BAT_UID] == pytest.approx(
            0 + (1000 / 1000) * self.GRID_PRICE_VALUE - 0 - 0
        )

    def test_prod_adapters_levelized_saving_rates(self, power_insight):
        # PV: 0 + self_cons_savings - 0 - lcoe_rate
        assert power_insight.prod_adapters_levelized_saving_rates[self.PV_UID] == pytest.approx(
            0 + (2000 / 1000) * self.GRID_PRICE_VALUE - 0 - (2000 / 1000) * self.PV_LCOE
        )
        # Battery: 0 + self_cons_savings - 0 - lcos_rate
        assert power_insight.prod_adapters_levelized_saving_rates[self.BAT_UID] == pytest.approx(
            0 + (1000 / 1000) * self.GRID_PRICE_VALUE - 0 - (1000 / 1000) * self.BAT_LCOS
        )


# ===================================================================
# Scenario 3 — Grid + PV + Battery + Consumer
# ===================================================================
# Same power setup as scenario 2, plus a consumer at -800 W.
# Consumer power is negative (consuming).
# ===================================================================

class TestScenario3GridPvBatteryConsumer:
    """Grid + PV + Battery + Consumer."""

    GRID_UID = "grid"
    PV_UID = "pv"
    BAT_UID = "bat"
    CONS_UID = "cons"

    GRID_POWER = "sensor.grid_power"
    GRID_PRICE = "sensor.grid_price"
    PV_POWER = "sensor.pv_power"
    BAT_POWER = "sensor.bat_power"
    CONS_POWER = "sensor.consumer_power"

    GRID_POWER_VALUE = 500     # W
    GRID_PRICE_VALUE = 0.30    # EUR/kWh
    PV_POWER_VALUE = 2000      # W
    PV_LCOE = 0.08             # EUR/kWh
    PV_EXPORT_COMP = 0.08      # EUR/kWh
    BAT_POWER_VALUE = 1000     # W
    BAT_LCOS = 0.12            # EUR/kWh
    CONS_POWER_VALUE = -800    # W, negative = consuming

    @pytest.fixture()
    def power_insight(self):
        return build_scenario([
            create_grid(self.GRID_UID, self.GRID_POWER, self.GRID_PRICE, self.GRID_POWER_VALUE, self.GRID_PRICE_VALUE),
            create_pv(self.PV_UID, self.PV_POWER, self.PV_POWER_VALUE, self.PV_LCOE, 0.0, True, self.PV_EXPORT_COMP),
            create_battery(self.BAT_UID, self.BAT_POWER, self.BAT_POWER_VALUE, self.BAT_LCOS, 0.0, False, 0.0, True, []),
            create_consumer(self.CONS_UID, self.CONS_POWER, self.CONS_POWER_VALUE),
        ])

    # === Combined values (consumer doesn't affect production-side calculations) ===

    def test_total_power(self, power_insight):
        # Consumer is not a prod adapter — doesn't affect total_power
        assert power_insight.total_power == pytest.approx(500 + 2000 + 1000)

    def test_self_consumption(self, power_insight):
        assert power_insight.self_consumption == pytest.approx(3500.0)

    def test_coe(self, power_insight):
        grid_coe_rate = (500 / 1000) * self.GRID_PRICE_VALUE
        assert power_insight.coe == pytest.approx(grid_coe_rate / (3500 / 1000))

    def test_lcoe(self, power_insight):
        lcoe_rate = (
            (500 / 1000) * self.GRID_PRICE_VALUE
            + (2000 / 1000) * self.PV_LCOE
            + (1000 / 1000) * self.BAT_LCOS
        )
        assert power_insight.lcoe == pytest.approx(lcoe_rate / (3500 / 1000))

    # === Production adapters — unchanged from scenario 2 ===

    def test_prod_adapters_saving_rates(self, power_insight):
        assert power_insight.prod_adapters_saving_rates[self.PV_UID] == pytest.approx(
            0 + (2000 / 1000) * self.GRID_PRICE_VALUE - 0 - 0
        )
        assert power_insight.prod_adapters_saving_rates[self.BAT_UID] == pytest.approx(
            0 + (1000 / 1000) * self.GRID_PRICE_VALUE - 0 - 0
        )

    # === Consumption adapters ===

    def test_cons_adapter_total_power_share(self, power_insight):
        # consumption = -power = 800; share = 800 / 3500
        assert power_insight.cons_adapter_total_power_shares[self.CONS_UID] == pytest.approx(
            800 / 3500
        )

    def test_cons_adapter_self_cons_share(self, power_insight):
        # power_share / self_cons_share = (800/3500) / 1.0
        assert power_insight.cons_adapters_self_cons_share[self.CONS_UID] == pytest.approx(
            (800 / 3500) / 1.0
        )

    def test_cons_adapter_source_shares(self, power_insight):
        # Each provider's self_cons_share = (applicable_sc * provider_power_share) / sc_share
        # applicable_sc = 1.0, sc_share = 1.0 → shares equal power_shares
        shares = power_insight.cons_adapters_source_shares[self.CONS_UID]
        assert shares[self.GRID_UID] == pytest.approx(500 / 3500)
        assert shares[self.PV_UID] == pytest.approx(2000 / 3500)
        assert shares[self.BAT_UID] == pytest.approx(1000 / 3500)

    def test_cons_adapter_coo_rate(self, power_insight):
        # consumption_kW * coe (blended)
        coe = ((500 / 1000) * self.GRID_PRICE_VALUE) / (3500 / 1000)
        assert power_insight.cons_adapters_coo_rates[self.CONS_UID] == pytest.approx(
            (800 / 1000) * coe
        )

    def test_cons_adapter_lcoo_rate(self, power_insight):
        # consumption_kW * lcoe (blended)
        lcoe_rate = (
            (500 / 1000) * self.GRID_PRICE_VALUE
            + (2000 / 1000) * self.PV_LCOE
            + (1000 / 1000) * self.BAT_LCOS
        )
        lcoe = lcoe_rate / (3500 / 1000)
        assert power_insight.cons_adapters_lcoo_rates[self.CONS_UID] == pytest.approx(
            (800 / 1000) * lcoe
        )
