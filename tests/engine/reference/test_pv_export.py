"""Reference case: PV export."""

from __future__ import annotations

from tests.engine.reference.case import TODO, F, ReferenceCase, expect
from tests.engine.scenario_framework import Adapter, State, state, topology


class TestPvExport(ReferenceCase):
    """The same two devices, with the string now permitted to export. Reversing
    the grid changes its kind rather than its sign: it stops being a source and
    becomes a sink, which is all it takes to switch on the export channel and
    its compensation.

    Decides:

    * An exporting grid is a sink, not a source with a negative reading.
    * Export compensation is earned by the sources the export was drawn from.
    * The applicable self-consumption ratio measures only what stayed home.
    * Zero gross power guards to zero rather than dividing by zero.
    """

    case_id = "pv-export"
    title = "PV export"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10, exports=True, export_comp=0.08),
        )

    # ----------------------------------------------------------------------

    @state
    def export_surplus(self):
        """The string outruns the house; the surplus leaves through the grid."""
        return State(grid=-400, pv1=900, price=F(1, 4))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_export_surplus_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_export_surplus_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_export_surplus_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_export_surplus_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_export_surplus_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_export_surplus_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_export_surplus_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_export_surplus_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_export_surplus_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_export_surplus_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_export_surplus_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_export_surplus_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_export_surplus_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_export_surplus_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_export_surplus_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_export_surplus_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_export_surplus_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_export_surplus_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_export_surplus_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_export_surplus_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_export_surplus_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_export_surplus_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_export_surplus_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_export_surplus_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_export_surplus_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_export_surplus_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_export_surplus_source_adapters_dynamic_lcoe(self):
        return TODO

    # ----------------------------------------------------------------------

    @state
    def export_all(self):
        """Everything the string makes is exported: the home base load is exactly
        zero.
        """
        return State(grid=-900, pv1=900, price=F(1, 4))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_export_all_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_export_all_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_export_all_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_export_all_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_export_all_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_export_all_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_export_all_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_export_all_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_export_all_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_export_all_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_export_all_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_export_all_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_export_all_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_export_all_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_export_all_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_export_all_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_export_all_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_export_all_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_export_all_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_export_all_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_export_all_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_export_all_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_export_all_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_export_all_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_export_all_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_export_all_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_export_all_source_adapters_dynamic_lcoe(self):
        return TODO

    # ----------------------------------------------------------------------

    @state
    def zero_gross(self):
        """The grid exports while nothing is producing — an impossible meter set
        that must not divide by zero.
        """
        return State(grid=-500, pv1=0, price=F(1, 4))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_zero_gross_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_zero_gross_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_zero_gross_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_zero_gross_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_zero_gross_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_zero_gross_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_zero_gross_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_zero_gross_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_zero_gross_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_zero_gross_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_zero_gross_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_zero_gross_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_zero_gross_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_zero_gross_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_zero_gross_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_zero_gross_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_zero_gross_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_zero_gross_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_zero_gross_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_zero_gross_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_zero_gross_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_zero_gross_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_zero_gross_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_zero_gross_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_zero_gross_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_zero_gross_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_zero_gross_source_adapters_dynamic_lcoe(self):
        return TODO
