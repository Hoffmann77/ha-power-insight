"""Publish the reference cases to ``docs/spec/cases/`` for the docs site.

The cases live in ``tests/engine/reference/`` as scenario classes — the same
``@topology`` / ``@state`` blocks every engine test uses, with ``@expect``
methods claiming the values somebody derived by hand. Each class knows how to
hand the docs its own contents: :meth:`ReferenceCase.publish` walks the class
with the same source-order binding pytest binds by, so a published page cannot
describe a snapshot differently from the way it is asserted.

This tool is the IO around that. It holds no information of its own: run it,
and whatever the test classes say appears on the site.

It writes three things into ``docs/spec/cases/``:

``<case-id>.json``
    One file per case — the wiring, the snapshots, and the values claimed for
    them. Only derived values appear. A property nobody has worked out here is
    simply absent, because the corpus publishes answers rather than an
    inventory of the questions.

``index.json``
    The ladder, with each case's published-value count.

``coverage.json``
    Where the derivation programme has got to: how many values each property
    has across the corpus, and which rungs they are on.

Nothing here touches the engine. The published values are the hand-derived ones
and only those, so the site can never end up quoting the implementation back at
itself.

Usage::

    uv run --group engine python tools/export_cases.py
    uv run --group engine python tools/export_cases.py --check   # CI: is it stale?
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.engine.reference import CATALOG, PROPERTIES, REFERENCE_CASES  # noqa: E402

OUT = ROOT / "docs" / "spec" / "cases"


def _values(case: dict) -> int:
    return sum(len(state["expectations"]) for state in case["states"])


def index_json(built: list[dict]) -> dict:
    return {
        "cases": [
            {
                "id": case["id"],
                "title": case["title"],
                "file": f"{case['id']}.json",
                "states": [s["id"] for s in case["states"]],
                "derived": _values(case),
            }
            for case in built
        ]
    }


def coverage_json(built: list[dict]) -> dict:
    """Where the derivation programme has got to, per property and per rung.

    How many values each property has across the corpus, and which cases they
    are in. It is a worklist as much as a coverage table, and it will read as
    mostly empty for a while — that is the honest picture, not a defect in the
    report. A property with no values anywhere is one the engine is not being
    held to.
    """
    catalog = CATALOG["properties"]
    entries = {}
    for name in PROPERTIES:
        doc = catalog[name]
        derived_in = [
            case["id"]
            for case in built
            if any(
                exp["property"] == name
                for state in case["states"]
                for exp in state["expectations"]
            )
        ]
        entries[name] = {
            "title": doc["title"],
            "layer": doc["layer"],
            "derived": sum(
                1
                for case in built
                for state in case["states"]
                for exp in state["expectations"]
                if exp["property"] == name
            ),
            "derived_in": derived_in,
        }

    return {
        "order": [case["id"] for case in built],
        "decisions": [
            {
                "case": case["id"],
                "case_title": case["title"],
                "decides": case["decides"],
                "derived": _values(case),
            }
            for case in built
        ],
        "properties": entries,
        "totals": {
            "derived": sum(e["derived"] for e in entries.values()),
            "untouched": sorted(n for n, e in entries.items() if not e["derived"]),
        },
    }


def render() -> dict[str, str]:
    """Every file this tool owns, as ``filename -> content``."""
    built = [case.publish() for case in REFERENCE_CASES]
    files: dict[str, object] = {f"{case['id']}.json": case for case in built}
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
    total = json.loads(files["coverage.json"])["totals"]["derived"]
    print(
        f"wrote {len(files)} files to {OUT.relative_to(ROOT)}  "
        f"({total} derived values published)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
