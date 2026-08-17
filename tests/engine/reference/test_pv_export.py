"""Reference case: PV export."""

from __future__ import annotations

from tests.engine.reference.case import F, ReferenceCase, expect  # noqa: F401
from tests.engine.scenario_framework import Adapter, State, state, topology

# `expect` is imported ready for the first answer derived here — see
# tests/engine/reference/case.py for how to write one.


class TestPvExport(ReferenceCase):
    """The same two devices, with the string now permitted to export. Reversing
    the grid changes its kind rather than its sign: it stops being a source and
    becomes a sink, which is all it takes to switch on the export channel and
    its compensation.

    Decides:

    * An exporting grid is a sink, not a source with a negative reading.
    * Export compensation is earned by the sources the export was drawn from.
    * The applicable self-consumption ratio measures only what stayed home.
    * Zero gross power guards to zero rather than dividing by zero.
    """

    case_id = "pv-export"
    title = "PV export"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10, exports=True, export_comp=0.08),
        )

    # ----------------------------------------------------------------------

    @state
    def export_surplus(self):
        """The string outruns the house; the surplus leaves through the grid."""
        return State(grid=-400, pv1=900, price=F(1, 4))

    # Nothing derived for this snapshot yet. Add @expect methods here;
    # see tests/engine/reference/case.py.

    # ----------------------------------------------------------------------

    @state
    def export_all(self):
        """Everything the string makes is exported: the home base load is exactly
        zero.
        """
        return State(grid=-900, pv1=900, price=F(1, 4))

    # Nothing derived for this snapshot yet. Add @expect methods here;
    # see tests/engine/reference/case.py.

    # ----------------------------------------------------------------------

    @state
    def zero_gross(self):
        """The grid exports while nothing is producing — an impossible meter set
        that must not divide by zero.
        """
        return State(grid=-500, pv1=0, price=F(1, 4))

    # Nothing derived for this snapshot yet. Add @expect methods here;
    # see tests/engine/reference/case.py.
