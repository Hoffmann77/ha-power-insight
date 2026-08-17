"""Mixed export house.

Every device class at once, with the export permissions deliberately unequal:
one battery may feed the grid and the other may not. Nothing here is settled
for the first time — this is the case that checks the rules of the lower rungs
still hold when they all apply together.

What this case pins down:

* A device that cannot export is excluded from the export mix, even while
  discharging.
* Standby draw is routed through the provenance allocation, not by gross share.
* Two dischargers with different levelized costs price the mix between them.
"""

from __future__ import annotations

from tests.engine.reference.case import F, Case, Snapshot
from tests.engine.scenario_framework import Adapter

CASE = Case(
    id="mixed-export-house",
    title="Mixed export house",
    summary=(
        "Every device class at once, with the export permissions deliberately unequal: one "
        "battery may feed the grid and the other may not. Nothing here is settled for the "
        "first time — this is the case that checks the rules of the lower rungs still hold "
        "when they all apply together."
    ),
    decides=[
        (
            "A device that cannot export is excluded from the export mix, even while "
            "discharging."
        ),
        "Standby draw is routed through the provenance allocation, not by gross share.",
        "Two dischargers with different levelized costs price the mix between them.",
    ],
    topology=[
        Adapter.grid(),
        Adapter.pv("pv1", lcoe=0.10, exports=True, export_comp=0.08),
        Adapter.pv("pv2", lcoe=0.10, exports=True, export_comp=0.08),
        Adapter.battery("bat1", lcos=0.15, exports=True, export_comp=0.08),
        Adapter.battery("bat2", lcos=0.20, exports=False),
        Adapter.consumer("cons1"),
    ],
    snapshots=[
        Snapshot(
            id="export_non_exporting_battery",
            note="bat2 discharges but may not feed the grid, so the export mix excludes it.",
            readings=dict(grid=-600, pv1=800, pv2=0, bat1=200, bat2=200, cons1=-400),
            price=F(1, 4),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
        Snapshot(
            id="export_with_standby",
            note=(
                "pv2 in standby while the house exports; standby competes in the "
                "allocation."
            ),
            readings=dict(grid=-600, pv1=800, pv2=-50, bat1=200, bat2=200, cons1=-400),
            price=F(1, 4),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
        Snapshot(
            id="discharge_dynamic_prices",
            note="Both batteries discharging; the mix they charged on is in the past.",
            readings=dict(grid=-300, pv1=0, pv2=-50, bat1=400, bat2=400, cons1=-400),
            price=F(1, 4),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
    ],
)
