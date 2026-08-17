"""The reference corpus: nine small homes the engine is specified against.

Each module here is one case — a wiring, a few snapshots of it, and the answers
somebody worked out by hand for those snapshots. Two things read them:

* ``tests/engine/test_reference_corpus.py`` asserts the engine against every
  answer. That is the direction that means something: the values are derived
  from the model, not read back from the code, so a disagreement is evidence
  rather than a tautology.
* ``tools/export_cases.py`` publishes them to ``docs/spec/cases/*.json``, which
  is what the documentation site renders.

Write answers by hand. An answer copied out of a failing test's "engine says"
line records what the code already does, which proves nothing and quietly
turns the corpus into a changelog. If you cannot derive a value, leave the slot
out — an empty slot is honest, and a wrong one is worse than none.

The corpus is a **ladder**, and ``REFERENCE_CASES`` is in ladder order. Each
case is the smallest wiring that can express the decision it settles, and every
rung adds exactly one device or flips exactly one configuration flag against
the rung above it. Two rules keep it finite, and both are load-bearing:

* A case earns its place only if it settles a decision no lower rung can
  express. Where a decision *is* expressible lower down, it belongs lower down
  — a restriction deficit derived by hand across three adapters is a napkin;
  across six it is an afternoon.
* A snapshot earns its place only if it moves a published value that no other
  snapshot of its case moves.

The last two cases break the one-device-at-a-time growth on purpose. They are
specialists: Hall's condition quantifies over *subsets* of sinks and cannot be
shown with fewer than two sources and two restricted sinks, and the mixed
export permissions only mean anything with two dischargers that differ. They
are the only cases allowed to be large, and neither is the first home of any
decision.
"""

from __future__ import annotations

from tests.engine.reference.battery_basics import CASE as BATTERY_BASICS
from tests.engine.reference.captive_battery import CASE as CAPTIVE_BATTERY
from tests.engine.reference.captive_load import CASE as CAPTIVE_LOAD
from tests.engine.reference.case import CATALOG, PROPERTIES, Case, F, Snapshot
from tests.engine.reference.grid_only import CASE as GRID_ONLY
from tests.engine.reference.group_captivity import CASE as GROUP_CAPTIVITY
from tests.engine.reference.metered_load import CASE as METERED_LOAD
from tests.engine.reference.mixed_export_house import CASE as MIXED_EXPORT_HOUSE
from tests.engine.reference.pv_export import CASE as PV_EXPORT
from tests.engine.reference.pv_self_consumption import CASE as PV_SELF_CONSUMPTION

#: Every reference case, in ladder order. The order is the corpus's argument,
#: not an accident — see the module docstring.
REFERENCE_CASES: tuple[Case, ...] = (
    GRID_ONLY,
    PV_SELF_CONSUMPTION,
    PV_EXPORT,
    METERED_LOAD,
    CAPTIVE_LOAD,
    BATTERY_BASICS,
    CAPTIVE_BATTERY,
    GROUP_CAPTIVITY,
    MIXED_EXPORT_HOUSE,
)

_BY_ID = {case.id: case for case in REFERENCE_CASES}
if len(_BY_ID) != len(REFERENCE_CASES):
    raise ValueError("duplicate reference case id")


def reference_case(case_id: str) -> Case:
    """One case by id, e.g. ``reference_case("group-captivity")``."""
    try:
        return _BY_ID[case_id]
    except KeyError:
        raise KeyError(
            f"unknown reference case {case_id!r}; known: {sorted(_BY_ID)}"
        ) from None


def derived_slots() -> list[tuple[Case, Snapshot, str]]:
    """Every ``(case, snapshot, property)`` somebody has written an answer for."""
    return [
        (case, snap, prop)
        for case in REFERENCE_CASES
        for snap in case.snapshots
        for prop in snap.derived
    ]


__all__ = [
    "CATALOG",
    "PROPERTIES",
    "REFERENCE_CASES",
    "Case",
    "F",
    "Snapshot",
    "derived_slots",
    "reference_case",
]
