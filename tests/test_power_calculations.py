"""Tests for PowerInsight core calculation logic.

Four scenarios of increasing complexity:
  1. Grid + PV  (excess production → exporting)
  2. Grid + PV + Battery  (all consumed, no export)
  3. Grid + PV + Battery + Consumer  (consumer cost allocation)
  4. Grid + PV_1 + PV_2  (multiple adapters of same class)
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


def create_grid(unique_id, power_entity, price_entity, power_value, price_value):
    adapter = GridAdapter(
        unique_id=unique_id,
        verbose_name=unique_id.upper(),
        power_entity=power_entity,
        price_entity=price_entity,
    )
    return adapter, {power_entity: power_value, price_entity: price_value}


def create_pv(unique_id, power_entity, power_value, lcoe, lco2_intensity, exports_power, export_compensation):
    adapter = PvAdapter(
        unique_id=unique_id,
        verbose_name=unique_id.upper(),
        power_entity=power_entity,
        power_entity_inverted=False,
        lcoe=lcoe,
        lco2_intensity=lco2_intensity,
        exports_power=exports_power,
        export_compensation=export_compensation,
    )
    return adapter, {power_entity: power_value}


def create_battery(unique_id, power_entity, power_value, lcos, lco2_intensity, exports_power, export_compensation):
    adapter = BatteryAdapter(
        unique_id=unique_id,
        verbose_name=unique_id.upper(),
        power_entity=power_entity,
        power_entity_inverted=False,
        lcos=lcos,
        lco2_intensity=lco2_intensity,
        exports_power=exports_power,
        export_compensation=export_compensation,
    )
    return adapter, {power_entity: power_value}


def create_consumer(unique_id, power_entity, power_value):
    adapter = ConsumerAdapter(
        unique_id=unique_id,
        verbose_name=unique_id.upper(),
        power_entity=power_entity,
    )
    return adapter, {power_entity: power_value}


def build_scenario(adapter_specs):
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

    GRID_ENTITY = "sensor.grid_power"
    GRID_PRICE_ENTITY = "sensor.grid_price"
    PV_ENTITY = "sensor.pv_power"

    GRID_POWER = -1000
    GRID_PRICE = 0.30
    PV_POWER = 3000
    PV_LCOE = 0.08
    PV_EXPORT_COMP = 0.08

    @pytest.fixture()
    def power_insight(self):
        return build_scenario([
            create_grid("grid", self.GRID_ENTITY, self.GRID_PRICE_ENTITY, self.GRID_POWER, self.GRID_PRICE),
            create_pv("pv", self.PV_ENTITY, self.PV_POWER, self.PV_LCOE, 0.0, True, self.PV_EXPORT_COMP),
        ])

    # -- Common --

    def test_grid_import(self, power_insight):
        # grid power = -1000 → import = max(power, 0) = 0
        assert power_insight.grid_import == pytest.approx(0.0)

    def test_grid_export(self, power_insight):
        # grid power = -1000 → export = -power = 1000
        assert power_insight.grid_export == pytest.approx(1000.0)

    def test_production(self, power_insight):
        assert power_insight.production == pytest.approx(3000.0)

    def test_utilization(self, power_insight):
        assert power_insight.utilization == pytest.approx(0.0)

    def test_total_power(self, power_insight):
        # grid_import + production = 0 + 3000
        assert power_insight.total_power == pytest.approx(3000.0)

    def test_self_consumption(self, power_insight):
        # total_power - grid_export - utilization = 3000 - 1000 - 0
        assert power_insight.self_consumption == pytest.approx(2000.0)

    def test_export_share(self, power_insight):
        # grid_export / total_power = 1000 / 3000
        assert power_insight.export_share == pytest.approx(1000 / 3000)

    def test_utilization_share(self, power_insight):
        assert power_insight.utilization_share == pytest.approx(0.0)

    def test_self_consumption_share(self, power_insight):
        # self_consumption / total_power = 2000 / 3000
        assert power_insight.self_consumption_share == pytest.approx(2000 / 3000)

    def test_applicable_utilization_share(self, power_insight):
        assert power_insight.applicable_utilization_share == pytest.approx(0.0)

    def test_applicable_self_consumption_share(self, power_insight):
        # self_cons_share / (1 - export_share) = (2/3) / (2/3) = 1.0
        assert power_insight.applicable_self_consumption_share == pytest.approx(1.0)

    def test_coe_rate(self, power_insight):
        # grid_import=0 → grid coe_rate=0; pv coe=0 → total=0
        assert power_insight.coe_rate == pytest.approx(0.0)

    def test_coe(self, power_insight):
        assert power_insight.coe == pytest.approx(0.0)

    def test_lcoe_rate(self, power_insight):
        # grid: 0, pv: (3000/1000) * 0.08 = 0.24
        assert power_insight.lcoe_rate == pytest.approx((3000 / 1000) * self.PV_LCOE)

    def test_lcoe(self, power_insight):
        lcoe_rate = (3000 / 1000) * self.PV_LCOE
        assert power_insight.lcoe == pytest.approx(lcoe_rate / (3000 / 1000))

    # -- Grid adapter --

    def test_grid_total_power_share(self, power_insight):
        # grid_import / total_power = 0 / 3000
        assert power_insight.grid_adapter_total_power_shares["grid"] == pytest.approx(0.0)

    def test_grid_self_cons_rate(self, power_insight):
        # applicable_self_consumption_share = 1.0
        assert power_insight.grid_adapter_self_cons_rates["grid"] == pytest.approx(1.0)

    def test_grid_self_cons_share(self, power_insight):
        # (self_cons_rate * power_share) / self_cons_share = (1.0 * 0) / (2/3) = 0
        assert power_insight.grid_adapter_self_cons_shares["grid"] == pytest.approx(0.0)

    # -- PV adapter --

    def test_pv_total_power_share(self, power_insight):
        # 3000 / 3000 = 1.0
        assert power_insight.prod_adapters_total_power_shares["pv"] == pytest.approx(1.0)

    def test_pv_export_share(self, power_insight):
        # PV is the only exporter → 100%
        assert power_insight.prod_adapters_export_shares["pv"] == pytest.approx(1.0)

    def test_pv_export_rate(self, power_insight):
        # export_share * total_export_share / power_share = 1.0 * (1/3) / 1.0 = 1/3
        assert power_insight.prod_adapters_export_rates["pv"] == pytest.approx(1000 / 3000)

    def test_pv_export_power(self, power_insight):
        # grid_export * export_share = 1000 * 1.0
        assert power_insight.prod_adapters_export_power["pv"] == pytest.approx(1000.0)

    def test_pv_export_compensation_rate(self, power_insight):
        # (1000/1000) * 0.08 = 0.08
        assert power_insight.prod_adapters_export_compensation_rates["pv"] == pytest.approx(
            (1000 / 1000) * self.PV_EXPORT_COMP
        )

    def test_pv_self_cons_rate(self, power_insight):
        # (1 - export_rate) * applicable_sc_share = (1 - 1/3) * 1.0 = 2/3
        assert power_insight.prod_adapters_self_cons_rates["pv"] == pytest.approx(2000 / 3000)

    def test_pv_self_cons_share(self, power_insight):
        # (self_cons_rate * power_share) / self_cons_share = (2/3 * 1.0) / (2/3) = 1.0
        assert power_insight.prod_adapters_self_cons_shares["pv"] == pytest.approx(1.0)

    def test_pv_self_cons_power(self, power_insight):
        # production * self_cons_rate = 3000 * 2/3 = 2000
        assert power_insight.prod_adapters_self_cons_power["pv"] == pytest.approx(2000.0)

    def test_pv_self_cons_saving_rate(self, power_insight):
        # self_cons_power_kW * grid_price = (2000/1000) * 0.30 = 0.60
        assert power_insight.prod_adapters_self_cons_saving_rates["pv"] == pytest.approx(
            (2000 / 1000) * self.GRID_PRICE
        )

    def test_pv_coo_rate(self, power_insight):
        # PV consumption = 0 → coo_rate = 0
        assert power_insight.prod_adapters_coo_rates["pv"] == pytest.approx(0.0)

    def test_pv_lcoo_rate(self, power_insight):
        assert power_insight.prod_adapters_lcoo_rates["pv"] == pytest.approx(0.0)

    def test_pv_saving_rate(self, power_insight):
        # export_comp + self_cons_savings - coo - coe_rate
        export_comp = (1000 / 1000) * self.PV_EXPORT_COMP
        self_cons_savings = (2000 / 1000) * self.GRID_PRICE
        assert power_insight.prod_adapters_saving_rates["pv"] == pytest.approx(
            export_comp + self_cons_savings
        )

    def test_pv_levelized_saving_rate(self, power_insight):
        # Same but subtracts lcoe_rate
        export_comp = (1000 / 1000) * self.PV_EXPORT_COMP
        self_cons_savings = (2000 / 1000) * self.GRID_PRICE
        lcoe_rate = (3000 / 1000) * self.PV_LCOE
        assert power_insight.prod_adapters_levelized_saving_rates["pv"] == pytest.approx(
            export_comp + self_cons_savings - lcoe_rate
        )

    # -- Totals --

    def test_total_export_compensation_rate(self, power_insight):
        assert power_insight.total_export_compensation_rate == pytest.approx(
            (1000 / 1000) * self.PV_EXPORT_COMP
        )

    def test_total_self_cons_saving_rate(self, power_insight):
        assert power_insight.total_self_cons_saving_rate == pytest.approx(
            (2000 / 1000) * self.GRID_PRICE
        )

    def test_total_coo_rate(self, power_insight):
        assert power_insight.total_coo_rate == pytest.approx(0.0)

    def test_total_saving_rate(self, power_insight):
        export_comp = (1000 / 1000) * self.PV_EXPORT_COMP
        self_cons_savings = (2000 / 1000) * self.GRID_PRICE
        assert power_insight.total_saving_rate == pytest.approx(
            export_comp + self_cons_savings
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

    GRID_ENTITY = "sensor.grid_power"
    GRID_PRICE_ENTITY = "sensor.grid_price"
    PV_ENTITY = "sensor.pv_power"
    BAT_ENTITY = "sensor.bat_power"

    GRID_POWER = 500
    GRID_PRICE = 0.30
    PV_POWER = 2000
    PV_LCOE = 0.08
    PV_EXPORT_COMP = 0.08
    BAT_POWER = 1000
    BAT_LCOS = 0.12

    @pytest.fixture()
    def power_insight(self):
        return build_scenario([
            create_grid("grid", self.GRID_ENTITY, self.GRID_PRICE_ENTITY, self.GRID_POWER, self.GRID_PRICE),
            create_pv("pv", self.PV_ENTITY, self.PV_POWER, self.PV_LCOE, 0.0, True, self.PV_EXPORT_COMP),
            create_battery("bat", self.BAT_ENTITY, self.BAT_POWER, self.BAT_LCOS, 0.0, False, 0.0),
        ])

    # -- Common --

    def test_grid_import(self, power_insight):
        assert power_insight.grid_import == pytest.approx(500.0)

    def test_grid_export(self, power_insight):
        assert power_insight.grid_export == pytest.approx(0.0)

    def test_production(self, power_insight):
        # PV + Battery = 2000 + 1000
        assert power_insight.production == pytest.approx(3000.0)

    def test_utilization(self, power_insight):
        assert power_insight.utilization == pytest.approx(0.0)

    def test_total_power(self, power_insight):
        # grid_import + production = 500 + 3000
        assert power_insight.total_power == pytest.approx(3500.0)

    def test_self_consumption(self, power_insight):
        # total_power - export - utilization = 3500 - 0 - 0
        assert power_insight.self_consumption == pytest.approx(3500.0)

    def test_export_share(self, power_insight):
        assert power_insight.export_share == pytest.approx(0.0)

    def test_self_consumption_share(self, power_insight):
        assert power_insight.self_consumption_share == pytest.approx(1.0)

    def test_applicable_self_consumption_share(self, power_insight):
        assert power_insight.applicable_self_consumption_share == pytest.approx(1.0)

    def test_coe_rate(self, power_insight):
        # grid: (500/1000) * 0.30 = 0.15
        assert power_insight.coe_rate == pytest.approx((500 / 1000) * self.GRID_PRICE)

    def test_coe(self, power_insight):
        grid_coe_rate = (500 / 1000) * self.GRID_PRICE
        assert power_insight.coe == pytest.approx(grid_coe_rate / (3500 / 1000))

    def test_lcoe_rate(self, power_insight):
        # grid + pv + bat
        assert power_insight.lcoe_rate == pytest.approx(
            (500 / 1000) * self.GRID_PRICE
            + (2000 / 1000) * self.PV_LCOE
            + (1000 / 1000) * self.BAT_LCOS
        )

    def test_lcoe(self, power_insight):
        lcoe_rate = (
            (500 / 1000) * self.GRID_PRICE
            + (2000 / 1000) * self.PV_LCOE
            + (1000 / 1000) * self.BAT_LCOS
        )
        assert power_insight.lcoe == pytest.approx(lcoe_rate / (3500 / 1000))

    # -- Grid adapter --

    def test_grid_total_power_share(self, power_insight):
        assert power_insight.grid_adapter_total_power_shares["grid"] == pytest.approx(500 / 3500)

    def test_grid_self_cons_rate(self, power_insight):
        assert power_insight.grid_adapter_self_cons_rates["grid"] == pytest.approx(1.0)

    def test_grid_self_cons_share(self, power_insight):
        # (1.0 * 500/3500) / 1.0 = 500/3500
        assert power_insight.grid_adapter_self_cons_shares["grid"] == pytest.approx(500 / 3500)

    # -- PV adapter --

    def test_pv_total_power_share(self, power_insight):
        assert power_insight.prod_adapters_total_power_shares["pv"] == pytest.approx(2000 / 3500)

    def test_pv_export_share(self, power_insight):
        # PV is the only exporter (exports_power=True), but actual export = 0 → 100% of 0
        assert power_insight.prod_adapters_export_shares["pv"] == pytest.approx(1.0)

    def test_pv_export_rate(self, power_insight):
        # total_export_share = 0 → rate = 0
        assert power_insight.prod_adapters_export_rates["pv"] == pytest.approx(0.0)

    def test_pv_export_power(self, power_insight):
        assert power_insight.prod_adapters_export_power["pv"] == pytest.approx(0.0)

    def test_pv_export_compensation_rate(self, power_insight):
        assert power_insight.prod_adapters_export_compensation_rates["pv"] == pytest.approx(0.0)

    def test_pv_self_cons_rate(self, power_insight):
        # (1 - 0) * 1.0 = 1.0
        assert power_insight.prod_adapters_self_cons_rates["pv"] == pytest.approx(1.0)

    def test_pv_self_cons_share(self, power_insight):
        # (1.0 * 2000/3500) / 1.0 = 2000/3500
        assert power_insight.prod_adapters_self_cons_shares["pv"] == pytest.approx(2000 / 3500)

    def test_pv_self_cons_power(self, power_insight):
        assert power_insight.prod_adapters_self_cons_power["pv"] == pytest.approx(2000.0)

    def test_pv_self_cons_saving_rate(self, power_insight):
        assert power_insight.prod_adapters_self_cons_saving_rates["pv"] == pytest.approx(
            (2000 / 1000) * self.GRID_PRICE
        )

    def test_pv_coo_rate(self, power_insight):
        assert power_insight.prod_adapters_coo_rates["pv"] == pytest.approx(0.0)

    def test_pv_saving_rate(self, power_insight):
        # export_comp=0 + self_cons_savings - coo=0 - coe=0
        assert power_insight.prod_adapters_saving_rates["pv"] == pytest.approx(
            (2000 / 1000) * self.GRID_PRICE
        )

    def test_pv_levelized_saving_rate(self, power_insight):
        assert power_insight.prod_adapters_levelized_saving_rates["pv"] == pytest.approx(
            (2000 / 1000) * self.GRID_PRICE - (2000 / 1000) * self.PV_LCOE
        )

    # -- Battery adapter --

    def test_bat_total_power_share(self, power_insight):
        assert power_insight.prod_adapters_total_power_shares["bat"] == pytest.approx(1000 / 3500)

    def test_bat_export_share(self, power_insight):
        # battery has exports_power=False → 0%
        assert power_insight.prod_adapters_export_shares["bat"] == pytest.approx(0.0)

    def test_bat_export_rate(self, power_insight):
        assert power_insight.prod_adapters_export_rates["bat"] == pytest.approx(0.0)

    def test_bat_export_power(self, power_insight):
        assert power_insight.prod_adapters_export_power["bat"] == pytest.approx(0.0)

    def test_bat_export_compensation_rate(self, power_insight):
        assert power_insight.prod_adapters_export_compensation_rates["bat"] == pytest.approx(0.0)

    def test_bat_self_cons_rate(self, power_insight):
        assert power_insight.prod_adapters_self_cons_rates["bat"] == pytest.approx(1.0)

    def test_bat_self_cons_share(self, power_insight):
        # (1.0 * 1000/3500) / 1.0 = 1000/3500
        assert power_insight.prod_adapters_self_cons_shares["bat"] == pytest.approx(1000 / 3500)

    def test_bat_self_cons_power(self, power_insight):
        assert power_insight.prod_adapters_self_cons_power["bat"] == pytest.approx(1000.0)

    def test_bat_self_cons_saving_rate(self, power_insight):
        assert power_insight.prod_adapters_self_cons_saving_rates["bat"] == pytest.approx(
            (1000 / 1000) * self.GRID_PRICE
        )

    def test_bat_coo_rate(self, power_insight):
        assert power_insight.prod_adapters_coo_rates["bat"] == pytest.approx(0.0)

    def test_bat_saving_rate(self, power_insight):
        assert power_insight.prod_adapters_saving_rates["bat"] == pytest.approx(
            (1000 / 1000) * self.GRID_PRICE
        )

    def test_bat_levelized_saving_rate(self, power_insight):
        assert power_insight.prod_adapters_levelized_saving_rates["bat"] == pytest.approx(
            (1000 / 1000) * self.GRID_PRICE - (1000 / 1000) * self.BAT_LCOS
        )

    # -- Totals --

    def test_total_export_compensation_rate(self, power_insight):
        assert power_insight.total_export_compensation_rate == pytest.approx(0.0)

    def test_total_self_cons_saving_rate(self, power_insight):
        assert power_insight.total_self_cons_saving_rate == pytest.approx(
            (2000 / 1000) * self.GRID_PRICE + (1000 / 1000) * self.GRID_PRICE
        )

    def test_total_coo_rate(self, power_insight):
        assert power_insight.total_coo_rate == pytest.approx(0.0)

    def test_total_lcoo_rate(self, power_insight):
        assert power_insight.total_lcoo_rate == pytest.approx(0.0)

    def test_total_saving_rate(self, power_insight):
        assert power_insight.total_saving_rate == pytest.approx(
            (2000 / 1000) * self.GRID_PRICE + (1000 / 1000) * self.GRID_PRICE
        )

    def test_total_levelized_saving_rate(self, power_insight):
        pv_saving = (2000 / 1000) * self.GRID_PRICE - (2000 / 1000) * self.PV_LCOE
        bat_saving = (1000 / 1000) * self.GRID_PRICE - (1000 / 1000) * self.BAT_LCOS
        assert power_insight.total_levelized_saving_rate == pytest.approx(pv_saving + bat_saving)


# ===================================================================
# Scenario 3 — Grid + PV + Battery + Consumer
# ===================================================================
# Same power setup as Scenario 2, plus a consumer at -800 W.
# Consumer power is negative (consuming).
# ===================================================================

class TestScenario3GridPvBatteryConsumer:
    """Grid + PV + Battery + Consumer."""

    GRID_ENTITY = "sensor.grid_power"
    GRID_PRICE_ENTITY = "sensor.grid_price"
    PV_ENTITY = "sensor.pv_power"
    BAT_ENTITY = "sensor.bat_power"
    CONS_ENTITY = "sensor.consumer_power"

    GRID_POWER = 500
    GRID_PRICE = 0.30
    PV_POWER = 2000
    PV_LCOE = 0.08
    PV_EXPORT_COMP = 0.08
    BAT_POWER = 1000
    BAT_LCOS = 0.12
    CONS_POWER = -800

    @pytest.fixture()
    def power_insight(self):
        return build_scenario([
            create_grid("grid", self.GRID_ENTITY, self.GRID_PRICE_ENTITY, self.GRID_POWER, self.GRID_PRICE),
            create_pv("pv", self.PV_ENTITY, self.PV_POWER, self.PV_LCOE, 0.0, True, self.PV_EXPORT_COMP),
            create_battery("bat", self.BAT_ENTITY, self.BAT_POWER, self.BAT_LCOS, 0.0, False, 0.0),
            create_consumer("cons", self.CONS_ENTITY, self.CONS_POWER),
        ])

    # -- Common (power flows unchanged by consumer) --

    def test_total_power(self, power_insight):
        assert power_insight.total_power == pytest.approx(3500.0)

    def test_self_consumption(self, power_insight):
        assert power_insight.self_consumption == pytest.approx(3500.0)

    # -- Consumer adapter --

    def test_cons_total_power_share(self, power_insight):
        # consumption / total_power = 800 / 3500
        assert power_insight.cons_adapter_total_power_shares["cons"] == pytest.approx(800 / 3500)

    def test_cons_self_cons_share(self, power_insight):
        # (800/3500) / 1.0 = 800/3500
        assert power_insight.cons_adapters_self_cons_share["cons"] == pytest.approx(800 / 3500)

    def test_cons_source_share_grid(self, power_insight):
        # grid self_cons_share = (1.0 * 500/3500) / 1.0 = 500/3500
        assert power_insight.cons_adapters_source_shares["cons"]["grid"] == pytest.approx(
            500 / 3500
        )

    def test_cons_source_share_pv(self, power_insight):
        assert power_insight.cons_adapters_source_shares["cons"]["pv"] == pytest.approx(
            2000 / 3500
        )

    def test_cons_source_share_bat(self, power_insight):
        assert power_insight.cons_adapters_source_shares["cons"]["bat"] == pytest.approx(
            1000 / 3500
        )

    def test_cons_coo_rate(self, power_insight):
        # consumption_kW * coe (blended)
        coe = ((500 / 1000) * self.GRID_PRICE) / (3500 / 1000)
        assert power_insight.cons_adapters_coo_rates["cons"] == pytest.approx(
            (800 / 1000) * coe
        )

    def test_cons_lcoo_rate(self, power_insight):
        lcoe_rate = (
            (500 / 1000) * self.GRID_PRICE
            + (2000 / 1000) * self.PV_LCOE
            + (1000 / 1000) * self.BAT_LCOS
        )
        lcoe = lcoe_rate / (3500 / 1000)
        assert power_insight.cons_adapters_lcoo_rates["cons"] == pytest.approx(
            (800 / 1000) * lcoe
        )

    # -- Production adapters (verify unchanged by consumer) --

    def test_pv_saving_rate_unchanged(self, power_insight):
        assert power_insight.prod_adapters_saving_rates["pv"] == pytest.approx(
            (2000 / 1000) * self.GRID_PRICE
        )

    def test_bat_saving_rate_unchanged(self, power_insight):
        assert power_insight.prod_adapters_saving_rates["bat"] == pytest.approx(
            (1000 / 1000) * self.GRID_PRICE
        )


# ===================================================================
# Scenario 4 — Grid + PV_1 + PV_2  (multiple adapters of same class)
# ===================================================================
# Grid power: -1000 W  (exporting)
# PV_1 power:  2000 W  (producing), LCOE=0.08, comp=0.08
# PV_2 power:  1000 W  (producing), LCOE=0.10, comp=0.08
#
# Both PV adapters export; export is distributed proportionally:
#   PV_1 export_share = 2/3, export_power = 1000 * (2/3) ≈ 667 W
#   PV_2 export_share = 1/3, export_power = 1000 * (1/3) ≈ 333 W
# ===================================================================

class TestScenario4GridPv1Pv2:
    """Grid + two PV adapters; export is split proportionally."""

    GRID_ENTITY = "sensor.grid_power"
    GRID_PRICE_ENTITY = "sensor.grid_price"
    PV1_ENTITY = "sensor.pv1_power"
    PV2_ENTITY = "sensor.pv2_power"

    GRID_POWER = -1000
    GRID_PRICE = 0.30
    PV1_POWER = 2000
    PV1_LCOE = 0.08
    PV1_EXPORT_COMP = 0.08
    PV2_POWER = 1000
    PV2_LCOE = 0.10
    PV2_EXPORT_COMP = 0.08

    @pytest.fixture()
    def power_insight(self):
        return build_scenario([
            create_grid("grid", self.GRID_ENTITY, self.GRID_PRICE_ENTITY, self.GRID_POWER, self.GRID_PRICE),
            create_pv("pv_1", self.PV1_ENTITY, self.PV1_POWER, self.PV1_LCOE, 0.0, True, self.PV1_EXPORT_COMP),
            create_pv("pv_2", self.PV2_ENTITY, self.PV2_POWER, self.PV2_LCOE, 0.0, True, self.PV2_EXPORT_COMP),
        ])

    # -- Common --

    def test_grid_import(self, power_insight):
        assert power_insight.grid_import == pytest.approx(0.0)

    def test_grid_export(self, power_insight):
        assert power_insight.grid_export == pytest.approx(1000.0)

    def test_production(self, power_insight):
        assert power_insight.production == pytest.approx(3000.0)

    def test_utilization(self, power_insight):
        assert power_insight.utilization == pytest.approx(0.0)

    def test_total_power(self, power_insight):
        assert power_insight.total_power == pytest.approx(3000.0)

    def test_self_consumption(self, power_insight):
        # 3000 - 1000 - 0 = 2000
        assert power_insight.self_consumption == pytest.approx(2000.0)

    def test_export_share(self, power_insight):
        assert power_insight.export_share == pytest.approx(1000 / 3000)

    def test_self_consumption_share(self, power_insight):
        assert power_insight.self_consumption_share == pytest.approx(2000 / 3000)

    def test_applicable_self_consumption_share(self, power_insight):
        # (2/3) / (1 - 1/3) = 1.0
        assert power_insight.applicable_self_consumption_share == pytest.approx(1.0)

    def test_coe_rate(self, power_insight):
        # grid_import = 0 → coe_rate = 0
        assert power_insight.coe_rate == pytest.approx(0.0)

    def test_coe(self, power_insight):
        assert power_insight.coe == pytest.approx(0.0)

    def test_lcoe_rate(self, power_insight):
        # pv_1: (2000/1000) * 0.08, pv_2: (1000/1000) * 0.10
        assert power_insight.lcoe_rate == pytest.approx(
            (2000 / 1000) * self.PV1_LCOE + (1000 / 1000) * self.PV2_LCOE
        )

    def test_lcoe(self, power_insight):
        lcoe_rate = (2000 / 1000) * self.PV1_LCOE + (1000 / 1000) * self.PV2_LCOE
        assert power_insight.lcoe == pytest.approx(lcoe_rate / (3000 / 1000))

    # -- Grid adapter --

    def test_grid_total_power_share(self, power_insight):
        assert power_insight.grid_adapter_total_power_shares["grid"] == pytest.approx(0.0)

    def test_grid_self_cons_rate(self, power_insight):
        assert power_insight.grid_adapter_self_cons_rates["grid"] == pytest.approx(1.0)

    def test_grid_self_cons_share(self, power_insight):
        # (1.0 * 0) / (2/3) = 0
        assert power_insight.grid_adapter_self_cons_shares["grid"] == pytest.approx(0.0)

    # -- PV_1 adapter --

    def test_pv1_total_power_share(self, power_insight):
        # 2000 / 3000
        assert power_insight.prod_adapters_total_power_shares["pv_1"] == pytest.approx(2000 / 3000)

    def test_pv1_export_share(self, power_insight):
        # proportional to power among exporters: 2000 / (2000 + 1000) = 2/3
        assert power_insight.prod_adapters_export_shares["pv_1"] == pytest.approx(2000 / 3000)

    def test_pv1_export_rate(self, power_insight):
        # export_share * total_export_share / power_share
        # = (2/3) * (1/3) / (2/3) = 1/3
        assert power_insight.prod_adapters_export_rates["pv_1"] == pytest.approx(1000 / 3000)

    def test_pv1_export_power(self, power_insight):
        # grid_export * pv1_export_share = 1000 * 2/3
        assert power_insight.prod_adapters_export_power["pv_1"] == pytest.approx(
            1000 * (2000 / 3000)
        )

    def test_pv1_export_compensation_rate(self, power_insight):
        # (export_power / 1000) * compensation
        export_power = 1000 * (2000 / 3000)
        assert power_insight.prod_adapters_export_compensation_rates["pv_1"] == pytest.approx(
            (export_power / 1000) * self.PV1_EXPORT_COMP
        )

    def test_pv1_self_cons_rate(self, power_insight):
        # (1 - export_rate) * applicable_sc_share = (1 - 1/3) * 1.0 = 2/3
        assert power_insight.prod_adapters_self_cons_rates["pv_1"] == pytest.approx(2000 / 3000)

    def test_pv1_self_cons_share(self, power_insight):
        # (self_cons_rate * power_share) / self_cons_share
        # = (2/3 * 2/3) / (2/3) = 2/3
        assert power_insight.prod_adapters_self_cons_shares["pv_1"] == pytest.approx(2000 / 3000)

    def test_pv1_self_cons_power(self, power_insight):
        # production * self_cons_rate = 2000 * 2/3
        assert power_insight.prod_adapters_self_cons_power["pv_1"] == pytest.approx(
            2000 * (2000 / 3000)
        )

    def test_pv1_self_cons_saving_rate(self, power_insight):
        self_cons_power = 2000 * (2000 / 3000)
        assert power_insight.prod_adapters_self_cons_saving_rates["pv_1"] == pytest.approx(
            (self_cons_power / 1000) * self.GRID_PRICE
        )

    def test_pv1_coo_rate(self, power_insight):
        assert power_insight.prod_adapters_coo_rates["pv_1"] == pytest.approx(0.0)

    def test_pv1_saving_rate(self, power_insight):
        export_comp = (1000 * (2000 / 3000) / 1000) * self.PV1_EXPORT_COMP
        self_cons_savings = (2000 * (2000 / 3000) / 1000) * self.GRID_PRICE
        assert power_insight.prod_adapters_saving_rates["pv_1"] == pytest.approx(
            export_comp + self_cons_savings
        )

    def test_pv1_levelized_saving_rate(self, power_insight):
        export_comp = (1000 * (2000 / 3000) / 1000) * self.PV1_EXPORT_COMP
        self_cons_savings = (2000 * (2000 / 3000) / 1000) * self.GRID_PRICE
        lcoe_rate = (2000 / 1000) * self.PV1_LCOE
        assert power_insight.prod_adapters_levelized_saving_rates["pv_1"] == pytest.approx(
            export_comp + self_cons_savings - lcoe_rate
        )

    # -- PV_2 adapter --

    def test_pv2_total_power_share(self, power_insight):
        assert power_insight.prod_adapters_total_power_shares["pv_2"] == pytest.approx(1000 / 3000)

    def test_pv2_export_share(self, power_insight):
        # proportional to power among exporters: 1000 / (2000 + 1000) = 1/3
        assert power_insight.prod_adapters_export_shares["pv_2"] == pytest.approx(1000 / 3000)

    def test_pv2_export_rate(self, power_insight):
        # (1/3) * (1/3) / (1/3) = 1/3
        assert power_insight.prod_adapters_export_rates["pv_2"] == pytest.approx(1000 / 3000)

    def test_pv2_export_power(self, power_insight):
        # grid_export * pv2_export_share = 1000 * 1/3
        assert power_insight.prod_adapters_export_power["pv_2"] == pytest.approx(
            1000 * (1000 / 3000)
        )

    def test_pv2_export_compensation_rate(self, power_insight):
        export_power = 1000 * (1000 / 3000)
        assert power_insight.prod_adapters_export_compensation_rates["pv_2"] == pytest.approx(
            (export_power / 1000) * self.PV2_EXPORT_COMP
        )

    def test_pv2_self_cons_rate(self, power_insight):
        # (1 - 1/3) * 1.0 = 2/3
        assert power_insight.prod_adapters_self_cons_rates["pv_2"] == pytest.approx(2000 / 3000)

    def test_pv2_self_cons_share(self, power_insight):
        # (2/3 * 1/3) / (2/3) = 1/3
        assert power_insight.prod_adapters_self_cons_shares["pv_2"] == pytest.approx(1000 / 3000)

    def test_pv2_self_cons_power(self, power_insight):
        # production * self_cons_rate = 1000 * 2/3
        assert power_insight.prod_adapters_self_cons_power["pv_2"] == pytest.approx(
            1000 * (2000 / 3000)
        )

    def test_pv2_self_cons_saving_rate(self, power_insight):
        self_cons_power = 1000 * (2000 / 3000)
        assert power_insight.prod_adapters_self_cons_saving_rates["pv_2"] == pytest.approx(
            (self_cons_power / 1000) * self.GRID_PRICE
        )

    def test_pv2_coo_rate(self, power_insight):
        assert power_insight.prod_adapters_coo_rates["pv_2"] == pytest.approx(0.0)

    def test_pv2_saving_rate(self, power_insight):
        export_comp = (1000 * (1000 / 3000) / 1000) * self.PV2_EXPORT_COMP
        self_cons_savings = (1000 * (2000 / 3000) / 1000) * self.GRID_PRICE
        assert power_insight.prod_adapters_saving_rates["pv_2"] == pytest.approx(
            export_comp + self_cons_savings
        )

    def test_pv2_levelized_saving_rate(self, power_insight):
        export_comp = (1000 * (1000 / 3000) / 1000) * self.PV2_EXPORT_COMP
        self_cons_savings = (1000 * (2000 / 3000) / 1000) * self.GRID_PRICE
        lcoe_rate = (1000 / 1000) * self.PV2_LCOE
        assert power_insight.prod_adapters_levelized_saving_rates["pv_2"] == pytest.approx(
            export_comp + self_cons_savings - lcoe_rate
        )

    # -- Totals --

    def test_total_export_compensation_rate(self, power_insight):
        # Sum of both PV export compensations = (1000/1000) * 0.08 = 0.08
        assert power_insight.total_export_compensation_rate == pytest.approx(
            (1000 / 1000) * self.PV1_EXPORT_COMP
        )

    def test_total_self_cons_saving_rate(self, power_insight):
        # Both PVs self-consume 2000 W total
        assert power_insight.total_self_cons_saving_rate == pytest.approx(
            (2000 / 1000) * self.GRID_PRICE
        )

    def test_total_coo_rate(self, power_insight):
        assert power_insight.total_coo_rate == pytest.approx(0.0)

    def test_total_saving_rate(self, power_insight):
        export_comp = (1000 / 1000) * self.PV1_EXPORT_COMP
        self_cons_savings = (2000 / 1000) * self.GRID_PRICE
        assert power_insight.total_saving_rate == pytest.approx(
            export_comp + self_cons_savings
        )
