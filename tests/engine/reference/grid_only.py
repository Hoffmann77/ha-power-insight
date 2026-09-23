"""Reference case: Grid only."""

from __future__ import annotations

from tests.engine.reference.case import F, ReferenceCase
from tests.engine.scenario_framework import Adapter, State, state, topology


class GridOnly(ReferenceCase):
    """One meter and nothing else. Every published property still has a value
    here, which makes this the simplest place to see what the
    engine does at the edges: a single source, a house that draws nothing, and
    a sensor that has dropped out.

    Shows:

    * With no local device, the whole gross power is the unmetered home base
      load.
    * A sink with one available source has a provenance row of exactly one.
    * Marginal and levelized cost agree while the grid is the only source.
    * An unavailable meter collapses everything derived from it to nothing,
      while a total over an empty device set (no PV, no battery) stays zero.
    """

    case_id = "grid-only"
    title = "Grid only"

    @topology
    def wiring(self):
        return (Adapter.grid(),)

    # ----------------------------------------------------------------------

    @state
    def import_only(self):
        """The house runs on the grid alone; every watt is unmetered base load."""
        return State(
            grid=1200,
            price=F(3, 10),
        )

    # ----------------------------------------------------------------------

    @state
    def grid_idle(self):
        """The meter reads exactly 0 W: gross power is zero and every ratio has to
        survive it.

        Open question: at exactly 0 W the grid is idle — in no flow group — so
        every per-source map is empty and the sensors reading them publish
        nothing. A connected meter reading zero is arguably not the same as an
        absent one; whether these per-source sensors should show 0 (grid present,
        delivering nothing) rather than go blank is unsettled.
        """
        return State(
            grid=0,
            price=F(3, 10),
        )

    # ----------------------------------------------------------------------

    @state
    def grid_unavailable(self):
        """The grid sensor has dropped out. Everything derived from the meter
        collapses to nothing, while a total over an empty device set — no PV,
        no battery — is still a confident zero.

        Where a value is grid-derived (gross power, consumption, the ratios, the
        provenance maps, every cost rate) the engine publishes nothing at all
        rather than a stale or invented figure. Where a value is a structural
        sum over devices that do not exist here (production, charging,
        discharging, standby) it stays 0: the missing meter says nothing about
        PV that is not installed.
        """
        return State(
            grid=None,
            price=F(3, 10),
        )
