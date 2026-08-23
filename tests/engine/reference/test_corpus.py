"""Corpus-level checks: the ladder is well formed, and the docs are current.

The values themselves are asserted by the case classes — every ``@expect``
method in this package is a test, run against a freshly built engine like any
other scenario test. What is left over is the corpus as a whole: that each rung
says what it is for, and that the pages published from these classes still
match what the classes say.
"""

from __future__ import annotations

import pytest

from tests.engine.reference import PROPERTIES, REFERENCE_CASES
from tools.export_cases import OUT, render


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=lambda c: c.case_id)
def test_case_is_wellformed(case):
    """A rung names itself, says what it settles, and can publish its page."""
    assert case.case_id and case.title, f"{case.__name__} must set case_id and title"
    assert case.summary(), (
        f"{case.case_id} has no summary — the class docstring above its "
        f"'Decides:' list is the text of its documentation page"
    )
    assert case.decides(), (
        f"{case.case_id} lists no decisions — a case earns its place on the "
        f"ladder by settling something no lower rung can express"
    )
    published = case.publish()
    assert published["states"], f"{case.case_id} declares no @state"
    for state in published["states"]:
        assert state["note"], (
            f"{case.case_id}/{state['id']} has no note — a @state's docstring "
            f"is the caption under its snapshot card"
        )
        props = [exp["property"] for exp in state["expectations"]]
        assert len(props) == len(set(props)), (
            f"{case.case_id}/{state['id']} claims {props} — two @expect methods "
            f"bound to one snapshot are claiming the same property"
        )
        assert set(props) <= set(PROPERTIES), (
            f"{case.case_id}/{state['id']} publishes a property the catalog "
            f"does not document"
        )


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=lambda c: c.case_id)
def test_every_property_has_a_method(case):
    """Every snapshot declares an ``@expect`` for every catalogued property.

    Most of them still ``return TODO``, which skips and publishes nothing —
    that is the worklist, and it is meant to read as mostly unfinished. What
    this pins is that the worklist is *complete*: add a property to the catalog
    and every snapshot tells you it needs one, rather than the gap going
    unnoticed because nothing was there to notice it.
    """
    for block in case.blocks():
        declared = {exp.attribute for exp in block.expectations} | set(block.pending)
        missing = [p for p in PROPERTIES if p not in declared]
        assert not missing, (
            f"{case.case_id}/{block.state.name} has no @expect method for "
            f"{missing}. Add one per property, in catalog order:\n\n"
            f'    @expect("{missing[0]}")\n'
            f"    def test_{block.state.name}_{missing[0]}(self):\n"
            f"        return TODO\n"
        )


def test_ladder_ids_are_unique():
    ids = [case.case_id for case in REFERENCE_CASES]
    assert len(ids) == len(set(ids)), f"duplicate case ids in the ladder: {ids}"


def test_published_cases_are_current():
    """``docs/spec/cases/`` still matches the classes it was generated from.

    The site renders generated JSON, so a value derived here but never exported
    is one CI holds the engine to and the published spec does not show.
    """
    stale = sorted(
        name
        for name, content in render().items()
        if not (OUT / name).exists() or (OUT / name).read_text() != content
    )
    assert not stale, (
        f"docs/spec/cases is out of date with tests/engine/reference: {stale}\n"
        f"Run: uv run --group engine python tools/export_cases.py"
    )
