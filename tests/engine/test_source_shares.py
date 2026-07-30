"""Source-share scenario: the two-tier power-provenance attribution.

``PowerInsight.sink_adapters_source_shares`` answers "where does each drawing
adapter's power come from?" — ``{sink_uid: {source_uid: share}}``, each row
summing to 1 (or collapsing to all-zeros when the sink's allowed sources are all
idle). It is the single richest piece of engine logic, so it gets its own
scenario, one block per branch of the three-tier algorithm (see
``docs/dev/engine-calculations.md`` for the full model):

* **Priority tier** — sinks restricted to non-grid sources (a PV-only battery, a
  smart-plug consumer). Active *only while the grid is importing*: they get first
  pick of their allowed sources and can exhaust a scarce one.
* **Home base-load tier** — the unmetered home load consumes the remaining local
  generation next, grid as fallback.
* **Leftover tier** — grid-capable / unrestricted sinks (and *every* sink when
  the grid is not importing). They split what the first two tiers left behind.

The blocks run simplest → hardest: one unrestricted battery tracking a home
load, then a restricted-to-idle collapse, then a two-source export pass with no
priority tier, and finally the full priority/home/leftover split with several
restricted sinks at once.

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
    # Home base-load tier in isolation. One grid, one PV, one unrestricted
    # (whole-mix -> grid-capable leftover) battery. Sources are held at grid
    # 1000 W + pv1 1000 W (a fixed 0.5 / 0.5 availability); only the home load
    # varies, set by how much of gross the battery leaves unclaimed. As it grows
    # it eats the local PV first, pushing the battery's provenance to grid.
    # -----------------------------------------------------------------------

    @topology
    def grid_pv_flex_battery(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.battery("bat"),  # empty charge_from -> whole mix, leftover sink
        )

    @state
    def home_none(self):
        # bat draws all 2000 W of gross -> no unmetered home load.
        return State(grid=1000, pv1=1000, bat=-2000, price=0.30)

    @expect_attribute("sink_adapters_source_shares")
    def test_no_home_load_battery_keeps_half_solar(self):
        """No home load competes for the PV, so bat mirrors 0.5 / 0.5 availability."""
        return {"bat": {"grid": 0.5, "pv1": 0.5}}

    @state
    def home_moderate(self):
        # bat draws 1500 W -> 500 W unmetered home load (0.25 of gross).
        return State(grid=1000, pv1=1000, bat=-1500, price=0.30)

    @expect_attribute("sink_adapters_source_shares")
    def test_moderate_home_load_shifts_battery_toward_grid(self):
        """Home eats 0.25 of the 0.5 pv1 share first; bat splits the rest, 2/3 grid."""
        return {"bat": {"grid": 2 / 3, "pv1": 1 / 3}}

    @state
    def home_large(self):
        # bat draws 1000 W -> 1000 W home load (0.5 of gross) eats all the PV.
        return State(grid=1000, pv1=1000, bat=-1000, price=0.30)

    @expect_attribute("sink_adapters_source_shares")
    def test_large_home_load_pushes_battery_fully_to_grid(self):
        """Home load consumes the whole pv1 share; bat falls fully back on grid."""
        return {"bat": {"grid": 1.0, "pv1": 0.0}}

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
        """No import -> one pass at full availability; bat_solar still masked to pv1."""
        # Grid and the unrestricted bat_flex take the full 2/3 / 1/3 availability;
        # bat_solar's pv1-only restriction masks it to pv1 even with no priority
        # tier; the exporting grid is itself a sink sourced from the PV mix.
        return {
            "grid": {"pv1": 2 / 3, "pv2": 1 / 3},
            "bat_solar": {"pv1": 1.0, "pv2": 0.0},
            "bat_flex": {"pv1": 2 / 3, "pv2": 1 / 3},
        }

    # -----------------------------------------------------------------------
    # Two PV, three batteries (each restricted differently) and a smart-plug
    # consumer — the full priority / home / leftover split with several
    # restricted sinks at once while the grid imports.
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
    def charging_with_import(self):
        return State(
            grid=1200,
            pv_1=800,
            pv_2=500,
            bat_1=-400,
            bat_2=-400,
            bat_3=-600,
            cons_1=-600,
            price=0.30,
        )

    @expect_attribute("sink_adapters_source_shares", abs_tol=SHARE_ABS_TOL)
    def test_charging_with_import(self):
        """Grid-capable bat_1/bat_2 land on grid; pv-only bat_3/cons_1 take priority PV."""
        return {
            "bat_1": {"grid": 1.0, "pv_1": 0.0, "pv_2": 0.0},
            "bat_2": {"grid": 1.0, "pv_1": 0.0, "pv_2": 0.0},
            "bat_3": {"grid": 0.0, "pv_1": 0.615, "pv_2": 0.385},
            "cons_1": {"grid": 0.0, "pv_1": 0.615, "pv_2": 0.385},
        }

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

    @expect_attribute("sink_adapters_source_shares", abs_tol=SHARE_ABS_TOL)
    def test_charging_with_partial_import(self):
        """Abundant pv_1 survives the priority + home tiers, so bat_1 keeps more local."""
        # pv_1 (1000 W) is more abundant than pv_2 (600 W): after the priority +
        # home tiers consume local, more pv_1 survives, so bat_1 (on pv_1) keeps
        # more local than bat_2 (on pv_2).
        return {
            "bat_1": {"grid": 0.615, "pv_1": 0.385, "pv_2": 0.0},
            "bat_2": {"grid": 0.727, "pv_1": 0.0, "pv_2": 0.273},
            "bat_3": {"grid": 0.0, "pv_1": 0.625, "pv_2": 0.375},
            "cons_1": {"grid": 0.0, "pv_1": 0.625, "pv_2": 0.375},
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
