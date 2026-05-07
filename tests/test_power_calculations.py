"""Tests for PowerInsight core calculation logic.

Four scenarios of increasing complexity:
  1. Grid + PV  (excess production → exporting)
  2. Grid + PV + Battery  (all consumed, no export)
  3. Grid + PV + Battery + Consumer  (consumer cost allocation)
  4. Grid + PV_1 + PV_2  (multiple adapters of same class)

Each scenario class defines ENTITY_VALUES as a nested dict:

    ENTITY_VALUES = {
        "case_name": {"sensor.entity_id": value, ...},
        ...
    }

The ``entity_values`` fixture is parametrized over every key so that all
test methods run once per named case.  Test methods compute expected results
directly from ``entity_values`` — adding a new test case requires only a
single new entry in ENTITY_VALUES, no changes to test methods.
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

def build_power_insight(adapters, entity_values):
    """Create a PowerInsight instance, register adapters, and set entity values."""
    pi = PowerInsight()
    for adapter in adapters:
        pi.register_adapter(adapter)
    for entity_id, value in entity_values.items():
        pi.set_value(entity_id, value)
    return pi


def create_grid(unique_id, power_entity, price_entity):
    return GridAdapter(
        unique_id=unique_id,
        verbose_name=unique_id.upper(),
        power_entity=power_entity,
        price_entity=price_entity,
    )


def create_pv(unique_id, power_entity, lcoe, lco2_intensity, exports_power, export_compensation):
    return PvAdapter(
        unique_id=unique_id,
        verbose_name=unique_id.upper(),
        power_entity=power_entity,
        power_entity_inverted=False,
        lcoe=lcoe,
        lco2_intensity=lco2_intensity,
        exports_power=exports_power,
        export_compensation=export_compensation,
    )


def create_battery(unique_id, power_entity, lcos, lco2_intensity, exports_power, export_compensation):
    return BatteryAdapter(
        unique_id=unique_id,
        verbose_name=unique_id.upper(),
        power_entity=power_entity,
        power_entity_inverted=False,
        lcos=lcos,
        lco2_intensity=lco2_intensity,
        exports_power=exports_power,
        export_compensation=export_compensation,
    )


def create_consumer(unique_id, power_entity):
    return ConsumerAdapter(
        unique_id=unique_id,
        verbose_name=unique_id.upper(),
        power_entity=power_entity,
    )


# ===================================================================
# Scenario 1 — Grid + PV  (PV overproducing → exporting to grid)
# ===================================================================

class TestSinglePVwithExport:
    """Grid + PV with excess production (exporting)."""

    GRID_POWER_ENTITY = "sensor.grid_power"
    GRID_PRICE_ENTITY = "sensor.grid_price"
    PV_POWER_ENTITY = "sensor.pv_power"

    ENTITY_VALUES = {
        "import": {
            GRID_POWER_ENTITY: 1000.0, # import
            GRID_PRICE_ENTITY: 0.30,
            PV_POWER_ENTITY: 2000.0,
        },
        "export": {
            GRID_POWER_ENTITY: -2000.0,
            GRID_PRICE_ENTITY: 0.30,
            PV_POWER_ENTITY: 4000.0,
        },
        "net_zero": {
            GRID_POWER_ENTITY: -3000.0,
            GRID_PRICE_ENTITY: 0.30,
            PV_POWER_ENTITY: 3000.0,
        },
        "nighttime": {
            GRID_POWER_ENTITY: 500.0,
            GRID_PRICE_ENTITY: 0.30,
            PV_POWER_ENTITY: -50.0,
        },
    }

    ADAPTERS = (
        GridAdapter(
            unique_id="grid",
            verbose_name="Grid",
            power_entity=GRID_POWER_ENTITY,
            price_entity=GRID_PRICE_ENTITY,
        ),
        PvAdapter(
            unique_id="pv_system",
            verbose_name="PV-System",
            power_entity=PV_POWER_ENTITY,
            power_entity_inverted=False,
            lcoe=0.15,
            lco2_intensity=50.0,
            exports_power=True,
            export_compensation=0.08,
        ),
    )

    @pytest.fixture(params=list(ENTITY_VALUES))
    def entity_values(self, request):
        return self.ENTITY_VALUES[request.param]

    @pytest.fixture()
    def test_case(self, request):
        # entity_values is parameterized, so its param is accessible via the parent fixture's node
        return request.node.callspec.params["entity_values"]

    @pytest.fixture()
    def power_insight(self, entity_values):
        return build_power_insight(self.ADAPTERS, entity_values)

    # -- Common --

    def test_grid_import(self, power_insight, entity_values, test_case):
        results = {
            "import": 1000.0,
            "export": 0.0,
            "net_zero": 0.0,
            "nighttime": 500.0,
        }
        assert power_insight.combined_grid_import == results[test_case]

    def test_grid_export(self, power_insight, entity_values, test_case):
        results = {
            "import": 0.0,
            "export": 2000.0,
            "net_zero": 3000.0,
            "nighttime": 0.0,
        }

        assert power_insight.combined_grid_export == results[test_case]

    def test_production(self, power_insight, entity_values, test_case):

        results = {
            "import": 2000.0,
            "export": 4000.0,
            "net_zero": 3000.0,
            "nighttime": 0.0,
        }

        assert power_insight.combined_production == results[test_case]

    def test_utilization(self, power_insight, entity_values, test_case):
        results = {
            "import": 0.0,
            "export": 0.0,
            "net_zero": 0.0,
            "nighttime": 50.0,
        }

        assert power_insight.combined_standby_power == results[test_case]

    # def test_total_power(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     pv_power = entity_values[self.PV_ENTITY]
    #     assert power_insight.total_power == pytest.approx(grid_import + pv_power)

    # def test_self_consumption(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     pv_power = entity_values[self.PV_ENTITY]
    #     total_power = grid_import + pv_power
    #     assert power_insight.self_consumption == pytest.approx(total_power - grid_export)

    def test_export_ratio(self, power_insight, entity_values, test_case):
        results = {
            "import": 0.0,
            "export": 0.5,
            "net_zero": 1.0,
            "nighttime": 0.0,
        }

        assert power_insight.gross_power_export_ratio == results[test_case]

    # def test_utilization_share(self, power_insight, entity_values):
    #     assert power_insight.utilization_share == pytest.approx(0.0)

    # def test_self_consumption_share(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     pv_power = entity_values[self.PV_ENTITY]
    #     total_power = grid_import + pv_power
    #     self_consumption = total_power - grid_export
    #     assert power_insight.self_consumption_share == pytest.approx(
    #         self_consumption / total_power
    #     )

    # def test_applicable_utilization_share(self, power_insight, entity_values):
    #     assert power_insight.applicable_utilization_share == pytest.approx(0.0)

    # def test_applicable_self_consumption_share(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     pv_power = entity_values[self.PV_ENTITY]
    #     total_power = grid_import + pv_power
    #     sc = total_power - grid_export
    #     sc_share = sc / total_power
    #     export_share = grid_export / total_power
    #     applicable_sc = sc_share / (1 - export_share) if export_share < 1 else 0.0
    #     assert power_insight.applicable_self_consumption_share == pytest.approx(applicable_sc)

    # def test_coe_rate(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     grid_price = entity_values[self.GRID_PRICE_ENTITY]
    #     assert power_insight.coe_rate == pytest.approx((grid_import / 1000) * grid_price)

    # def test_coe(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     grid_price = entity_values[self.GRID_PRICE_ENTITY]
    #     pv_power = entity_values[self.PV_ENTITY]
    #     total_power = grid_import + pv_power
    #     coe_rate = (grid_import / 1000) * grid_price
    #     assert power_insight.coe == pytest.approx(coe_rate / (total_power / 1000))

    # def test_lcoe_rate(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     grid_price = entity_values[self.GRID_PRICE_ENTITY]
    #     pv_power = entity_values[self.PV_ENTITY]
    #     assert power_insight.lcoe_rate == pytest.approx(
    #         (grid_import / 1000) * grid_price + (pv_power / 1000) * self.PV_LCOE
    #     )

    # def test_lcoe(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     grid_price = entity_values[self.GRID_PRICE_ENTITY]
    #     pv_power = entity_values[self.PV_ENTITY]
    #     total_power = grid_import + pv_power
    #     lcoe_rate = (grid_import / 1000) * grid_price + (pv_power / 1000) * self.PV_LCOE
    #     assert power_insight.lcoe == pytest.approx(lcoe_rate / (total_power / 1000))

    # # -- Grid adapter --

    # def test_grid_total_power_share(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     pv_power = entity_values[self.PV_ENTITY]
    #     total_power = grid_import + pv_power
    #     assert power_insight.grid_adapter_total_power_shares["grid"] == pytest.approx(
    #         grid_import / total_power
    #     )

    # def test_grid_self_cons_rate(self, power_insight, entity_values):
    #     # Grid always self-consumes at the applicable_sc_share rate; in this
    #     # scenario (only PV exports, grid never imports and exports simultaneously)
    #     # that rate is always 1.0.
    #     assert power_insight.grid_adapter_self_cons_rates["grid"] == pytest.approx(1.0)

    # def test_grid_self_cons_share(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     pv_power = entity_values[self.PV_ENTITY]
    #     total_power = grid_import + pv_power
    #     self_consumption = total_power - grid_export
    #     # grid_self_cons_share = (1.0 * grid_import/total_power) / sc_share
    #     sc_share = self_consumption / total_power
    #     assert power_insight.grid_adapter_self_cons_shares["grid"] == pytest.approx(
    #         (grid_import / total_power) / sc_share if sc_share > 0 else 0.0
    #     )

    # # -- PV adapter --

    # def test_pv_total_power_share(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     pv_power = entity_values[self.PV_ENTITY]
    #     total_power = grid_import + pv_power
    #     assert power_insight.prod_adapters_total_power_shares["pv"] == pytest.approx(
    #         pv_power / total_power
    #     )

    # def test_pv_export_share(self, power_insight, entity_values):
    #     # PV is the only exporter → 100% of exports
    #     assert power_insight.prod_adapters_export_shares["pv"] == pytest.approx(1.0)

    # def test_pv_export_rate(self, power_insight, entity_values):
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     pv_power = entity_values[self.PV_ENTITY]
    #     assert power_insight.prod_adapters_export_rates["pv"] == pytest.approx(
    #         grid_export / pv_power
    #     )

    # def test_pv_export_power(self, power_insight, entity_values):
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     assert power_insight.prod_adapters_export_power["pv"] == pytest.approx(grid_export)

    # def test_pv_export_compensation_rate(self, power_insight, entity_values):
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     assert power_insight.prod_adapters_export_compensation_rates["pv"] == pytest.approx(
    #         (grid_export / 1000) * self.PV_EXPORT_COMP
    #     )

    # def test_pv_self_cons_rate(self, power_insight, entity_values):
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     pv_power = entity_values[self.PV_ENTITY]
    #     assert power_insight.prod_adapters_self_cons_rates["pv"] == pytest.approx(
    #         (pv_power - grid_export) / pv_power
    #     )

    # def test_pv_self_cons_share(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     pv_power = entity_values[self.PV_ENTITY]
    #     total_power = grid_import + pv_power
    #     self_consumption = total_power - grid_export
    #     pv_self_cons_power = pv_power - grid_export
    #     assert power_insight.prod_adapters_self_cons_shares["pv"] == pytest.approx(
    #         pv_self_cons_power / self_consumption
    #     )

    # def test_pv_self_cons_power(self, power_insight, entity_values):
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     pv_power = entity_values[self.PV_ENTITY]
    #     assert power_insight.prod_adapters_self_cons_power["pv"] == pytest.approx(
    #         pv_power - grid_export
    #     )

    # def test_pv_self_cons_saving_rate(self, power_insight, entity_values):
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     grid_price = entity_values[self.GRID_PRICE_ENTITY]
    #     pv_power = entity_values[self.PV_ENTITY]
    #     pv_self_cons_power = pv_power - grid_export
    #     assert power_insight.prod_adapters_self_cons_saving_rates["pv"] == pytest.approx(
    #         (pv_self_cons_power / 1000) * grid_price
    #     )

    # def test_pv_coo_rate(self, power_insight, entity_values):
    #     assert power_insight.prod_adapters_coo_rates["pv"] == pytest.approx(0.0)

    # def test_pv_lcoo_rate(self, power_insight, entity_values):
    #     assert power_insight.prod_adapters_lcoo_rates["pv"] == pytest.approx(0.0)

    # def test_pv_saving_rate(self, power_insight, entity_values):
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     grid_price = entity_values[self.GRID_PRICE_ENTITY]
    #     pv_power = entity_values[self.PV_ENTITY]
    #     export_comp = (grid_export / 1000) * self.PV_EXPORT_COMP
    #     self_cons_savings = ((pv_power - grid_export) / 1000) * grid_price
    #     assert power_insight.prod_adapters_saving_rates["pv"] == pytest.approx(
    #         export_comp + self_cons_savings
    #     )

    # def test_pv_levelized_saving_rate(self, power_insight, entity_values):
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     grid_price = entity_values[self.GRID_PRICE_ENTITY]
    #     pv_power = entity_values[self.PV_ENTITY]
    #     export_comp = (grid_export / 1000) * self.PV_EXPORT_COMP
    #     self_cons_savings = ((pv_power - grid_export) / 1000) * grid_price
    #     lcoe_rate = (pv_power / 1000) * self.PV_LCOE
    #     assert power_insight.prod_adapters_levelized_saving_rates["pv"] == pytest.approx(
    #         export_comp + self_cons_savings - lcoe_rate
    #     )

    # # -- Totals --

    # def test_total_export_compensation_rate(self, power_insight, entity_values):
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     assert power_insight.total_export_compensation_rate == pytest.approx(
    #         (grid_export / 1000) * self.PV_EXPORT_COMP
    #     )

    # def test_total_self_cons_saving_rate(self, power_insight, entity_values):
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     grid_price = entity_values[self.GRID_PRICE_ENTITY]
    #     pv_power = entity_values[self.PV_ENTITY]
    #     assert power_insight.total_self_cons_saving_rate == pytest.approx(
    #         ((pv_power - grid_export) / 1000) * grid_price
    #     )

    # def test_total_coo_rate(self, power_insight, entity_values):
    #     assert power_insight.total_coo_rate == pytest.approx(0.0)

    # def test_total_saving_rate(self, power_insight, entity_values):
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     grid_price = entity_values[self.GRID_PRICE_ENTITY]
    #     pv_power = entity_values[self.PV_ENTITY]
    #     export_comp = (grid_export / 1000) * self.PV_EXPORT_COMP
    #     self_cons_savings = ((pv_power - grid_export) / 1000) * grid_price
    #     assert power_insight.total_saving_rate == pytest.approx(
    #         export_comp + self_cons_savings
    #     )


# # ===================================================================
# # Scenario 2 — Grid + PV + Battery  (all consumed, no export)
# # ===================================================================

# class TestScenario2GridPvBattery:
#     """Grid + PV + Battery, all power consumed (no export)."""

#     GRID_ENTITY = "sensor.grid_power"
#     GRID_PRICE_ENTITY = "sensor.grid_price"
#     PV_ENTITY = "sensor.pv_power"
#     BAT_ENTITY = "sensor.bat_power"

#     PV_LCOE = 0.08
#     PV_EXPORT_COMP = 0.08
#     BAT_LCOS = 0.12

#     ENTITY_VALUES = {
#         "default": {
#             "sensor.grid_power":  500,
#             "sensor.grid_price":  0.30,
#             "sensor.pv_power":   2000,
#             "sensor.bat_power":  1000,
#         },
#     }

#     @pytest.fixture(params=list(ENTITY_VALUES))
#     def entity_values(self, request):
#         return self.ENTITY_VALUES[request.param]

#     @pytest.fixture()
#     def power_insight(self, entity_values):
#         return build_power_insight(
#             [
#                 create_grid("grid", self.GRID_ENTITY, self.GRID_PRICE_ENTITY),
#                 create_pv("pv", self.PV_ENTITY, self.PV_LCOE, 0.0, True, self.PV_EXPORT_COMP),
#                 create_battery("bat", self.BAT_ENTITY, self.BAT_LCOS, 0.0, False, 0.0),
#             ],
#             entity_values,
#         )

#     # -- Common --

#     def test_grid_import(self, power_insight, entity_values):
#         assert power_insight.grid_import == pytest.approx(
#             max(entity_values[self.GRID_ENTITY], 0)
#         )

#     def test_grid_export(self, power_insight, entity_values):
#         assert power_insight.grid_export == pytest.approx(
#             max(-entity_values[self.GRID_ENTITY], 0)
#         )

#     def test_production(self, power_insight, entity_values):
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         assert power_insight.production == pytest.approx(pv_power + bat_power)

#     def test_utilization(self, power_insight, entity_values):
#         assert power_insight.utilization == pytest.approx(0.0)

#     def test_total_power(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         assert power_insight.total_power == pytest.approx(grid_import + pv_power + bat_power)

#     def test_self_consumption(self, power_insight, entity_values):
#         # no export → self_consumption = total_power
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         assert power_insight.self_consumption == pytest.approx(
#             grid_import + pv_power + bat_power
#         )

#     def test_export_share(self, power_insight, entity_values):
#         assert power_insight.export_share == pytest.approx(0.0)

#     def test_self_consumption_share(self, power_insight, entity_values):
#         assert power_insight.self_consumption_share == pytest.approx(1.0)

#     def test_applicable_self_consumption_share(self, power_insight, entity_values):
#         assert power_insight.applicable_self_consumption_share == pytest.approx(1.0)

#     def test_coe_rate(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         assert power_insight.coe_rate == pytest.approx((grid_import / 1000) * grid_price)

#     def test_coe(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         coe_rate = (grid_import / 1000) * grid_price
#         assert power_insight.coe == pytest.approx(coe_rate / (total_power / 1000))

#     def test_lcoe_rate(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         assert power_insight.lcoe_rate == pytest.approx(
#             (grid_import / 1000) * grid_price
#             + (pv_power / 1000) * self.PV_LCOE
#             + (bat_power / 1000) * self.BAT_LCOS
#         )

#     def test_lcoe(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         lcoe_rate = (
#             (grid_import / 1000) * grid_price
#             + (pv_power / 1000) * self.PV_LCOE
#             + (bat_power / 1000) * self.BAT_LCOS
#         )
#         assert power_insight.lcoe == pytest.approx(lcoe_rate / (total_power / 1000))

#     # -- Grid adapter --

#     def test_grid_total_power_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         assert power_insight.grid_adapter_total_power_shares["grid"] == pytest.approx(
#             grid_import / total_power
#         )

#     def test_grid_self_cons_rate(self, power_insight, entity_values):
#         assert power_insight.grid_adapter_self_cons_rates["grid"] == pytest.approx(1.0)

#     def test_grid_self_cons_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         # sc_share = 1.0 (no export) → grid_self_cons_share = grid_import / total_power
#         assert power_insight.grid_adapter_self_cons_shares["grid"] == pytest.approx(
#             grid_import / total_power
#         )

#     # -- PV adapter --

#     def test_pv_total_power_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         assert power_insight.prod_adapters_total_power_shares["pv"] == pytest.approx(
#             pv_power / total_power
#         )

#     def test_pv_export_share(self, power_insight, entity_values):
#         # PV is the only exporter (exports_power=True) but actual export = 0
#         assert power_insight.prod_adapters_export_shares["pv"] == pytest.approx(1.0)

#     def test_pv_export_rate(self, power_insight, entity_values):
#         assert power_insight.prod_adapters_export_rates["pv"] == pytest.approx(0.0)

#     def test_pv_export_power(self, power_insight, entity_values):
#         assert power_insight.prod_adapters_export_power["pv"] == pytest.approx(0.0)

#     def test_pv_export_compensation_rate(self, power_insight, entity_values):
#         assert power_insight.prod_adapters_export_compensation_rates["pv"] == pytest.approx(0.0)

#     def test_pv_self_cons_rate(self, power_insight, entity_values):
#         # (1 - export_rate=0) * applicable_sc_share=1.0 = 1.0
#         assert power_insight.prod_adapters_self_cons_rates["pv"] == pytest.approx(1.0)

#     def test_pv_self_cons_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         assert power_insight.prod_adapters_self_cons_shares["pv"] == pytest.approx(
#             pv_power / total_power
#         )

#     def test_pv_self_cons_power(self, power_insight, entity_values):
#         assert power_insight.prod_adapters_self_cons_power["pv"] == pytest.approx(
#             entity_values[self.PV_ENTITY]
#         )

#     def test_pv_self_cons_saving_rate(self, power_insight, entity_values):
#         pv_power = entity_values[self.PV_ENTITY]
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         assert power_insight.prod_adapters_self_cons_saving_rates["pv"] == pytest.approx(
#             (pv_power / 1000) * grid_price
#         )

#     def test_pv_coo_rate(self, power_insight, entity_values):
#         assert power_insight.prod_adapters_coo_rates["pv"] == pytest.approx(0.0)

#     def test_pv_saving_rate(self, power_insight, entity_values):
#         pv_power = entity_values[self.PV_ENTITY]
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         assert power_insight.prod_adapters_saving_rates["pv"] == pytest.approx(
#             (pv_power / 1000) * grid_price
#         )

#     def test_pv_levelized_saving_rate(self, power_insight, entity_values):
#         pv_power = entity_values[self.PV_ENTITY]
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         assert power_insight.prod_adapters_levelized_saving_rates["pv"] == pytest.approx(
#             (pv_power / 1000) * grid_price - (pv_power / 1000) * self.PV_LCOE
#         )

#     # -- Battery adapter --

#     def test_bat_total_power_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         assert power_insight.prod_adapters_total_power_shares["bat"] == pytest.approx(
#             bat_power / total_power
#         )

#     def test_bat_export_share(self, power_insight, entity_values):
#         # battery has exports_power=False → 0%
#         assert power_insight.prod_adapters_export_shares["bat"] == pytest.approx(0.0)

#     def test_bat_export_rate(self, power_insight, entity_values):
#         assert power_insight.prod_adapters_export_rates["bat"] == pytest.approx(0.0)

#     def test_bat_export_power(self, power_insight, entity_values):
#         assert power_insight.prod_adapters_export_power["bat"] == pytest.approx(0.0)

#     def test_bat_export_compensation_rate(self, power_insight, entity_values):
#         assert power_insight.prod_adapters_export_compensation_rates["bat"] == pytest.approx(0.0)

#     def test_bat_self_cons_rate(self, power_insight, entity_values):
#         assert power_insight.prod_adapters_self_cons_rates["bat"] == pytest.approx(1.0)

#     def test_bat_self_cons_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         assert power_insight.prod_adapters_self_cons_shares["bat"] == pytest.approx(
#             bat_power / total_power
#         )

#     def test_bat_self_cons_power(self, power_insight, entity_values):
#         assert power_insight.prod_adapters_self_cons_power["bat"] == pytest.approx(
#             entity_values[self.BAT_ENTITY]
#         )

#     def test_bat_self_cons_saving_rate(self, power_insight, entity_values):
#         bat_power = entity_values[self.BAT_ENTITY]
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         assert power_insight.prod_adapters_self_cons_saving_rates["bat"] == pytest.approx(
#             (bat_power / 1000) * grid_price
#         )

#     def test_bat_coo_rate(self, power_insight, entity_values):
#         assert power_insight.prod_adapters_coo_rates["bat"] == pytest.approx(0.0)

#     def test_bat_saving_rate(self, power_insight, entity_values):
#         bat_power = entity_values[self.BAT_ENTITY]
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         assert power_insight.prod_adapters_saving_rates["bat"] == pytest.approx(
#             (bat_power / 1000) * grid_price
#         )

#     def test_bat_levelized_saving_rate(self, power_insight, entity_values):
#         bat_power = entity_values[self.BAT_ENTITY]
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         assert power_insight.prod_adapters_levelized_saving_rates["bat"] == pytest.approx(
#             (bat_power / 1000) * grid_price - (bat_power / 1000) * self.BAT_LCOS
#         )

#     # -- Totals --

#     def test_total_export_compensation_rate(self, power_insight, entity_values):
#         assert power_insight.total_export_compensation_rate == pytest.approx(0.0)

#     def test_total_self_cons_saving_rate(self, power_insight, entity_values):
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         assert power_insight.total_self_cons_saving_rate == pytest.approx(
#             (pv_power / 1000) * grid_price + (bat_power / 1000) * grid_price
#         )

#     def test_total_coo_rate(self, power_insight, entity_values):
#         assert power_insight.total_coo_rate == pytest.approx(0.0)

#     def test_total_lcoo_rate(self, power_insight, entity_values):
#         assert power_insight.total_lcoo_rate == pytest.approx(0.0)

#     def test_total_saving_rate(self, power_insight, entity_values):
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         assert power_insight.total_saving_rate == pytest.approx(
#             (pv_power / 1000) * grid_price + (bat_power / 1000) * grid_price
#         )

#     def test_total_levelized_saving_rate(self, power_insight, entity_values):
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv_saving = (pv_power / 1000) * grid_price - (pv_power / 1000) * self.PV_LCOE
#         bat_saving = (bat_power / 1000) * grid_price - (bat_power / 1000) * self.BAT_LCOS
#         assert power_insight.total_levelized_saving_rate == pytest.approx(
#             pv_saving + bat_saving
#         )


# # ===================================================================
# # Scenario 3 — Grid + PV + Battery + Consumer
# # ===================================================================

# class TestScenario3GridPvBatteryConsumer:
#     """Grid + PV + Battery + Consumer."""

#     GRID_ENTITY = "sensor.grid_power"
#     GRID_PRICE_ENTITY = "sensor.grid_price"
#     PV_ENTITY = "sensor.pv_power"
#     BAT_ENTITY = "sensor.bat_power"
#     CONS_ENTITY = "sensor.consumer_power"

#     PV_LCOE = 0.08
#     PV_EXPORT_COMP = 0.08
#     BAT_LCOS = 0.12

#     ENTITY_VALUES = {
#         "default": {
#             "sensor.grid_power":      500,
#             "sensor.grid_price":      0.30,
#             "sensor.pv_power":       2000,
#             "sensor.bat_power":      1000,
#             "sensor.consumer_power": -800,
#         },
#     }

#     @pytest.fixture(params=list(ENTITY_VALUES))
#     def entity_values(self, request):
#         return self.ENTITY_VALUES[request.param]

#     @pytest.fixture()
#     def power_insight(self, entity_values):
#         return build_power_insight(
#             [
#                 create_grid("grid", self.GRID_ENTITY, self.GRID_PRICE_ENTITY),
#                 create_pv("pv", self.PV_ENTITY, self.PV_LCOE, 0.0, True, self.PV_EXPORT_COMP),
#                 create_battery("bat", self.BAT_ENTITY, self.BAT_LCOS, 0.0, False, 0.0),
#                 create_consumer("cons", self.CONS_ENTITY),
#             ],
#             entity_values,
#         )

#     # -- Common (power flows unchanged by consumer) --

#     def test_total_power(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         assert power_insight.total_power == pytest.approx(grid_import + pv_power + bat_power)

#     def test_self_consumption(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         assert power_insight.self_consumption == pytest.approx(
#             grid_import + pv_power + bat_power
#         )

#     # -- Consumer adapter --

#     def test_cons_total_power_share(self, power_insight, entity_values):
#         cons_power = abs(entity_values[self.CONS_ENTITY])
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         assert power_insight.cons_adapter_total_power_shares["cons"] == pytest.approx(
#             cons_power / total_power
#         )

#     def test_cons_self_cons_share(self, power_insight, entity_values):
#         cons_power = abs(entity_values[self.CONS_ENTITY])
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         # sc_share = 1.0 (no export) → cons_self_cons_share = cons_power / total_power
#         assert power_insight.cons_adapters_self_cons_share["cons"] == pytest.approx(
#             cons_power / total_power
#         )

#     def test_cons_source_share_grid(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         assert power_insight.cons_adapters_source_shares["cons"]["grid"] == pytest.approx(
#             grid_import / total_power
#         )

#     def test_cons_source_share_pv(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         assert power_insight.cons_adapters_source_shares["cons"]["pv"] == pytest.approx(
#             pv_power / total_power
#         )

#     def test_cons_source_share_bat(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         assert power_insight.cons_adapters_source_shares["cons"]["bat"] == pytest.approx(
#             bat_power / total_power
#         )

#     def test_cons_coo_rate(self, power_insight, entity_values):
#         cons_power = abs(entity_values[self.CONS_ENTITY])
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         coe_rate = (grid_import / 1000) * grid_price
#         coe = coe_rate / (total_power / 1000)
#         assert power_insight.cons_adapters_coo_rates["cons"] == pytest.approx(
#             (cons_power / 1000) * coe
#         )

#     def test_cons_lcoo_rate(self, power_insight, entity_values):
#         cons_power = abs(entity_values[self.CONS_ENTITY])
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv_power = entity_values[self.PV_ENTITY]
#         bat_power = entity_values[self.BAT_ENTITY]
#         total_power = grid_import + pv_power + bat_power
#         lcoe_rate = (
#             (grid_import / 1000) * grid_price
#             + (pv_power / 1000) * self.PV_LCOE
#             + (bat_power / 1000) * self.BAT_LCOS
#         )
#         lcoe = lcoe_rate / (total_power / 1000)
#         assert power_insight.cons_adapters_lcoo_rates["cons"] == pytest.approx(
#             (cons_power / 1000) * lcoe
#         )

#     # -- Production adapters (verify unchanged by consumer) --

#     def test_pv_saving_rate_unchanged(self, power_insight, entity_values):
#         pv_power = entity_values[self.PV_ENTITY]
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         assert power_insight.prod_adapters_saving_rates["pv"] == pytest.approx(
#             (pv_power / 1000) * grid_price
#         )

#     def test_bat_saving_rate_unchanged(self, power_insight, entity_values):
#         bat_power = entity_values[self.BAT_ENTITY]
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         assert power_insight.prod_adapters_saving_rates["bat"] == pytest.approx(
#             (bat_power / 1000) * grid_price
#         )


# # ===================================================================
# # Scenario 4 — Grid + PV_1 + PV_2  (multiple adapters of same class)
# # ===================================================================

# class TestScenario4GridPv1Pv2:
#     """Grid + two PV adapters; export is split proportionally."""

#     GRID_ENTITY = "sensor.grid_power"
#     GRID_PRICE_ENTITY = "sensor.grid_price"
#     PV1_ENTITY = "sensor.pv1_power"
#     PV2_ENTITY = "sensor.pv2_power"

#     PV1_LCOE = 0.08
#     PV1_EXPORT_COMP = 0.08
#     PV2_LCOE = 0.10
#     PV2_EXPORT_COMP = 0.08

#     ENTITY_VALUES = {
#         "default": {
#             "sensor.grid_power": -1000,
#             "sensor.grid_price":  0.30,
#             "sensor.pv1_power":  2000,
#             "sensor.pv2_power":  1000,
#         },
#     }

#     @pytest.fixture(params=list(ENTITY_VALUES))
#     def entity_values(self, request):
#         return self.ENTITY_VALUES[request.param]

#     @pytest.fixture()
#     def power_insight(self, entity_values):
#         return build_power_insight(
#             [
#                 create_grid("grid", self.GRID_ENTITY, self.GRID_PRICE_ENTITY),
#                 create_pv("pv_1", self.PV1_ENTITY, self.PV1_LCOE, 0.0, True, self.PV1_EXPORT_COMP),
#                 create_pv("pv_2", self.PV2_ENTITY, self.PV2_LCOE, 0.0, True, self.PV2_EXPORT_COMP),
#             ],
#             entity_values,
#         )

#     # -- Common --

#     def test_grid_import(self, power_insight, entity_values):
#         assert power_insight.grid_import == pytest.approx(
#             max(entity_values[self.GRID_ENTITY], 0)
#         )

#     def test_grid_export(self, power_insight, entity_values):
#         assert power_insight.grid_export == pytest.approx(
#             max(-entity_values[self.GRID_ENTITY], 0)
#         )

#     def test_production(self, power_insight, entity_values):
#         assert power_insight.production == pytest.approx(
#             entity_values[self.PV1_ENTITY] + entity_values[self.PV2_ENTITY]
#         )

#     def test_utilization(self, power_insight, entity_values):
#         assert power_insight.utilization == pytest.approx(0.0)

#     def test_total_power(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         assert power_insight.total_power == pytest.approx(grid_import + pv1 + pv2)

#     def test_self_consumption(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         total_power = grid_import + pv1 + pv2
#         assert power_insight.self_consumption == pytest.approx(total_power - grid_export)

#     def test_export_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         total_power = grid_import + pv1 + pv2
#         assert power_insight.export_share == pytest.approx(grid_export / total_power)

#     def test_self_consumption_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         total_power = grid_import + pv1 + pv2
#         sc = total_power - grid_export
#         assert power_insight.self_consumption_share == pytest.approx(sc / total_power)

#     def test_applicable_self_consumption_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         total_power = grid_import + pv1 + pv2
#         sc = total_power - grid_export
#         sc_share = sc / total_power
#         export_share = grid_export / total_power
#         applicable_sc = sc_share / (1 - export_share) if export_share < 1 else 0.0
#         assert power_insight.applicable_self_consumption_share == pytest.approx(applicable_sc)

#     def test_coe_rate(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         assert power_insight.coe_rate == pytest.approx((grid_import / 1000) * grid_price)

#     def test_coe(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         total_power = grid_import + pv1 + pv2
#         coe_rate = (grid_import / 1000) * grid_price
#         assert power_insight.coe == pytest.approx(coe_rate / (total_power / 1000))

#     def test_lcoe_rate(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         assert power_insight.lcoe_rate == pytest.approx(
#             (grid_import / 1000) * grid_price
#             + (pv1 / 1000) * self.PV1_LCOE
#             + (pv2 / 1000) * self.PV2_LCOE
#         )

#     def test_lcoe(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         total_power = grid_import + pv1 + pv2
#         lcoe_rate = (
#             (grid_import / 1000) * grid_price
#             + (pv1 / 1000) * self.PV1_LCOE
#             + (pv2 / 1000) * self.PV2_LCOE
#         )
#         assert power_insight.lcoe == pytest.approx(lcoe_rate / (total_power / 1000))

#     # -- Grid adapter --

#     def test_grid_total_power_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         total_power = grid_import + pv1 + pv2
#         assert power_insight.grid_adapter_total_power_shares["grid"] == pytest.approx(
#             grid_import / total_power
#         )

#     def test_grid_self_cons_rate(self, power_insight, entity_values):
#         assert power_insight.grid_adapter_self_cons_rates["grid"] == pytest.approx(1.0)

#     def test_grid_self_cons_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         total_power = grid_import + pv1 + pv2
#         self_consumption = total_power - grid_export
#         sc_share = self_consumption / total_power
#         assert power_insight.grid_adapter_self_cons_shares["grid"] == pytest.approx(
#             (grid_import / total_power) / sc_share if sc_share > 0 else 0.0
#         )

#     # -- PV_1 adapter --

#     def test_pv1_total_power_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         total_power = grid_import + pv1 + pv2
#         assert power_insight.prod_adapters_total_power_shares["pv_1"] == pytest.approx(
#             pv1 / total_power
#         )

#     def test_pv1_export_share(self, power_insight, entity_values):
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         assert power_insight.prod_adapters_export_shares["pv_1"] == pytest.approx(
#             pv1 / (pv1 + pv2)
#         )

#     def test_pv1_export_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv1_export_power = grid_export * (pv1 / (pv1 + pv2))
#         assert power_insight.prod_adapters_export_rates["pv_1"] == pytest.approx(
#             pv1_export_power / pv1
#         )

#     def test_pv1_export_power(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         assert power_insight.prod_adapters_export_power["pv_1"] == pytest.approx(
#             grid_export * (pv1 / (pv1 + pv2))
#         )

#     def test_pv1_export_compensation_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv1_export_power = grid_export * (pv1 / (pv1 + pv2))
#         assert power_insight.prod_adapters_export_compensation_rates["pv_1"] == pytest.approx(
#             (pv1_export_power / 1000) * self.PV1_EXPORT_COMP
#         )

#     def test_pv1_self_cons_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv1_export_power = grid_export * (pv1 / (pv1 + pv2))
#         assert power_insight.prod_adapters_self_cons_rates["pv_1"] == pytest.approx(
#             (pv1 - pv1_export_power) / pv1
#         )

#     def test_pv1_self_cons_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         total_power = grid_import + pv1 + pv2
#         self_consumption = total_power - grid_export
#         pv1_export_power = grid_export * (pv1 / (pv1 + pv2))
#         pv1_self_cons_power = pv1 - pv1_export_power
#         assert power_insight.prod_adapters_self_cons_shares["pv_1"] == pytest.approx(
#             pv1_self_cons_power / self_consumption
#         )

#     def test_pv1_self_cons_power(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv1_export_power = grid_export * (pv1 / (pv1 + pv2))
#         assert power_insight.prod_adapters_self_cons_power["pv_1"] == pytest.approx(
#             pv1 - pv1_export_power
#         )

#     def test_pv1_self_cons_saving_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv1_self_cons_power = pv1 - grid_export * (pv1 / (pv1 + pv2))
#         assert power_insight.prod_adapters_self_cons_saving_rates["pv_1"] == pytest.approx(
#             (pv1_self_cons_power / 1000) * grid_price
#         )

#     def test_pv1_coo_rate(self, power_insight, entity_values):
#         assert power_insight.prod_adapters_coo_rates["pv_1"] == pytest.approx(0.0)

#     def test_pv1_saving_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv1_export_power = grid_export * (pv1 / (pv1 + pv2))
#         pv1_self_cons_power = pv1 - pv1_export_power
#         export_comp = (pv1_export_power / 1000) * self.PV1_EXPORT_COMP
#         self_cons_savings = (pv1_self_cons_power / 1000) * grid_price
#         assert power_insight.prod_adapters_saving_rates["pv_1"] == pytest.approx(
#             export_comp + self_cons_savings
#         )

#     def test_pv1_levelized_saving_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv1_export_power = grid_export * (pv1 / (pv1 + pv2))
#         pv1_self_cons_power = pv1 - pv1_export_power
#         export_comp = (pv1_export_power / 1000) * self.PV1_EXPORT_COMP
#         self_cons_savings = (pv1_self_cons_power / 1000) * grid_price
#         lcoe_rate = (pv1 / 1000) * self.PV1_LCOE
#         assert power_insight.prod_adapters_levelized_saving_rates["pv_1"] == pytest.approx(
#             export_comp + self_cons_savings - lcoe_rate
#         )

#     # -- PV_2 adapter --

#     def test_pv2_total_power_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         total_power = grid_import + pv1 + pv2
#         assert power_insight.prod_adapters_total_power_shares["pv_2"] == pytest.approx(
#             pv2 / total_power
#         )

#     def test_pv2_export_share(self, power_insight, entity_values):
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         assert power_insight.prod_adapters_export_shares["pv_2"] == pytest.approx(
#             pv2 / (pv1 + pv2)
#         )

#     def test_pv2_export_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv2_export_power = grid_export * (pv2 / (pv1 + pv2))
#         assert power_insight.prod_adapters_export_rates["pv_2"] == pytest.approx(
#             pv2_export_power / pv2
#         )

#     def test_pv2_export_power(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         assert power_insight.prod_adapters_export_power["pv_2"] == pytest.approx(
#             grid_export * (pv2 / (pv1 + pv2))
#         )

#     def test_pv2_export_compensation_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv2_export_power = grid_export * (pv2 / (pv1 + pv2))
#         assert power_insight.prod_adapters_export_compensation_rates["pv_2"] == pytest.approx(
#             (pv2_export_power / 1000) * self.PV2_EXPORT_COMP
#         )

#     def test_pv2_self_cons_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv2_export_power = grid_export * (pv2 / (pv1 + pv2))
#         assert power_insight.prod_adapters_self_cons_rates["pv_2"] == pytest.approx(
#             (pv2 - pv2_export_power) / pv2
#         )

#     def test_pv2_self_cons_share(self, power_insight, entity_values):
#         grid_import = max(entity_values[self.GRID_ENTITY], 0)
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         total_power = grid_import + pv1 + pv2
#         self_consumption = total_power - grid_export
#         pv2_export_power = grid_export * (pv2 / (pv1 + pv2))
#         pv2_self_cons_power = pv2 - pv2_export_power
#         assert power_insight.prod_adapters_self_cons_shares["pv_2"] == pytest.approx(
#             pv2_self_cons_power / self_consumption
#         )

#     def test_pv2_self_cons_power(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv2_export_power = grid_export * (pv2 / (pv1 + pv2))
#         assert power_insight.prod_adapters_self_cons_power["pv_2"] == pytest.approx(
#             pv2 - pv2_export_power
#         )

#     def test_pv2_self_cons_saving_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv2_self_cons_power = pv2 - grid_export * (pv2 / (pv1 + pv2))
#         assert power_insight.prod_adapters_self_cons_saving_rates["pv_2"] == pytest.approx(
#             (pv2_self_cons_power / 1000) * grid_price
#         )

#     def test_pv2_coo_rate(self, power_insight, entity_values):
#         assert power_insight.prod_adapters_coo_rates["pv_2"] == pytest.approx(0.0)

#     def test_pv2_saving_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv2_export_power = grid_export * (pv2 / (pv1 + pv2))
#         pv2_self_cons_power = pv2 - pv2_export_power
#         export_comp = (pv2_export_power / 1000) * self.PV2_EXPORT_COMP
#         self_cons_savings = (pv2_self_cons_power / 1000) * grid_price
#         assert power_insight.prod_adapters_saving_rates["pv_2"] == pytest.approx(
#             export_comp + self_cons_savings
#         )

#     def test_pv2_levelized_saving_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv2_export_power = grid_export * (pv2 / (pv1 + pv2))
#         pv2_self_cons_power = pv2 - pv2_export_power
#         export_comp = (pv2_export_power / 1000) * self.PV2_EXPORT_COMP
#         self_cons_savings = (pv2_self_cons_power / 1000) * grid_price
#         lcoe_rate = (pv2 / 1000) * self.PV2_LCOE
#         assert power_insight.prod_adapters_levelized_saving_rates["pv_2"] == pytest.approx(
#             export_comp + self_cons_savings - lcoe_rate
#         )

#     # -- Totals --

#     def test_total_export_compensation_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv1_export_power = grid_export * (pv1 / (pv1 + pv2))
#         pv2_export_power = grid_export * (pv2 / (pv1 + pv2))
#         assert power_insight.total_export_compensation_rate == pytest.approx(
#             (pv1_export_power / 1000) * self.PV1_EXPORT_COMP
#             + (pv2_export_power / 1000) * self.PV2_EXPORT_COMP
#         )

#     def test_total_self_cons_saving_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv1_self_cons = pv1 - grid_export * (pv1 / (pv1 + pv2))
#         pv2_self_cons = pv2 - grid_export * (pv2 / (pv1 + pv2))
#         assert power_insight.total_self_cons_saving_rate == pytest.approx(
#             ((pv1_self_cons + pv2_self_cons) / 1000) * grid_price
#         )

#     def test_total_coo_rate(self, power_insight, entity_values):
#         assert power_insight.total_coo_rate == pytest.approx(0.0)

#     def test_total_saving_rate(self, power_insight, entity_values):
#         grid_export = max(-entity_values[self.GRID_ENTITY], 0)
#         grid_price = entity_values[self.GRID_PRICE_ENTITY]
#         pv1 = entity_values[self.PV1_ENTITY]
#         pv2 = entity_values[self.PV2_ENTITY]
#         pv1_export_power = grid_export * (pv1 / (pv1 + pv2))
#         pv2_export_power = grid_export * (pv2 / (pv1 + pv2))
#         pv1_self_cons = pv1 - pv1_export_power
#         pv2_self_cons = pv2 - pv2_export_power
#         export_comp = (
#             (pv1_export_power / 1000) * self.PV1_EXPORT_COMP
#             + (pv2_export_power / 1000) * self.PV2_EXPORT_COMP
#         )
#         self_cons_savings = ((pv1_self_cons + pv2_self_cons) / 1000) * grid_price
#         assert power_insight.total_saving_rate == pytest.approx(
#             export_comp + self_cons_savings
#         )
