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

from tests.engine.home import Battery, Consumer, Grid, Home, Pv, expect
from tests.engine.manual.provenance import rows


class TestTheGridGoesFirst(Home):
    """Decision: restricted sinks allowed the grid take it first, split by draw.

    bat1 and bat2 may use the grid and take the whole 400 W import, so the
    unrestricted base load gets none of it. See rules 1 and 2 of "Choosing
    among valid allocations" (and its worked example) in
    engine-calculations.md.
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
        """bat1 and bat2 share the grid import evenly.

        Each draws 400 W: 200 W from the grid and 200 W from its own PV
        system. bat3 and cons1 split the leftover pv1 (800 W) and pv2 (400 W)
        2 : 1.
        """
        return rows({
            "bat1": {"grid": 200, "pv1": 200, "pv2": 0},
            "bat2": {"grid": 200, "pv1": 0, "pv2": 200},
            "bat3": {"grid": 0, "pv1": F(1000, 3), "pv2": F(500, 3)},
            "cons1": {"grid": 0, "pv1": F(1000, 3), "pv2": F(500, 3)},
        })

    @expect("home_base_load_source_shares")
    def test_base_load_source_shares(self):
        """The base load gets no grid power, although it is allowed some.

        The batteries already took the whole import, so the 200 W base load
        runs on leftover PV, 2 : 1 like bat3 and cons1.
        """
        return {"grid": 0, "pv1": F(2, 3), "pv2": F(1, 3)}


class TestSameRestrictionGetsTheSameRow(Home):
    """Decision: sinks with the same restriction get the same row.

    Scarce sources are split in proportion to draw: cons1 (100 W) and cons2
    (300 W) use all of pv1 and pv2, and each PV system is split 1 : 3 between
    them. See rule 2 of "Choosing among valid allocations" in
    engine-calculations.md.
    """

    grid = Grid(200)
    pv1 = Pv(300)
    pv2 = Pv(100)
    cons1 = Consumer(-100, power_from=(pv1, pv2))
    cons2 = Consumer(-300, power_from=(pv1, pv2))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """Both loads read the same mix: 3/4 pv1, 1/4 pv2.

        Each PV system is split 100 : 300 by draw, so cons1 gets 75 W pv1 and
        25 W pv2, and cons2 three times that. cons2 must take 200 W of pv1 in
        any valid plan, and 225 W honours that.
        """
        return rows({
            "cons1": {"grid": 0, "pv1": 75, "pv2": 25},
            "cons2": {"grid": 0, "pv1": 225, "pv2": 75},
        })


class TestRestrictedSinksAreServedFirst(Home):
    """Decision: unrestricted sinks, the base load included, get what is left.

    cons1 may only use pv1 and takes 500 of its 600 W, so the base load gets
    just the other 100 W and the rest from the grid. See rule 3 of "Choosing
    among valid allocations" in engine-calculations.md.
    """

    grid = Grid(800)
    pv1 = Pv(600)
    cons1 = Consumer(-500, power_from=(pv1,))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """cons1 runs entirely on pv1.

        pv1's 600 W cover cons1's 500 W draw, so it needs no grid power.
        """
        return rows({"cons1": {"grid": 0, "pv1": 500}})

    @expect("home_base_load_source_shares")
    def test_base_load_source_shares(self):
        """The base load gets only the pv1 power cons1 left over.

        The 900 W base load is served last: 100 W of pv1 and 800 W of grid,
        so 1/9 pv1 and 8/9 grid.
        """
        return {"grid": F(8, 9), "pv1": F(1, 9)}


class TestASinkSplitsOverWhatIsLeft(Home):
    """Decision: a sink splits its draw by what is left of each source.

    cons1 takes 250 W of pv1 first, so the 1200 W export splits over what
    remains, 2750 : 400, not over the readings, 3000 : 400. See "a sink splits
    over what is left" (and its worked example) in engine-calculations.md.
    """

    grid = Grid(-1200)
    pv1 = Pv(3000, exports=True)
    bat1 = Battery(400, exports=True)
    cons1 = Consumer(-250, power_from=(pv1,))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The export splits 2750 : 400 between pv1 and bat1.

        An exporting grid is a sink. After cons1's 250 W, pv1 has 2750 W left
        and bat1 400 W, so pv1 supplies 55/63 of the export. Splitting by the
        readings would have given 15/17.
        """
        return rows({
            "grid": {"pv1": F(22000, 21), "bat1": F(3200, 21)},
            "cons1": {"pv1": 250, "bat1": 0},
        })
