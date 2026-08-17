"""Captive load.

The same three devices, with the consumer now restricted to the string. This is
the smallest wiring in which a restriction can be honoured at all — and the
smallest in which one can fail, which is where the restriction deficit is first
published.

What this case pins down:

* A restricted sink is served from its allowed sources before anything
  unrestricted shares them.
* Serving the captive sink first pushes the unrestricted base load onto the
  grid.
* A draw the allowed sources cannot cover is still attributed, and the
  shortfall is reported as a restriction deficit.
"""

from __future__ import annotations

from tests.engine.reference.case import F, Case, Snapshot
from tests.engine.scenario_framework import Adapter

CASE = Case(
    id="captive-load",
    title="Captive load",
    summary=(
        "The same three devices, with the consumer now restricted to the string. This is "
        "the smallest wiring in which a restriction can be honoured at all — and the "
        "smallest in which one can fail, which is where the restriction deficit is first "
        "published."
    ),
    decides=[
        (
            "A restricted sink is served from its allowed sources before anything "
            "unrestricted shares them."
        ),
        (
            "Serving the captive sink first pushes the unrestricted base load onto the "
            "grid."
        ),
        (
            "A draw the allowed sources cannot cover is still attributed, and the "
            "shortfall is reported as a restriction deficit."
        ),
    ],
    topology=[
        Adapter.grid(),
        Adapter.pv("pv1", lcoe=0.10),
        Adapter.consumer("cons1", power_from=("pv1",)),
    ],
    snapshots=[
        Snapshot(
            id="captive_load",
            note=(
                "pv1 makes more than cons1 draws, so cons1 runs on solar alone and the "
                "base load is pushed onto the grid."
            ),
            readings=dict(grid=800, pv1=600, cons1=-500),
            price=F(3, 10),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
        Snapshot(
            id="load_exceeds",
            note=(
                "cons1 draws 500 W but pv1 makes only 300 W: the missing 200 W came from a "
                "source it is not allowed to use."
            ),
            readings=dict(grid=800, pv1=300, cons1=-500),
            price=F(3, 10),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
    ],
)
