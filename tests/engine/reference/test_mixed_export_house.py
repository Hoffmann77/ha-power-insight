"""Reference case: Mixed export house."""

from __future__ import annotations

from tests.engine.reference.case import TODO, F, ReferenceCase, expect
from tests.engine.scenario_framework import Adapter, State, state, topology


class TestMixedExportHouse(ReferenceCase):
    """Every device class at once, with the export permissions deliberately
    unequal: one battery may feed the grid and the other may not. Nothing here
    is settled for the first time — this is the case that checks the rules of
    the lower rungs still hold when they all apply together.

    Decides:

    * A device that cannot export is excluded from the export mix, even while
      discharging.
    * Standby draw is routed through the provenance allocation, not by gross
      share.
    * Two dischargers with different levelized costs price the mix between
      them.
    """

    case_id = "mixed-export-house"
    title = "Mixed export house"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.pv("pv2", lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.battery("bat1", lcos=0.15, exports=True, export_comp=0.08),
            Adapter.battery("bat2", lcos=0.20, exports=False),
            Adapter.consumer("cons1"),
        )

    # ----------------------------------------------------------------------

    @state
    def export_non_exporting_battery(self):
        """bat2 discharges but may not feed the grid, so the export mix excludes
        it.
        """
        return State(
            grid=-600, pv1=800, pv2=0, bat1=200, bat2=200, cons1=-400, price=F(1, 4)
        )

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_export_non_exporting_battery_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_export_non_exporting_battery_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_export_non_exporting_battery_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_export_non_exporting_battery_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_export_non_exporting_battery_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_export_non_exporting_battery_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_export_non_exporting_battery_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_export_non_exporting_battery_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_export_non_exporting_battery_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_export_non_exporting_battery_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_export_non_exporting_battery_home_base_load_source_shares(self):
        return TODO

    @expect("sink_adapters_restriction_deficit")
    def test_export_non_exporting_battery_sink_adapters_restriction_deficit(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_export_non_exporting_battery_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_export_non_exporting_battery_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_export_non_exporting_battery_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_export_non_exporting_battery_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_export_non_exporting_battery_gross_power_applicable_consumption_ratio(
        self,
    ):
        return TODO

    @expect("source_adapters_export_power")
    def test_export_non_exporting_battery_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_export_non_exporting_battery_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_export_non_exporting_battery_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_export_non_exporting_battery_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_export_non_exporting_battery_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_export_non_exporting_battery_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_export_non_exporting_battery_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_export_non_exporting_battery_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_export_non_exporting_battery_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_export_non_exporting_battery_source_adapters_dynamic_lcoe(self):
        return TODO

    # ----------------------------------------------------------------------

    @state
    def export_with_standby(self):
        """pv2 in standby while the house exports; standby competes in the
        allocation.
        """
        return State(
            grid=-600, pv1=800, pv2=-50, bat1=200, bat2=200, cons1=-400, price=F(1, 4)
        )

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_export_with_standby_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_export_with_standby_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_export_with_standby_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_export_with_standby_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_export_with_standby_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_export_with_standby_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_export_with_standby_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_export_with_standby_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_export_with_standby_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_export_with_standby_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_export_with_standby_home_base_load_source_shares(self):
        return TODO

    @expect("sink_adapters_restriction_deficit")
    def test_export_with_standby_sink_adapters_restriction_deficit(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_export_with_standby_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_export_with_standby_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_export_with_standby_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_export_with_standby_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_export_with_standby_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_export_with_standby_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_export_with_standby_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_export_with_standby_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_export_with_standby_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_export_with_standby_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_export_with_standby_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_export_with_standby_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_export_with_standby_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_export_with_standby_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_export_with_standby_source_adapters_dynamic_lcoe(self):
        return TODO

    # ----------------------------------------------------------------------

    @state
    def discharge_dynamic_prices(self):
        """Both batteries discharging; the mix they charged on is in the past."""
        return State(
            grid=-300, pv1=0, pv2=-50, bat1=400, bat2=400, cons1=-400, price=F(1, 4)
        )

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_discharge_dynamic_prices_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_discharge_dynamic_prices_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_discharge_dynamic_prices_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_discharge_dynamic_prices_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_discharge_dynamic_prices_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_discharge_dynamic_prices_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_discharge_dynamic_prices_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_discharge_dynamic_prices_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_discharge_dynamic_prices_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_discharge_dynamic_prices_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_discharge_dynamic_prices_home_base_load_source_shares(self):
        return TODO

    @expect("sink_adapters_restriction_deficit")
    def test_discharge_dynamic_prices_sink_adapters_restriction_deficit(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_discharge_dynamic_prices_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_discharge_dynamic_prices_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_discharge_dynamic_prices_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_discharge_dynamic_prices_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_discharge_dynamic_prices_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_discharge_dynamic_prices_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_discharge_dynamic_prices_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_discharge_dynamic_prices_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_discharge_dynamic_prices_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_discharge_dynamic_prices_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_discharge_dynamic_prices_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_discharge_dynamic_prices_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_discharge_dynamic_prices_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_discharge_dynamic_prices_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_discharge_dynamic_prices_source_adapters_dynamic_lcoe(self):
        return TODO
