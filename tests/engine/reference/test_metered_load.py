"""Reference case: Metered load."""

from __future__ import annotations

from tests.engine.reference.case import TODO, F, ReferenceCase, expect
from tests.engine.scenario_framework import Adapter, State, state, topology


class TestMeteredLoad(ReferenceCase):
    """A consumer with a meter on it, next to the unmetered remainder. The base
    load stops being the whole house and becomes what is left after the metered
    draw — including when the meters disagree and there is nothing left.

    Decides:

    * A metered consumer gets its own provenance row; the remainder is the home
      base load.
    * A metered draw larger than gross power clamps the base load to zero
      rather than going negative.
    * A zeroed base load still publishes a share row, of zeros.
    """

    case_id = "metered-load"
    title = "Metered load"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10),
            Adapter.consumer("cons1"),
        )

    # ----------------------------------------------------------------------

    @state
    def load_and_base(self):
        """cons1 draws 500 W of the 1400 W entering the house; the other 900 W is
        unmetered.
        """
        return State(grid=800, pv1=600, cons1=-500, price=F(3, 10))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_load_and_base_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_load_and_base_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_load_and_base_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_load_and_base_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_load_and_base_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_load_and_base_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_load_and_base_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_load_and_base_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_load_and_base_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_load_and_base_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_load_and_base_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_load_and_base_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_load_and_base_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_load_and_base_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_load_and_base_gross_power_standby_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_load_and_base_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_load_and_base_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_load_and_base_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_load_and_base_source_adapters_standby_power(self):
        return TODO

    @expect("source_adapters_charging_power")
    def test_load_and_base_source_adapters_charging_power(self):
        return TODO

    @expect("source_adapters_consumption_ratios")
    def test_load_and_base_source_adapters_consumption_ratios(self):
        return TODO

    @expect("source_adapters_export_ratios")
    def test_load_and_base_source_adapters_export_ratios(self):
        return TODO

    @expect("source_adapters_charging_ratios")
    def test_load_and_base_source_adapters_charging_ratios(self):
        return TODO

    @expect("source_adapters_standby_ratios")
    def test_load_and_base_source_adapters_standby_ratios(self):
        return TODO

    @expect("source_adapters_consumption_shares")
    def test_load_and_base_source_adapters_consumption_shares(self):
        return TODO

    @expect("source_adapters_charging_shares")
    def test_load_and_base_source_adapters_charging_shares(self):
        return TODO

    @expect("source_adapters_standby_shares")
    def test_load_and_base_source_adapters_standby_shares(self):
        return TODO

    @expect("sink_adapters_consumption_shares")
    def test_load_and_base_sink_adapters_consumption_shares(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_load_and_base_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_load_and_base_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_load_and_base_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_load_and_base_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_load_and_base_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_load_and_base_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_load_and_base_source_adapters_dynamic_lcoe(self):
        return TODO

    @expect("source_adapters_coe_rate")
    def test_load_and_base_source_adapters_coe_rate(self):
        return TODO

    @expect("source_adapters_export_compensation_rates")
    def test_load_and_base_source_adapters_export_compensation_rates(self):
        return TODO

    @expect("source_adapters_coo_rates")
    def test_load_and_base_source_adapters_coo_rates(self):
        return TODO

    @expect("source_adapters_lcoo_rates")
    def test_load_and_base_source_adapters_lcoo_rates(self):
        return TODO

    @expect("sink_adapters_coo_rates")
    def test_load_and_base_sink_adapters_coo_rates(self):
        return TODO

    @expect("sink_adapters_lcoo_rates")
    def test_load_and_base_sink_adapters_lcoo_rates(self):
        return TODO

    @expect("sink_adapters_avoided_cost_rates")
    def test_load_and_base_sink_adapters_avoided_cost_rates(self):
        return TODO

    @expect("home_base_load_avoided_cost_rate")
    def test_load_and_base_home_base_load_avoided_cost_rate(self):
        return TODO

    @expect("combined_coe")
    def test_load_and_base_combined_coe(self):
        return TODO

    @expect("combined_lcoe")
    def test_load_and_base_combined_lcoe(self):
        return TODO

    @expect("combined_consumption_cost_rate")
    def test_load_and_base_combined_consumption_cost_rate(self):
        return TODO

    @expect("combined_levelized_consumption_cost_rate")
    def test_load_and_base_combined_levelized_consumption_cost_rate(self):
        return TODO

    @expect("combined_charging_cost_rate")
    def test_load_and_base_combined_charging_cost_rate(self):
        return TODO

    @expect("combined_levelized_export_cost_rate")
    def test_load_and_base_combined_levelized_export_cost_rate(self):
        return TODO

    @expect("combined_levelized_standby_cost_rate")
    def test_load_and_base_combined_levelized_standby_cost_rate(self):
        return TODO

    @expect("combined_device_operating_cost_rate")
    def test_load_and_base_combined_device_operating_cost_rate(self):
        return TODO

    @expect("adapters_saving_rates")
    def test_load_and_base_adapters_saving_rates(self):
        return TODO

    @expect("adapters_levelized_saving_rates")
    def test_load_and_base_adapters_levelized_saving_rates(self):
        return TODO

    @expect("adapters_financial_return_rates")
    def test_load_and_base_adapters_financial_return_rates(self):
        return TODO

    @expect("adapters_levelized_financial_return_rates")
    def test_load_and_base_adapters_levelized_financial_return_rates(self):
        return TODO

    @expect("combined_financial_return_rate")
    def test_load_and_base_combined_financial_return_rate(self):
        return TODO

    # ----------------------------------------------------------------------

    @state
    def over_metered(self):
        """cons1 reads more than the sources supply — the meters disagree, and the
        base load has nowhere to go but zero.
        """
        return State(grid=100, pv1=200, cons1=-400, price=F(3, 10))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_over_metered_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_over_metered_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_over_metered_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_over_metered_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_over_metered_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_over_metered_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_over_metered_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_over_metered_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_over_metered_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_over_metered_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_over_metered_home_base_load_source_shares(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_over_metered_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_over_metered_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_over_metered_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_over_metered_gross_power_standby_ratio(self):
        return TODO

    @expect("source_adapters_consumption_power")
    def test_over_metered_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_over_metered_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_over_metered_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_over_metered_source_adapters_standby_power(self):
        return TODO

    @expect("source_adapters_charging_power")
    def test_over_metered_source_adapters_charging_power(self):
        return TODO

    @expect("source_adapters_consumption_ratios")
    def test_over_metered_source_adapters_consumption_ratios(self):
        return TODO

    @expect("source_adapters_export_ratios")
    def test_over_metered_source_adapters_export_ratios(self):
        return TODO

    @expect("source_adapters_charging_ratios")
    def test_over_metered_source_adapters_charging_ratios(self):
        return TODO

    @expect("source_adapters_standby_ratios")
    def test_over_metered_source_adapters_standby_ratios(self):
        return TODO

    @expect("source_adapters_consumption_shares")
    def test_over_metered_source_adapters_consumption_shares(self):
        return TODO

    @expect("source_adapters_charging_shares")
    def test_over_metered_source_adapters_charging_shares(self):
        return TODO

    @expect("source_adapters_standby_shares")
    def test_over_metered_source_adapters_standby_shares(self):
        return TODO

    @expect("sink_adapters_consumption_shares")
    def test_over_metered_sink_adapters_consumption_shares(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_over_metered_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_over_metered_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_over_metered_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_over_metered_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_over_metered_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_over_metered_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_over_metered_source_adapters_dynamic_lcoe(self):
        return TODO

    @expect("source_adapters_coe_rate")
    def test_over_metered_source_adapters_coe_rate(self):
        return TODO

    @expect("source_adapters_export_compensation_rates")
    def test_over_metered_source_adapters_export_compensation_rates(self):
        return TODO

    @expect("source_adapters_coo_rates")
    def test_over_metered_source_adapters_coo_rates(self):
        return TODO

    @expect("source_adapters_lcoo_rates")
    def test_over_metered_source_adapters_lcoo_rates(self):
        return TODO

    @expect("sink_adapters_coo_rates")
    def test_over_metered_sink_adapters_coo_rates(self):
        return TODO

    @expect("sink_adapters_lcoo_rates")
    def test_over_metered_sink_adapters_lcoo_rates(self):
        return TODO

    @expect("sink_adapters_avoided_cost_rates")
    def test_over_metered_sink_adapters_avoided_cost_rates(self):
        return TODO

    @expect("home_base_load_avoided_cost_rate")
    def test_over_metered_home_base_load_avoided_cost_rate(self):
        return TODO

    @expect("combined_coe")
    def test_over_metered_combined_coe(self):
        return TODO

    @expect("combined_lcoe")
    def test_over_metered_combined_lcoe(self):
        return TODO

    @expect("combined_consumption_cost_rate")
    def test_over_metered_combined_consumption_cost_rate(self):
        return TODO

    @expect("combined_levelized_consumption_cost_rate")
    def test_over_metered_combined_levelized_consumption_cost_rate(self):
        return TODO

    @expect("combined_charging_cost_rate")
    def test_over_metered_combined_charging_cost_rate(self):
        return TODO

    @expect("combined_levelized_export_cost_rate")
    def test_over_metered_combined_levelized_export_cost_rate(self):
        return TODO

    @expect("combined_levelized_standby_cost_rate")
    def test_over_metered_combined_levelized_standby_cost_rate(self):
        return TODO

    @expect("combined_device_operating_cost_rate")
    def test_over_metered_combined_device_operating_cost_rate(self):
        return TODO

    @expect("adapters_saving_rates")
    def test_over_metered_adapters_saving_rates(self):
        return TODO

    @expect("adapters_levelized_saving_rates")
    def test_over_metered_adapters_levelized_saving_rates(self):
        return TODO

    @expect("adapters_financial_return_rates")
    def test_over_metered_adapters_financial_return_rates(self):
        return TODO

    @expect("adapters_levelized_financial_return_rates")
    def test_over_metered_adapters_levelized_financial_return_rates(self):
        return TODO

    @expect("combined_financial_return_rate")
    def test_over_metered_combined_financial_return_rate(self):
        return TODO
