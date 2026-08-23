"""Reference case: Captive load."""

from __future__ import annotations

from tests.engine.reference.case import TODO, F, ReferenceCase, expect
from tests.engine.scenario_framework import Adapter, State, state, topology


class TestCaptiveLoad(ReferenceCase):
    """The same three devices, with the consumer now restricted to the string.
    This is the smallest wiring in which a restriction can be honoured at all —
    and the smallest in which one can fail, which is where the restriction
    deficit is first published.

    Decides:

    * A restricted sink is served from its allowed sources before anything
      unrestricted shares them.
    * Serving the captive sink first pushes the unrestricted base load onto the
      grid.
    * A draw the allowed sources cannot cover is still attributed, and the
      shortfall is reported as a restriction deficit.
    """

    case_id = "captive-load"
    title = "Captive load"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10),
            Adapter.consumer("cons1", power_from=("pv1",)),
        )

    # ----------------------------------------------------------------------

    @state
    def captive_load(self):
        """pv1 makes more than cons1 draws, so cons1 runs on solar alone and the
        base load is pushed onto the grid.
        """
        return State(grid=800, pv1=600, cons1=-500, price=F(3, 10))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_captive_load_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_captive_load_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_captive_load_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_captive_load_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_captive_load_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_captive_load_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_captive_load_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_captive_load_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_captive_load_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_captive_load_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_captive_load_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_captive_load_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_captive_load_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_captive_load_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_captive_load_gross_power_standby_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_captive_load_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_captive_load_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_captive_load_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_captive_load_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_captive_load_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_captive_load_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_captive_load_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_captive_load_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_captive_load_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_captive_load_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_captive_load_source_adapters_dynamic_lcoe(self):
        return TODO

    # ----------------------------------------------------------------------

    @state
    def load_exceeds(self):
        """cons1 draws 500 W but pv1 makes only 300 W: the missing 200 W came from
        a source it is not allowed to use.
        """
        return State(grid=800, pv1=300, cons1=-500, price=F(3, 10))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_load_exceeds_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_load_exceeds_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_load_exceeds_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_load_exceeds_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_load_exceeds_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_load_exceeds_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_load_exceeds_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_load_exceeds_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_load_exceeds_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_load_exceeds_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_load_exceeds_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_load_exceeds_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_load_exceeds_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_load_exceeds_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_load_exceeds_gross_power_standby_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_load_exceeds_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_load_exceeds_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_load_exceeds_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_load_exceeds_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_load_exceeds_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_load_exceeds_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_load_exceeds_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_load_exceeds_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_load_exceeds_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_load_exceeds_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_load_exceeds_source_adapters_dynamic_lcoe(self):
        return TODO
