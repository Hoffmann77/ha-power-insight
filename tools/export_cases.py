"""Publish the reference cases to ``docs/spec/cases/`` for the docs site.

The cases live in ``tests/engine/reference/`` as fixed homes — a wiring and a
few snapshots of readings each. :meth:`ReferenceCase.publish` passes every
snapshot through the engine and records every catalogued property, so what
appears on a page is exactly what the engine computes at this commit.

This tool is the IO around that. It writes two things into
``docs/spec/cases/``:

``<case-id>.json``
    One file per case — the wiring, the snapshots, and the engine's results
    for each of them.

``index.json``
    The ladder, in order.

The output is committed. ``tests/engine/reference/test_corpus.py`` fails when
it no longer matches the engine, so a change that moves a published number
carries the new numbers in the same commit — the PR diff shows which moved —
and a docs version cut from any commit freezes that commit's own results.

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

from tests.engine.reference import REFERENCE_CASES  # noqa: E402

OUT = ROOT / "docs" / "spec" / "cases"


def index_json(built: list[dict]) -> dict:
    return {
        "cases": [
            {
                "id": case["id"],
                "title": case["title"],
                "file": f"{case['id']}.json",
                "states": [s["id"] for s in case["states"]],
            }
            for case in built
        ]
    }


def render() -> dict[str, str]:
    """Every file this tool owns, as ``filename -> content``."""
    built = [case.publish() for case in REFERENCE_CASES]
    files: dict[str, object] = {f"{case['id']}.json": case for case in built}
    files["index.json"] = index_json(built)
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
                "docs/spec/cases is out of date with the engine:\n"
                + "".join(f"  {name}\n" for name in sorted(stale))
                + "Run: uv run --group engine python tools/export_cases.py",
                file=sys.stderr,
            )
            return 1
        print(f"docs/spec/cases is up to date ({len(files)} files)")
        return 0

    for name, content in files.items():
        (OUT / name).write_text(content)
    print(f"wrote {len(files)} files to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
