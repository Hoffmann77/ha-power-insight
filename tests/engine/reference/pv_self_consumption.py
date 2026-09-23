"""Reference case: PV self-consumption."""

from __future__ import annotations

from tests.engine.reference.case import F, ReferenceCase
from tests.engine.scenario_framework import Adapter, State, state, topology


class PvSelfConsumption(ReferenceCase):
    """One PV system added to the grid, and nothing restricted. Two sources are
    enough for the raw proportional mix, for the divergence between what power
    costs now and what it costs levelized, and for a PV system that is drawing
    rather than producing.

    Shows:

    * An unrestricted sink's provenance row is the raw source mix.
    * PV standby is a sink drawing from the mix, not negative production.
    * Marginal cost and levelized cost diverge as soon as a local source runs.
    * A source that only draws standby makes the saving rate negative.
    """

    case_id = "pv-self-consumption"
    title = "PV self-consumption"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10),
        )

    # ----------------------------------------------------------------------

    @state
    def sunny_partial(self):
        """Grid and PV system both supplying; the base load takes them in proportion."""
        return State(grid=800, pv1=600, price=F(3, 10))

    # ----------------------------------------------------------------------

    @state
    def pv_covers_all(self):
        """The PV system covers the house exactly. The grid is present but
        contributes nothing.
        """
        return State(grid=0, pv1=600, price=F(3, 10))

    # ----------------------------------------------------------------------

    @state
    def pv_standby(self):
        """pv1 draws 20 W standby, so it is a sink served by the grid — and the
        saving goes negative.
        """
        return State(grid=1000, pv1=-20, price=F(3, 10))

    # ----------------------------------------------------------------------

    @state
    def pv_unavailable(self):
        """The PV system's sensor has dropped out; the grid still reads, but the
        total cannot be trusted.
        """
        return State(grid=1000, pv1=None, price=F(3, 10))
