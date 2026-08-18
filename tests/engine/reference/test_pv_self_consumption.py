"""Reference case: PV self-consumption."""

from __future__ import annotations

from tests.engine.reference.case import TODO, F, ReferenceCase, expect
from tests.engine.scenario_framework import Adapter, State, state, topology


class TestPvSelfConsumption(ReferenceCase):
    """One string added to the grid, and nothing restricted. Two sources are
    enough for the raw proportional mix, for the divergence between what power
    costs now and what it costs levelized, and for a string that is drawing
    rather than producing.

    Decides:

    * An unrestricted sink's provenance row is the raw source mix.
    * PV standby is a sink drawing from the mix, not negative production.
    * Marginal cost and levelized cost diverge as soon as a local source runs.
    * A source that only draws standby makes the saving rate negative.
    """

    case_id = "pv-self-consumption"
    title = "PV self-consumption"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10),
        )

    # ----------------------------------------------------------------------

    @state
    def sunny_partial(self):
        """Grid and string both supplying; the base load takes them in proportion."""
        return State(grid=800, pv1=600, price=F(3, 10))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_sunny_partial_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_sunny_partial_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_sunny_partial_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_sunny_partial_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_sunny_partial_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_sunny_partial_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_sunny_partial_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_sunny_partial_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_sunny_partial_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_sunny_partial_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_sunny_partial_home_base_load_source_shares(self):
        return TODO

    @expect("sink_adapters_restriction_deficit")
    def test_sunny_partial_sink_adapters_restriction_deficit(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_sunny_partial_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_sunny_partial_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_sunny_partial_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_sunny_partial_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_sunny_partial_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_sunny_partial_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_sunny_partial_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_sunny_partial_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_sunny_partial_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_sunny_partial_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_sunny_partial_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_sunny_partial_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_sunny_partial_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_sunny_partial_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_sunny_partial_source_adapters_dynamic_lcoe(self):
        return TODO

    # ----------------------------------------------------------------------

    @state
    def pv_covers_all(self):
        """The string covers the house exactly. The grid is present but
        contributes nothing.
        """
        return State(grid=0, pv1=600, price=F(3, 10))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_pv_covers_all_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_pv_covers_all_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_pv_covers_all_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_pv_covers_all_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_pv_covers_all_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_pv_covers_all_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_pv_covers_all_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_pv_covers_all_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_pv_covers_all_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_pv_covers_all_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_pv_covers_all_home_base_load_source_shares(self):
        return TODO

    @expect("sink_adapters_restriction_deficit")
    def test_pv_covers_all_sink_adapters_restriction_deficit(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_pv_covers_all_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_pv_covers_all_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_pv_covers_all_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_pv_covers_all_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_pv_covers_all_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_pv_covers_all_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_pv_covers_all_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_pv_covers_all_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_pv_covers_all_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_pv_covers_all_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_pv_covers_all_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_pv_covers_all_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_pv_covers_all_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_pv_covers_all_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_pv_covers_all_source_adapters_dynamic_lcoe(self):
        return TODO

    # ----------------------------------------------------------------------

    @state
    def pv_standby(self):
        """pv1 draws 20 W standby, so it is a sink served by the grid — and the
        saving goes negative.
        """
        return State(grid=1000, pv1=-20, price=F(3, 10))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_pv_standby_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_pv_standby_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_pv_standby_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_pv_standby_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_pv_standby_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_pv_standby_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_pv_standby_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_pv_standby_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_pv_standby_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_pv_standby_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_pv_standby_home_base_load_source_shares(self):
        return TODO

    @expect("sink_adapters_restriction_deficit")
    def test_pv_standby_sink_adapters_restriction_deficit(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_pv_standby_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_pv_standby_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_pv_standby_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_pv_standby_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_pv_standby_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_pv_standby_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_pv_standby_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_pv_standby_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_pv_standby_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_pv_standby_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_pv_standby_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_pv_standby_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_pv_standby_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_pv_standby_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_pv_standby_source_adapters_dynamic_lcoe(self):
        return TODO

    # ----------------------------------------------------------------------

    @state
    def pv_unavailable(self):
        """The string's sensor has dropped out; the grid still reads, but the
        total cannot be trusted.
        """
        return State(grid=1000, pv1=None, price=F(3, 10))

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_pv_unavailable_gross_power(self):
        return TODO

    @expect("combined_grid_import")
    def test_pv_unavailable_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_pv_unavailable_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_pv_unavailable_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_pv_unavailable_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_pv_unavailable_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_pv_unavailable_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_pv_unavailable_combined_consumption(self):
        return TODO

    @expect("home_base_load_power")
    def test_pv_unavailable_home_base_load_power(self):
        return TODO

    # Layer 2 — Source provenance.

    @expect("sink_adapters_source_shares")
    def test_pv_unavailable_sink_adapters_source_shares(self):
        return TODO

    @expect("home_base_load_source_shares")
    def test_pv_unavailable_home_base_load_source_shares(self):
        return TODO

    @expect("sink_adapters_restriction_deficit")
    def test_pv_unavailable_sink_adapters_restriction_deficit(self):
        return TODO

    # Layer 3 — Channel split and per-source attribution.

    @expect("gross_power_export_ratio")
    def test_pv_unavailable_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_pv_unavailable_gross_power_consumption_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_pv_unavailable_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_pv_unavailable_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_applicable_consumption_ratio")
    def test_pv_unavailable_gross_power_applicable_consumption_ratio(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_pv_unavailable_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_export_shares")
    def test_pv_unavailable_source_adapters_export_shares(self):
        return TODO

    @expect("source_adapters_standby_power")
    def test_pv_unavailable_source_adapters_standby_power(self):
        return TODO

    # Layer 4 — The monetary model.

    @expect("combined_coe_rate")
    def test_pv_unavailable_combined_coe_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_pv_unavailable_combined_lcoe_rate(self):
        return TODO

    @expect("combined_avoided_cost_rate")
    def test_pv_unavailable_combined_avoided_cost_rate(self):
        return TODO

    @expect("combined_saving_rate")
    def test_pv_unavailable_combined_saving_rate(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_pv_unavailable_combined_export_compensation_rate(self):
        return TODO

    @expect("source_adapters_dynamic_coe")
    def test_pv_unavailable_source_adapters_dynamic_coe(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_pv_unavailable_source_adapters_dynamic_lcoe(self):
        return TODO
