"""Reference case: Two PV systems."""

from __future__ import annotations

from tests.engine.reference.case import F, ReferenceCase
from tests.engine.scenario_framework import Adapter, State, state, topology


class TwoPvSystems(ReferenceCase):
    """Two equal PV systems, east and west, and a smaller third on the carport.
    A plug may run on east or west but not on the carport. Everything else is
    exported, and there is no unmetered base load, so every watt in the house
    is spoken for.

    The plug needs 400 W from east and west together, but neither system in
    particular — either one alone could cover it. That is easy to get wrong: a
    solver that reasons one source at a time finds nothing it must set aside
    for the plug on east, nothing on west, and can hand the export watts the
    plug needed.

    Shows:

    * A restriction naming several PV systems is honoured jointly: a load
      allowed two systems is served from them whenever together they can cover
      it, even though it needs neither in particular.
    * A sink spreads its draw over the systems it may use in proportion to
      what each has left, so two equal systems each carry half of it.
    """

    case_id = "two-pv-systems"
    title = "Two PV systems"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("east", lcoe=0.10, exports=True),
            Adapter.pv("west", lcoe=0.10, exports=True),
            Adapter.pv("carport", lcoe=0.10, exports=True),
            Adapter.consumer("plug", power_from=("east", "west")),
        )

    # ----------------------------------------------------------------------

    @state
    def every_watt_spoken_for(self):
        """East and west make 1000 W each and the carport 200 W. The plug draws
        400 W and the other 1800 W is exported. The carport's power can only go
        to the export, so the export takes all of it, and east and west cover
        the rest of the export and the whole plug — exactly.
        """
        return State(
            grid=-1800,
            east=1000,
            west=1000,
            carport=200,
            plug=-400,
            price=F(3, 10),
        )
