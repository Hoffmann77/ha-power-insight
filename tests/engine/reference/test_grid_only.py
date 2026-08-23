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
    * An unavailable meter collapses everything derived from it to nothing,
      while a total over an empty device set (no PV, no battery) stays zero.
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
        return State(
            grid=1200,
            price=F(3, 10),
        )

    # Layer 1 — the totals. One source, so the grid reading *is* the gross
    # power, and with no local device every other channel total is a sum over
    # an empty set.

    @expect("gross_power")
    def test_import_only_gross_power(self):
        """The grid is the only source, so its 1200 W in is the whole gross power."""
        return 1200

    @expect("combined_grid_import")
    def test_import_only_combined_grid_import(self):
        """A positive grid reading is all import."""
        return 1200

    @expect("combined_grid_export")
    def test_import_only_combined_grid_export(self):
        """Nothing is fed back while the grid is importing."""
        return 0

    @expect("combined_production")
    def test_import_only_combined_production(self):
        """No PV adapter exists, so production sums over an empty set."""
        return 0

    @expect("combined_charging_power")
    def test_import_only_combined_charging_power(self):
        """No battery, so nothing is charging."""
        return 0

    @expect("combined_discharging_power")
    def test_import_only_combined_discharging_power(self):
        """No battery, so nothing is discharging."""
        return 0

    @expect("combined_standby_power")
    def test_import_only_combined_standby_power(self):
        """No PV, so there is no standby draw."""
        return 0

    @expect("combined_consumption")
    def test_import_only_combined_consumption(self):
        """Residual: 1200 gross − 0 export − 0 charging − 0 standby."""
        return 1200

    @expect("home_base_load_power")
    def test_import_only_home_base_load_power(self):
        """Nothing is metered, so the whole 1200 W draw is unmetered base load."""
        return 1200

    # Layer 2 — provenance. The base load has exactly one source available to
    # it, so its row is that source at 1. No metered adapter draws, so the
    # public (adapter-only) row set is empty.

    @expect("sink_adapters_source_shares")
    def test_import_only_sink_adapters_source_shares(self):
        """No metered sink draws — the base load is published separately — so
        the adapter row set is empty."""
        return {}

    @expect("home_base_load_source_shares")
    def test_import_only_home_base_load_source_shares(self):
        """The base load's only available source is the grid, so its row is grid at 1."""
        return {
            "grid": 1,
        }

    # Layer 3a — the channel split, as ratios of gross power. Everything is
    # self-consumed, so consumption takes the whole of it.

    @expect("gross_power_export_ratio")
    def test_import_only_gross_power_export_ratio(self):
        """Nothing exported, so 0 of gross power."""
        return 0

    @expect("gross_power_consumption_ratio")
    def test_import_only_gross_power_consumption_ratio(self):
        """All 1200 W is self-consumed, so the whole of gross power."""
        return 1

    @expect("gross_power_charging_ratio")
    def test_import_only_gross_power_charging_ratio(self):
        """Nothing charged, so 0 of gross power."""
        return 0

    @expect("gross_power_standby_ratio")
    def test_import_only_gross_power_standby_ratio(self):
        """No standby draw, so 0 of gross power."""
        return 0

    @expect("gross_power_applicable_consumption_ratio")
    def test_import_only_gross_power_applicable_consumption_ratio(self):
        """Of the power that stayed home and was not stored (all 1200 W), all of
        it was used — no standby — so the ratio is 1."""
        return 1

    # Layer 3b — per-source power. The grid alone supplies each channel, so its
    # entire 1200 W sits in consumption and nothing in the others.

    @expect("source_adapters_consumption_power")
    def test_import_only_source_adapters_consumption_power(self):
        """The whole 1200 W self-consumption is served by the grid."""
        return {
            "grid": 1200,
        }

    @expect("source_adapters_export_power")
    def test_import_only_source_adapters_export_power(self):
        """The grid is a source this snapshot but exports nothing."""
        return {
            "grid": 0,
        }

    @expect("source_adapters_standby_power")
    def test_import_only_source_adapters_standby_power(self):
        """No standby draw for the grid to have supplied."""
        return {
            "grid": 0,
        }

    # Layer 3c — per-source shares.

    @expect("source_adapters_export_shares")
    def test_import_only_source_adapters_export_shares(self):
        """Nothing is exported, so the grid's share of export is 0."""
        return {
            "grid": 0,
        }

    # Layer 4 — money. 1.2 kW at 0.30 EUR/kWh, and marginal equals levelized
    # while the grid is the only source.

    @expect("combined_coe_rate")
    def test_import_only_combined_coe_rate(self):
        """1.2 kW × 0.30 EUR/kWh = 0.36 = 9/25 EUR/h."""
        return F(9, 25)

    @expect("combined_lcoe_rate")
    def test_import_only_combined_lcoe_rate(self):
        """No local source to add an LCOE, so levelized equals marginal: 9/25 EUR/h."""
        return F(9, 25)

    # Nothing local supplied the CON channel, so nothing was avoided; nothing
    # was generated or stored, so nothing was saved.

    @expect("combined_avoided_cost_rate")
    def test_import_only_combined_avoided_cost_rate(self):
        """The grid supplied everything, so nothing was avoided."""
        return 0

    @expect("combined_saving_rate")
    def test_import_only_combined_saving_rate(self):
        """No local generation earning or storage costing, so the net saving is 0."""
        return 0

    @expect("combined_export_compensation_rate")
    def test_import_only_combined_export_compensation_rate(self):
        """Nothing exported, so nothing earned."""
        return 0

    @expect("source_adapters_dynamic_coe")
    def test_import_only_source_adapters_dynamic_coe(self):
        """The grid's marginal price is its tariff, 3/10 EUR/kWh."""
        return {
            "grid": F(3, 10),
        }

    @expect("source_adapters_dynamic_lcoe")
    def test_import_only_source_adapters_dynamic_lcoe(self):
        """The grid carries no levelized premium, so its levelized price is the tariff too."""
        return {
            "grid": F(3, 10),
        }

    # ----------------------------------------------------------------------

    @state
    def grid_idle(self):
        """The meter reads exactly 0 W: gross power is zero and every ratio has to
        survive it.

        Open question: at exactly 0 W the grid is idle — in no flow group — so
        every per-source map is empty and the sensors reading them publish
        nothing. A connected meter reading zero is arguably not the same as an
        absent one; whether these per-source sensors should show 0 (grid present,
        delivering nothing) rather than go blank is unsettled.
        """
        return State(
            grid=0,
            price=F(3, 10),
        )

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_grid_idle_gross_power(self):
        """The meter reads 0, so gross power is 0."""
        return 0

    @expect("combined_grid_import")
    def test_grid_idle_combined_grid_import(self):
        """0 W is neither import nor export."""
        return 0

    @expect("combined_grid_export")
    def test_grid_idle_combined_grid_export(self):
        """0 W is neither import nor export."""
        return 0

    @expect("combined_production")
    def test_grid_idle_combined_production(self):
        """No PV adapter, so production is 0."""
        return 0

    @expect("combined_charging_power")
    def test_grid_idle_combined_charging_power(self):
        """No battery, so nothing is charging."""
        return 0

    @expect("combined_discharging_power")
    def test_grid_idle_combined_discharging_power(self):
        """No battery, so nothing is discharging."""
        return 0

    @expect("combined_standby_power")
    def test_grid_idle_combined_standby_power(self):
        """No PV, so no standby draw."""
        return 0

    @expect("combined_consumption")
    def test_grid_idle_combined_consumption(self):
        """Residual of a zero gross power is 0."""
        return 0

    @expect("home_base_load_power")
    def test_grid_idle_home_base_load_power(self):
        """Nothing enters and nothing is metered, so the base load is 0."""
        return 0

    # Layer 2 — Source provenance. Nothing is providing, so there is nothing to
    # attribute: every provenance map is empty (not None — the meter is present).

    @expect("sink_adapters_source_shares")
    def test_grid_idle_sink_adapters_source_shares(self):
        """No source is providing, so there is nothing to attribute — empty."""
        return {}

    @expect("home_base_load_source_shares")
    def test_grid_idle_home_base_load_source_shares(self):
        """The base load draws nothing and the grid is idle, so its row is empty."""
        return {}

    # Layer 3a — Channel-split ratios. Gross power is zero, so each ratio guards
    # to zero rather than dividing by zero.

    @expect("gross_power_export_ratio")
    def test_grid_idle_gross_power_export_ratio(self):
        """0/0 guards to 0."""
        return 0

    @expect("gross_power_consumption_ratio")
    def test_grid_idle_gross_power_consumption_ratio(self):
        """0/0 guards to 0."""
        return 0

    @expect("gross_power_charging_ratio")
    def test_grid_idle_gross_power_charging_ratio(self):
        """0/0 guards to 0."""
        return 0

    @expect("gross_power_standby_ratio")
    def test_grid_idle_gross_power_standby_ratio(self):
        """0/0 guards to 0."""
        return 0

    @expect("gross_power_applicable_consumption_ratio")
    def test_grid_idle_gross_power_applicable_consumption_ratio(self):
        """Applicable gross power is 0, so the guarded ratio is 0."""
        return 0

    # Layer 3b — Per-source power. The grid is idle, so it is in no source
    # group and every per-source map is empty.

    @expect("source_adapters_consumption_power")
    def test_grid_idle_source_adapters_consumption_power(self):
        """No source is providing, so the per-source consumption split is empty."""
        return {}

    @expect("source_adapters_export_power")
    def test_grid_idle_source_adapters_export_power(self):
        """No source is providing, so the per-source export split is empty."""
        return {}

    @expect("source_adapters_standby_power")
    def test_grid_idle_source_adapters_standby_power(self):
        """No source is providing, so the per-source standby split is empty."""
        return {}

    # Layer 3c — Per-source shares.

    @expect("source_adapters_export_shares")
    def test_grid_idle_source_adapters_export_shares(self):
        """No source is providing, so the export share map is empty."""
        return {}

    # Layer 4 — The monetary model. Nothing flows, so every rate is 0.

    @expect("combined_coe_rate")
    def test_grid_idle_combined_coe_rate(self):
        """No power imported, so the marginal cost rate is 0."""
        return 0

    @expect("combined_lcoe_rate")
    def test_grid_idle_combined_lcoe_rate(self):
        """No power entering, so the levelized cost rate is 0."""
        return 0

    @expect("combined_avoided_cost_rate")
    def test_grid_idle_combined_avoided_cost_rate(self):
        """No local generation, so nothing avoided."""
        return 0

    @expect("combined_saving_rate")
    def test_grid_idle_combined_saving_rate(self):
        """Nothing generated or stored, so the net saving is 0."""
        return 0

    @expect("combined_export_compensation_rate")
    def test_grid_idle_combined_export_compensation_rate(self):
        """Nothing exported, so nothing earned."""
        return 0

    @expect("source_adapters_dynamic_coe")
    def test_grid_idle_source_adapters_dynamic_coe(self):
        """The grid is idle, delivering no priced power, so the map is empty."""
        return {}

    @expect("source_adapters_dynamic_lcoe")
    def test_grid_idle_source_adapters_dynamic_lcoe(self):
        """The grid is idle, delivering no priced power, so the map is empty."""
        return {}

    # ----------------------------------------------------------------------

    @state
    def grid_unavailable(self):
        """The grid sensor has dropped out. Everything derived from the meter
        collapses to nothing, while a total over an empty device set — no PV,
        no battery — is still a confident zero.

        Where a value is grid-derived (gross power, consumption, the ratios, the
        provenance maps, every cost rate) the engine publishes nothing at all
        rather than a stale or invented figure. Where a value is a structural
        sum over devices that do not exist here (production, charging,
        discharging, standby) it stays 0: the missing meter says nothing about
        PV that is not installed.
        """
        return State(
            grid=None,
            price=F(3, 10),
        )

    # Layer 1 — Readings and totals.

    @expect("gross_power")
    def test_grid_unavailable_gross_power(self):
        """The only inflow meter is unavailable, so gross power is unknown."""
        return None

    @expect("combined_grid_import")
    def test_grid_unavailable_combined_grid_import(self):
        """The grid reading is unavailable, so import is unknown."""
        return None

    @expect("combined_grid_export")
    def test_grid_unavailable_combined_grid_export(self):
        """The grid reading is unavailable, so export is unknown."""
        return None

    @expect("combined_production")
    def test_grid_unavailable_combined_production(self):
        """A sum over zero PV adapters is 0, independent of the grid meter."""
        return 0

    @expect("combined_charging_power")
    def test_grid_unavailable_combined_charging_power(self):
        """A sum over zero batteries is 0, independent of the grid meter."""
        return 0

    @expect("combined_discharging_power")
    def test_grid_unavailable_combined_discharging_power(self):
        """A sum over zero batteries is 0, independent of the grid meter."""
        return 0

    @expect("combined_standby_power")
    def test_grid_unavailable_combined_standby_power(self):
        """A sum over zero PV adapters is 0, independent of the grid meter."""
        return 0

    @expect("combined_consumption")
    def test_grid_unavailable_combined_consumption(self):
        """Consumption is a residual of gross power, which is unknown."""
        return None

    @expect("home_base_load_power")
    def test_grid_unavailable_home_base_load_power(self):
        """The base load is gross minus metered draw, and gross is unknown."""
        return None

    # Layer 2 — Source provenance. Provenance is derived from the grid reading,
    # so it collapses to nothing ("we can't tell"), not an empty row set.

    @expect("sink_adapters_source_shares")
    def test_grid_unavailable_sink_adapters_source_shares(self):
        """Provenance is unknowable with the only source's reading missing."""
        return None

    @expect("home_base_load_source_shares")
    def test_grid_unavailable_home_base_load_source_shares(self):
        """The base load's provenance is unknowable with the grid unavailable."""
        return None

    # Layer 3a — Channel-split ratios.

    @expect("gross_power_export_ratio")
    def test_grid_unavailable_gross_power_export_ratio(self):
        """A ratio of an unknown gross power is unknown."""
        return None

    @expect("gross_power_consumption_ratio")
    def test_grid_unavailable_gross_power_consumption_ratio(self):
        """A ratio of an unknown gross power is unknown."""
        return None

    @expect("gross_power_charging_ratio")
    def test_grid_unavailable_gross_power_charging_ratio(self):
        """A ratio of an unknown gross power is unknown."""
        return None

    @expect("gross_power_standby_ratio")
    def test_grid_unavailable_gross_power_standby_ratio(self):
        """A ratio of an unknown gross power is unknown."""
        return None

    @expect("gross_power_applicable_consumption_ratio")
    def test_grid_unavailable_gross_power_applicable_consumption_ratio(self):
        """A ratio of an unknown gross power is unknown."""
        return None

    # Layer 3b — Per-source power.

    @expect("source_adapters_consumption_power")
    def test_grid_unavailable_source_adapters_consumption_power(self):
        """The per-source split is unknowable with the grid unavailable."""
        return None

    @expect("source_adapters_export_power")
    def test_grid_unavailable_source_adapters_export_power(self):
        """The per-source split is unknowable with the grid unavailable."""
        return None

    @expect("source_adapters_standby_power")
    def test_grid_unavailable_source_adapters_standby_power(self):
        """The per-source split is unknowable with the grid unavailable."""
        return None

    # Layer 3c — Per-source shares.

    @expect("source_adapters_export_shares")
    def test_grid_unavailable_source_adapters_export_shares(self):
        """The per-source split is unknowable with the grid unavailable."""
        return None

    # Layer 4 — The monetary model. Every rate is priced off the grid reading,
    # so all of them collapse to nothing.

    @expect("combined_coe_rate")
    def test_grid_unavailable_combined_coe_rate(self):
        """Priced off the unavailable grid import, so unknown."""
        return None

    @expect("combined_lcoe_rate")
    def test_grid_unavailable_combined_lcoe_rate(self):
        """Priced off the unavailable grid reading, so unknown."""
        return None

    @expect("combined_avoided_cost_rate")
    def test_grid_unavailable_combined_avoided_cost_rate(self):
        """Nothing can be attributed to local generation, so unknown."""
        return None

    @expect("combined_saving_rate")
    def test_grid_unavailable_combined_saving_rate(self):
        """With gross power unavailable the saving rate collapses to nothing —
        it does not sum an empty ledger to a confident 0."""
        return None

    @expect("combined_export_compensation_rate")
    def test_grid_unavailable_combined_export_compensation_rate(self):
        """Export earnings are priced off the unavailable reading, so unknown."""
        return None

    @expect("source_adapters_dynamic_coe")
    def test_grid_unavailable_source_adapters_dynamic_coe(self):
        """No source has a knowable delivered price, so the map is unknown."""
        return None

    @expect("source_adapters_dynamic_lcoe")
    def test_grid_unavailable_source_adapters_dynamic_lcoe(self):
        """No source has a knowable delivered price, so the map is unknown."""
        return None
