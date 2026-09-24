"""Allocation rules: how the engine picks one answer among the valid ones.

A sink may be *restricted* to some sources (a battery's ``charge_from``, a
consumer's ``power_from``). Usually many allocations of power honour every
restriction and balance every total, so the engine applies three rules, in
order, to choose one: the grid goes first, scarce sources are split in
proportion to draw, and unrestricted sinks take what is left. A restricted
sink spreading its draw over several sources weights them by what each has
left. See "Choosing among valid allocations" in
``docs/dev/engine-calculations.md``, and ``provenance.py`` for how the
expected provenance is written.
"""

from __future__ import annotations

from fractions import Fraction as F

import pytest

from tests.engine.home import Battery, Consumer, Grid, Home, Pv, expect
from tests.engine.manual.provenance import rows


class TestTheGridGoesFirst(Home):
    """Decision: a restricted sink allowed the grid draws it before competing
    for local generation, and a shared import splits in proportion to draw
    (rules 1 and 2 of "Choosing among valid allocations"; the worked example
    there).

    bat1 and bat2 may each use the grid and their own PV system. They take the
    whole 400 W import, 200 W each, and their other 200 W from their own PV
    system. That leaves pv1 800 W and pv2 400 W for bat3, cons1 and the 200 W
    base load, all split 2 : 1. The base load, also allowed the grid, gets
    none of it: the grid went first to the restricted sinks.
    """

    grid = Grid(400)
    pv1 = Pv(1000)
    pv2 = Pv(600)
    bat1 = Battery(-400, charge_from=(grid, pv1))
    bat2 = Battery(-400, charge_from=(grid, pv2))
    bat3 = Battery(-500, charge_from=(pv1, pv2))
    cons1 = Consumer(-500, power_from=(pv1, pv2))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The two batteries allowed the grid take all of it, half each.

        bat1 and bat2 draw the same 400 W, so the 400 W import splits evenly:
        200 W each, the other 200 W from their own PV system. bat3 and
        cons1, which may only use PV, then share what is left of pv1
        (800 W) and pv2 (400 W) in that 2 : 1 ratio.
        """
        return rows({
            "bat1": {"grid": 200, "pv1": 200, "pv2": 0},
            "bat2": {"grid": 200, "pv1": 0, "pv2": 200},
            "bat3": {"grid": 0, "pv1": F(1000, 3), "pv2": F(500, 3)},
            "cons1": {"grid": 0, "pv1": F(1000, 3), "pv2": F(500, 3)},
        })

    @expect("home_base_load_source_shares")
    def test_base_load_source_shares(self):
        """The base load gets no grid power, although it was allowed some.

        The 200 W base load is unrestricted, so it could have used the grid,
        but the restricted batteries already took the whole import. It runs
        on leftover PV instead, in the same 2 : 1 ratio as bat3 and cons1.
        """
        return {"grid": 0, "pv1": F(2, 3), "pv2": F(1, 3)}


class TestSameRestrictionGetsTheSameRow(Home):
    """Decision: scarce sources are split in proportion to draw, so two sinks
    with the same restriction come out with the same row (rule 2 of "Choosing
    among valid allocations").

    cons1 draws 100 W and cons2 300 W, exactly what pv1 and pv2 make together.
    Each PV system is split 1 : 3 between them, so both read pv1 3/4, pv2 1/4
    — serving them one at a time would have given one of them all of pv1.
    """

    grid = Grid(200)
    pv1 = Pv(300)
    pv2 = Pv(100)
    cons1 = Consumer(-100, power_from=(pv1, pv2))
    cons2 = Consumer(-300, power_from=(pv1, pv2))

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
    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """Two loads with the same restriction read the same mix, 3/4 : 1/4.

        Each PV system is shared between cons1 and cons2 in proportion to
        their draws, 100 : 300, so cons1 gets 75 W of pv1 and 25 W of pv2 and
        cons2 three times that. Both rows then read pv1 3/4, pv2 1/4. Known
        to fail today — see the xfail reason.
        """
        return rows({
            "cons1": {"grid": 0, "pv1": 75, "pv2": 25},
            "cons2": {"grid": 0, "pv1": 225, "pv2": 75},
        })


class TestRestrictedSinksAreServedFirst(Home):
    """Decision: unrestricted sinks — the base load included — take what is
    left after the restricted ones (rule 3 of "Choosing among valid
    allocations").

    cons1 may only use pv1 and takes 500 of its 600 W. The 900 W base load
    could have used pv1 too, but gets only the 100 W left, and 800 W grid.
    """

    grid = Grid(800)
    pv1 = Pv(600)
    cons1 = Consumer(-500, power_from=(pv1,))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The restricted load runs entirely on the source it is allowed.

        cons1 may only use pv1, and pv1's 600 W are enough for its 500 W
        draw, so its row is all pv1 and none of the grid.
        """
        return rows({"cons1": {"grid": 0, "pv1": 500}})

    @expect("home_base_load_source_shares")
    def test_base_load_source_shares(self):
        """The unrestricted base load gets only the PV that cons1 left over.

        The 900 W base load may use anything, so it is served last: the
        100 W of pv1 that cons1 did not need, and 800 W from the grid —
        8/9 grid, 1/9 pv1. Serving it first or in proportion would have
        given it more pv1.
        """
        return {"grid": F(8, 9), "pv1": F(1, 9)}


class TestASinkSplitsOverWhatIsLeft(Home):
    """Decision: a sink spreading its draw over several sources weights them by
    what is *left* of each, not by their readings (engine-calculations.md, "a
    sink splits over what is left"; its worked example).

    cons1 is captive to pv1 and takes 250 W of its 3000 W first. The 1200 W
    export may use pv1 and bat1, and splits over what is left of them,
    2750 : 400 — pv1 55/63 — not the 3000 : 400 their readings would give.
    """

    grid = Grid(-1200)
    pv1 = Pv(3000, exports=True)
    bat1 = Battery(400, exports=True)
    cons1 = Consumer(-250, power_from=(pv1,))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The export is split by what pv1 and bat1 have left, not by output.

        An exporting grid is a sink. cons1 is restricted to pv1 and takes
        its 250 W first, leaving pv1 2750 W and bat1 400 W. The 1200 W export
        splits 2750 : 400 — pv1 supplies 22000/21 W (55/63), bat1 3200/21 W.
        Splitting by the readings, 3000 : 400, would have given pv1 15/17.
        """
        return rows({
            "grid": {"pv1": F(22000, 21), "bat1": F(3200, 21)},
            "cons1": {"pv1": 250, "bat1": 0},
        })
