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

from tests.engine.home import Battery, Consumer, Grid, Home, Pv, expect
from tests.engine.manual.provenance import rows


class TestFeasibilityIsDecidedForGroups(Home):
    """Decision: feasibility is decided for groups of sinks, with max flow
    (engine-calculations.md, "feasibility is decided for groups").

    Each battery on its own could be covered by east or by west, so asking
    sink by sink finds nothing either *must* have. But together they need
    every watt east and west make. The plug may use east or the carport; it
    must take the carport, or the pair comes up short.
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
        """The plug stays off east, because the two batteries need all of it.

        Together bat_a and bat_b need every watt of east and west (200 W),
        so they split both evenly, 50 W from each. The plug may use east or
        the carport, and gets all of its 100 W from the carport — any east
        power it took would leave a battery short.
        """
        return rows({
            "bat_a": {"grid": 0, "east": 50, "west": 50, "carport": 0},
            "bat_b": {"grid": 0, "east": 50, "west": 50, "carport": 0},
            "plug": {"grid": 0, "east": 0, "west": 0, "carport": 100},
        })

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """No restriction is broken, so no deficit is reported.

        An allocation honouring every restriction exists — the one above —
        and the engine finds it, so the deficit map is empty.
        """
        return {}


class TestFeasibilityOutranksTheRules(Home):
    """Decision: feasibility outranks the rules — they only choose among
    allocations that already work (engine-calculations.md, "feasibility
    outranks all three").

    bat1 and bat2 draw 300 W each and may both use the grid's 400 W, so the
    proportional rule says 200 W each. But cons1 needs all of pv1, leaving
    bat1 nothing local: it must take 300 W of grid, and bat2 the other 100 W
    with pv2's 200 W.
    """

    grid = Grid(400)
    pv1 = Pv(100)
    pv2 = Pv(200)
    bat1 = Battery(-300, charge_from=(grid, pv1))
    bat2 = Battery(-300, charge_from=(grid, pv2))
    cons1 = Consumer(-100, power_from=(pv1,))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """bat1 takes more of the grid than an even split would give it.

        The proportional rule alone would split the 400 W import 200 : 200
        between the two equal batteries. But cons1 may only use pv1 and needs
        all of it, so bat1 has no local power left and must take 300 W from
        the grid. bat2 gets the remaining 100 W of grid plus pv2's 200 W.
        """
        return rows({
            "bat1": {"grid": 300, "pv1": 0, "pv2": 0},
            "bat2": {"grid": 100, "pv1": 0, "pv2": 200},
            "cons1": {"grid": 0, "pv1": 100, "pv2": 0},
        })

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """No restriction is broken: the rule gave way, not the restriction.

        The allocation above honours every restriction, so the deficit map
        is empty. Following the proportional rule would have forced a
        restriction to break instead.
        """
        return {}


class TestReservesAreNeverScaledAway(Home):
    """Decision: what every valid allocation carries is never scaled away
    (engine-calculations.md).

    The plug may use east or west, and needs neither in particular, so nothing
    is reserved for it on either. The carport may only feed the export, so all
    200 W of it is the export's reserve. The export is offered more than its
    1800 W and its offers are scaled down — but never below that 200 W, or the
    carport's leftover would be forced onto the plug, which may not use it.
    """

    grid = Grid(-1800)
    east = Pv(1000, exports=True)
    west = Pv(1000, exports=True)
    carport = Pv(200, exports=True)
    plug = Consumer(-400, power_from=(east, west))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The export keeps all of the carport, the one source only it may use.

        An exporting grid is a sink. The carport's 200 W can go nowhere but
        the export, so the export takes all of it and its other 1600 W half
        from east and half from west. The plug takes its 400 W half from
        each of the two systems it may use, and none from the carport.
        """
        return rows({
            "grid": {"east": 800, "west": 800, "carport": 200},
            "plug": {"east": 200, "west": 200, "carport": 0},
        })

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """No restriction is broken, so no deficit is reported.

        Every restriction can be honoured here. Scaling the carport's reserve
        away would have left carport power stranded and pushed it onto the
        plug, reporting a deficit for a house with nothing wrong in it.
        """
        return {}
