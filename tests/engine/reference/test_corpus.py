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
    assert published["states"], f"{case.case_id} declares no Snapshot"
    for state in published["states"]:
        assert state["note"], (
            f"{case.case_id}/{state['id']} has no note — a Snapshot's docstring "
            f"is the caption on its snapshot's chart"
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


def test_sensor_map_names_published_properties():
    """Every sensor the docs name reads a property the docs publish.

    ``sensors.json`` is read out of ``sensor.py`` by source, so a sensor whose
    ``value_fn`` reads a property the catalog does not carry would send the
    flow chart looking for a value no case file holds. The three levelized
    ledger totals read no property at all — they sum other sensors — and are
    the only ones allowed none.
    """
    import json

    catalog = json.loads((OUT.parent / "properties.json").read_text())["properties"]
    sensors = json.loads(render()["sensors.json"])["sensors"]
    assert sensors, "the sensor map found no sensors in sensor.py"
    unknown = sorted(
        {s["property"] for s in sensors if s["property"] and s["property"] not in catalog}
    )
    assert not unknown, f"sensors read properties the catalog does not document: {unknown}"
    unmapped = sorted(s["key"] for s in sensors if s["property"] is None)
    assert unmapped == sorted(
        [
            "combined_total_levelized_cost_savings",
            "combined_total_levelized_device_operating_cost",
            "combined_total_levelized_financial_return",
        ]
    ), f"sensors with no engine property: {unmapped}"
