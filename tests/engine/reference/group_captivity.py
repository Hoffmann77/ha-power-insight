"""Reference case: Group captivity."""

from __future__ import annotations

from tests.engine.home import Battery, Grid, Pv
from tests.engine.reference.case import F, ReferenceCase, Snapshot


class GroupCaptivity(ReferenceCase):
    """Two batteries are each allowed both PV systems, and neither is individually
    stuck — but together they need every watt the two PV systems make. Deciding
    feasibility one sink at a time cannot see that; this is the case the max-
    flow solver exists for.

    Shows:

    * Feasibility is a property of groups of sinks, not of single sinks.
    * A flexible sink must not take local power a tight group needs.
    * When restrictions cannot all be honoured, the sink with the fewest
      permitted alternatives is served first and the deficit falls on the sinks
      that had somewhere else to go.
    """

    case_id = "group-captivity"
    title = "Group captivity"

    grid = Grid()
    east = Pv(lcoe=0.10, exports=True)
    west = Pv(lcoe=0.10, exports=True)
    bat_a = Battery(lcos=0.15, charge_from=(east, west))
    bat_b = Battery(lcos=0.15, charge_from=(east, west))
    bat_c = Battery(lcos=0.15, charge_from=(east,))

    class HallTightPair(Snapshot):
        """bat_c idle. {bat_a, bat_b} exactly exhaust east+west, so the 200 W home
        load must be served entirely from the grid.
        """

        grid = 200
        east = 100
        west = 100
        bat_a = -100
        bat_b = -100
        bat_c = 0
        price = F(3, 10)

    class UnsatisfiableOverlap(Snapshot):
        """bat_c now draws 100 W and is captive to east alone. Captive demand (300
        W) exceeds local supply (200 W): someone must be deficited.
        """

        grid = 200
        east = 100
        west = 100
        bat_a = -100
        bat_b = -100
        bat_c = -100
        price = F(3, 10)
