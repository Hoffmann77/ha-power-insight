"""Reference case: Battery basics."""

from __future__ import annotations

from tests.engine.reference.case import TODO, F, ReferenceCase, expect
from tests.engine.scenario_framework import Adapter, State, state, topology


class TestBatteryBasics(ReferenceCase):
    """An unrestricted battery, which is the only device that changes which side
    of the diagram it sits on. Charging it is a sink like any other;
    discharging it is a source whose energy was paid for in the past, and a
    snapshot engine has to price that somehow.

    Decides:

    * A charging battery is a sink and takes the same raw mix as any other.
    * A discharging battery is a source priced at its flat levelized cost of
      storage.
    * Its marginal price is zero — the mix it charged on happened earlier,
      where a snapshot cannot see it.
    * An adapter reading exactly 0 W belongs to neither flow group.
    """

    case_id = "battery-basics"
    title = "Battery basics"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10),
            Adapter.consumer("cons1"),
            Adapter.battery("bat1", lcos=0.15),
        )

    # ----------------------------------------------------------------------

    @state
    def charging(self):
        """bat1 charges from the mix, taking the same proportions as the metered
        load beside it.
        """
        return State(grid=800, pv1=600, cons1=-500, bat1=-600, price=F(3, 10))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_charging_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_charging_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_charging_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_charging_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_charging_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_charging_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_charging_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_charging_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_charging_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_charging_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_charging_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_charging_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_charging_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_charging_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_charging_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_charging_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_charging_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_charging_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_charging_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_charging_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_charging_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_charging_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_charging_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_charging_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_charging_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_charging_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_charging_source_adapters_dynamic_lcoe(self):
        return TODO

    # ----------------------------------------------------------------------

    @state
    def discharging(self):
        """The sun is down and bat1 has become a source, supplying two thirds of
        the house.
        """
        return State(grid=200, pv1=0, cons1=-500, bat1=400, price=F(3, 10))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_discharging_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_discharging_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_discharging_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_discharging_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_discharging_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_discharging_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_discharging_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_discharging_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_discharging_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_discharging_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_discharging_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_discharging_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_discharging_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_discharging_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_discharging_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_discharging_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_discharging_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_discharging_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_discharging_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_discharging_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_discharging_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_discharging_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_discharging_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_discharging_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_discharging_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_discharging_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_discharging_source_adapters_dynamic_lcoe(self):
        return TODO

    # ----------------------------------------------------------------------

    @state
    def idle(self):
        """bat1 sits at exactly 0 W: neither a source nor a sink, and absent from
        both groups.
        """
        return State(grid=900, pv1=600, cons1=-500, bat1=0, price=F(3, 10))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_idle_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_idle_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_idle_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_idle_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_idle_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_idle_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_idle_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_idle_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_idle_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_idle_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_idle_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_idle_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_idle_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_idle_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_idle_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_idle_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_idle_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_idle_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_idle_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_idle_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_idle_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_idle_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_idle_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_idle_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_idle_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_idle_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_idle_source_adapters_dynamic_lcoe(self):
        return TODO
