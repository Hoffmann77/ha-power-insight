"""Assert the engine against the hand-derived reference corpus.

This runs in the direction that means something. The values in
``docs/spec/cases/`` are not read from the engine — they are worked out by hand
from the model, on paper, without the engine's answer in view — so a
disagreement here is genuine evidence rather than a tautology. A corpus
generated from the implementation could only ever confirm that the
implementation does what it does; this one can say it is wrong.

Three statuses, three meanings:

``pending``
    Nobody has derived this yet. Skipped — there is nothing to assert, and
    failing on it would just punish an unfinished worklist.

``verified``
    A human derived it and the engine agreed at the time. The engine must
    still agree. This is the regression net: change the code so it contradicts
    a published page and the build goes red.

``disputed``
    A human derived it, the engine disagreed, and the human stood by the
    derivation. The engine must *still* disagree — because if it has started
    agreeing, somebody has changed the code and the dispute is resolved but
    unrecorded. That is also a red build: go and re-certify it.

Comparison is by unit, at the tolerance the certification tool accepts, so a
value written as a rounded literal on paper is not failed for being rounded.
"""

from __future__ import annotations

import json
import pathlib
from fractions import Fraction

import pytest

from tests.engine.scenario_framework import engine_from_corpus

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES = ROOT / "docs" / "spec" / "cases"
CATALOG = json.loads((ROOT / "docs" / "spec" / "properties.json").read_text())

# Matches tools/certify.py. Shares and ratios are written as rounded literals
# on paper, so three decimals is the bar; money is quoted to the cent-per-hour;
# watts should come out exact.
TOLERANCE = {
    "share": 1e-3,
    "ratio": 1e-3,
    "EUR/h": 1e-4,
    "EUR/kWh": 1e-4,
    "W": 1e-6,
}

#: A derived answer of "the engine should report nothing here". Distinct from
#: a null value, which means nobody has derived this slot at all.
UNAVAILABLE = "unavailable"


def load_corpus() -> list[dict]:
    index = json.loads((CASES / "index.json").read_text())["cases"]
    return [json.loads((CASES / entry["file"]).read_text()) for entry in index]


def agrees(derived, actual, unit: str) -> bool:
    """Whether the engine's answer matches a hand-derived one, by unit."""
    if derived == UNAVAILABLE or actual is None:
        return derived == UNAVAILABLE and actual is None
    if isinstance(derived, dict):
        if not isinstance(actual, dict) or set(derived) != set(actual):
            return False
        return all(agrees(derived[k], actual[k], unit) for k in derived)
    if isinstance(actual, dict):
        return False
    tol = TOLERANCE.get(unit, 1e-6)
    return abs(float(Fraction(derived)) - float(actual)) <= tol


def encode(value):
    """The engine's answer, in the corpus's own shape, for reporting."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, bool):
        return value
    return str(Fraction(value).limit_denominator(1_000_000))


def derived_slots():
    """Every slot a human has filled in, as pytest parameters."""
    params = []
    for case in load_corpus():
        for state in case["states"]:
            for exp in state["expectations"]:
                status = exp["certification"]["status"]
                if status == "pending":
                    continue
                params.append(
                    pytest.param(
                        case,
                        state,
                        exp,
                        id=f"{case['id']}/{state['id']}/{exp['property']}",
                    )
                )
    return params


SLOTS = derived_slots()


@pytest.mark.skipif(not SLOTS, reason="no hand-derived values in the corpus yet")
@pytest.mark.parametrize("case,state,exp", SLOTS)
def test_engine_matches_derivation(case, state, exp):
    engine = engine_from_corpus(case, state)
    prop = exp["property"]
    unit = CATALOG["properties"][prop]["unit"]
    actual = getattr(engine, prop)
    matched = agrees(exp["value"], actual, unit)

    if exp["certification"]["status"] == "verified":
        assert matched, (
            f"{case['id']}/{state['id']}/{prop}: the engine contradicts a "
            f"certified value.\n"
            f"  derived by hand: {exp['value']}\n"
            f"  engine says:     {encode(actual)}\n"
            f"Either the change that caused this is a regression, or the "
            f"derivation was wrong and needs re-certifying."
        )
    else:
        assert not matched, (
            f"{case['id']}/{state['id']}/{prop}: the engine now agrees with a "
            f"value recorded as disputed ({exp['value']}). The dispute has "
            f"been resolved but not recorded — re-certify it."
        )


def test_every_slot_is_catalogued():
    """No case may publish a slot the property catalog does not document."""
    known = set(CATALOG["properties"])
    for case in load_corpus():
        for state in case["states"]:
            for exp in state["expectations"]:
                assert exp["property"] in known, (
                    f"{case['id']}/{state['id']} publishes {exp['property']!r}, "
                    f"which properties.json does not document"
                )


def test_no_value_without_a_derivation_status():
    """A filled value must carry a status that says a human put it there."""
    for case in load_corpus():
        for state in case["states"]:
            for exp in state["expectations"]:
                status = exp["certification"]["status"]
                assert status in ("pending", "verified", "disputed"), (
                    f"{case['id']}/{state['id']}/{exp['property']}: unknown "
                    f"certification status {status!r}"
                )
                if status == "pending":
                    assert exp["value"] is None, (
                        f"{case['id']}/{state['id']}/{exp['property']}: a "
                        f"pending slot must not carry a value — every value in "
                        f"the corpus is hand-derived, and a pending one is by "
                        f"definition nobody's derivation"
                    )
                else:
                    assert exp["value"] is not None, (
                        f"{case['id']}/{state['id']}/{exp['property']}: marked "
                        f"{status} but has no value. A derivation that concluded "
                        f"the engine should report nothing is written as "
                        f"{UNAVAILABLE!r}, not as null — null is reserved for "
                        f"slots nobody has worked out yet"
                    )
