"""Source-share edge cases: power provenance at the boundaries.

``PowerInsight.sink_adapters_source_shares`` answers "where does each drawing
adapter's power come from?" — ``{sink_uid: {source_uid: share}}``, each row
summing to 1 (or collapsing to all-zeros when the sink's allowed sources are all
idle). See ``docs/dev/engine-calculations.md`` for the model.

This file is deliberately **not** a second pass over the ordinary case: the rich
everyday wiring (two PV strings, batteries in all three restriction modes,
restricted and unrestricted consumers, a large home base load, import and export
snapshots) is pinned by ``test_full_topology.py``. What lives here is only what
that scenario cannot reach — the degenerate and the over-constrained:

* **No restrictions at all** — every sink mirrors the raw availability. The
  degenerate baseline the tiered logic must collapse to.
* **Every allowed source idle** — a sink pinned to a PV that is in standby has
  nowhere to draw from and collapses to an all-zeros row rather than dividing by
  zero.
* **Exporting with a captive sink** — no import, so a single pass, but a
  restricted sink still depletes its source before the flexible ones share it.
* **A short grid import** — the import cannot cover the sinks anchored to it,
  so it has to be rationed between them (blocks 1 and 2 below).
* **A source short of its captives** — more demand is pinned to one PV string
  than the string produces, so the claims are scaled and the excess falls back
  (block 3, second state).

The last three groups are **specifications**: they describe the ordering the
engine is moving to, not what it does today, and currently fail. Each derives
its expected values so that every source column balances exactly against its
reading — the property the current implementation violates.

Each ``test_`` method uses the ``@expect_attribute("sink_adapters_source_shares")`` decorator
(see ``scenario_framework.py``): it returns the hand-written expected map for the
``@topology`` / ``@state`` block declared above it, and the framework reads the
engine attribute back and compares. Expected values are derived from first
principles, not read from the engine.

An empty restriction (``charge_from`` / ``power_from``) means *unrestricted* — the
sink draws the whole source mix (a normal consumer, or a battery in the config
flow's "whole mix" source mode). A non-empty list restricts it to those sources.
The config flow surfaces this as an explicit "whole mix" vs "specific devices"
mode, but the engine only sees the list: empty is the mix, non-empty restricts.

Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery ``+``
produce/discharge / ``-`` standby/charge; consumer ``-`` = load.
"""

from __future__ import annotations

from tests.engine.scenario_framework import (
    Adapter,
    EngineScenario,
    State,
    state,
    expect_attribute,
    topology,
)


# Shares written as rounded literals (e.g. 0.615 for 8/13) are compared to three
# decimal places via ``@expect_attribute(..., abs_tol=SHARE_ABS_TOL)`` — enough to catch any
# real regression (which shifts a share by far more) while keeping the expected
# map readable. Blocks whose expectations are exact fractions omit ``abs_tol`` so
# ``pytest.approx``'s tight relative tolerance applies. See
# docs/dev/engine-calculations.md ("Approximation policy").
SHARE_ABS_TOL = 1e-3


class TestSourceShares(EngineScenario):
    """Power provenance under the three-tier ``sink_adapters_source_shares`` rule."""

    # -----------------------------------------------------------------------
    # The degenerate baseline: nothing is restricted, so there is nothing to
    # ration and every sink mirrors the raw availability. One grid + one PV at
    # 1000 W each -> a 0.5 / 0.5 mix, and the battery draws all of gross so
    # there is no home base load either.
    # -----------------------------------------------------------------------

    @topology
    def grid_pv_flex_battery(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.battery("bat"),  # empty charge_from -> whole mix
        )

    @state
    def no_restrictions_no_home_load(self):
        # bat draws all 2000 W of gross -> no unmetered home load.
        return State(grid=1000, pv1=1000, bat=-2000, price=0.30)

    @expect_attribute("sink_adapters_source_shares")
    def test_unrestricted_sink_mirrors_availability(self):
        """Nothing to ration: bat mirrors the 0.5 / 0.5 availability."""
        return {"bat": {"grid": 0.5, "pv1": 0.5}}

    # -----------------------------------------------------------------------
    # Restricted sinks whose only allowed source is idle. The lone PV is in
    # standby (a sink, not a source), so a battery and a smart plug both pinned
    # to it collapse to an all-zeros row, while the unrestricted standby PV
    # draws from the grid.
    # -----------------------------------------------------------------------

    @topology
    def grid_with_idle_pv(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.consumer("cons_plug", power_from=("pv1",)),
            Adapter.battery("bat_dead", charge_from=("pv1",)),
        )

    @state
    def night_standby(self):
        # Only the grid provides (1000 W). pv1 draws 10 W standby -> a sink. The
        # plug (300 W) and battery (200 W) are pinned to the now-idle pv1.
        return State(grid=1000, pv1=-10, cons_plug=-300, bat_dead=-200, price=0.30)

    @expect_attribute("sink_adapters_source_shares")
    def test_restricted_to_idle_source_collapses_to_zero(self):
        """pv1 is idle: sinks pinned to it collapse to all-zeros; standby pv1 -> grid."""
        # Masking to the idle pv1 leaves nothing over the sole source (grid), so
        # the plug and dead battery are all-zeros rather than divide-by-zero. The
        # unrestricted standby pv1 draws the only source there is, the grid.
        return {
            "cons_plug": {"grid": 0.0},
            "bat_dead": {"grid": 0.0},
            "pv1": {"grid": 1.0},
        }

    # -----------------------------------------------------------------------
    # Grid exporting: no import, so the priority tier is empty and every sink
    # shares the sources in a single pass (restriction still honoured). The
    # exporting grid is itself a sink, sourced from the PV mix. Sources are
    # pv1 2000 W + pv2 1000 W -> availability pv1 2/3, pv2 1/3.
    # -----------------------------------------------------------------------

    @topology
    def two_pv_two_batteries(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.pv("pv2", exports=True),
            Adapter.battery("bat_solar", charge_from=("pv1",)),
            Adapter.battery("bat_flex"),  # empty charge_from -> whole mix, leftover
        )

    @state
    def pure_solar_export(self):
        # gross 3000 W; grid exports 1000 W, so it is a sink, not a source.
        return State(
            grid=-1000, pv1=2000, pv2=1000, bat_solar=-500, bat_flex=-500, price=0.30
        )

    @expect_attribute("sink_adapters_source_shares")
    def test_export_single_pass_honours_restriction(self):
        """bat_solar's captive pv1 draw comes off the pool before anyone else shares it."""
        # bat_solar can only use pv1, so its 500 W is taken from pv1 first.
        # What is left -- pv1 1500 + pv2 1000 = 2500 W -- is shared by the
        # exporting grid (1000 W), bat_flex (500 W) and the home load (1000 W),
        # which is exactly 2500 W, so they all read 1500/2500 pv1, 1000/2500 pv2.
        # Columns: pv1 500 + 1500 = 2000 | pv2 1000. Sharing the *raw* 2/3 - 1/3
        # availability instead would attribute 2167 W of a 2000 W pv1 reading.
        return {
            "grid": {"pv1": 0.6, "pv2": 0.4},
            "bat_solar": {"pv1": 1.0, "pv2": 0.0},
            "bat_flex": {"pv1": 0.6, "pv2": 0.4},
        }

    # -----------------------------------------------------------------------
    # A short import shared by two grid-anchored sinks with *different*
    # fallbacks: bat_1 can top up from pv_1, bat_2 from pv_2. Neither is
    # captive (either PV string could cover its battery on its own), so the
    # 400 W import is split between them and each covers its deficit from its
    # own string. The abundant-vs-scarce string asymmetry is the point.
    #
    # The everyday case this file used to duplicate -- an import that comfortably
    # covers every grid-anchored sink -- is pinned by test_full_topology.py.
    # -----------------------------------------------------------------------

    @topology
    def two_pv_three_batteries(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv_1", lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.pv("pv_2", lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.battery("bat_1", charge_from=("grid", "pv_1")),
            Adapter.battery("bat_2", charge_from=("grid", "pv_2")),
            Adapter.battery("bat_3", charge_from=("pv_1", "pv_2")),
            Adapter.consumer("cons_1", power_from=("pv_1", "pv_2")),
        )

    @state
    def charging_with_partial_import(self):
        return State(
            grid=400,
            pv_1=1000,
            pv_2=600,
            bat_1=-400,
            bat_2=-400,
            bat_3=-500,
            cons_1=-500,
            price=0.30,
        )

    @expect_attribute("sink_adapters_source_shares")
    def test_charging_with_partial_import(self):
        """A short import splits evenly; each battery then tops up from its own string."""
        # Neither grid-anchored battery is forced onto the grid -- pv_1 alone
        # could cover bat_1 and pv_2 alone could cover bat_2 -- so neither
        # reserves any of it, and the 400 W import splits in proportion to their
        # draws, which are equal: 200 W each. Each covers its remaining 200 W
        # from its own string, giving both 0.5 / 0.5.
        # That leaves pv_1 800 + pv_2 400 = 1200 W for bat_3 500 + cons_1 500 +
        # home 200 = 1200 W, so those read 2/3 pv_1, 1/3 pv_2.
        # Columns: grid 400 | pv_1 200 + 333.3 + 333.3 + 133.3 = 1000 |
        #          pv_2 200 + 166.7 + 166.7 + 66.7 = 600.
        # The asymmetry between the strings is real but lands on *which* string
        # each battery keeps, not on how the shared import is divided.
        return {
            "bat_1": {"grid": 0.5, "pv_1": 0.5, "pv_2": 0.0},
            "bat_2": {"grid": 0.5, "pv_1": 0.0, "pv_2": 0.5},
            "bat_3": {"grid": 0.0, "pv_1": 2 / 3, "pv_2": 1 / 3},
            "cons_1": {"grid": 0.0, "pv_1": 2 / 3, "pv_2": 1 / 3},
        }

    # -----------------------------------------------------------------------
    # A grid-capable restricted sink drawing MORE than the grid imports.
    #
    # The two blocks below pin the behaviour when the grid cannot cover the
    # sinks that are anchored to it. Both are specifications for the refined
    # ordering (grid drained first, then the local competition) rather than
    # descriptions of the current implementation — see the review notes: the
    # engine's leftover tier normalises each row independently, so it does not
    # reproduce them yet.
    #
    # Ordering used to derive both:
    #   1. grid phase   — grid-capable restricted sinks claim the import. Each
    #      first reserves what it *cannot* get elsewhere
    #      (``max(0, draw - allowed local supply)``); whatever import is left is
    #      split between them in proportion to their remaining draw.
    #   2. local phase  — every restricted sink still short (including a
    #      grid-capable one that has exhausted the import: its residual is now
    #      an ordinary local demand) competes for the local generation it is
    #      allowed, most-constrained-first.
    #   3. flexible     — unrestricted sinks plus the unmetered home load share
    #      whatever survives.
    # Each source column must balance exactly against its reading.
    #
    # Block 1: one battery on (grid, pv2) drawing 900 W against a 400 W import,
    # sharing pv2 with a battery that has no other option.
    #   sources  grid 400 + pv1 1500 + pv2 800     -> gross 2700 W
    #   sinks    900 + 300 + 600 = 1800 W          -> home base load 900 W
    # -----------------------------------------------------------------------

    @topology
    def battery_outdrawing_the_import(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.pv("pv2", exports=True),
            # Anchored to the grid but allowed to fall back on pv2.
            Adapter.battery("bat_grid_pv2", charge_from=("grid", "pv2")),
            # pv2 is its only option -- it has nowhere else to go.
            Adapter.battery("bat_pv2_only", charge_from=("pv2",)),
            Adapter.consumer("cons_flex"),  # unrestricted -> flexible tier
        )

    @state
    def import_below_battery_draw(self):
        return State(
            grid=400,
            pv1=1500,
            pv2=800,
            bat_grid_pv2=-900,
            bat_pv2_only=-300,
            cons_flex=-600,
            price=0.30,
        )

    @expect_attribute("sink_adapters_source_shares")
    def test_battery_takes_whole_import_then_digs_into_pv2(self):
        """The 900 W battery empties the 400 W import, then takes 500 W of pv2."""
        # Grid phase: bat_grid_pv2 is the only grid-capable restricted sink, and
        # its 900 W draw exceeds the 400 W import, so it takes all of it
        # -> 400/900 = 4/9. Deficit 500 W.
        # Local phase: that 500 W deficit is now a plain pv2 demand, competing
        # with bat_pv2_only's 300 W. 500 + 300 = 800 W against pv2's 800 W, so
        # both are served in full and pv2 is exactly exhausted -- digging into
        # pv2 must not starve the sink that has no alternative.
        # Flexible: pv1 is untouched (1500 W) and cons_flex 600 + home 900 =
        # 1500 W, so the flexible tier is pure pv1 and sees no grid at all.
        # Columns: grid 400 | pv1 1500 | pv2 500 + 300 = 800.
        return {
            "bat_grid_pv2": {"grid": 4 / 9, "pv1": 0.0, "pv2": 5 / 9},
            "bat_pv2_only": {"grid": 0.0, "pv1": 0.0, "pv2": 1.0},
            "cons_flex": {"grid": 0.0, "pv1": 1.0, "pv2": 0.0},
        }

    # -----------------------------------------------------------------------
    # Block 2: two grid-capable restricted sinks competing for an import that
    # cannot cover both -- one of them has no fallback at all.
    #   sources  grid 600 + pv1 1000 + pv2 900     -> gross 2500 W
    #   sinks    500 + 400 + 400 = 1300 W          -> home base load 1200 W
    #   combined grid-anchored draw 900 W > 600 W import
    # -----------------------------------------------------------------------

    @topology
    def two_grid_capable_batteries(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.pv("pv2", exports=True),
            Adapter.battery("bat_grid_pv2", charge_from=("grid", "pv2")),
            # Grid-only: no fallback, so it must be served from the import first.
            Adapter.battery("bat_grid_only", charge_from=("grid",)),
            Adapter.consumer("cons_flex"),
        )

    @state
    def import_below_combined_draw(self):
        return State(
            grid=600,
            pv1=1000,
            pv2=900,
            bat_grid_pv2=-500,
            bat_grid_only=-400,
            cons_flex=-400,
            price=0.30,
        )

    @expect_attribute("sink_adapters_source_shares")
    def test_grid_only_battery_is_served_before_the_flexible_one(self):
        """400 W of the 600 W import is reserved for the battery with no fallback."""
        # Grid phase: combined draw 900 W > 600 W import. bat_grid_only has no
        # allowed local source, so its whole 400 W is reserved; bat_grid_pv2 can
        # fall back on pv2 and reserves nothing, so it gets the remaining 200 W
        # -> 200/500 = 0.4 grid, 300 W deficit.
        # A demand-proportional split would instead hand bat_grid_pv2
        # 600 x 5/9 = 333 W and leave bat_grid_only 133 W short of any source it
        # is allowed to use -- which is what this case exists to rule out.
        # Local phase: bat_grid_pv2's 300 W deficit comes off pv2 (900 W
        # available) -> 0.6; 600 W of pv2 survives.
        # Flexible: cons_flex 400 + home 1200 = 1600 W against pv1 1000 +
        # pv2 600 = 1600 W -> 5/8 pv1, 3/8 pv2.
        # Columns: grid 400 + 200 = 600 | pv1 250 + 750 = 1000 |
        #          pv2 300 + 150 + 450 = 900.
        return {
            "bat_grid_pv2": {"grid": 0.4, "pv1": 0.0, "pv2": 0.6},
            "bat_grid_only": {"grid": 1.0, "pv1": 0.0, "pv2": 0.0},
            "cons_flex": {"grid": 0.0, "pv1": 5 / 8, "pv2": 3 / 8},
        }

    # -----------------------------------------------------------------------
    # Block 3: captive demand on a *local* source. Four sinks want pv2 and they
    # are not equally stuck with it:
    #
    #   bat_grid_pv2  (grid, pv2)  -- captive to pv2 once the import is gone
    #   bat_pv2_a     (pv2)        -- captive to pv2 from the start
    #   bat_pv2_b     (pv2)        -- same restriction, different draw
    #   bat_pv1_pv2   (pv1, pv2)   -- can step aside onto pv1
    #
    # The captives must be served from pv2 before the sink that has somewhere
    # else to go, otherwise the two pv2-only batteries are starved by one that
    # had an alternative all along. This is the local-source counterpart of the
    # grid reservation in block 2 -- the same rule, applied to pv2.
    #
    # ``bat_pv2_a`` and ``bat_pv2_b`` carry the *same* restriction and
    # *different* draws on purpose: their claim on pv2 must never depend on
    # which one is looked at first. Two states run the topology, one either
    # side of the point where pv2 stops covering them.
    # -----------------------------------------------------------------------

    @topology
    def captive_competition_on_pv2(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.pv("pv2", exports=True),
            Adapter.battery("bat_grid_pv2", charge_from=("grid", "pv2")),
            Adapter.battery("bat_pv2_a", charge_from=("pv2",)),
            Adapter.battery("bat_pv2_b", charge_from=("pv2",)),
            Adapter.battery("bat_pv1_pv2", charge_from=("pv1", "pv2")),
            Adapter.consumer("cons_flex"),
        )

    # pv2 (900 W) covers its captives exactly: 300 + 400 + 200 = 900 W.
    #   sources  grid 400 + pv1 1200 + pv2 900          -> gross 2500 W
    #   sinks    700 + 400 + 200 + 600 + 300 = 2200 W   -> home base load 300 W

    @state
    def pv2_exactly_covers_its_captives(self):
        return State(
            grid=400,
            pv1=1200,
            pv2=900,
            bat_grid_pv2=-700,
            bat_pv2_a=-400,
            bat_pv2_b=-200,
            bat_pv1_pv2=-600,
            cons_flex=-300,
            price=0.30,
        )

    @expect_attribute("sink_adapters_source_shares")
    def test_captives_take_pv2_and_displace_the_sink_that_can_use_pv1(self):
        """The captives absorb pv2 exactly; bat_pv1_pv2 is pushed entirely onto pv1."""
        # Grid phase: bat_grid_pv2 takes the whole 400 W import (4/7 of its
        # 700 W draw); its 300 W deficit can now only come from pv2.
        # Local phase on pv2 (900 W): captive demand is 300 (bat_grid_pv2) +
        # 400 (bat_pv2_a) + 200 (bat_pv2_b) = 900 W. None of it can be served
        # anywhere else, so it consumes pv2 exactly and nothing is left over.
        # bat_pv1_pv2 is not captive -- pv1 alone could cover it -- so it is
        # displaced onto pv1 in full. A plain proportional split would instead
        # hand it a slice of pv2 and leave a captive short.
        # Flexible: pv1 600 W left for cons_flex 300 + home 300.
        # Columns: grid 400 | pv1 600 + 600 = 1200 | pv2 300 + 400 + 200 = 900.
        return {
            "bat_grid_pv2": {"grid": 4 / 7, "pv1": 0.0, "pv2": 3 / 7},
            "bat_pv2_a": {"grid": 0.0, "pv1": 0.0, "pv2": 1.0},
            "bat_pv2_b": {"grid": 0.0, "pv1": 0.0, "pv2": 1.0},
            "bat_pv1_pv2": {"grid": 0.0, "pv1": 1.0, "pv2": 0.0},
            "cons_flex": {"grid": 0.0, "pv1": 1.0, "pv2": 0.0},
        }

    # Same wiring, pv2 now short of its captives: 600 W of pv2 against 900 W
    # pinned to it. The import covers bat_grid_pv2 outright, so the shortfall
    # falls on the two pv2-only batteries alone.
    #   sources  grid 500 + pv1 1500 + pv2 600          -> gross 2600 W
    #   sinks    500 + 600 + 300 + 400 + 300 = 2100 W   -> home base load 500 W

    @state
    def pv2_short_of_its_captives(self):
        return State(
            grid=500,
            pv1=1500,
            pv2=600,
            bat_grid_pv2=-500,
            bat_pv2_a=-600,
            bat_pv2_b=-300,
            bat_pv1_pv2=-400,
            cons_flex=-300,
            price=0.30,
        )

    @expect_attribute("sink_adapters_source_shares")
    def test_identical_restrictions_split_a_short_source_in_proportion(self):
        """Same restriction, different draws, identical rows -- and the excess falls back."""
        # Grid phase: bat_grid_pv2's 500 W draw fits inside the 500 W import,
        # so it is pure grid and never touches pv2.
        # Local phase on pv2 (600 W): bat_pv2_a and bat_pv2_b are both fully
        # captive, claiming 600 + 300 = 900 W against 600 W. The claims scale
        # by 600/900 = 2/3 -> 400 W and 200 W, in proportion to the draws. The
        # scaling is what makes their *rows* identical (2/3 pv2, 1/3 pv1)
        # even though their draws differ 2:1; an implementation that walked the
        # sinks in some order would serve one in full and starve the other.
        # bat_pv1_pv2 is not captive and pv2 is gone, so it takes pv1 in full.
        # Fallback: 200 + 100 = 300 W of captive demand has no allowed source
        # left. The configuration disagrees with the meter -- those batteries
        # drew more than pv2 produced -- so the unservable remainder is treated
        # as unrestricted and joins the flexible pool, which is why a and b show
        # pv1 at all. Leaving it out instead would break the row sum or the pv1
        # column.
        # Flexible: pv1 1100 W for cons_flex 300 + home 500 + the 300 W
        # fallback -> exactly 1100 W, all pv1.
        # Columns: grid 500 | pv1 400 + 200 + 100 + 300 + 500 = 1500 |
        #          pv2 400 + 200 = 600.
        return {
            "bat_grid_pv2": {"grid": 1.0, "pv1": 0.0, "pv2": 0.0},
            "bat_pv2_a": {"grid": 0.0, "pv1": 1 / 3, "pv2": 2 / 3},
            "bat_pv2_b": {"grid": 0.0, "pv1": 1 / 3, "pv2": 2 / 3},
            "bat_pv1_pv2": {"grid": 0.0, "pv1": 1.0, "pv2": 0.0},
            "cons_flex": {"grid": 0.0, "pv1": 1.0, "pv2": 0.0},
        }
