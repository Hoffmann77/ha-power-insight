"""Power-flow decisions, each pinned by a hand-derived harness.

Every block in :class:`TestPowerFlow` pins exactly one decision the engine
makes about *where power goes* — one ``@topology``, one ``@state``, and the
``@expect_attribute`` claims that only hold if the decision is honoured. The
values are derived by hand from the decision, never read back from the
engine. Each block's ``@state`` docstring names its decision and the place in
``docs/dev/engine-calculations.md`` that states it, so a red test here reads as
"this decision no longer holds", not as "some number moved".

Add a block whenever a new decision is made about power flow, as the smallest
wiring that can tell the decision apart from its alternatives.

Answers are written as watts — ``{sink: {source: watts}}``, the form they are
derived in — and :func:`rows` turns them into the shares the engine publishes.
A row lists every source providing this snapshot, zeros included.
"""

from __future__ import annotations

from fractions import Fraction as F

import pytest

from tests.engine.scenario_framework import (
    Adapter,
    EngineScenario,
    State,
    expect_attribute,
    state,
    topology,
)


def rows(watts: dict[str, dict[str, int | F]]) -> dict[str, dict[str, F]]:
    """A ``{sink: {source: watts}}`` table as the provenance rows it implies.

    A row with no watts at all — a sink with nothing it may draw from — is a
    row of zeros, not a division by zero.
    """
    out = {}
    for sink, row in watts.items():
        total = sum(row.values())
        out[sink] = {src: F(w) / total if total else F(0) for src, w in row.items()}
    return out


class TestPowerFlow(EngineScenario):
    """Where each sink's power comes from."""

    # ----------------------------------------------------------------------
    # Decision: an adapter reading exactly 0 W is in neither flow group.

    @topology
    def idle_battery(self):
        return (
            Adapter.grid(),
            Adapter.battery("bat1"),
            Adapter.consumer("plug"),
        )

    @state
    def battery_at_zero(self):
        """Decision: an adapter reading exactly 0 W belongs to neither flow
        group (engine-calculations.md, "Conventions this builds on").

        The battery neither charges nor discharges, so it is not a source any
        row can name and not a sink with a row of its own.
        """
        return State(grid=500, bat1=0, plug=-100)

    @expect_attribute("sink_adapters_source_shares")
    def test_battery_at_zero_power_flow(self):
        return rows({"plug": {"grid": 100}})

    # ----------------------------------------------------------------------
    # Decision: an unrestricted sink takes the raw source mix, and a PV system
    # drawing standby is such a sink — not negative production.

    @topology
    def pv_in_standby_beside_a_producing_one(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1"),
            Adapter.pv("pv2"),
        )

    @state
    def one_producing_one_in_standby(self):
        """Decision: an unrestricted sink's row is the raw source mix, and a PV
        system drawing standby is a sink like any other (engine-calculations.md,
        "Conventions this builds on"; rule 3 of "Choosing among valid
        allocations").

        Nothing is restricted, so every sink — pv1's 20 W standby and the 780 W
        base load alike — draws grid and pv2 in the ratio they supply, 5 : 3.
        """
        return State(grid=500, pv1=-20, pv2=300)

    @expect_attribute("sink_adapters_source_shares")
    def test_one_producing_one_in_standby_power_flow(self):
        return rows({"pv1": {"grid": F(25, 2), "pv2": F(15, 2)}})

    @expect_attribute("home_base_load_source_shares")
    def test_one_producing_one_in_standby_base_load(self):
        return {"grid": F(5, 8), "pv2": F(3, 8)}

    @expect_attribute("source_adapters_standby_power")
    def test_one_producing_one_in_standby_standby_power(self):
        """The standby watts land in the standby channel, per supplying source."""
        return {"grid": F(25, 2), "pv2": F(15, 2)}

    # ----------------------------------------------------------------------
    # Decision: restricted sinks are served before unrestricted ones.

    @topology
    def load_captive_to_pv(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1"),
            Adapter.consumer("cons1", power_from=("pv1",)),
        )

    @state
    def captive_load_fits(self):
        """Decision: unrestricted sinks — the base load included — take what is
        left after the restricted ones (rule 3 of "Choosing among valid
        allocations").

        cons1 may only use pv1 and takes 500 of its 600 W. The 900 W base load
        could have used pv1 too, but gets only the 100 W left, and 800 W grid.
        """
        return State(grid=800, pv1=600, cons1=-500)

    @expect_attribute("sink_adapters_source_shares")
    def test_captive_load_fits_power_flow(self):
        return rows({"cons1": {"grid": 0, "pv1": 500}})

    @expect_attribute("home_base_load_source_shares")
    def test_captive_load_fits_base_load(self):
        return {"grid": F(8, 9), "pv1": F(1, 9)}

    # ----------------------------------------------------------------------
    # Decision: a broken restriction is reported, not hidden. (Same wiring.)

    @state
    def captive_load_exceeds_its_source(self):
        """Decision: when the meter contradicts a restriction, the restriction
        is relaxed and the shortfall reported as a deficit (engine-calculations.md,
        "a broken restriction is reported, not hidden").

        cons1 may only use pv1, draws 500 W, and pv1 makes 300 W. The other
        200 W came from somewhere — the grid, the only other source — and is
        reported as cons1's restriction deficit. The 600 W base load is all grid.
        """
        return State(grid=800, pv1=300, cons1=-500)

    @expect_attribute("sink_adapters_source_shares")
    def test_captive_load_exceeds_its_source_power_flow(self):
        return rows({"cons1": {"grid": 200, "pv1": 300}})

    @expect_attribute("sink_adapters_restriction_deficit")
    def test_captive_load_exceeds_its_source_restriction_deficit(self):
        return {"cons1": 200}

    @expect_attribute("home_base_load_source_shares")
    def test_captive_load_exceeds_its_source_base_load(self):
        return {"grid": 1, "pv1": 0}

    # ----------------------------------------------------------------------
    # Decision: the grid goes first.

    @topology
    def batteries_anchored_to_the_grid(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1"),
            Adapter.pv("pv2"),
            Adapter.battery("bat1", charge_from=("grid", "pv1")),
            Adapter.battery("bat2", charge_from=("grid", "pv2")),
            Adapter.battery("bat3", charge_from=("pv1", "pv2")),
            Adapter.consumer("cons1", power_from=("pv1", "pv2")),
        )

    @state
    def import_shared_by_two_batteries(self):
        """Decision: a restricted sink allowed the grid draws it before
        competing for local generation, and a shared import splits in
        proportion to draw (rules 1 and 2 of "Choosing among valid
        allocations"; the worked example there).

        bat1 and bat2 may each use the grid and their own PV system. They take
        the whole 400 W import, 200 W each, and their other 200 W from their
        own PV system. That leaves pv1 800 W and pv2 400 W for bat3, cons1 and
        the 200 W base load, all split 2 : 1. The base load, also allowed the
        grid, gets none of it: the grid went first to the restricted sinks.
        """
        return State(
            grid=400, pv1=1000, pv2=600,
            bat1=-400, bat2=-400, bat3=-500, cons1=-500,
        )

    @expect_attribute("sink_adapters_source_shares")
    def test_import_shared_by_two_batteries_power_flow(self):
        return rows({
            "bat1": {"grid": 200, "pv1": 200, "pv2": 0},
            "bat2": {"grid": 200, "pv1": 0, "pv2": 200},
            "bat3": {"grid": 0, "pv1": F(1000, 3), "pv2": F(500, 3)},
            "cons1": {"grid": 0, "pv1": F(1000, 3), "pv2": F(500, 3)},
        })

    @expect_attribute("home_base_load_source_shares")
    def test_import_shared_by_two_batteries_base_load(self):
        return {"grid": 0, "pv1": F(2, 3), "pv2": F(1, 3)}

    # ----------------------------------------------------------------------
    # Decision: sinks with the same restriction get the same row, whatever
    # their draws.

    @topology
    def two_loads_on_the_same_pv_systems(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1"),
            Adapter.pv("pv2"),
            Adapter.consumer("cons1", power_from=("pv1", "pv2")),
            Adapter.consumer("cons2", power_from=("pv1", "pv2")),
        )

    @state
    def unequal_draws(self):
        """Decision: scarce sources are split in proportion to draw, so two
        sinks with the same restriction come out with the same row (rule 2 of
        "Choosing among valid allocations").

        cons1 draws 100 W and cons2 300 W, exactly what pv1 and pv2 make
        together. Each PV system is split 1 : 3 between them, so both read
        pv1 3/4, pv2 1/4 — serving them one at a time would have given one of
        them all of pv1.
        """
        return State(grid=200, pv1=300, pv2=100, cons1=-100, cons2=-300)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Engine bug: when the draws exactly exhaust the sources, cons2 must "
            "take at least 200 W of pv1 in every plan; the engine hands out "
            "that reserve first and splits only the rest by draw, so the two "
            "rows come out 9/13 and 10/13 on pv1 instead of 3/4 each. The "
            "same-row answer is feasible and honours the reserve."
        ),
    )
    @expect_attribute("sink_adapters_source_shares")
    def test_unequal_draws_power_flow(self):
        return rows({
            "cons1": {"grid": 0, "pv1": 75, "pv2": 25},
            "cons2": {"grid": 0, "pv1": 225, "pv2": 75},
        })

    # ----------------------------------------------------------------------
    # Decision: a sink splits over what is left, not over total output.

    @topology
    def export_beside_a_captive_load(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.battery("bat1", exports=True),
            Adapter.consumer("cons1", power_from=("pv1",)),
        )

    @state
    def export_after_the_captive_load(self):
        """Decision: a sink spreading its draw over several sources weights them
        by what is *left* of each, not by their readings (engine-calculations.md,
        "a sink splits over what is left"; its worked example).

        cons1 is captive to pv1 and takes 250 W of its 3000 W first. The 1200 W
        export may use pv1 and bat1, and splits over what is left of them,
        2750 : 400 — pv1 55/63 — not the 3000 : 400 their readings would give.
        """
        return State(grid=-1200, pv1=3000, bat1=400, cons1=-250)

    @expect_attribute("sink_adapters_source_shares")
    def test_export_after_the_captive_load_power_flow(self):
        return rows({
            "grid": {"pv1": F(22000, 21), "bat1": F(3200, 21)},
            "cons1": {"pv1": 250, "bat1": 0},
        })

    # ----------------------------------------------------------------------
    # Decision: feasibility is decided for groups of sinks, with max flow.

    @topology
    def battery_pair_and_a_plug_with_an_alternative(self):
        return (
            Adapter.grid(),
            Adapter.pv("east"),
            Adapter.pv("west"),
            Adapter.pv("carport"),
            Adapter.battery("bat_a", charge_from=("east", "west")),
            Adapter.battery("bat_b", charge_from=("east", "west")),
            Adapter.consumer("plug", power_from=("east", "carport")),
        )

    @state
    def pair_needs_both_pv_systems(self):
        """Decision: feasibility is decided for groups of sinks, with max flow
        (engine-calculations.md, "feasibility is decided for groups").

        Each battery on its own could be covered by east or by west, so asking
        sink by sink finds nothing either *must* have. But together they need
        every watt east and west make. The plug may use east or the carport;
        it must take the carport, or the pair comes up short.
        """
        return State(
            grid=200, east=100, west=100, carport=100,
            bat_a=-100, bat_b=-100, plug=-100,
        )

    @expect_attribute("sink_adapters_source_shares")
    def test_pair_needs_both_pv_systems_power_flow(self):
        return rows({
            "bat_a": {"grid": 0, "east": 50, "west": 50, "carport": 0},
            "bat_b": {"grid": 0, "east": 50, "west": 50, "carport": 0},
            "plug": {"grid": 0, "east": 0, "west": 0, "carport": 100},
        })

    @expect_attribute("sink_adapters_restriction_deficit")
    def test_pair_needs_both_pv_systems_restriction_deficit(self):
        return {}

    # ----------------------------------------------------------------------
    # Decision: feasibility outranks the rules that choose an allocation.

    @topology
    def two_batteries_on_the_grid_one_pv_taken(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1"),
            Adapter.pv("pv2"),
            Adapter.battery("bat1", charge_from=("grid", "pv1")),
            Adapter.battery("bat2", charge_from=("grid", "pv2")),
            Adapter.consumer("cons1", power_from=("pv1",)),
        )

    @state
    def import_cannot_split_by_draw(self):
        """Decision: feasibility outranks the rules — they only choose among
        allocations that already work (engine-calculations.md, "feasibility
        outranks all three").

        bat1 and bat2 draw 300 W each and may both use the grid's 400 W, so the
        proportional rule says 200 W each. But cons1 needs all of pv1, leaving
        bat1 nothing local: it must take 300 W of grid, and bat2 the other
        100 W with pv2's 200 W.
        """
        return State(
            grid=400, pv1=100, pv2=200, bat1=-300, bat2=-300, cons1=-100,
        )

    @expect_attribute("sink_adapters_source_shares")
    def test_import_cannot_split_by_draw_power_flow(self):
        return rows({
            "bat1": {"grid": 300, "pv1": 0, "pv2": 0},
            "bat2": {"grid": 100, "pv1": 0, "pv2": 200},
            "cons1": {"grid": 0, "pv1": 100, "pv2": 0},
        })

    @expect_attribute("sink_adapters_restriction_deficit")
    def test_import_cannot_split_by_draw_restriction_deficit(self):
        return {}

    # ----------------------------------------------------------------------
    # Decision: the sink with somewhere else to go is the one that yields.

    @topology
    def overlapping_captive_batteries(self):
        return (
            Adapter.grid(),
            Adapter.pv("east"),
            Adapter.pv("west"),
            Adapter.battery("bat_a", charge_from=("east", "west")),
            Adapter.battery("bat_b", charge_from=("east", "west")),
            Adapter.battery("bat_c", charge_from=("east",)),
        )

    @state
    def captive_demand_exceeds_supply(self):
        """Decision: when no allocation honours every restriction, the most
        constrained sink is served first and the deficit falls on the sinks
        that had somewhere else to go (engine-calculations.md, "the sink with
        somewhere else to go is the one that yields").

        Three batteries want 300 W from east and west's 200 W. bat_c may only
        use east and takes all of it. bat_a and bat_b share west, 50 W each,
        and each takes its missing 50 W from the grid as a reported deficit.
        """
        return State(
            grid=200, east=100, west=100, bat_a=-100, bat_b=-100, bat_c=-100,
        )

    @expect_attribute("sink_adapters_source_shares")
    def test_captive_demand_exceeds_supply_power_flow(self):
        return rows({
            "bat_a": {"grid": 50, "east": 0, "west": 50},
            "bat_b": {"grid": 50, "east": 0, "west": 50},
            "bat_c": {"grid": 0, "east": 100, "west": 0},
        })

    @expect_attribute("sink_adapters_restriction_deficit")
    def test_captive_demand_exceeds_supply_restriction_deficit(self):
        return {"bat_a": 50, "bat_b": 50}

    # ----------------------------------------------------------------------
    # Decision: a sink whose allowed sources are all idle collapses to zeros.

    @topology
    def battery_captive_to_pv_in_standby(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1"),
            Adapter.battery("bat1", charge_from=("pv1",)),
            Adapter.consumer("cons1"),
        )

    @state
    def allowed_source_not_producing(self):
        """Decision: a sink whose allowed sources are all idle collapses to an
        all-zeros row instead of being forced onto excluded sources, and its
        whole draw is reported as the deficit (engine-calculations.md, "a
        broken restriction is reported, not hidden").

        bat1 may only charge from pv1, which is drawing 20 W of standby and so
        is not a source at all. Nothing may be attributed to bat1; its 400 W
        is the deficit.
        """
        return State(grid=1000, pv1=-20, bat1=-400, cons1=-100)

    @expect_attribute("sink_adapters_source_shares")
    def test_allowed_source_not_producing_power_flow(self):
        return rows({
            "pv1": {"grid": 20},
            "bat1": {"grid": 0},
            "cons1": {"grid": 100},
        })

    @expect_attribute("sink_adapters_restriction_deficit")
    def test_allowed_source_not_producing_restriction_deficit(self):
        return {"bat1": 400}

    # ----------------------------------------------------------------------
    # Decision: what every valid allocation carries is never scaled away.

    @topology
    def plug_on_either_of_two_pv_systems(self):
        return (
            Adapter.grid(),
            Adapter.pv("east", exports=True),
            Adapter.pv("west", exports=True),
            Adapter.pv("carport", exports=True),
            Adapter.consumer("plug", power_from=("east", "west")),
        )

    @state
    def every_watt_spoken_for(self):
        """Decision: what every valid allocation carries is never scaled away
        (engine-calculations.md).

        The plug may use east or west, and needs neither in particular, so
        nothing is reserved for it on either. The carport may only feed the
        export, so all 200 W of it is the export's reserve. The export is
        offered more than its 1800 W and its offers are scaled down — but never
        below that 200 W, or the carport's leftover would be forced onto the
        plug, which may not use it.
        """
        return State(grid=-1800, east=1000, west=1000, carport=200, plug=-400)

    @expect_attribute("sink_adapters_source_shares")
    def test_every_watt_spoken_for_power_flow(self):
        """The carport's 200 W all goes to the export, which takes the other
        1600 W half from east and half from west; the plug takes its 400 W
        half from each of the two it may use."""
        return rows({
            "grid": {"east": 800, "west": 800, "carport": 200},
            "plug": {"east": 200, "west": 200, "carport": 0},
        })

    @expect_attribute("sink_adapters_restriction_deficit")
    def test_every_watt_spoken_for_restriction_deficit(self):
        """Every restriction can be honoured, so none is reported broken."""
        return {}

    # ----------------------------------------------------------------------
    # Decision: an exporting grid may only take power from exporting devices.

    @topology
    def battery_that_may_not_export(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.battery("bat1", exports=False),
            Adapter.consumer("cons1"),
        )

    @state
    def battery_discharging_while_exporting(self):
        """Decision: ``exports_power=False`` is a hard routing restriction — an
        exporting grid is a sink allowed only the sources that may export
        (engine-calculations.md, "exports_power=False is a hard routing
        restriction").

        bat1 discharges 200 W but may not feed the grid, so the 300 W export
        is all pv1. cons1 is unrestricted and takes what is left: pv1's other
        200 W and all of bat1.
        """
        return State(grid=-300, pv1=500, bat1=200, cons1=-400)

    @expect_attribute("sink_adapters_source_shares")
    def test_battery_discharging_while_exporting_power_flow(self):
        return rows({
            "grid": {"pv1": 300, "bat1": 0},
            "cons1": {"pv1": 200, "bat1": 200},
        })
