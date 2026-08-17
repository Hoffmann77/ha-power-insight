"""Captive battery.

bat1 may only charge from pv1. That single restriction changes the answer in
two opposite ways depending on whether pv1 is producing: when it is, the
captive sink depletes it before anyone else may share it; when it is not, the
sink has nowhere legal to draw from.

What this case pins down:

* A captive sink is served from its allowed source before flexible sinks share
  it.
* When every allowed source is idle the row collapses to zero rather than
  dividing by zero.
* The unservable draw is reported as a restriction deficit.
"""

from __future__ import annotations

from tests.engine.reference.case import F, Case, Snapshot
from tests.engine.scenario_framework import Adapter

CASE = Case(
    id="captive-battery",
    title="Captive battery",
    summary=(
        "bat1 may only charge from pv1. That single restriction changes the answer in two "
        "opposite ways depending on whether pv1 is producing: when it is, the captive sink "
        "depletes it before anyone else may share it; when it is not, the sink has nowhere "
        "legal to draw from."
    ),
    decides=[
        (
            "A captive sink is served from its allowed source before flexible sinks share "
            "it."
        ),
        (
            "When every allowed source is idle the row collapses to zero rather than "
            "dividing by zero."
        ),
        "The unservable draw is reported as a restriction deficit.",
    ],
    topology=[
        Adapter.grid(),
        Adapter.pv("pv1", lcoe=0.10, exports=True),
        Adapter.battery("bat1", lcos=0.15, charge_from=("pv1",)),
        Adapter.consumer("cons1"),
    ],
    snapshots=[
        Snapshot(
            id="captive_depletes_first",
            note="pv1 produces exactly what bat1 draws, so bat1 takes all of it.",
            readings=dict(grid=500, pv1=400, bat1=-400, cons1=-200),
            price=F(3, 10),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
        Snapshot(
            id="source_in_standby",
            note=(
                "pv1 is drawing standby, so it is a sink; bat1's only allowed source does "
                "not exist."
            ),
            readings=dict(grid=1000, pv1=-20, bat1=-400, cons1=-100),
            price=F(3, 10),
            open_question=(
                "home_base_load_power includes the 400 W bat1 drew but could not legally "
                "be attributed, so the 'unmetered' load contains a device that has a meter "
                "on it. Its docstring says gross minus metered draw, which would be 580 W "
                "rather than 980 W."
            ),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
    ],
)
