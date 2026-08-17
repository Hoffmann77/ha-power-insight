"""PV self-consumption.

One string added to the grid, and nothing restricted. Two sources are enough
for the raw proportional mix, for the divergence between what power costs now
and what it costs levelized, and for a string that is drawing rather than
producing.

What this case pins down:

* An unrestricted sink's provenance row is the raw source mix.
* PV standby is a sink drawing from the mix, not negative production.
* Marginal cost and levelized cost diverge as soon as a local source runs.
* A source that only draws standby makes the saving rate negative.
"""

from __future__ import annotations

from tests.engine.reference.case import F, Case, Snapshot
from tests.engine.scenario_framework import Adapter

CASE = Case(
    id="pv-self-consumption",
    title="PV self-consumption",
    summary=(
        "One string added to the grid, and nothing restricted. Two sources are enough for "
        "the raw proportional mix, for the divergence between what power costs now and "
        "what it costs levelized, and for a string that is drawing rather than producing."
    ),
    decides=[
        "An unrestricted sink's provenance row is the raw source mix.",
        "PV standby is a sink drawing from the mix, not negative production.",
        "Marginal cost and levelized cost diverge as soon as a local source runs.",
        "A source that only draws standby makes the saving rate negative.",
    ],
    topology=[
        Adapter.grid(),
        Adapter.pv("pv1", lcoe=0.10),
    ],
    snapshots=[
        Snapshot(
            id="sunny_partial",
            note="Grid and string both supplying; the base load takes them in proportion.",
            readings=dict(grid=800, pv1=600),
            price=F(3, 10),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
        Snapshot(
            id="pv_covers_all",
            note=(
                "The string covers the house exactly. The grid is present but contributes "
                "nothing."
            ),
            readings=dict(grid=0, pv1=600),
            price=F(3, 10),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
        Snapshot(
            id="pv_standby",
            note=(
                "pv1 draws 20 W standby, so it is a sink served by the grid — and the "
                "saving goes negative."
            ),
            readings=dict(grid=1000, pv1=-20),
            price=F(3, 10),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
        Snapshot(
            id="pv_unavailable",
            note=(
                "The string's sensor has dropped out; the grid still reads, but the total "
                "cannot be trusted."
            ),
            readings=dict(grid=1000, pv1=None),
            price=F(3, 10),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
    ],
)
