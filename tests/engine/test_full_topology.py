"""Full-topology scenario: every engine property under one rich home.

This is the comprehensive value scenario — one realistic prosumer wiring
(grid + 2 PV + 3 batteries + 2 consumers) exercised across two complementary
snapshots, with an assertion for *every* ``PowerInsight`` property, the
implemented ones and the stubbed ones alike. It is the backbone the per-family
files fan out from: where the flow partition, gross-power split, three-tier
provenance, combined rates/prices and per-source/per-sink attribution are all
pinned against the same devices.

Two states, because a single grid cannot import and export at once:

* :meth:`midday_import_charging` — grid **importing**, both PV producing,
  every battery **charging**, both consumers loading. Activates the three-tier
  provenance (priority / home / leftover), the CHG + CON channels, and the
  cost/saving side that needs a priced import. Export, standby and discharge are
  zero here.
* :meth:`evening_export_discharge` — grid **exporting** surplus, ``pv1``
  producing while ``pv2`` sits in **standby**, ``bat1``/``bat2`` **discharging**
  and ``bat3`` idle, both consumers loading. Activates the EXP + STB channels,
  battery discharge as a source, the single-pass (no-import) provenance with the
  grid *itself* a sink, and the export-compensation family.

The device config is chosen to cover the branchy static axis in one place:

* **Unequal PV strings** (``pv1`` : ``pv2`` = 2 : 1) — the asymmetric
  local-generation split.
* **All three battery restriction modes** — ``bat1`` whole-mix (unrestricted,
  grid-capable leftover), ``bat2`` PV-only (priority tier while importing),
  ``bat3`` grid+``pv1`` (grid-capable leftover that only gets the ``pv1`` the
  priority and home tiers leave behind).
* **Both consumer modes** — ``cons1`` unrestricted, ``cons2`` solar-only
  (a smart plug on excess solar; a priority sink while importing).
* **A non-unit correction factor** on ``pv1`` (1.25) so the ``*_corrected``
  rates and ``levelized_correction_factors`` differ from their base.
* **A non-exporting battery** (``bat2`` ``exports=False``) so the export
  attribution has a device that is *paid* nothing for the watts it exports —
  the flag governs compensation, not routing, so bat2 still feeds the EXP
  channel and consequently turns a negative financial return.

Deliberately *out of scope* here (they belong to the small side scenarios, since
they are static config a state cannot vary): the empty-container degenerate paths
(no PV / no battery / no consumer), the missing-config ``None`` paths (grid
without a price entity, a device without an LCOE/LCOS), CO2 entities, and the
sensor-unavailable (``None``) propagation. This topology keeps every device
present and fully configured.

Expected values are hand-derived from first principles (the topology + state
each block declares), matching ``test_gross_power_ratios.py`` — never read back
from the engine. The implemented properties (flow view, combined powers, gross
shares, channel ratios, provenance) go green; the stubbed monetary families stay
red until they are implemented, because this scenario *is* the specification we
implement them against.

Alongside the per-property expectations, four invariants are asserted directly.
They need no hand-derived value and are the load-bearing part of the monetary
model (see ``docs/dev/engine-calculations.md``):

* **Cost conservation** — the four channel cost buckets sum to the cost of gross
  power. Every watt is bought once, in exactly one channel.
* **Savings additivity** — the per-device savings sum to the combined saving.
* **Avoided-cost duality** — the source side and the sink side (loads plus the
  home base load) of the CON channel come to the same number.
* **Source balance** — each source's per-channel watts sum back to its reading.

Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery ``+``
produce/discharge / ``-`` standby/charge; consumer ``-`` = load.
"""

from __future__ import annotations

import pytest

from tests.engine.scenario_framework import (
    Adapter,
    EngineScenario,
    State,
    state,
    topology,
)


def _uids(adapters):
    return {a.uid for a in adapters}


class TestGrid2Pv3Bat2Cons(EngineScenario):
    """Every engine property under grid + 2 PV + 3 batteries + 2 consumers."""

    @topology
    def grid_2pv_3bat_2cons(self):
        return (
            Adapter.grid(),
            # Unequal strings; pv1 carries a non-unit correction factor.
            Adapter.pv(
                "pv1",
                lcoe=0.12,
                lco2_intensity=50.0,
                exports=True,
                export_comp=0.08,
                correction_factor=1.25,
            ),
            Adapter.pv(
                "pv2",
                lcoe=0.10,
                lco2_intensity=45.0,
                exports=True,
                export_comp=0.08,
            ),
            # bat1: whole mix (unrestricted) -> grid-capable leftover sink.
            Adapter.battery(
                "bat1",
                lcos=0.15,
                lco2_intensity=100.0,
                exports=True,
                export_comp=0.08,
            ),
            # bat2: PV-only -> priority sink while importing; cannot export.
            Adapter.battery(
                "bat2",
                lcos=0.18,
                lco2_intensity=110.0,
                exports=False,
                charge_from=("pv1", "pv2"),
            ),
            # bat3: grid + pv1 -> grid-capable leftover; gets the pv1 the
            # priority + home tiers leave behind.
            Adapter.battery(
                "bat3",
                lcos=0.16,
                lco2_intensity=105.0,
                exports=True,
                export_comp=0.08,
                charge_from=("grid", "pv1"),
            ),
            # cons1: unrestricted; cons2: solar-only smart plug (priority sink).
            Adapter.consumer("cons1"),
            Adapter.consumer("cons2", power_from=("pv1", "pv2")),
        )

    # =====================================================================
    #   STATE 1 — midday import + charging
    #   grid importing; three-tier provenance active; CHG + CON channels;
    #   export = standby = discharge = 0.
    #
    #   gross = grid_import 1500 + pv1 2000 + pv2 1000 = 4500 W
    #   (source availability: grid 1/3, pv1 4/9, pv2 2/9)
    #   metered sinks: bat1 400 + bat2 1000 + bat3 600 + cons1 700 + cons2 300
    #                = 3000 W  ->  home base load 1500 W
    #   channels: charging 2000, consumption 2500 (metered 1000 + home 1500),
    #             export 0, standby 0
    # =====================================================================

    @state
    def midday_import_charging(self):
        return State(
            grid=1500,
            pv1=2000,
            pv2=1000,
            bat1=-400,
            bat2=-1000,
            bat3=-600,
            cons1=-700,
            cons2=-300,
            price=0.30,
        )

    # -- Flow partition ---------------------------------------------------

    def test_flow_partition(self, power_insight):
        # Grid imports -> it joins the sources. Every battery is charging, so
        # all three are sinks; both PV produce; both consumers load.
        assert _uids(power_insight.source_adapters) == {"grid", "pv1", "pv2"}
        assert _uids(power_insight.local_source_adapters) == {"pv1", "pv2"}
        assert _uids(power_insight.sink_adapters) == {
            "bat1", "bat2", "bat3", "cons1", "cons2",
        }
        assert _uids(power_insight.local_sink_adapters) == {
            "bat1", "bat2", "bat3", "cons1", "cons2",
        }
        assert _uids(power_insight.grid_adapters) == {"grid"}

    # -- Combined powers --------------------------------------------------

    def test_combined_powers(self, power_insight):
        assert power_insight.combined_grid_import == 1500.0
        assert power_insight.combined_grid_export == 0.0
        assert power_insight.combined_production == 3000.0
        assert power_insight.combined_charging_power == 2000.0
        assert power_insight.combined_discharging_power == 0.0
        assert power_insight.combined_standby_power == 0.0
        assert power_insight.combined_consumption == 2500.0

    # -- Gross power + share vectors --------------------------------------

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == 4500.0

    def test_source_and_sink_power_lists(self, power_insight):
        # Order is grid-first, then registration order within the flow group.
        # Source readings are positive, sink readings negative (as read).
        src_arr, src_index = power_insight.source_adapters_power
        assert src_index == ["grid", "pv1", "pv2"]
        assert src_arr == [1500.0, 2000.0, 1000.0]
        sink_arr, sink_index = power_insight.sink_adapters_power
        assert sink_index == ["bat1", "bat2", "bat3", "cons1", "cons2"]
        assert sink_arr == [-400.0, -1000.0, -600.0, -700.0, -300.0]

    def test_gross_power_shares(self, power_insight):
        src_arr, src_index = power_insight.source_adapters_gross_power_shares
        assert src_index == ["grid", "pv1", "pv2"]
        assert src_arr == [1/3, 4/9, 2/9]
        sink_arr, sink_index = power_insight.sink_adapters_gross_power_shares
        assert sink_index == ["bat1", "bat2", "bat3", "cons1", "cons2"]
        assert sink_arr == [4/45, 2/9, 2/15, 7/45, 1/15]

    # -- Gross-power channel ratios (EXP / CON / CHG / STB) ---------------

    def test_channel_ratios(self, power_insight):
        assert power_insight.gross_power_export_ratio == 0.0
        assert power_insight.gross_power_consumption_ratio == 5/9
        assert power_insight.gross_power_charging_ratio == 4/9
        assert power_insight.gross_power_standby_ratio == 0.0

    def test_channel_ratios_sum_to_one(self, power_insight):
        # Invariant (no hand-derived value needed): the four channels partition
        # gross power, so their ratios sum to 1 whenever consumption is not
        # clamped. Here gross 4500, charging 2000, standby 0, export 0,
        # consumption 2500 -> 4500/4500.
        total = (
            power_insight.gross_power_export_ratio
            + power_insight.gross_power_consumption_ratio
            + power_insight.gross_power_charging_ratio
            + power_insight.gross_power_standby_ratio
        )
        assert total == pytest.approx(1.0)

    # -- Source provenance (three-tier: priority / home / leftover) -------

    def test_source_provenance(self, power_insight):
        # bat2/cons2 are captive to the pv1/pv2 pool; bat3 is anchored to the
        # grid and takes it outright; bat1, cons1 and the home base load share
        # what is left. Compared row by row with ``pytest.approx``: these are
        # exact fractions, but the engine reaches them by a different arithmetic
        # route, so the last bit of the float need not match.
        expected = {
            "bat1": {
                "grid": 9/26,
                "pv1": 17/39,
                "pv2": 17/78,
            },
            "bat2": {
                "grid": 0.0,
                "pv1": 2/3,
                "pv2": 1/3,
            },
            "bat3": {
                "grid": 1.0,
                "pv1": 0.0,
                "pv2": 0.0,
            },
            "cons1": {
                "grid": 9/26,
                "pv1": 17/39,
                "pv2": 17/78,
            },
            "cons2": {
                "grid": 0.0,
                "pv1": 2/3,
                "pv2": 1/3,
            },
        }
        actual = power_insight.sink_adapters_source_shares
        assert actual.keys() == expected.keys()
        for uid, row in expected.items():
            assert actual[uid] == pytest.approx(row)

    def test_source_provenance_rows_sum_to_one(self, power_insight):
        # Invariant: every sink's provenance row sums to 1 (or 0 when its
        # allowed sources are all idle). No idle-collapse here, so all sum to 1.
        for row in power_insight.sink_adapters_source_shares.values():
            assert sum(row.values()) == pytest.approx(1.0)

    # -- Combined blended prices ------------------------------------------

    def test_combined_prices(self, power_insight):
        assert power_insight.combined_coe == 0.1
        assert power_insight.combined_lcoe == 79 / 450

    # -- Combined monetary rates (EUR/h) ----------------------------------

    def test_combined_rates(self, power_insight):
        assert power_insight.combined_coe_rate == 0.45
        assert power_insight.combined_lcoe_rate == 0.79
        assert power_insight.combined_coo_rate == 72 / 325
        assert power_insight.combined_lcoo_rate == 1777 / 4875
        assert power_insight.combined_avoided_cost_rate == 339 / 650
        assert power_insight.combined_saving_rate == 0.3
        assert power_insight.combined_levelized_saving_rate == -1 / 25
        assert power_insight.combined_financial_return_rate == 0.3
        assert power_insight.combined_levelized_financial_return_rate == -1 / 25
        # Zero while importing (nothing exported), but assert it explicitly.
        assert power_insight.combined_export_compensation_rate == 0.0

    def test_combined_rates_corrected(self, power_insight):
        # pv1's 1.25 correction factor makes these differ from the base rates:
        # its configured LCOE is the *base* 0.12, and the corrected results
        # price it at 0.12 * 1.25 = 0.15 instead.
        #
        #   lcoe_rate: 1.5*0.30 + 2.0*0.15 + 1.0*0.10 = 0.85 (base was 0.79)
        assert power_insight.combined_lcoe_rate_corrected == pytest.approx(0.85)
        #   lcoo_rate: bat1 0.4*(9/26*0.30 + 17/39*0.15 + 17/78*0.10) = 149/1950
        #              bat2 1.0*(2/3*0.15 + 1/3*0.10)                 = 2/15
        #              bat3 0.6*0.30                                  = 9/50
        assert power_insight.combined_lcoo_rate_corrected == pytest.approx(76 / 195)
        #   saving:  pv1 1.158974 kW * (0.30-0.15) + pv2 0.579487 * (0.30-0.10)
        #            = 113/390, minus the 76/195 above -> exactly -0.10
        assert power_insight.combined_levelized_saving_rate_corrected == pytest.approx(-0.1)
        # Nothing is exported here, so the financial return equals the saving.
        assert power_insight.combined_levelized_financial_return_rate_corrected == pytest.approx(-0.1)

    def test_levelized_correction_factors(self, power_insight):
        # uid -> correction_factor for prod adapters with an LCOE (pv1 = 1.25,
        # the rest 1.0). Batteries carry one too — they just default to 1.0.
        assert power_insight.levelized_correction_factors == {
            "pv1": 1.25,
            "pv2": 1.0,
            "bat1": 1.0,
            "bat2": 1.0,
            "bat3": 1.0,
        }

    # -- Per-source attribution: channel power / shares / ratios ----------

    def test_source_adapters_channel_power(self, power_insight):
        # Watts of each source's output going to each channel. Export and
        # standby are empty/zero while importing with no standby.
        assert power_insight.source_adapters_consumption_power == {
            "grid": 9900/13,
            "pv1": 45200 / 39,
            "pv2": 22600 / 39,
        }
        assert power_insight.source_adapters_charging_power == {
            "grid": 9600/13,
            "pv1": 32800 / 39,
            "pv2": 16400 / 39,
        }
        assert power_insight.source_adapters_export_power == {
            "grid": 0.0,
            "pv1": 0.0,
            "pv2": 0.0,
        }
        assert power_insight.source_adapters_standby_power == {
            "grid": 0.0,
            "pv1": 0.0,
            "pv2": 0.0,
        }

    def test_source_adapters_channel_shares(self, power_insight):
        assert power_insight.source_adapters_consumption_shares == {
            "grid": 99 / 325,
            "pv1": 452 / 975,
            "pv2": 226 / 975,
        }
        assert power_insight.source_adapters_charging_shares == {
            "grid": 24 / 65,
            "pv1": 82 / 195,
            "pv2": 41 / 195,
        }
        assert power_insight.source_adapters_export_shares == {
            "grid": 0.0,
            "pv1": 0.0,
            "pv2": 0.0,
        }
        assert power_insight.source_adapters_standby_shares == {
            "grid": 0.0,
            "pv1": 0.0,
            "pv2": 0.0,
        }

    def test_source_adapters_channel_ratios(self, power_insight):
        assert power_insight.source_adapters_consumption_ratios == {
            "grid": 33 / 65,
            "pv1": 113 / 195,
            "pv2": 113 / 195,
        }
        assert power_insight.source_adapters_charging_ratios == {
            "grid": 32 / 65,
            "pv1": 82 / 195,
            "pv2": 82 / 195,
        }
        assert power_insight.source_adapters_export_ratios == {
            "grid": 0.0,
            "pv1": 0.0,
            "pv2": 0.0,
        }
        assert power_insight.source_adapters_standby_ratios == {
            "grid": 0.0,
            "pv1": 0.0,
            "pv2": 0.0,
        }

    # -- Per-source attribution: rates ------------------------------------

    def test_source_adapters_rates(self, power_insight):
        # coe = the *marginal* price of what a source delivers: the grid's
        # tariff, and zero for local generation (the fuel is free).
        assert power_insight.source_adapters_coe_rate == {
            "grid": 0.45,   # 1.5 kW * 0.30
            "pv1": 0.0,
            "pv2": 0.0,
        }
        # lcoe additionally carries each device's own levelized cost (base,
        # uncorrected — pv1 at 0.12, not 0.15).
        assert power_insight.source_adapters_lcoe_rate == {
            "grid": 0.45,   # 1.5 kW * 0.30
            "pv1": 0.24,    # 2.0 kW * 0.12
            "pv2": 0.10,    # 1.0 kW * 0.10
        }

    def test_source_adapters_financial_rates(self, power_insight):
        assert power_insight.source_adapters_avoided_cost_rates == {
            "grid": 0.0,
            "pv1": 113 / 325,
            "pv2": 113 / 650,
        }
        assert power_insight.source_adapters_cost_saving_rates == {
            "grid": 0.0,
            "pv1": 113 / 325,
            "pv2": 113 / 650,
        }
        assert power_insight.source_adapters_levelized_cost_saving_rates == {
            "grid": 0.0,
            "pv1": 339 / 1625,
            "pv2": 113 / 975,
        }
        assert power_insight.source_adapters_financial_return_rates == {
            "grid": 0.0,
            "pv1": 113 / 325,
            "pv2": 113 / 650,
        }
        assert power_insight.source_adapters_levelized_financial_return_rates == {
            "grid": 0.0,
            "pv1": 339 / 1625,
            "pv2": 113 / 975,
        }

    # -- Per-sink attribution ---------------------------------------------

    def test_sink_adapters_attribution(self, power_insight):
        # Two loads (cons1, cons2) take their share of the CON channel. These
        # do *not* sum to 1: the 2500 W channel is mostly the 1500 W home base
        # load, which is not a consumer adapter.
        assert power_insight.sink_adapters_consumption_shares == {
            "cons1": 0.28,   # 700 / 2500
            "cons2": 0.12,   # 300 / 2500
        }
        assert power_insight.sink_adapters_coo_rates == {
            "bat1": 27 / 650,
            "bat2": 0.0,
            "bat3": 9 / 50,
            "cons1": 189 / 2600,
            "cons2": 0.0,
        }
        assert power_insight.sink_adapters_lcoo_rates == {
            "bat1": 347 / 4875,
            "bat2": 17 / 150,
            "bat3": 9 / 50,
            "cons1": 2429 / 19500,
            "cons2": 17 / 500,
        }

    # -- Channel cost buckets (the cost ledger) ---------------------------

    def test_channel_cost_buckets(self, power_insight):
        # Each channel's watts, priced at whatever supplied them. Marginal
        # (coe) prices only the grid contribution; local generation is free.
        #   CON: grid 9900/13 W -> 9.9/13 kW * 0.30 = 297/1300
        #   CHG: grid 9600/13 W -> 9.6/13 kW * 0.30 = 72/325
        assert power_insight.combined_consumption_cost_rate == pytest.approx(297 / 1300)
        assert power_insight.combined_charging_cost_rate == pytest.approx(72 / 325)
        assert power_insight.combined_standby_cost_rate == 0.0
        assert power_insight.combined_export_cost_rate == 0.0
        # Levelized additionally charges each local source its own LCOE.
        #   CON: 297/1300 (grid) + 226/1625 (pv1) + 113/1950 (pv2) = 8297/19500
        assert power_insight.combined_levelized_consumption_cost_rate == pytest.approx(8297 / 19500)
        assert power_insight.combined_levelized_charging_cost_rate == pytest.approx(1777 / 4875)
        assert power_insight.combined_levelized_standby_cost_rate == 0.0
        assert power_insight.combined_levelized_export_cost_rate == 0.0

    def test_cost_conservation_invariant(self, power_insight):
        # Invariant: every watt of gross power is bought exactly once and lands
        # in exactly one channel, so the buckets sum to the gross cost rate.
        assert (
            power_insight.combined_consumption_cost_rate
            + power_insight.combined_charging_cost_rate
            + power_insight.combined_standby_cost_rate
            + power_insight.combined_export_cost_rate
        ) == pytest.approx(power_insight.combined_coe_rate)
        assert (
            power_insight.combined_levelized_consumption_cost_rate
            + power_insight.combined_levelized_charging_cost_rate
            + power_insight.combined_levelized_standby_cost_rate
            + power_insight.combined_levelized_export_cost_rate
        ) == pytest.approx(power_insight.combined_lcoe_rate)

    # -- Per-device savings (the P&L) -------------------------------------

    def test_adapters_saving_rates(self, power_insight):
        # Every PV and battery appears in every flow role; a device with
        # nothing to contribute reads 0.0 rather than being absent.
        # Producing into CON earns (grid - own cost); charging spends the cost
        # of its own source mix.
        assert power_insight.adapters_saving_rates == {
            "pv1": pytest.approx(113 / 325),    # 1.158974 kW * 0.30
            "pv2": pytest.approx(113 / 650),    # 0.579487 kW * 0.30
            "bat1": pytest.approx(-27 / 650),   # 0.4 kW * 9/26 * 0.30 charged
            "bat2": 0.0,                        # charges on PV only -> free
            "bat3": pytest.approx(-9 / 50),     # 0.6 kW all grid * 0.30
        }
        assert power_insight.adapters_levelized_saving_rates == {
            "pv1": pytest.approx(339 / 1625),   # 1.158974 * (0.30 - 0.12)
            "pv2": pytest.approx(113 / 975),    # 0.579487 * (0.30 - 0.10)
            "bat1": pytest.approx(-347 / 4875),
            "bat2": pytest.approx(-17 / 150),
            "bat3": pytest.approx(-9 / 50),
        }

    def test_savings_additivity_invariant(self, power_insight):
        # Invariant: the per-device savings are a decomposition of the combined
        # saving, so they sum to it. Consumers contribute nothing (their
        # benefit is published as an avoided cost instead).
        assert sum(power_insight.adapters_saving_rates.values()) == pytest.approx(
            power_insight.combined_saving_rate
        )
        assert sum(
            power_insight.adapters_levelized_saving_rates.values()
        ) == pytest.approx(power_insight.combined_levelized_saving_rate)

    # -- Sink-side avoided cost + the home base load ----------------------

    def test_sink_avoided_cost_and_home_base_load(self, power_insight):
        # What each load did *not* pay the grid: its draw, times the non-grid
        # part of its mix, at the import price.
        assert power_insight.sink_adapters_avoided_cost_rates == {
            "cons1": pytest.approx(357 / 2600),   # 0.7 kW * 17/26 * 0.30
            "cons2": pytest.approx(0.09),         # 0.3 kW * 1.0  * 0.30
        }
        # The home base load is surfaced through its own properties rather than
        # as a dict key, so it can never collide with a user's device uid.
        assert power_insight.home_base_load_power == 1500.0
        assert power_insight.home_base_load_source_shares == pytest.approx(
            {"grid": 9 / 26, "pv1": 17 / 39, "pv2": 17 / 78}
        )
        assert power_insight.home_base_load_avoided_cost_rate == pytest.approx(153 / 520)

    def test_avoided_cost_duality_invariant(self, power_insight):
        # Invariant: the source side and the sink side measure the same saved
        # euro from opposite ends, so they agree. They must never be summed.
        source_side = sum(power_insight.source_adapters_avoided_cost_rates.values())
        sink_side = (
            sum(power_insight.sink_adapters_avoided_cost_rates.values())
            + power_insight.home_base_load_avoided_cost_rate
        )
        assert source_side == pytest.approx(sink_side)
        assert source_side == pytest.approx(power_insight.combined_avoided_cost_rate)

    # -- Source entities (enumeration, state-independent) -----------------

    def test_source_entities(self, power_insight):
        # These enumerate what the event handler subscribes to, so they are
        # compared as sets: uniqueness and coverage are the contract, order is
        # not. Every adapter contributes a power entity; only the grid has a
        # price entity, and this topology configures no CO2 entities at all.
        power_entities = {
            "sensor.grid_power",
            "sensor.pv1_power",
            "sensor.pv2_power",
            "sensor.bat1_power",
            "sensor.bat2_power",
            "sensor.bat3_power",
            "sensor.cons1_power",
            "sensor.cons2_power",
        }
        assert set(power_insight.source_entities_power) == power_entities
        assert set(power_insight.source_entities_price) == {"sensor.grid_price"}
        assert set(power_insight.source_entities_co2) == set()
        assert set(power_insight.source_entities) == power_entities | {
            "sensor.grid_price",
        }
        # No entity is subscribed to twice.
        assert len(power_insight.source_entities) == len(set(power_insight.source_entities))

    # =====================================================================
    #   STATE 2 — evening export + discharge + standby
    #   grid exporting; single-pass provenance (no import tier); EXP + STB
    #   channels; bat1/bat2 discharge (sources); bat3 idle; charging = 0.
    #
    #   gross = pv1 3000 + bat1 400 + bat2 600 = 4000 W
    #   channels: export 1200, standby 50, charging 0,
    #             consumption residual 4000 - 1200 - 0 - 50 = 2750 W
    #   metered sinks: grid 1200 + pv2 50 + cons1 500 + cons2 250 = 2000 W
    #                -> home base load 2000 W (so CON = 750 metered + 2000 home)
    # =====================================================================

    @state
    def evening_export_discharge(self):
        return State(
            grid=-1200,
            pv1=3000,
            pv2=-50,
            bat1=400,
            bat2=600,
            bat3=0,
            cons1=-500,
            cons2=-250,
            price=0.25,
        )

    # -- Flow partition (export / discharge / standby / idle) -------------

    def test_flow_partition_export(self, power_insight):
        # Sources: pv1 + discharging bat1/bat2. Sinks: exporting grid, standby
        # pv2, both loads. bat3 (0 W) is idle -> in neither group.
        assert _uids(power_insight.source_adapters) == {"pv1", "bat1", "bat2"}
        assert _uids(power_insight.local_source_adapters) == {"pv1", "bat1", "bat2"}
        assert _uids(power_insight.sink_adapters) == {"grid", "pv2", "cons1", "cons2"}
        assert _uids(power_insight.local_sink_adapters) == {"pv2", "cons1", "cons2"}
        assert _uids(power_insight.grid_adapters) == {"grid"}

    # -- Combined powers (export / discharge / standby) -------------------

    def test_combined_powers_export(self, power_insight):
        assert power_insight.combined_grid_import == 0.0
        assert power_insight.combined_grid_export == 1200.0
        # Production counts the PV systems only — pv2 is drawing standby, so it
        # contributes nothing here (and 50 W to combined_standby_power).
        assert power_insight.combined_production == 3000.0
        assert power_insight.combined_charging_power == 0.0
        assert power_insight.combined_discharging_power == 1000.0
        assert power_insight.combined_standby_power == 50.0
        # Residual: 4000 - 1200 export - 0 charging - 50 standby.
        assert power_insight.combined_consumption == 2750.0

    def test_gross_power_export(self, power_insight):
        assert power_insight.gross_power == 4000.0

    def test_gross_power_shares_export(self, power_insight):
        # The exporting grid is a sink, so it leaves the source index entirely
        # and the two discharging batteries take its place.
        src_arr, src_index = power_insight.source_adapters_gross_power_shares
        assert src_index == ["pv1", "bat1", "bat2"]
        assert src_arr == [0.75, 0.1, 0.15]
        sink_arr, sink_index = power_insight.sink_adapters_gross_power_shares
        assert sink_index == ["grid", "pv2", "cons1", "cons2"]
        assert sink_arr == [0.3, 0.0125, 0.125, 0.0625]

    # -- Gross-power channel ratios (export + standby non-zero) -----------

    def test_channel_ratios_export(self, power_insight):
        assert power_insight.gross_power_export_ratio == 0.3          # 1200/4000
        assert power_insight.gross_power_consumption_ratio == 11 / 16  # 2750/4000
        assert power_insight.gross_power_charging_ratio == 0.0
        assert power_insight.gross_power_standby_ratio == 0.0125       # 50/4000
        # Of what stayed home and was not stored (4000 - 1200 - 0 = 2800), the
        # fraction actually used rather than lost to standby: 2750/2800.
        assert power_insight.gross_power_applicable_consumption_ratio == pytest.approx(55 / 56)

    # -- Source provenance (single pass; exporting grid is itself a sink) --

    def test_source_provenance_export(self, power_insight):
        # No import, so there is no grid tier to go first: one pass. cons2 is
        # masked to pv1 (its other allowed source, pv2, is in standby and
        # therefore not a source) and is served first as the only restricted
        # sink, taking 250 W of pv1. That leaves pv1 2750 + bat1 400 + bat2 600
        # = 3750 W for the four unrestricted sinks (grid 1200, pv2 50,
        # cons1 500, home 2000 = 3750 W), which they share in equal proportion.
        #
        # bat2 is exports=False, which is a *compensation* flag: it does not
        # stop exported watts being attributed to it, only paid for. So the
        # exporting grid draws on bat2 like any other sink.
        leftover = {"pv1": 11 / 15, "bat1": 8 / 75, "bat2": 4 / 25}
        expected = {
            "grid": leftover,
            "pv2": leftover,
            "cons1": leftover,
            "cons2": {"pv1": 1.0, "bat1": 0.0, "bat2": 0.0},
        }
        actual = power_insight.sink_adapters_source_shares
        assert actual.keys() == expected.keys()
        for uid, row in expected.items():
            assert actual[uid] == pytest.approx(row)

    def test_source_provenance_rows_sum_to_one_export(self, power_insight):
        # Invariant: no sink is stranded here (cons2 keeps pv1), so every row
        # still sums to 1.
        for row in power_insight.sink_adapters_source_shares.values():
            assert sum(row.values()) == pytest.approx(1.0)

    # -- Export compensation (combined + per source) ----------------------

    def test_export_compensation(self, power_insight):
        # Only the watts a device is credited for: pv1 and bat1 export at 0.08,
        # bat2 exports 192 W but is exports=False, so it earns nothing on them.
        assert power_insight.source_adapters_export_compensation_rates == {
            "pv1": pytest.approx(44 / 625),    # 0.880 kW * 0.08
            "bat1": pytest.approx(32 / 3125),  # 0.128 kW * 0.08
            "bat2": 0.0,
        }
        assert power_insight.combined_export_compensation_rate == pytest.approx(252 / 3125)

    # -- Per-source export attribution (non-zero while exporting) ---------

    def test_source_adapters_export_attribution(self, power_insight):
        # The exporting grid is just another sink, so its provenance row *is*
        # the export attribution: 1200 W split 11/15, 8/75, 4/25.
        assert power_insight.source_adapters_export_power == {
            "pv1": pytest.approx(880.0),
            "bat1": pytest.approx(128.0),
            "bat2": pytest.approx(192.0),
        }
        assert power_insight.source_adapters_export_shares == {
            "pv1": pytest.approx(11 / 15),
            "bat1": pytest.approx(8 / 75),
            "bat2": pytest.approx(4 / 25),
        }
        # Fraction of each source's own output. pv1 differs from the batteries
        # because it also had to cover cons2 on its own.
        assert power_insight.source_adapters_export_ratios == {
            "pv1": pytest.approx(22 / 75),   # 880 / 3000
            "bat1": pytest.approx(0.32),     # 128 / 400
            "bat2": pytest.approx(0.32),     # 192 / 600
        }

    # -- Per-source standby attribution (pv2 in standby) ------------------

    def test_source_adapters_standby_attribution(self, power_insight):
        # Standby is routed like any other draw: pv2's 50 W carries the same
        # unrestricted mix as the other leftover sinks. Attributing it by gross
        # share instead would break the source-balance invariant below.
        assert power_insight.source_adapters_standby_power == {
            "pv1": pytest.approx(110 / 3),   # 50 * 11/15
            "bat1": pytest.approx(16 / 3),   # 50 * 8/75
            "bat2": pytest.approx(8.0),      # 50 * 4/25
        }
        assert power_insight.source_adapters_standby_shares == {
            "pv1": pytest.approx(11 / 15),
            "bat1": pytest.approx(8 / 75),
            "bat2": pytest.approx(4 / 25),
        }
        assert power_insight.source_adapters_standby_ratios == {
            "pv1": pytest.approx(11 / 900),
            "bat1": pytest.approx(1 / 75),
            "bat2": pytest.approx(1 / 75),
        }

    def test_source_balance_invariant(self, power_insight):
        # Invariant: the four channels partition each source's output, so a
        # source's per-channel watts sum back to its reading. This is what
        # forces every channel attribution through the provenance allocation.
        expected = {"pv1": 3000.0, "bat1": 400.0, "bat2": 600.0}
        for uid, reading in expected.items():
            total = (
                power_insight.source_adapters_consumption_power[uid]
                + power_insight.source_adapters_charging_power[uid]
                + power_insight.source_adapters_export_power[uid]
                + power_insight.source_adapters_standby_power[uid]
            )
            assert total == pytest.approx(reading)

    # -- Per-source dynamic prices (battery sources use their charge mix) --

    def test_source_adapters_dynamic_prices(self, power_insight):
        # bat1/bat2 are *discharging*, and the mix they charged on happened
        # earlier — which a snapshot engine cannot see. So the dynamic price
        # falls back to each battery's flat LCOS while discharging, and the
        # marginal side reads 0.0 because that energy's cost was already booked
        # when it was charged (see docs/dev/engine-calculations.md).
        assert power_insight.source_adapters_dynamic_coe == {
            "pv1": 0.0,
            "bat1": 0.0,
            "bat2": 0.0,
        }
        assert power_insight.source_adapters_dynamic_lcoe == {
            "pv1": 0.12,
            "bat1": 0.15,
            "bat2": 0.18,
        }

    # -- Channel cost buckets with all four channels live -----------------

    def test_channel_cost_buckets_export(self, power_insight):
        # Nothing is imported, so no watt has a marginal price: the whole
        # marginal ledger is zero even though the levelized one is not.
        assert power_insight.combined_consumption_cost_rate == 0.0
        assert power_insight.combined_charging_cost_rate == 0.0
        assert power_insight.combined_standby_cost_rate == 0.0
        assert power_insight.combined_export_cost_rate == 0.0
        # Levelized, each source carries its own LCOE into every channel:
        #   CON 2083.33 W pv1 * 0.12 + 266.67 bat1 * 0.15 + 400 bat2 * 0.18
        assert power_insight.combined_levelized_consumption_cost_rate == pytest.approx(0.362)
        assert power_insight.combined_levelized_charging_cost_rate == 0.0
        assert power_insight.combined_levelized_standby_cost_rate == pytest.approx(0.00664)
        assert power_insight.combined_levelized_export_cost_rate == pytest.approx(0.15936)

    def test_cost_conservation_invariant_export(self, power_insight):
        # Invariant, now with all four channels non-trivial: gross cost is
        # 3.0*0.12 + 0.4*0.15 + 0.6*0.18 = 0.528, and the buckets partition it.
        assert (
            power_insight.combined_levelized_consumption_cost_rate
            + power_insight.combined_levelized_charging_cost_rate
            + power_insight.combined_levelized_standby_cost_rate
            + power_insight.combined_levelized_export_cost_rate
        ) == pytest.approx(power_insight.combined_lcoe_rate)
        assert power_insight.combined_lcoe_rate == pytest.approx(0.528)

    # -- Per-device savings across every flow role ------------------------

    def test_adapters_saving_rates_export(self, power_insight):
        # Every role is represented: pv1 producing, bat1/bat2 discharging,
        # pv2 drawing standby (a cost), bat3 idle (present, and 0.0).
        assert power_insight.adapters_saving_rates == {
            "pv1": pytest.approx(25 / 48),   # 2.083333 kW * 0.25
            "pv2": 0.0,                      # standby, but its mix is free
            "bat1": pytest.approx(1 / 15),   # 0.266667 kW * 0.25
            "bat2": pytest.approx(0.1),      # 0.4 kW * 0.25
            "bat3": 0.0,
        }
        # Levelized, a discharge is worth (grid - LCOS) and standby costs the
        # levelized price of the mix it burns (0.05 kW * 0.1328).
        assert power_insight.adapters_levelized_saving_rates == {
            "pv1": pytest.approx(13 / 48),    # 2.083333 * (0.25 - 0.12)
            "pv2": pytest.approx(-0.00664),
            "bat1": pytest.approx(2 / 75),    # 0.266667 * (0.25 - 0.15)
            "bat2": pytest.approx(7 / 250),   # 0.4 * (0.25 - 0.18)
            "bat3": 0.0,
        }

    def test_savings_additivity_invariant_export(self, power_insight):
        assert sum(power_insight.adapters_saving_rates.values()) == pytest.approx(
            power_insight.combined_saving_rate
        )
        assert sum(
            power_insight.adapters_levelized_saving_rates.values()
        ) == pytest.approx(power_insight.combined_levelized_saving_rate)
        assert power_insight.combined_saving_rate == pytest.approx(0.6875)
        assert power_insight.combined_levelized_saving_rate == pytest.approx(0.31886)

    # -- Financial return = saving + compensation - cost of exporting -----

    def test_financial_return_export(self, power_insight):
        # bat2 goes *negative*: it exports 192 W at its 0.18 LCOS and, being
        # exports=False, is paid nothing for them.
        assert power_insight.adapters_levelized_financial_return_rates == {
            "pv1": pytest.approx(0.2356333),
            "pv2": pytest.approx(-0.00664),
            "bat1": pytest.approx(0.0177067),
            "bat2": pytest.approx(-0.00656),
            "bat3": 0.0,
        }
        assert power_insight.combined_financial_return_rate == pytest.approx(0.76814)
        assert power_insight.combined_levelized_financial_return_rate == pytest.approx(0.24014)

    # -- Sink-side avoided cost + the home base load ----------------------

    def test_sink_avoided_cost_and_home_base_load_export(self, power_insight):
        # No import at all, so every load's mix is fully local and it avoids
        # the whole import price on its whole draw.
        assert power_insight.sink_adapters_avoided_cost_rates == {
            "cons1": pytest.approx(0.125),    # 0.5 kW * 1.0 * 0.25
            "cons2": pytest.approx(0.0625),   # 0.25 kW * 1.0 * 0.25
        }
        assert power_insight.home_base_load_power == 2000.0
        assert power_insight.home_base_load_source_shares == pytest.approx(
            {"pv1": 11 / 15, "bat1": 8 / 75, "bat2": 4 / 25}
        )
        assert power_insight.home_base_load_avoided_cost_rate == pytest.approx(0.5)

    def test_avoided_cost_duality_invariant_export(self, power_insight):
        source_side = sum(power_insight.source_adapters_avoided_cost_rates.values())
        sink_side = (
            sum(power_insight.sink_adapters_avoided_cost_rates.values())
            + power_insight.home_base_load_avoided_cost_rate
        )
        assert source_side == pytest.approx(sink_side)
        assert source_side == pytest.approx(power_insight.combined_avoided_cost_rate)
