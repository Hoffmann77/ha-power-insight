"""Battery basics.

An unrestricted battery, which is the only device that changes which side of
the diagram it sits on. Charging it is a sink like any other; discharging it is
a source whose energy was paid for in the past, and a snapshot engine has to
price that somehow.

What this case pins down:

* A charging battery is a sink and takes the same raw mix as any other.
* A discharging battery is a source priced at its flat levelized cost of
  storage.
* Its marginal price is zero — the mix it charged on happened earlier, where a
  snapshot cannot see it.
* An adapter reading exactly 0 W belongs to neither flow group.
"""

from __future__ import annotations

from tests.engine.reference.case import F, Case, Snapshot
from tests.engine.scenario_framework import Adapter

CASE = Case(
    id="battery-basics",
    title="Battery basics",
    summary=(
        "An unrestricted battery, which is the only device that changes which side of the "
        "diagram it sits on. Charging it is a sink like any other; discharging it is a "
        "source whose energy was paid for in the past, and a snapshot engine has to price "
        "that somehow."
    ),
    decides=[
        "A charging battery is a sink and takes the same raw mix as any other.",
        (
            "A discharging battery is a source priced at its flat levelized cost of "
            "storage."
        ),
        (
            "Its marginal price is zero — the mix it charged on happened earlier, where a "
            "snapshot cannot see it."
        ),
        "An adapter reading exactly 0 W belongs to neither flow group.",
    ],
    topology=[
        Adapter.grid(),
        Adapter.pv("pv1", lcoe=0.10),
        Adapter.consumer("cons1"),
        Adapter.battery("bat1", lcos=0.15),
    ],
    snapshots=[
        Snapshot(
            id="charging",
            note=(
                "bat1 charges from the mix, taking the same proportions as the metered "
                "load beside it."
            ),
            readings=dict(grid=800, pv1=600, cons1=-500, bat1=-600),
            price=F(3, 10),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
        Snapshot(
            id="discharging",
            note=(
                "The sun is down and bat1 has become a source, supplying two thirds of the "
                "house."
            ),
            readings=dict(grid=200, pv1=0, cons1=-500, bat1=400),
            price=F(3, 10),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
        Snapshot(
            id="idle",
            note=(
                "bat1 sits at exactly 0 W: neither a source nor a sink, and absent from "
                "both groups."
            ),
            readings=dict(grid=900, pv1=600, cons1=-500, bat1=0),
            price=F(3, 10),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
    ],
)
