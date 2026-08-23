"""Reference case: Group captivity."""

from __future__ import annotations

from tests.engine.reference.case import TODO, F, ReferenceCase, expect
from tests.engine.scenario_framework import Adapter, State, state, topology


class TestGroupCaptivity(ReferenceCase):
    """Two batteries are each allowed both strings, and neither is individually
    stuck — but together they need every watt the two strings make. Deciding
    feasibility one sink at a time cannot see that; this is the case the max-
    flow solver exists for.

    Decides:

    * Feasibility is a property of groups of sinks, not of single sinks.
    * A flexible sink must not take local power a tight group needs.
    * When restrictions cannot all be honoured, the sink with the fewest
      permitted alternatives is served first and the deficit falls on the sinks
      that had somewhere else to go.
    """

    case_id = "group-captivity"
    title = "Group captivity"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("east", lcoe=0.10, exports=True),
            Adapter.pv("west", lcoe=0.10, exports=True),
            Adapter.battery("bat_a", lcos=0.15, charge_from=("east", "west")),
            Adapter.battery("bat_b", lcos=0.15, charge_from=("east", "west")),
            Adapter.battery("bat_c", lcos=0.15, charge_from=("east",)),
        )

    # ----------------------------------------------------------------------

    @state
    def hall_tight_pair(self):
        """bat_c idle. {bat_a, bat_b} exactly exhaust east+west, so the 200 W home
        load must be served entirely from the grid.
        """
        return State(
            grid=200,
            east=100,
            west=100,
            bat_a=-100,
            bat_b=-100,
            bat_c=0,
            price=F(3, 10),
        )

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_hall_tight_pair_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_hall_tight_pair_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_hall_tight_pair_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_hall_tight_pair_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_hall_tight_pair_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_hall_tight_pair_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_hall_tight_pair_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_hall_tight_pair_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_hall_tight_pair_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_hall_tight_pair_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_hall_tight_pair_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_hall_tight_pair_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_hall_tight_pair_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_hall_tight_pair_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_hall_tight_pair_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_hall_tight_pair_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_hall_tight_pair_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_hall_tight_pair_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_hall_tight_pair_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_hall_tight_pair_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_hall_tight_pair_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_hall_tight_pair_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_hall_tight_pair_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_hall_tight_pair_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_hall_tight_pair_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_hall_tight_pair_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_hall_tight_pair_source_adapters_dynamic_lcoe(self):
        return TODO

    # ----------------------------------------------------------------------

    @state
    def unsatisfiable_overlap(self):
        """bat_c now draws 100 W and is captive to east alone. Captive demand (300
        W) exceeds local supply (200 W): someone must be deficited.
        """
        return State(
            grid=200,
            east=100,
            west=100,
            bat_a=-100,
            bat_b=-100,
            bat_c=-100,
            price=F(3, 10),
        )

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_unsatisfiable_overlap_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_unsatisfiable_overlap_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_unsatisfiable_overlap_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_unsatisfiable_overlap_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_unsatisfiable_overlap_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_unsatisfiable_overlap_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_unsatisfiable_overlap_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_unsatisfiable_overlap_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_unsatisfiable_overlap_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_unsatisfiable_overlap_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_unsatisfiable_overlap_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_unsatisfiable_overlap_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_unsatisfiable_overlap_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_unsatisfiable_overlap_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_unsatisfiable_overlap_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_unsatisfiable_overlap_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_unsatisfiable_overlap_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_unsatisfiable_overlap_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_unsatisfiable_overlap_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_unsatisfiable_overlap_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_unsatisfiable_overlap_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_unsatisfiable_overlap_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_unsatisfiable_overlap_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_unsatisfiable_overlap_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_unsatisfiable_overlap_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_unsatisfiable_overlap_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_unsatisfiable_overlap_source_adapters_dynamic_lcoe(self):
        return TODO
