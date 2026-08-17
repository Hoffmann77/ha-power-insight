"""PV export.

The same two devices, with the string now permitted to export. Reversing the
grid changes its kind rather than its sign: it stops being a source and becomes
a sink, which is all it takes to switch on the export channel and its
compensation.

What this case pins down:

* An exporting grid is a sink, not a source with a negative reading.
* Export compensation is earned by the sources the export was drawn from.
* The applicable self-consumption ratio measures only what stayed home.
* Zero gross power guards to zero rather than dividing by zero.
"""

from __future__ import annotations

from tests.engine.reference.case import F, Case, Snapshot
from tests.engine.scenario_framework import Adapter

CASE = Case(
    id="pv-export",
    title="PV export",
    summary=(
        "The same two devices, with the string now permitted to export. Reversing the grid "
        "changes its kind rather than its sign: it stops being a source and becomes a "
        "sink, which is all it takes to switch on the export channel and its compensation."
    ),
    decides=[
        "An exporting grid is a sink, not a source with a negative reading.",
        "Export compensation is earned by the sources the export was drawn from.",
        "The applicable self-consumption ratio measures only what stayed home.",
        "Zero gross power guards to zero rather than dividing by zero.",
    ],
    topology=[
        Adapter.grid(),
        Adapter.pv("pv1", lcoe=0.10, exports=True, export_comp=0.08),
    ],
    snapshots=[
        Snapshot(
            id="export_surplus",
            note="The string outruns the house; the surplus leaves through the grid.",
            readings=dict(grid=-400, pv1=900),
            price=F(1, 4),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
        Snapshot(
            id="export_all",
            note=(
                "Everything the string makes is exported: the home base load is exactly "
                "zero."
            ),
            readings=dict(grid=-900, pv1=900),
            price=F(1, 4),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
        Snapshot(
            id="zero_gross",
            note=(
                "The grid exports while nothing is producing — an impossible meter set "
                "that must not divide by zero."
            ),
            readings=dict(grid=-500, pv1=0),
            price=F(1, 4),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
    ],
)
