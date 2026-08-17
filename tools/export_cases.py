"""Publish the reference cases to ``docs/spec/cases/`` for the docs site.

The cases themselves live in ``tests/engine/reference/`` — Python modules
holding a wiring, its snapshots, and the answers somebody derived by hand. That
is the single source of truth. This tool is a one-way projection of it into the
JSON the Docusaurus site imports, and it holds no information of its own: run
it, and whatever is in the Python appears on the site.

It writes three things into ``docs/spec/cases/``:

``<case-id>.json``
    One file per case — the wiring, the snapshots, and every catalogued
    property as a slot. A slot the corpus has no answer for is published as
    ``derived: false`` rather than omitted, because *which* metrics nobody has
    checked yet is exactly what a reader needs to know.

``index.json``
    The ladder, with each case's slot counts.

``coverage.json``
    Where the derivation programme has got to, per property and per rung.

Nothing here touches the engine. The published values are the hand-derived
ones and only those, so the site can never end up quoting the implementation
back at itself.

Usage::

    uv run --group engine python tools/export_cases.py
    uv run --group engine python tools/export_cases.py --check   # CI: is it stale?
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from fractions import Fraction
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.engine.reference import (  # noqa: E402
    CATALOG,
    PROPERTIES,
    REFERENCE_CASES,
    Case,
    Snapshot,
)
from tests.engine.scenario_framework import Adapter  # noqa: E402

OUT = ROOT / "docs" / "spec" / "cases"


def rat(value: Any) -> Any:
    """A number as an exact rational string — "1200", "-600", "8/15".

    Every number in a published case file is a string for the same reason the
    answers are written as fractions: these are the engine's specification and
    have to stay comparable by hand, which a JSON float is not.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(Fraction(value).limit_denominator(1_000_000))


def encode(value: Any) -> Any:
    """A derived answer in the site's storage shape (scalars, or maps of them)."""
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    return rat(value)


def adapter_json(adapter: Adapter) -> dict:
    cfg = {k: v for k, v in adapter.config.items() if v is not None and k != "name"}
    for key, value in list(cfg.items()):
        if isinstance(value, float):
            cfg[key] = rat(value)
        elif isinstance(value, tuple):
            cfg[key] = list(value)
    if adapter.kind == "grid":
        cfg["has_price_entity"] = adapter.has_price
    return {"uid": adapter.uid, "kind": adapter.kind, "config": cfg}


def snapshot_json(snapshot: Snapshot) -> dict:
    expectations = []
    for name in PROPERTIES:
        # Every property gets a slot on every snapshot, derived or not. A slot
        # the exporter silently omitted would read as a metric that does not
        # apply here, when what it means is that nobody has checked it.
        derived = name in snapshot.answers
        expectations.append(
            {
                "property": name,
                "value": encode(snapshot.answers[name]) if derived else None,
                "derived": derived,
            }
        )
    entry = {
        "id": snapshot.id,
        "note": snapshot.note,
        "readings": {uid: rat(v) for uid, v in snapshot.readings.items()},
        "price": rat(snapshot.price),
        "expectations": expectations,
    }
    if snapshot.open_question:
        entry["open_question"] = snapshot.open_question
    return entry


def case_json(case: Case) -> dict:
    return {
        "id": case.id,
        "title": case.title,
        "summary": case.summary,
        "decides": list(case.decides),
        "topology": [adapter_json(a) for a in case.topology],
        "states": [snapshot_json(s) for s in case.snapshots],
    }


def index_json(built: list[dict]) -> dict:
    return {
        "cases": [
            {
                "id": case["id"],
                "title": case["title"],
                "file": f"{case['id']}.json",
                "states": [s["id"] for s in case["states"]],
                "derived": _count(case, derived=True),
                "total": _count(case),
                "pending": _count(case, derived=False),
            }
            for case in built
        ]
    }


def _count(case: dict, derived: bool | None = None) -> int:
    return sum(
        1
        for state in case["states"]
        for exp in state["expectations"]
        if derived is None or exp["derived"] is derived
    )


def coverage_json(built: list[dict]) -> dict:
    """Where the derivation programme has got to, per property and per rung.

    How many slots each property has, how many are filled, and which cases the
    filled ones are in. It is a worklist as much as a coverage table, and it
    will read as mostly empty for a while — that is the honest picture, not a
    defect in the report.
    """
    catalog = CATALOG["properties"]
    entries = {}
    for name in PROPERTIES:
        doc = catalog[name]
        entry = {
            "title": doc["title"],
            "layer": doc["layer"],
            "slots": 0,
            "derived": 0,
            "derived_in": [],
        }
        for case in built:
            for state in case["states"]:
                for exp in state["expectations"]:
                    if exp["property"] != name:
                        continue
                    entry["slots"] += 1
                    if not exp["derived"]:
                        continue
                    entry["derived"] += 1
                    if case["id"] not in entry["derived_in"]:
                        entry["derived_in"].append(case["id"])
        entries[name] = entry

    return {
        "order": [case["id"] for case in built],
        "decisions": [
            {
                "case": case["id"],
                "case_title": case["title"],
                "decides": case["decides"],
                "slots": _count(case),
                "derived": _count(case, derived=True),
            }
            for case in built
        ],
        "properties": entries,
        "totals": {
            "slots": sum(e["slots"] for e in entries.values()),
            "derived": sum(e["derived"] for e in entries.values()),
            "untouched": sorted(n for n, e in entries.items() if not e["derived"]),
        },
    }


def render() -> dict[str, str]:
    """Every file this tool owns, as ``filename -> content``."""
    built = [case_json(case) for case in REFERENCE_CASES]
    files = {f"{case['id']}.json": case for case in built}
    files["index.json"] = index_json(built)
    files["coverage.json"] = coverage_json(built)
    return {name: json.dumps(data, indent=2) + "\n" for name, data in files.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the published JSON is out of date, writing nothing",
    )
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    files = render()

    if args.check:
        stale = [
            name
            for name, content in files.items()
            if not (OUT / name).exists() or (OUT / name).read_text() != content
        ]
        if stale:
            print(
                "docs/spec/cases is out of date with tests/engine/reference:\n"
                + "".join(f"  {name}\n" for name in sorted(stale))
                + "Run: uv run --group engine python tools/export_cases.py",
                file=sys.stderr,
            )
            return 1
        print(f"docs/spec/cases is up to date ({len(files)} files)")
        return 0

    for name, content in files.items():
        (OUT / name).write_text(content)
    totals = json.loads(files["coverage.json"])["totals"]
    print(
        f"wrote {len(files)} files to {OUT.relative_to(ROOT)}  "
        f"({totals['derived']} of {totals['slots']} slots derived)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
