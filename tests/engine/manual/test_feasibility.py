"""Feasibility: which allocations honour every restriction at all.

Before choosing an answer, the engine works out which allocations are
*feasible* — which honour every sink's restriction and balance every total.
It decides that for groups of sinks together, with a max-flow computation;
feasibility always outranks the rules that choose among answers; and power
that every feasible allocation must send to a sink (a *reserve*) is never
taken away from it. See "It is a transportation problem" in
``docs/dev/engine-calculations.md``, and ``provenance.py`` for how the
expected provenance is written.

The *restriction deficit* (``sink_adapters_restriction_deficit``) is how many
watts a sink had to take from a source it is not allowed; an empty map says
every restriction was honoured.
"""

from __future__ import annotations

from fractions import Fraction as F

from tests.engine.home import Battery, Consumer, Grid, Home, Pv, expect
from tests.engine.manual.provenance import rows


class TestFeasibilityIsDecidedForGroups(Home):
    """Decision: feasibility is checked for groups of sinks together, with max flow.

    Each battery alone could use east or west, but together they need all of
    both, so the plug must take the carport. See "feasibility is decided for
    groups" in engine-calculations.md.
    """

    grid = Grid(200)
    east = Pv(100)
    west = Pv(100)
    carport = Pv(100)
    bat_a = Battery(-100, charge_from=(east, west))
    bat_b = Battery(-100, charge_from=(east, west))
    plug = Consumer(-100, power_from=(east, carport))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The plug stays off east because the batteries need all of it.

        bat_a and bat_b take 50 W each from east and west (all 200 W), so the
        plug's 100 W come entirely from the carport.
        """
        return rows({
            "bat_a": {"grid": 0, "east": 50, "west": 50, "carport": 0},
            "bat_b": {"grid": 0, "east": 50, "west": 50, "carport": 0},
            "plug": {"grid": 0, "east": 0, "west": 0, "carport": 100},
        })

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """No restriction is broken, so the deficit map is empty.

        The allocation above honours every restriction, and the engine finds
        it.
        """
        return {}


class TestFeasibilityOutranksTheRules(Home):
    """Decision: the allocation rules only choose among feasible allocations.

    The proportional rule would give bat1 and bat2 200 W of grid each, but
    cons1 needs all of pv1, so bat1 must take 300 W of grid. See "feasibility
    outranks all three" in engine-calculations.md.
    """

    grid = Grid(400)
    pv1 = Pv(100)
    pv2 = Pv(200)
    bat1 = Battery(-300, charge_from=(grid, pv1))
    bat2 = Battery(-300, charge_from=(grid, pv2))
    cons1 = Consumer(-100, power_from=(pv1,))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """bat1 takes more grid than an even split would give it.

        cons1 needs all of pv1, so bat1 gets its 300 W from the grid. bat2
        gets the remaining 100 W of grid plus pv2's 200 W.
        """
        return rows({
            "bat1": {"grid": 300, "pv1": 0, "pv2": 0},
            "bat2": {"grid": 100, "pv1": 0, "pv2": 200},
            "cons1": {"grid": 0, "pv1": 100, "pv2": 0},
        })

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """No restriction is broken: the rule gave way instead.

        Following the proportional rule would have forced a restriction to
        break; the allocation above honours them all.
        """
        return {}


class TestACaptiveSinkTakesTheWholeImport(Home):
    """Decision: a sink allowed only the grid takes the whole import.

    bat1, bat2 and bat3 may all use the grid, but bat3 may use nothing else,
    so the rules give way and bat1 and bat2 get no grid at all. See
    "feasibility outranks all three" in engine-calculations.md.
    """

    grid = Grid(600)
    pv1 = Pv(1000)
    pv2 = Pv(600)
    bat1 = Battery(-400, charge_from=(grid, pv1))
    bat2 = Battery(-400, charge_from=(grid, pv2))
    bat3 = Battery(-600, charge_from=(grid,))
    cons1 = Consumer(-500, power_from=(pv1, pv2))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """bat3 takes all 600 W of grid; bat1 and bat2 run on their own PV.

        bat1 then takes 400 W of pv1 and bat2 400 W of pv2. cons1 splits over
        what is left, pv1 600 W and pv2 200 W, 3 : 1: 375 W and 125 W.
        """
        return rows({
            "bat1": {"grid": 0, "pv1": 400, "pv2": 0},
            "bat2": {"grid": 0, "pv1": 0, "pv2": 400},
            "bat3": {"grid": 600, "pv1": 0, "pv2": 0},
            "cons1": {"grid": 0, "pv1": 375, "pv2": 125},
        })

    @expect("home_base_load_source_shares")
    def test_base_load_source_shares(self):
        """The base load gets the last 225 W of pv1 and 75 W of pv2.

        It is unrestricted, so it is served last: the 300 W base load reads
        3/4 pv1, 1/4 pv2, and no grid.
        """
        return {"grid": 0, "pv1": F(3, 4), "pv2": F(1, 4)}

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """No restriction is broken, so the deficit map is empty.

        The allocation above honours every restriction, including bat3's
        grid-only one.
        """
        return {}


class TestReservesAreNeverScaledAway(Home):
    """Decision: power reserved for a sink is never scaled away.

    The carport may only feed the export, so all 200 W of it are the export's
    reserve. The export is offered more than it needs and its offers are
    scaled down, but never below that reserve. See "what every valid
    allocation carries is never scaled away" in engine-calculations.md.
    """

    grid = Grid(-1800)
    east = Pv(1000, exports=True)
    west = Pv(1000, exports=True)
    carport = Pv(200, exports=True)
    plug = Consumer(-400, power_from=(east, west))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The export keeps all of the carport, which only it may use.

        The export takes the carport's 200 W plus 800 W each from east and
        west. The plug takes 200 W each from east and west, and none from the
        carport.
        """
        return rows({
            "grid": {"east": 800, "west": 800, "carport": 200},
            "plug": {"east": 200, "west": 200, "carport": 0},
        })

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """No restriction is broken, so the deficit map is empty.

        Scaling the carport's reserve away would have pushed carport power
        onto the plug and reported a deficit that does not exist.
        """
        return {}
