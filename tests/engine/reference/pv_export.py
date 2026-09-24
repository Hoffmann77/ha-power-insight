"""Reference case: PV export."""

from __future__ import annotations

from tests.engine.home import Grid, Pv
from tests.engine.reference.case import F, ReferenceCase, Snapshot


class PvExport(ReferenceCase):
    """The same two devices, with the PV system now permitted to export. Reversing
    the grid changes its kind rather than its sign: it stops being a source and
    becomes a sink, which is all it takes to switch on the export channel and
    its compensation.

    Shows:

    * An exporting grid is a sink, not a source with a negative reading.
    * Export compensation is earned by the sources the export was drawn from.
    * Zero gross power guards to zero rather than dividing by zero.
    """

    case_id = "pv-export"
    title = "PV export"

    grid = Grid()
    pv1 = Pv(lcoe=0.10, exports=True, export_comp=0.08)

    class ExportSurplus(Snapshot):
        """The PV system outruns the house; the surplus leaves through the grid."""

        grid = -400
        pv1 = 900
        price = F(1, 4)

    class ExportAll(Snapshot):
        """Everything the PV system makes is exported: the home base load is exactly
        zero.
        """

        grid = -900
        pv1 = 900
        price = F(1, 4)

    class ZeroGross(Snapshot):
        """The grid exports while nothing is producing — an impossible meter set
        that must not divide by zero.
        """

        grid = -500
        pv1 = 0
        price = F(1, 4)
