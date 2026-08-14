# -*- coding: utf-8 -*-
"""
Created on Tue Jul 21 01:52:01 2026

@author: Bobby
"""

from mock_power_insight import MockPowerInsight, Grid, Pv, Battery, Consumer


power_insight = MockPowerInsight(
    Grid(),
    Pv("pv_1", exports_power=True, export_compensation=0.08),
    Battery("bat_1", charge_from=["grid", "pv_1"]),
    Battery("bat_2", charge_from=["pv_1"]),
    Consumer("cons_1"),
)

power_insight.mock(
    grid=1500,
    pv_1=800,
    bat_1=-500,
    bat_2=-500,
    cons_1=-800,
    grid_price=0.30,
)


print(power_insight.combined_charging_power)
print(power_insight.prod_adapters_charging_shares_by_battery)

print(power_insight.storage_adapters_charging_source_shares)




# Pv power distribution order
# 1. Battery with only pv adapers or battery with pv adapters and grid with no import
# 2. Consumers
# 3. Battery with pv adapters and grid import


# @expect
# def outputs(self):
#     return {
#         "gross_power": 2000.0,
#         "combined_charging_power": 1000.0,
#         "storage_adapters_charging_source_shares": {
#             "bat_1": {"grid": 1.0, "pv_1": 0.0},
#             "bat_2": {"pv_1": 1.0},
#         },
#         "grid_adapters_charging_power": {"grid": 125.0},
#         "storage_adapters_dynamic_lcoe": {"bat1": 0.15},
#     }
