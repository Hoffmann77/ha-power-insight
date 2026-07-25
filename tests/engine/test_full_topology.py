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
  attribution has a device that cannot feed the EXP channel.

Deliberately *out of scope* here (they belong to the small side scenarios, since
they are static config a state cannot vary): the empty-container degenerate paths
(no PV / no battery / no consumer), the missing-config ``None`` paths (grid
without a price entity, a device without an LCOE/LCOS), CO2 entities, and the
sensor-unavailable (``None``) propagation. This topology keeps every device
present and fully configured.

Expected values are left as ``...`` to be filled in by hand from first
principles (the topology + state each block declares), matching
``test_gross_power_ratios.py``. Once filled, the implemented properties should go
green immediately and the stubbed families stay red until they are implemented —
this scenario is the specification we implement the stubs against.

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
                "bat1", lcos=0.15, lco2_intensity=100.0, exports=True, export_comp=0.08
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
    #   metered sinks: bat1 500 + bat2 1000 + bat3 600 + cons1 700 + cons2 300
    #                = 3100 W  ->  home base load 1400 W
    # =====================================================================

    @state
    def midday_import_charging(self):
        return State(
            grid=1500,
            pv1=2000,
            pv2=1000,
            bat1=-500,
            bat2=-1000,
            bat3=-600,
            cons1=-700,
            cons2=-300,
            price=0.30,
        )

    # -- Flow partition ---------------------------------------------------

    def test_flow_partition(self, power_insight):
        assert _uids(power_insight.source_adapters) == ...
        assert _uids(power_insight.local_source_adapters) == ...
        assert _uids(power_insight.sink_adapters) == ...
        assert _uids(power_insight.local_sink_adapters) == ...
        assert _uids(power_insight.grid_adapters) == ...

    # -- Combined powers --------------------------------------------------

    def test_combined_powers(self, power_insight):
        assert power_insight.combined_grid_import == ...
        assert power_insight.combined_grid_export == ...
        assert power_insight.combined_production == ...
        assert power_insight.combined_charging_power == ...
        assert power_insight.combined_discharging_power == ...
        assert power_insight.combined_standby_power == ...
        assert power_insight.combined_consumption == ...

    # -- Gross power + share vectors --------------------------------------

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == ...

    def test_source_and_sink_power_arrays(self, power_insight):
        src_arr, src_index = power_insight.source_adapters_power
        assert src_index == ...
        assert src_arr.tolist() == ...
        sink_arr, sink_index = power_insight.sink_adapters_power
        assert sink_index == ...
        assert sink_arr.tolist() == ...

    def test_gross_power_shares(self, power_insight):
        src_arr, src_index = power_insight.source_adapters_gross_power_shares
        assert src_index == ...
        assert src_arr.tolist() == ...
        sink_arr, sink_index = power_insight.sink_adapters_gross_power_shares
        assert sink_index == ...
        assert sink_arr.tolist() == ...

    # -- Gross-power channel ratios (EXP / CON / CHG / STB) ---------------

    def test_channel_ratios(self, power_insight):
        assert power_insight.gross_power_export_ratio == ...
        assert power_insight.gross_power_consumption_ratio == ...
        assert power_insight.gross_power_charging_ratio == ...
        assert power_insight.gross_power_standby_ratio == ...
        assert power_insight.gross_power_applicable_consumption_ratio == ...

    def test_channel_ratios_sum_to_one(self, power_insight):
        # Invariant (no hand-derived value needed): the four channels partition
        # gross power, so their ratios sum to 1 whenever consumption is not
        # clamped. Here gross 4500, charging 2100, standby 0, export 0,
        # consumption 2400 -> 4500/4500.
        total = (
            power_insight.gross_power_export_ratio
            + power_insight.gross_power_consumption_ratio
            + power_insight.gross_power_charging_ratio
            + power_insight.gross_power_standby_ratio
        )
        assert total == pytest.approx(1.0)

    # -- Source provenance (three-tier: priority / home / leftover) -------

    def test_source_provenance(self, power_insight):
        # priority: bat2, cons2 (PV-only) share the pv1/pv2 pool;
        # home base load (1400 W) eats remaining local, grid as fallback;
        # leftover: bat1 (whole mix), bat3 (grid+pv1), cons1 (unrestricted).
        assert power_insight.sink_adapters_source_shares == ...

    def test_source_provenance_rows_sum_to_one(self, power_insight):
        # Invariant: every sink's provenance row sums to 1 (or 0 when its
        # allowed sources are all idle). No idle-collapse here, so all sum to 1.
        for row in power_insight.sink_adapters_source_shares.values():
            assert sum(row.values()) == pytest.approx(1.0)

    # -- Combined blended prices ------------------------------------------

    def test_combined_prices(self, power_insight):
        assert power_insight.combined_coe == ...
        assert power_insight.combined_lcoe == ...

    # -- Combined monetary rates (EUR/h) ----------------------------------

    def test_combined_rates(self, power_insight):
        assert power_insight.combined_coe_rate == ...
        assert power_insight.combined_lcoe_rate == ...
        assert power_insight.combined_coo_rate == ...
        assert power_insight.combined_lcoo_rate == ...
        assert power_insight.combined_avoided_cost_rate == ...
        assert power_insight.combined_saving_rate == ...
        assert power_insight.combined_levelized_saving_rate == ...
        assert power_insight.combined_financial_return_rate == ...
        assert power_insight.combined_levelized_financial_return_rate == ...
        # Zero while importing (nothing exported), but assert it explicitly.
        assert power_insight.combined_export_compensation_rate == ...

    def test_combined_rates_corrected(self, power_insight):
        # pv1's 1.25 correction factor makes these differ from the base rates.
        assert power_insight.combined_lcoe_rate_corrected == ...
        assert power_insight.combined_lcoo_rate_corrected == ...
        assert power_insight.combined_levelized_saving_rate_corrected == ...
        assert power_insight.combined_levelized_financial_return_rate_corrected == ...

    def test_levelized_correction_factors(self, power_insight):
        # uid -> correction_factor for prod adapters with an LCOE (pv1 = 1.25,
        # the rest 1.0).
        assert power_insight.levelized_correction_factors == ...

    # -- Per-source attribution: channel power / shares / ratios ----------

    def test_source_adapters_channel_power(self, power_insight):
        # Watts of each source's output going to each channel. Export and
        # standby are empty/zero while importing with no standby.
        assert power_insight.source_adapters_consumption_power == ...
        assert power_insight.source_adapters_charging_power == ...
        assert power_insight.source_adapters_export_power == ...
        assert power_insight.source_adapters_standby_power == ...

    def test_source_adapters_channel_shares(self, power_insight):
        assert power_insight.source_adapters_consumption_shares == ...
        assert power_insight.source_adapters_charging_shares == ...
        assert power_insight.source_adapters_export_shares == ...
        assert power_insight.source_adapters_standby_shares == ...

    def test_source_adapters_channel_ratios(self, power_insight):
        assert power_insight.source_adapters_consumption_ratios == ...
        assert power_insight.source_adapters_charging_ratios == ...
        assert power_insight.source_adapters_export_ratios == ...
        assert power_insight.source_adapters_standby_ratios == ...

    # -- Per-source attribution: rates ------------------------------------

    def test_source_adapters_rates(self, power_insight):
        assert power_insight.source_adapters_coe_rate == ...
        assert power_insight.source_adapters_lcoe_rate == ...
        assert power_insight.source_adapters_coo_rates == ...
        assert power_insight.source_adapters_lcoo_rates == ...

    def test_source_adapters_financial_rates(self, power_insight):
        assert power_insight.source_adapters_avoided_cost_rates == ...
        assert power_insight.source_adapters_cost_saving_rates == ...
        assert power_insight.source_adapters_levelized_cost_saving_rates == ...
        assert power_insight.source_adapters_financial_return_rates == ...
        assert power_insight.source_adapters_levelized_financial_return_rates == ...

    # -- Per-sink attribution ---------------------------------------------

    def test_sink_adapters_attribution(self, power_insight):
        # Two loads (cons1, cons2) split the metered self-consumption.
        assert power_insight.sink_adapters_consumption_shares == ...
        assert power_insight.sink_adapters_coo_rates == ...
        assert power_insight.sink_adapters_lcoo_rates == ...

    # -- Source entities (enumeration, state-independent) -----------------

    def test_source_entities(self, power_insight):
        assert power_insight.source_entities == ...
        assert power_insight.source_entities_power == ...
        assert power_insight.source_entities_price == ...
        assert power_insight.source_entities_co2 == ...

    # =====================================================================
    #   STATE 2 — evening export + discharge + standby
    #   grid exporting; single-pass provenance (no import tier); EXP + STB
    #   channels; bat1/bat2 discharge (sources); bat3 idle; charging = 0.
    #
    #   gross = pv1 3000 + bat1 400 + bat2 600 = 4000 W
    #   channels: export 1200, standby 50, charging 0,
    #             consumption residual 4000 - 1200 - 0 - 50 = 2750 W
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
        assert _uids(power_insight.source_adapters) == ...
        assert _uids(power_insight.local_source_adapters) == ...
        assert _uids(power_insight.sink_adapters) == ...
        assert _uids(power_insight.local_sink_adapters) == ...
        assert _uids(power_insight.grid_adapters) == ...

    # -- Combined powers (export / discharge / standby) -------------------

    def test_combined_powers_export(self, power_insight):
        assert power_insight.combined_grid_import == ...
        assert power_insight.combined_grid_export == ...
        assert power_insight.combined_production == ...
        assert power_insight.combined_charging_power == ...
        assert power_insight.combined_discharging_power == ...
        assert power_insight.combined_standby_power == ...
        assert power_insight.combined_consumption == ...

    def test_gross_power_export(self, power_insight):
        assert power_insight.gross_power == ...

    def test_gross_power_shares_export(self, power_insight):
        src_arr, src_index = power_insight.source_adapters_gross_power_shares
        assert src_index == ...
        assert src_arr.tolist() == ...
        sink_arr, sink_index = power_insight.sink_adapters_gross_power_shares
        assert sink_index == ...
        assert sink_arr.tolist() == ...

    # -- Gross-power channel ratios (export + standby non-zero) -----------

    def test_channel_ratios_export(self, power_insight):
        assert power_insight.gross_power_export_ratio == ...
        assert power_insight.gross_power_consumption_ratio == ...
        assert power_insight.gross_power_charging_ratio == ...
        assert power_insight.gross_power_standby_ratio == ...
        assert power_insight.gross_power_applicable_consumption_ratio == ...

    # -- Source provenance (single pass; exporting grid is itself a sink) --

    def test_source_provenance_export(self, power_insight):
        # No import -> priority tier empty; every sink (incl. the exporting
        # grid) shares pv1/bat1/bat2 in one pass. cons2 is masked to pv1 (its
        # other allowed source, pv2, is in standby -> not a source).
        assert power_insight.sink_adapters_source_shares == ...

    # -- Export compensation (combined + per source) ----------------------

    def test_export_compensation(self, power_insight):
        assert power_insight.combined_export_compensation_rate == ...
        assert power_insight.source_adapters_export_compensation_rates == ...

    # -- Per-source export attribution (non-zero while exporting) ---------

    def test_source_adapters_export_attribution(self, power_insight):
        assert power_insight.source_adapters_export_power == ...
        assert power_insight.source_adapters_export_shares == ...
        assert power_insight.source_adapters_export_ratios == ...

    # -- Per-source standby attribution (pv2 in standby) ------------------

    def test_source_adapters_standby_attribution(self, power_insight):
        # STB has no routing -> attributed to sources in proportion to gross.
        assert power_insight.source_adapters_standby_power == ...
        assert power_insight.source_adapters_standby_shares == ...
        assert power_insight.source_adapters_standby_ratios == ...

    # -- Per-source dynamic prices (battery sources use their charge mix) --

    def test_source_adapters_dynamic_prices(self, power_insight):
        # bat1/bat2 are sources here; their blended cost derives from the mix
        # they charged on, not a flat rate.
        assert power_insight.source_adapters_dynamic_coe == ...
        assert power_insight.source_adapters_dynamic_lcoe == ...
