"""Metered load.

A consumer with a meter on it, next to the unmetered remainder. The base load
stops being the whole house and becomes what is left after the metered draw —
including when the meters disagree and there is nothing left.

What this case pins down:

* A metered consumer gets its own provenance row; the remainder is the home
  base load.
* A metered draw larger than gross power clamps the base load to zero rather
  than going negative.
* A zeroed base load still publishes a share row, of zeros.
"""

from __future__ import annotations

from tests.engine.reference.case import F, Case, Snapshot
from tests.engine.scenario_framework import Adapter

CASE = Case(
    id="metered-load",
    title="Metered load",
    summary=(
        "A consumer with a meter on it, next to the unmetered remainder. The base load "
        "stops being the whole house and becomes what is left after the metered draw — "
        "including when the meters disagree and there is nothing left."
    ),
    decides=[
        (
            "A metered consumer gets its own provenance row; the remainder is the home "
            "base load."
        ),
        (
            "A metered draw larger than gross power clamps the base load to zero rather "
            "than going negative."
        ),
        "A zeroed base load still publishes a share row, of zeros.",
    ],
    topology=[
        Adapter.grid(),
        Adapter.pv("pv1", lcoe=0.10),
        Adapter.consumer("cons1"),
    ],
    snapshots=[
        Snapshot(
            id="load_and_base",
            note=(
                "cons1 draws 500 W of the 1400 W entering the house; the other 900 W is "
                "unmetered."
            ),
            readings=dict(grid=800, pv1=600, cons1=-500),
            price=F(3, 10),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
        Snapshot(
            id="over_metered",
            note=(
                "cons1 reads more than the sources supply — the meters disagree, and the "
                "base load has nowhere to go but zero."
            ),
            readings=dict(grid=100, pv1=200, cons1=-400),
            price=F(3, 10),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
    ],
)
