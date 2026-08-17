"""The reference corpus: nine small homes the engine is specified against.

Each module here is one case — an ordinary scenario class (``@topology`` /
``@state`` / source-order binding, exactly like every other engine test) whose
``@expect`` methods claim values somebody worked out **by hand from the
model**. Two things read them:

* pytest, which runs each claim as a test. That is the direction that means
  something: the values are derived from the model, not read back from the
  code, so a disagreement is evidence rather than a tautology.
* ``tools/export_cases.py``, which calls :meth:`ReferenceCase.publish` on each
  class and writes ``docs/spec/cases/*.json`` for the documentation site. The
  export walks the same source-order binding the tests bind by, so a published
  page cannot describe a snapshot differently from the way it is asserted.

Write answers by hand. An answer copied out of a failing test's ``actual:``
line records what the code already does, which proves nothing and quietly turns
the corpus into a changelog. If you cannot derive a value, write no method for
it — nothing is published and nothing is asserted.

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

from tests.engine.reference.case import (
    CATALOG,
    PROPERTIES,
    TOLERANCE,
    F,
    ReferenceCase,
    expect,
)
from tests.engine.reference.test_battery_basics import TestBatteryBasics
from tests.engine.reference.test_captive_battery import TestCaptiveBattery
from tests.engine.reference.test_captive_load import TestCaptiveLoad
from tests.engine.reference.test_grid_only import TestGridOnly
from tests.engine.reference.test_group_captivity import TestGroupCaptivity
from tests.engine.reference.test_metered_load import TestMeteredLoad
from tests.engine.reference.test_mixed_export_house import TestMixedExportHouse
from tests.engine.reference.test_pv_export import TestPvExport
from tests.engine.reference.test_pv_self_consumption import TestPvSelfConsumption

#: Every reference case, in ladder order. The order is the corpus's argument,
#: not an accident — see the module docstring.
REFERENCE_CASES: tuple[type[ReferenceCase], ...] = (
    TestGridOnly,
    TestPvSelfConsumption,
    TestPvExport,
    TestMeteredLoad,
    TestCaptiveLoad,
    TestBatteryBasics,
    TestCaptiveBattery,
    TestGroupCaptivity,
    TestMixedExportHouse,
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
    "TOLERANCE",
    "F",
    "ReferenceCase",
    "expect",
    "reference_case",
]
