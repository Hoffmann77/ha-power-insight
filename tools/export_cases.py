"""The reference cases as the docs site shows them: ``docs/spec/cases/``.

The cases live in ``tests/engine/reference/`` as fixed homes — a wiring and a
few snapshots of readings each. :meth:`ReferenceCase.publish` passes every
snapshot through the engine and records every catalogued property. This module
renders that into:

``<case-id>.json``
    One file per case — the wiring, the snapshots, and the engine's results.

``index.json``
    The ladder, in order.

It has no command of its own: ``tools/snapshot.py`` writes these together with
the frozen engine outputs, and ``tests/engine/reference/test_corpus.py`` fails
when they are stale.
"""

from __future__ import annotations

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
