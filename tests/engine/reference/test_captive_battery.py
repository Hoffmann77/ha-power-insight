"""Reference case: Captive battery."""

from __future__ import annotations

from tests.engine.reference.case import TODO, F, ReferenceCase, expect
from tests.engine.scenario_framework import Adapter, State, state, topology


class TestCaptiveBattery(ReferenceCase):
    """bat1 may only charge from pv1. That single restriction changes the answer
    in two opposite ways depending on whether pv1 is producing: when it is, the
    captive sink depletes it before anyone else may share it; when it is not,
    the sink has nowhere legal to draw from.

    Decides:

    * A captive sink is served from its allowed source before flexible sinks
      share it.
    * When every allowed source is idle the row collapses to zero rather than
      dividing by zero.
    * The unservable draw is reported as a restriction deficit.
    """

    case_id = "captive-battery"
    title = "Captive battery"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10, exports=True),
            Adapter.battery("bat1", lcos=0.15, charge_from=("pv1",)),
            Adapter.consumer("cons1"),
        )

    # ----------------------------------------------------------------------

    @state
    def captive_depletes_first(self):
        """pv1 produces exactly what bat1 draws, so bat1 takes all of it."""
        return State(grid=500, pv1=400, bat1=-400, cons1=-200, price=F(3, 10))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_captive_depletes_first_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_captive_depletes_first_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_captive_depletes_first_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_captive_depletes_first_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_captive_depletes_first_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_captive_depletes_first_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_captive_depletes_first_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_captive_depletes_first_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_captive_depletes_first_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_captive_depletes_first_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_captive_depletes_first_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_captive_depletes_first_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_captive_depletes_first_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_captive_depletes_first_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_captive_depletes_first_gross_power_standby_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_captive_depletes_first_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_captive_depletes_first_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_captive_depletes_first_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_captive_depletes_first_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_captive_depletes_first_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_captive_depletes_first_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_captive_depletes_first_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_captive_depletes_first_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_captive_depletes_first_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_captive_depletes_first_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_captive_depletes_first_source_adapters_dynamic_lcoe(self):
        return TODO

    # ----------------------------------------------------------------------

    @state
    def source_in_standby(self):
        """pv1 is drawing standby, so it is a sink; bat1's only allowed source
        does not exist.

        Open question: home_base_load_power includes the 400 W bat1 drew but
        could not legally be attributed, so the 'unmetered' load contains a
        device that has a meter on it. Its docstring says gross minus metered
        draw, which would be 580 W rather than 980 W.
        """
        return State(grid=1000, pv1=-20, bat1=-400, cons1=-100, price=F(3, 10))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_source_in_standby_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_source_in_standby_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_source_in_standby_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_source_in_standby_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_source_in_standby_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_source_in_standby_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_source_in_standby_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_source_in_standby_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_source_in_standby_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_source_in_standby_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_source_in_standby_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_source_in_standby_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_source_in_standby_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_source_in_standby_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_source_in_standby_gross_power_standby_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_source_in_standby_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_source_in_standby_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_source_in_standby_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_source_in_standby_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_source_in_standby_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_source_in_standby_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_source_in_standby_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_source_in_standby_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_source_in_standby_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_source_in_standby_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_source_in_standby_source_adapters_dynamic_lcoe(self):
        return TODO
