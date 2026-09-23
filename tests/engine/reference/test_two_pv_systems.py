"""Reference case: Two PV systems."""

from __future__ import annotations

from tests.engine.reference.case import TODO, F, ReferenceCase, expect
from tests.engine.scenario_framework import Adapter, State, matches, show, state, topology


class TestTwoPvSystems(ReferenceCase):
    """Two equal PV systems, east and west, and a smaller third on the carport.
    A plug may run on east or west but not on the carport. Everything else is
    exported, and there is no unmetered base load, so every watt in the house
    is spoken for.

    The plug needs 400 W from east and west together, but neither system in
    particular — either one alone could cover it. That is easy to get wrong: a
    solver that reasons one source at a time finds nothing it must set aside
    for the plug on east, nothing on west, and can hand the export watts the
    plug needed.

    Decides:

    * A restriction naming several PV systems is honoured jointly: a load
      allowed two systems is served from them whenever together they can cover
      it, even though it needs neither in particular.
    * A sink spreads its draw over the systems it may use in proportion to
      what each has left, so two equal systems each carry half of it.
    """

    case_id = "two-pv-systems"
    title = "Two PV systems"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("east", lcoe=0.10, exports=True),
            Adapter.pv("west", lcoe=0.10, exports=True),
            Adapter.pv("carport", lcoe=0.10, exports=True),
            Adapter.consumer("plug", power_from=("east", "west")),
        )

    # ----------------------------------------------------------------------

    @state
    def every_watt_spoken_for(self):
        """East and west make 1000 W each and the carport 200 W. The plug draws
        400 W and the other 1800 W is exported. The carport's power can only go
        to the export, so the export takes all of it, and east and west cover
        the rest of the export and the whole plug — exactly.
        """
        return State(
            grid=-1800,
            east=1000,
            west=1000,
            carport=200,
            plug=-400,
            price=F(3, 10),
        )

    # Layer 1 — Readings and totals. Three producing PV systems, an exporting
    # grid and one metered load; no battery and nothing in standby.

    @expect("gross_power")
    def test_every_watt_spoken_for_gross_power(self):
        """1000 + 1000 + 200 W from the three PV systems; the grid is exporting."""
        return 2200

    @expect("combined_grid_import")
    def test_every_watt_spoken_for_combined_grid_import(self):
        """The grid is exporting, so nothing is imported."""
        return 0

    @expect("combined_grid_export")
    def test_every_watt_spoken_for_combined_grid_export(self):
        """The −1800 W grid reading, written positive."""
        return 1800

    @expect("combined_production")
    def test_every_watt_spoken_for_combined_production(self):
        """All three PV systems are producing: 1000 + 1000 + 200 W."""
        return 2200

    @expect("combined_charging_power")
    def test_every_watt_spoken_for_combined_charging_power(self):
        """No battery."""
        return 0

    @expect("combined_discharging_power")
    def test_every_watt_spoken_for_combined_discharging_power(self):
        """No battery."""
        return 0

    @expect("combined_standby_power")
    def test_every_watt_spoken_for_combined_standby_power(self):
        """Every PV system is producing, so none draws standby."""
        return 0

    @expect("combined_consumption")
    def test_every_watt_spoken_for_combined_consumption(self):
        """Residual: 2200 gross − 1800 export − 0 charging − 0 standby."""
        return 400

    @expect("home_base_load_power")
    def test_every_watt_spoken_for_home_base_load_power(self):
        """2200 W in, 1800 W exported and 400 W to the plug: nothing is left
        unmetered."""
        return 0

    # Layer 2 — provenance. The plug may not use the carport, so the carport
    # can only feed the export: all 200 W of it. That leaves 1600 W of export
    # and the 400 W plug to share east and west's 2000 W — exactly enough. Each
    # sink spreads its draw over east and west in proportion to what they have
    # left, and they are equal, so each sink takes half from each.

    #: Who gets how many watts from whom — the whole answer of this case in
    #: one table. Every row sums to that sink's draw, and every column to that
    #: PV system's output.
    DISTRIBUTION = {
        "grid": {"east": 800, "west": 800, "carport": 200},
        "plug": {"east": 200, "west": 200, "carport": 0},
    }

    def test_every_watt_spoken_for_power_distribution(self, power_insight, state):
        """The watts each sink draws from each PV system, and no deficit.

        The engine publishes provenance as shares; multiplied back by each
        sink's draw they must give exactly the table above. The plug's
        restriction can be honoured, so no restriction deficit may be reported.
        """
        shares = power_insight.sink_adapters_source_shares
        watts = {
            sink: {src: share * -state.readings[sink] for src, share in row.items()}
            for sink, row in shares.items()
        }
        assert matches(self.DISTRIBUTION, watts, abs_tol=1e-6), (
            f"expected {show(self.DISTRIBUTION)}\n  actual   {show(watts)}"
        )
        assert power_insight.sink_adapters_restriction_deficit == {}, (
            f"a deficit was reported: {power_insight.sink_adapters_restriction_deficit}"
        )

    @expect("sink_adapters_source_shares")
    def test_every_watt_spoken_for_sink_adapters_source_shares(self):
        """The distribution table, each row over its sink's draw: export 800,
        800 and 200 of 1800 W; plug 200, 200 and 0 of 400 W."""
        return {
            "grid": {"east": F(4, 9), "west": F(4, 9), "carport": F(1, 9)},
            "plug": {"east": F(1, 2), "west": F(1, 2), "carport": 0},
        }

    @expect("home_base_load_source_shares")
    def test_every_watt_spoken_for_home_base_load_source_shares(self):
        return TODO

    # Layer 3a — the channel split of gross power.

    @expect("gross_power_export_ratio")
    def test_every_watt_spoken_for_gross_power_export_ratio(self):
        """1800 of 2200 W exported."""
        return F(9, 11)

    @expect("gross_power_consumption_ratio")
    def test_every_watt_spoken_for_gross_power_consumption_ratio(self):
        """400 of 2200 W self-consumed, all of it by the plug."""
        return F(2, 11)

    @expect("gross_power_charging_ratio")
    def test_every_watt_spoken_for_gross_power_charging_ratio(self):
        """Nothing charged."""
        return 0

    @expect("gross_power_standby_ratio")
    def test_every_watt_spoken_for_gross_power_standby_ratio(self):
        """No standby draw."""
        return 0

    # Layer 3b — per-source power, read off the rows above.

    @expect("source_adapters_consumption_power")
    def test_every_watt_spoken_for_source_adapters_consumption_power(self):
        """The plug's 400 W, half from each of east and west; the base load draws nothing."""
        return {"east": 200, "west": 200, "carport": 0}

    @expect("source_adapters_export_power")
    def test_every_watt_spoken_for_source_adapters_export_power(self):
        """East and west each export what the plug left them: 1000 − 200 =
        800 W. The carport exports all 200 W."""
        return {"east": 800, "west": 800, "carport": 200}

    @expect("source_adapters_export_shares")
    def test_every_watt_spoken_for_source_adapters_export_shares(self):
        """800, 800 and 200 of the 1800 W exported."""
        return {"east": F(4, 9), "west": F(4, 9), "carport": F(1, 9)}

    @expect("source_adapters_standby_power")
    def test_every_watt_spoken_for_source_adapters_standby_power(self):
        """No standby draw for any source to supply."""
        return {"east": 0, "west": 0, "carport": 0}

    @expect("source_adapters_charging_power")
    def test_every_watt_spoken_for_source_adapters_charging_power(self):
        """No battery to charge."""
        return {"east": 0, "west": 0, "carport": 0}

    # Layer 3c — per-source ratios (down a source) and shares (across a channel).

    @expect("source_adapters_consumption_ratios")
    def test_every_watt_spoken_for_source_adapters_consumption_ratios(self):
        """200 of east's and west's 1000 W each went to the plug; none of the
        carport's."""
        return {"east": F(1, 5), "west": F(1, 5), "carport": 0}

    @expect("source_adapters_export_ratios")
    def test_every_watt_spoken_for_source_adapters_export_ratios(self):
        """800 of east's and west's 1000 W each was exported, and all of the
        carport's."""
        return {"east": F(4, 5), "west": F(4, 5), "carport": 1}

    @expect("source_adapters_charging_ratios")
    def test_every_watt_spoken_for_source_adapters_charging_ratios(self):
        """No source charged anything."""
        return {"east": 0, "west": 0, "carport": 0}

    @expect("source_adapters_standby_ratios")
    def test_every_watt_spoken_for_source_adapters_standby_ratios(self):
        """No source fed any standby draw."""
        return {"east": 0, "west": 0, "carport": 0}

    @expect("source_adapters_consumption_shares")
    def test_every_watt_spoken_for_source_adapters_consumption_shares(self):
        """The 400 W self-consumed came half from east and half from west."""
        return {"east": F(1, 2), "west": F(1, 2), "carport": 0}

    @expect("source_adapters_charging_shares")
    def test_every_watt_spoken_for_source_adapters_charging_shares(self):
        return TODO

    @expect("source_adapters_standby_shares")
    def test_every_watt_spoken_for_source_adapters_standby_shares(self):
        return TODO

    @expect("sink_adapters_consumption_shares")
    def test_every_watt_spoken_for_sink_adapters_consumption_shares(self):
        """The plug is the whole 400 W of self-consumption."""
        return {"plug": 1}

    # Layer 4 — money. Tariff 3/10 EUR/kWh, every PV system's LCOE 1/10 EUR/kWh,
    # no feed-in compensation configured. Nothing is imported, so every marginal
    # cost is zero.

    @expect("combined_coe_rate")
    def test_every_watt_spoken_for_combined_coe_rate(self):
        """Nothing imported, so there is no marginal cost."""
        return 0

    @expect("combined_lcoe_rate")
    def test_every_watt_spoken_for_combined_lcoe_rate(self):
        """2.2 kW of PV at 1/10 EUR/kWh = 11/50 EUR/h."""
        return F(11, 50)

    @expect("combined_avoided_cost_rate")
    def test_every_watt_spoken_for_combined_avoided_cost_rate(self):
        """The plug's 0.4 kW all came from local PV: 0.4 × 3/10 = 3/25 EUR/h."""
        return F(3, 25)

    @expect("combined_saving_rate")
    def test_every_watt_spoken_for_combined_saving_rate(self):
        """The avoided cost, less nothing — no device is drawing."""
        return F(3, 25)

    @expect("combined_export_compensation_rate")
    def test_every_watt_spoken_for_combined_export_compensation_rate(self):
        """No feed-in tariff is configured, so the export earns nothing."""
        return 0

    @expect("source_adapters_dynamic_coe")
    def test_every_watt_spoken_for_source_adapters_dynamic_coe(self):
        """Local generation has no marginal price."""
        return {"east": 0, "west": 0, "carport": 0}

    @expect("source_adapters_dynamic_lcoe")
    def test_every_watt_spoken_for_source_adapters_dynamic_lcoe(self):
        """Each PV system at its own LCOE."""
        return {"east": F(1, 10), "west": F(1, 10), "carport": F(1, 10)}

    @expect("source_adapters_coe_rate")
    def test_every_watt_spoken_for_source_adapters_coe_rate(self):
        """Every source's output at a marginal price of zero."""
        return {"east": 0, "west": 0, "carport": 0}

    @expect("source_adapters_export_compensation_rates")
    def test_every_watt_spoken_for_source_adapters_export_compensation_rates(self):
        """No feed-in tariff, so nothing earned per PV system."""
        return {"east": 0, "west": 0, "carport": 0}

    @expect("source_adapters_coo_rates")
    def test_every_watt_spoken_for_source_adapters_coo_rates(self):
        """No PV system is drawing, so none has an operating cost."""
        return {"east": 0, "west": 0, "carport": 0}

    @expect("source_adapters_lcoo_rates")
    def test_every_watt_spoken_for_source_adapters_lcoo_rates(self):
        """No PV system is drawing, so none has an operating cost."""
        return {"east": 0, "west": 0, "carport": 0}

    @expect("sink_adapters_coo_rates")
    def test_every_watt_spoken_for_sink_adapters_coo_rates(self):
        """Both sinks run on local PV only, whose marginal price is zero."""
        return {"grid": 0, "plug": 0}

    @expect("sink_adapters_lcoo_rates")
    def test_every_watt_spoken_for_sink_adapters_lcoo_rates(self):
        """Every source costs 1/10 EUR/kWh levelized: export 1.8 kW → 9/50,
        plug 0.4 kW → 1/25 EUR/h."""
        return {"grid": F(9, 50), "plug": F(1, 25)}

    @expect("sink_adapters_avoided_cost_rates")
    def test_every_watt_spoken_for_sink_adapters_avoided_cost_rates(self):
        """The plug's 0.4 kW, all local, at the 3/10 tariff it avoided."""
        return {"plug": F(3, 25)}

    @expect("home_base_load_avoided_cost_rate")
    def test_every_watt_spoken_for_home_base_load_avoided_cost_rate(self):
        """The base load draws nothing, so it avoids nothing."""
        return 0

    @expect("combined_coe")
    def test_every_watt_spoken_for_combined_coe(self):
        """A zero cost rate over 2.2 kW."""
        return 0

    @expect("combined_lcoe")
    def test_every_watt_spoken_for_combined_lcoe(self):
        """11/50 EUR/h over 2.2 kW — every source costs the same 1/10 EUR/kWh."""
        return F(1, 10)

    @expect("combined_consumption_cost_rate")
    def test_every_watt_spoken_for_combined_consumption_cost_rate(self):
        """Self-consumption is all local PV, free at the margin."""
        return 0

    @expect("combined_levelized_consumption_cost_rate")
    def test_every_watt_spoken_for_combined_levelized_consumption_cost_rate(self):
        """0.4 kW at 1/10 EUR/kWh."""
        return F(1, 25)

    @expect("combined_charging_cost_rate")
    def test_every_watt_spoken_for_combined_charging_cost_rate(self):
        """Nothing charged."""
        return 0

    @expect("combined_levelized_export_cost_rate")
    def test_every_watt_spoken_for_combined_levelized_export_cost_rate(self):
        """1.8 kW exported at 1/10 EUR/kWh."""
        return F(9, 50)

    @expect("combined_levelized_standby_cost_rate")
    def test_every_watt_spoken_for_combined_levelized_standby_cost_rate(self):
        """No standby draw."""
        return 0

    @expect("combined_device_operating_cost_rate")
    def test_every_watt_spoken_for_combined_device_operating_cost_rate(self):
        """No PV system or battery is drawing."""
        return 0

    @expect("adapters_saving_rates")
    def test_every_watt_spoken_for_adapters_saving_rates(self):
        """East and west each served 0.2 kW of the plug at the 3/10 tariff with no
        marginal cost of its own: 3/50 EUR/h. The carport served no load."""
        return {"east": F(3, 50), "west": F(3, 50), "carport": 0}

    @expect("adapters_levelized_saving_rates")
    def test_every_watt_spoken_for_adapters_levelized_saving_rates(self):
        """0.2 kW × (3/10 − 1/10) = 1/25 EUR/h for east and for west; the
        carport served no load."""
        return {"east": F(1, 25), "west": F(1, 25), "carport": 0}

    @expect("adapters_financial_return_rates")
    def test_every_watt_spoken_for_adapters_financial_return_rates(self):
        """The saving plus export earnings, which are zero without a tariff."""
        return {"east": F(3, 50), "west": F(3, 50), "carport": 0}

    @expect("adapters_levelized_financial_return_rates")
    def test_every_watt_spoken_for_adapters_levelized_financial_return_rates(self):
        """Levelized saving, less the exported watts at the system's own LCOE:
        1/25 − 0.8 × 1/10 = −1/25 for east and for west; carport: 0 − 0.2 × 1/10 = −1/50.
        Exporting for nothing costs money."""
        return {"east": F(-1, 25), "west": F(-1, 25), "carport": F(-1, 50)}

    @expect("combined_financial_return_rate")
    def test_every_watt_spoken_for_combined_financial_return_rate(self):
        """3/50 + 3/50 + 0."""
        return F(3, 25)
