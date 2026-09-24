"""The reference cases: ten fixed homes shown with everything the engine computes.

Each module here is one case — a wiring (its devices, declared bare), a few
snapshots of readings (one ``Snapshot`` class each), and prose in docstrings. Nothing in them is asserted:
``tools/snapshot.py`` passes every snapshot through the engine and writes
the results, for every catalogued property, to ``docs/spec/cases/*.json`` for
the documentation site. ``test_corpus.py`` fails whenever that output is out of
step with the engine, so each commit — and each docs version cut from one —
carries exactly the numbers its own engine produces.

Whether those numbers are *right* is asked elsewhere: each engine decision by a
hand-derived class in ``tests/engine/manual/``, every property's formula and
the laws they obey in ``tests/engine/automatic/``.

The cases form a **ladder**, and ``REFERENCE_CASES`` is in ladder order. Each
case is the smallest wiring that can show what it is there to show, and every
rung adds exactly one device or flips exactly one configuration flag against
the rung above it, so a reader meets one new thing at a time. A snapshot earns
its place by showing something no other snapshot of its case does.

The last three cases break the one-device-at-a-time growth on purpose. They
are specialists: Hall's condition quantifies over *subsets* of sinks and cannot
be shown with fewer than two sources and two restricted sinks; its mirror image
— one sink allowed a *group* of sources, none of which it needs on its own —
needs a second restricted sink competing for the group and a source only that
competitor may use; and the mixed export permissions only mean anything with
two dischargers that differ. They are the only cases allowed to be large.
"""

from __future__ import annotations

from tests.engine.reference.battery_basics import BatteryBasics
from tests.engine.reference.captive_battery import CaptiveBattery
from tests.engine.reference.captive_load import CaptiveLoad
from tests.engine.reference.case import CATALOG, PROPERTIES, F, ReferenceCase
from tests.engine.reference.grid_only import GridOnly
from tests.engine.reference.group_captivity import GroupCaptivity
from tests.engine.reference.metered_load import MeteredLoad
from tests.engine.reference.mixed_export_house import MixedExportHouse
from tests.engine.reference.pv_export import PvExport
from tests.engine.reference.pv_self_consumption import PvSelfConsumption
from tests.engine.reference.two_pv_systems import TwoPvSystems

#: Every reference case, in ladder order — see the module docstring.
REFERENCE_CASES: tuple[type[ReferenceCase], ...] = (
    GridOnly,
    PvSelfConsumption,
    PvExport,
    MeteredLoad,
    CaptiveLoad,
    BatteryBasics,
    CaptiveBattery,
    GroupCaptivity,
    TwoPvSystems,
    MixedExportHouse,
)

_BY_ID = {case.case_id: case for case in REFERENCE_CASES}
if len(_BY_ID) != len(REFERENCE_CASES):
    raise ValueError("duplicate reference case id")


def reference_case(case_id: str) -> type[ReferenceCase]:
    """One case by id, e.g. ``reference_case("group-captivity")``."""
    try:
        return _BY_ID[case_id]
    except KeyError:
        raise KeyError(
            f"unknown reference case {case_id!r}; known: {sorted(_BY_ID)}"
        ) from None


__all__ = [
    "CATALOG",
    "PROPERTIES",
    "REFERENCE_CASES",
    "F",
    "ReferenceCase",
    "reference_case",
]
