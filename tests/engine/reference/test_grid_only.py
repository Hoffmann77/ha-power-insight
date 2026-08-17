"""Reference case: Grid only."""

from __future__ import annotations

from tests.engine.reference.case import F, ReferenceCase, expect
from tests.engine.scenario_framework import Adapter, State, state, topology


class TestGridOnly(ReferenceCase):
    """One meter and nothing else. Every published property still has a value
    here, which makes this the cheapest place in the corpus to settle what the
    engine does at the edges: a single source, a house that draws nothing, and
    a sensor that has dropped out.

    Decides:

    * With no local device, the whole gross power is the unmetered home base
      load.
    * A sink with one available source has a provenance row of exactly one.
    * Marginal and levelized cost agree while the grid is the only source.
    * An unavailable reading collapses the derived values rather than
      defaulting to zero.
    """

    case_id = "grid-only"
    title = "Grid only"

    @topology
    def wiring(self):
        return (Adapter.grid(),)

    # ----------------------------------------------------------------------

    @state
    def import_only(self):
        """The house runs on the grid alone; every watt is unmetered base load."""
        return State(grid=1200, price=F(3, 10))

    # Layer 1 — the totals. One source, so the grid reading *is* the gross
    # power, and with no local device every other channel total is a sum over
    # an empty set.

    @expect("gross_power")
    def test_import_only_gross_power(self):
        return 1200

    @expect("combined_grid_import")
    def test_import_only_combined_grid_import(self):
        return 1200

    @expect("combined_grid_export")
    def test_import_only_combined_grid_export(self):
        return 0

    @expect("combined_production")
    def test_import_only_combined_production(self):
        return 0

    @expect("combined_charging_power")
    def test_import_only_combined_charging_power(self):
        return 0

    @expect("combined_discharging_power")
    def test_import_only_combined_discharging_power(self):
        return 0

    @expect("combined_standby_power")
    def test_import_only_combined_standby_power(self):
        return 0

    @expect("combined_consumption")
    def test_import_only_combined_consumption(self):
        # Residual: 1200 - 0 export - 0 charging - 0 standby.
        return 1200

    @expect("home_base_load_power")
    def test_import_only_home_base_load_power(self):
        # Nothing is metered, so the whole draw is unmetered.
        return 1200

    # Layer 2 — provenance. The base load has exactly one source available to
    # it, so its row is that source at 1.

    @expect("home_base_load_source_shares")
    def test_import_only_home_base_load_source_shares(self):
        return {
            "grid": 1,
        }

    # Layer 3 — the channel split. Everything self-consumed.

    @expect("gross_power_export_ratio")
    def test_import_only_gross_power_export_ratio(self):
        return 0

    @expect("gross_power_consumption_ratio")
    def test_import_only_gross_power_consumption_ratio(self):
        return 1

    @expect("gross_power_charging_ratio")
    def test_import_only_gross_power_charging_ratio(self):
        return 0

    @expect("gross_power_standby_ratio")
    def test_import_only_gross_power_standby_ratio(self):
        return 0

    @expect("gross_power_applicable_consumption_ratio")
    def test_import_only_gross_power_applicable_consumption_ratio(self):
        # 1200 / (1200 - 0 export - 0 charging): no standby to lose.
        return 1

    # Layer 4 — money. 1.2 kW at 0.30 EUR/kWh, and marginal equals levelized
    # while the grid is the only source.

    @expect("combined_coe_rate")
    def test_import_only_combined_coe_rate(self):
        return F(9, 25)

    @expect("combined_lcoe_rate")
    def test_import_only_combined_lcoe_rate(self):
        return F(9, 25)

    # Nothing local supplied the CON channel, so nothing was avoided; nothing
    # was generated or stored, so nothing was saved.

    @expect("combined_avoided_cost_rate")
    def test_import_only_combined_avoided_cost_rate(self):
        return 0

    @expect("combined_saving_rate")
    def test_import_only_combined_saving_rate(self):
        return 0

    @expect("combined_export_compensation_rate")
    def test_import_only_combined_export_compensation_rate(self):
        return 0

    # Still to derive for this snapshot: the map-shaped properties
    # (sink_adapters_source_shares, sink_adapters_restriction_deficit,
    # source_adapters_export_power / _export_shares / _standby_power,
    # source_adapters_dynamic_coe / _dynamic_lcoe). Their *key sets* are part
    # of the answer — whether a source with nothing to attribute appears as a
    # zero row or not at all — so they are a modelling decision, not
    # arithmetic.

    # ----------------------------------------------------------------------

    @state
    def grid_idle(self):
        """The meter reads exactly 0 W: gross power is zero and every ratio has to
        survive it.
        """
        return State(grid=0, price=F(3, 10))

    # Nothing derived for this snapshot yet. Add @expect methods here;
    # see tests/engine/reference/case.py.

    # ----------------------------------------------------------------------

    @state
    def grid_unavailable(self):
        """The grid sensor has dropped out. Nothing downstream of it can be
        answered.

        Open question: combined_saving_rate publishes 0 EUR/h here while every
        other rate in layer 4 correctly publishes nothing. Zero is a claim —
        that the house saved exactly nothing this snapshot — and the engine is
        in no position to make it with the only meter unavailable.
        """
        return State(grid=None, price=F(3, 10))

    # Nothing derived for this snapshot yet. Add @expect methods here;
    # see tests/engine/reference/case.py.
