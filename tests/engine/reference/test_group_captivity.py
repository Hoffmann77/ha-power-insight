"""Reference case: Group captivity."""

from __future__ import annotations

from tests.engine.reference.case import F, ReferenceCase, expect  # noqa: F401
from tests.engine.scenario_framework import Adapter, State, state, topology

# `expect` is imported ready for the first answer derived here — see
# tests/engine/reference/case.py for how to write one.


class TestGroupCaptivity(ReferenceCase):
    """Two batteries are each allowed both strings, and neither is individually
    stuck — but together they need every watt the two strings make. Deciding
    feasibility one sink at a time cannot see that; this is the case the max-
    flow solver exists for.

    Decides:

    * Feasibility is a property of groups of sinks, not of single sinks.
    * A flexible sink must not take local power a tight group needs.
    * When restrictions cannot all be honoured, the sink with the fewest
      permitted alternatives is served first and the deficit falls on the sinks
      that had somewhere else to go.
    """

    case_id = "group-captivity"
    title = "Group captivity"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("east", lcoe=0.10, exports=True),
            Adapter.pv("west", lcoe=0.10, exports=True),
            Adapter.battery("bat_a", lcos=0.15, charge_from=("east", "west")),
            Adapter.battery("bat_b", lcos=0.15, charge_from=("east", "west")),
            Adapter.battery("bat_c", lcos=0.15, charge_from=("east",)),
        )

    # ----------------------------------------------------------------------

    @state
    def hall_tight_pair(self):
        """bat_c idle. {bat_a, bat_b} exactly exhaust east+west, so the 200 W home
        load must be served entirely from the grid.
        """
        return State(
            grid=200,
            east=100,
            west=100,
            bat_a=-100,
            bat_b=-100,
            bat_c=0,
            price=F(3, 10),
        )

    # Nothing derived for this snapshot yet. Add @expect methods here;
    # see tests/engine/reference/case.py.

    # ----------------------------------------------------------------------

    @state
    def unsatisfiable_overlap(self):
        """bat_c now draws 100 W and is captive to east alone. Captive demand (300
        W) exceeds local supply (200 W): someone must be deficited.
        """
        return State(
            grid=200,
            east=100,
            west=100,
            bat_a=-100,
            bat_b=-100,
            bat_c=-100,
            price=F(3, 10),
        )

    # Nothing derived for this snapshot yet. Add @expect methods here;
    # see tests/engine/reference/case.py.
