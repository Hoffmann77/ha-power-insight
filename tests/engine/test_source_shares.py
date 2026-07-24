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

See ``scenario_framework.py`` for the block layout (``@topology`` → ``@state`` →
``test_`` methods, bound by source order). Expected values are hand-written, not
read back from the engine.

Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery ``+``
produce/discharge / ``-`` standby/charge; consumer ``-`` = load.
"""

from __future__ import annotations

import pytest

from tests.engine.scenario_framework import Adapter, EngineScenario, State, state, topology


# Shares are compared to three decimal places (0.1 percentage point). That lets
# a row list a readable rounded literal like 0.615 for 8/13 while still catching
# any real regression (which shifts a share by far more than this). Write a share
# as an exact fraction when you want it pinned tighter. See
# docs/dev/engine-calculations.md ("Approximation policy").
SHARE_ABS_TOL = 1e-3


def _assert_source_shares(power_insight, expected):
    """Compare ``sink_adapters_source_shares`` to a hand-written nested map.

    Row by row so the shares compare within ``SHARE_ABS_TOL`` while the sink set
    and each row's source set must still match exactly (a full row, every source
    uid the engine reports — so a leaked non-zero source fails loudly).
    """
    shares = power_insight.sink_adapters_source_shares
    assert shares.keys() == expected.keys()
    for uid, row in expected.items():
        assert shares[uid] == pytest.approx(row, abs=SHARE_ABS_TOL)


class TestSourceShares(EngineScenario):
    """Power provenance under the two-tier ``sink_adapters_source_shares`` rule."""

    # -----------------------------------------------------------------------
    # Two PV, three batteries (each restricted differently) and a smart-plug
    # consumer — the priority/leftover split with several restricted sinks at
    # once. Expected values below are author-maintained.
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

    def test_charging_with_import(self, power_insight):
        _assert_source_shares(
            power_insight,
            {
                "bat_1": {"grid": 1.0, "pv_1": 0.0, "pv_2": 0.0},
                "bat_2": {"grid": 1.0, "pv_1": 0.0, "pv_2": 0.0},
                "bat_3": {"grid": 0.0, "pv_1": 0.615, "pv_2": 0.385},
                "cons_1": {"grid": 0.0, "pv_1": 0.615, "pv_2": 0.385},
            },
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

    def test_charging_with_partial_import(self, power_insight):
        _assert_source_shares(
            power_insight,
            {
                # pv_1 (1000 W) is more abundant than pv_2 (600 W), so after the
                # priority + home tiers consume local, more pv_1 survives:
                # bat_1 (on pv_1) keeps more local than bat_2 (on pv_2).
                "bat_1": {"grid": 0.615, "pv_1": 0.385, "pv_2": 0.0},
                "bat_2": {"grid": 0.727, "pv_1": 0.0, "pv_2": 0.273},
                "bat_3": {"grid": 0.0, "pv_1": 0.625, "pv_2": 0.375},
                "cons_1": {"grid": 0.0, "pv_1": 0.625, "pv_2": 0.375},
            },
        )

    # -----------------------------------------------------------------------
    # Home base-load tier in isolation. Sources are held constant (grid 1000 W +
    # pv1 1000 W, so availability is a fixed 0.5 / 0.5); only the unmetered home
    # load changes, by varying how much of gross the lone grid-capable battery
    # draws. As the home load grows it eats the local PV first, pushing the
    # battery's provenance from half-solar fully onto the grid.
    # -----------------------------------------------------------------------

    @topology
    def grid_pv_flex_battery(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.battery("bat"),  # unrestricted -> grid-capable leftover sink
        )

    @state
    def home_none(self):
        # bat draws all 2000 W of gross -> no unmetered home load.
        return State(grid=1000, pv1=1000, bat=-2000, price=0.30)

    def test_no_home_load_battery_keeps_half_solar(self, power_insight):
        # Nothing competes for the PV: bat mirrors the 0.5 / 0.5 availability.
        shares = power_insight.sink_adapters_source_shares
        assert shares["bat"] == pytest.approx({"grid": 0.5, "pv1": 0.5})

    @state
    def home_moderate(self):
        # bat draws 1500 W -> 500 W unmetered home load (0.25 of gross).
        return State(grid=1000, pv1=1000, bat=-1500, price=0.30)

    def test_moderate_home_load_shifts_battery_toward_grid(self, power_insight):
        # Home eats 0.25 of the 0.5 pv1 share first; bat splits the rest -> 2/3 grid.
        shares = power_insight.sink_adapters_source_shares
        assert shares["bat"] == pytest.approx({"grid": 2 / 3, "pv1": 1 / 3})

    @state
    def home_large(self):
        # bat draws 1000 W -> 1000 W home load (0.5 of gross) eats all the PV.
        return State(grid=1000, pv1=1000, bat=-1000, price=0.30)

    def test_large_home_load_pushes_battery_fully_to_grid(self, power_insight):
        # Home load consumes the entire pv1 share; bat falls fully back on grid.
        shares = power_insight.sink_adapters_source_shares
        assert shares["bat"] == pytest.approx({"grid": 1.0, "pv1": 0.0})

    # -----------------------------------------------------------------------
    # Grid exporting: no import, so the priority tier is empty and every sink
    # shares the sources in a single pass (restriction still honoured). The
    # exporting grid is itself a sink, sourced from the PV mix.
    # -----------------------------------------------------------------------

    @topology
    def two_pv_two_batteries(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.pv("pv2", exports=True),
            Adapter.battery("bat_solar", charge_from=("pv1",)),
            Adapter.battery("bat_flex"),
        )

    @state
    def pure_solar_export(self):
        # Sources: pv1 2000 W + pv2 1000 W -> gross 3000 W (grid exports 1000 W,
        # so it is a sink, not a source). Availability: pv1 2/3, pv2 1/3.
        return State(
            grid=-1000, pv1=2000, pv2=1000, bat_solar=-500, bat_flex=-500, price=0.30
        )

    def test_grid_export_sourced_from_pv_mix(self, power_insight):
        # Unrestricted sink -> full availability: pv1 2/3, pv2 1/3.
        shares = power_insight.sink_adapters_source_shares
        assert shares["grid"] == pytest.approx({"pv1": 2 / 3, "pv2": 1 / 3})

    def test_restriction_still_honoured_without_priority(self, power_insight):
        # No grid import means no priority tier, but bat_solar's PV-only
        # restriction still masks it to pv1 in the single leftover pass.
        shares = power_insight.sink_adapters_source_shares
        assert shares["bat_solar"] == pytest.approx({"pv1": 1.0, "pv2": 0.0})

    def test_unrestricted_battery_matches_availability(self, power_insight):
        shares = power_insight.sink_adapters_source_shares
        assert shares["bat_flex"] == pytest.approx({"pv1": 2 / 3, "pv2": 1 / 3})

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

    def test_restricted_to_idle_source_collapses_to_zero(self, power_insight):
        # pv1 is not a source, so masking to it leaves nothing: an all-zeros row
        # over the sole source index (grid), rather than a divide-by-zero.
        shares = power_insight.sink_adapters_source_shares
        assert shares["cons_plug"] == pytest.approx({"grid": 0.0})
        assert shares["bat_dead"] == pytest.approx({"grid": 0.0})

    def test_unrestricted_standby_pv_draws_from_grid(self, power_insight):
        shares = power_insight.sink_adapters_source_shares
        assert shares["pv1"] == pytest.approx({"grid": 1.0})
