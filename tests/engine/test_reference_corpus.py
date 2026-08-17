"""Assert the engine against the hand-derived reference corpus.

The answers live in ``tests/engine/reference/`` — one module per case, each
holding a wiring, its snapshots, and whatever somebody has worked out by hand
for them. This file does one thing: for every answer written down, build that
snapshot's engine and check it publishes the same value.

This runs in the direction that means something. The values are derived from
the model, on paper, rather than read back from the engine — so a disagreement
here is evidence rather than a tautology. A corpus generated from the
implementation could only ever confirm that the implementation does what it
does; this one can say it is wrong.

Which is also why there are only two outcomes. A red test means *either* the
engine is broken *or* the derivation was, and the corpus has no opinion about
which — that call is yours, and it is the interesting part. Fix the code or fix
the answer; there is no third state to park it in.

Comparison is by unit, at a tolerance that lets a value written as a rounded
literal on paper pass without being failed for being rounded. Write the answer
as a ``Fraction`` when you want it pinned tighter than that.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from tests.engine.reference import CATALOG, PROPERTIES, REFERENCE_CASES, derived_slots

# Shares and ratios are written as rounded literals on paper, so three decimals
# is the bar; money is quoted to the cent-per-hour; watts should come out exact.
TOLERANCE = {
    "share": 1e-3,
    "ratio": 1e-3,
    "EUR/h": 1e-4,
    "EUR/kWh": 1e-4,
    "W": 1e-6,
}


def agrees(derived, actual, unit: str) -> bool:
    """Whether the engine's answer matches a hand-derived one, by unit.

    ``None`` is a derived answer in its own right — the model saying there is
    no value here — so it matches only a genuine ``None`` from the engine, and
    never a zero. Maps must have exactly the same keys: a leaked or missing row
    is a real disagreement, not a rounding one.
    """
    if derived is None or actual is None:
        return derived is None and actual is None
    if isinstance(derived, dict):
        if not isinstance(actual, dict) or set(derived) != set(actual):
            return False
        return all(agrees(derived[k], actual[k], unit) for k in derived)
    if isinstance(actual, dict):
        return False
    return abs(float(derived) - float(actual)) <= TOLERANCE.get(unit, 1e-6)


def show(value) -> str:
    """A value in the most readable exact form: ``1200``, ``8/15``, a map."""
    if value is None:
        return "nothing at all"
    if isinstance(value, dict):
        return (
            "{" + ", ".join(f"{k}: {show(v)}" for k, v in sorted(value.items())) + "}"
        )
    if isinstance(value, bool):
        return str(value)
    exact = Fraction(value).limit_denominator(1_000_000)
    return str(exact.numerator) if exact.denominator == 1 else str(exact)


SLOTS = [
    pytest.param(case, snap, prop, id=f"{case.id}/{snap.id}/{prop}")
    for case, snap, prop in derived_slots()
]


@pytest.mark.skipif(not SLOTS, reason="no hand-derived answers in the corpus yet")
@pytest.mark.parametrize("case,snapshot,prop", SLOTS)
def test_engine_matches_derivation(case, snapshot, prop):
    derived = snapshot.answers[prop]
    actual = getattr(case.build_engine(snapshot), prop)
    unit = CATALOG["properties"][prop]["unit"]

    assert agrees(derived, actual, unit), (
        f"\n{case.id} / {snapshot.id} / {prop} ({unit})\n"
        f"  {snapshot.note}\n"
        f"  readings: "
        + ", ".join(f"{k}={show(v)}" for k, v in snapshot.readings.items())
        + f", price={show(snapshot.price)}\n\n"
        f"  you derived: {show(derived)}\n"
        f"  engine says: {show(actual)}\n\n"
        f"One of the two is wrong. Work out which before touching either:\n"
        f"  * the engine regressed        -> fix the engine\n"
        f"  * the derivation was wrong    -> fix the answer in "
        f"tests/engine/reference/{case.id.replace('-', '_')}.py\n"
    )


def test_ladder_is_wellformed():
    """Case ids are unique and every case says what it decides."""
    ids = [case.id for case in REFERENCE_CASES]
    assert len(ids) == len(set(ids)), f"duplicate case ids in the ladder: {ids}"
    for case in REFERENCE_CASES:
        assert case.decides, (
            f"{case.id} lists no decisions — a case earns its place on the "
            f"ladder by settling something no lower rung can express"
        )
        assert case.snapshots, f"{case.id} has no snapshots"


def test_catalog_covers_the_corpus():
    """Every catalogued property has a unit the comparison knows how to use.

    Answer *keys* are already checked against the catalog when a ``Snapshot``
    is constructed, so a misspelled property name never reaches here. This
    checks the other half: that a property the catalog documents can actually
    be compared once somebody derives it.
    """
    for prop in PROPERTIES:
        unit = CATALOG["properties"][prop]["unit"]
        assert unit in TOLERANCE, (
            f"{prop} is documented in unit {unit!r}, which has no comparison "
            f"tolerance — add one to TOLERANCE"
        )
