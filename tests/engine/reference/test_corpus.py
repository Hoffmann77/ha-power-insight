"""Corpus-level checks: the ladder is well formed, and the docs are current.

The cases assert nothing about the engine — they are a showcase of what it
computes. What is checked here is that each rung says what it is for, and that
the results published for the docs are exactly what the engine computes now.
"""

from __future__ import annotations

import pytest

from tests.engine.reference import REFERENCE_CASES
from tools.export_cases import OUT, render


@pytest.mark.parametrize("case", REFERENCE_CASES, ids=lambda c: c.case_id)
def test_case_is_wellformed(case):
    """A rung names itself, says what it shows, and can publish its page."""
    assert case.case_id and case.title, f"{case.__name__} must set case_id and title"
    assert case.summary(), (
        f"{case.case_id} has no summary — the class docstring above its "
        f"'Shows:' list is the text of its documentation page"
    )
    assert case.shows(), (
        f"{case.case_id} lists nothing under 'Shows:' — a case earns its place "
        f"on the ladder by showing something no lower rung can"
    )
    published = case.publish()
    assert published["states"], f"{case.case_id} declares no @state"
    for state in published["states"]:
        assert state["note"], (
            f"{case.case_id}/{state['id']} has no note — a @state's docstring "
            f"is the caption under its snapshot card"
        )


def test_ladder_ids_are_unique():
    ids = [case.case_id for case in REFERENCE_CASES]
    assert len(ids) == len(set(ids)), f"duplicate case ids in the ladder: {ids}"


def test_published_cases_are_current():
    """``docs/spec/cases/`` holds exactly what the engine computes now.

    The site renders the committed JSON, and cutting a docs version freezes it,
    so a change to the engine that moves a published number must re-export in
    the same commit — which is also what makes the PR diff show which numbers
    moved.
    """
    stale = sorted(
        name
        for name, content in render().items()
        if not (OUT / name).exists() or (OUT / name).read_text() != content
    )
    assert not stale, (
        f"docs/spec/cases is out of date with the engine: {stale}\n"
        f"Run: uv run --group engine python tools/snapshot.py"
    )
