"""Reference case: Mixed export house."""

from __future__ import annotations

from tests.engine.home import Battery, Consumer, Grid, Pv
from tests.engine.reference.case import F, ReferenceCase, Snapshot


class MixedExportHouse(ReferenceCase):
    """Every device class at once, with the export permissions deliberately
    unequal: one battery may feed the grid and the other may not. Nothing here
    appears for the first time — this is the case that shows the rules of
    the lower rungs still hold when they all apply together.

    Shows:

    * A device that cannot export is excluded from the export mix, even while
      discharging.
    * Standby draw is routed through the provenance allocation, not by gross
      share.
    * Two dischargers with different levelized costs price the mix between
      them.
    """

    case_id = "mixed-export-house"
    title = "Mixed export house"

    grid = Grid()
    pv1 = Pv(lcoe=0.10, exports=True, export_comp=0.08)
    pv2 = Pv(lcoe=0.10, exports=True, export_comp=0.08)
    bat1 = Battery(lcos=0.15, exports=True, export_comp=0.08)
    bat2 = Battery(lcos=0.20, exports=False)
    cons1 = Consumer()

    class ExportNonExportingBattery(Snapshot):
        """bat2 discharges but may not feed the grid, so the export mix excludes
        it.
        """

        grid = -600
        pv1 = 800
        pv2 = 0
        bat1 = 200
        bat2 = 200
        cons1 = -400
        price = F(1, 4)

    class ExportWithStandby(Snapshot):
        """pv2 in standby while the house exports; standby competes in the
        allocation.
        """

        grid = -600
        pv1 = 800
        pv2 = -50
        bat1 = 200
        bat2 = 200
        cons1 = -400
        price = F(1, 4)

    class DischargeDynamicPrices(Snapshot):
        """Both batteries discharging; the mix they charged on is in the past."""

        grid = -300
        pv1 = 0
        pv2 = -50
        bat1 = 400
        bat2 = 400
        cons1 = -400
        price = F(1, 4)
