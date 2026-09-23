"""The engine's outputs have not moved since they were last frozen.

A failure here is not a bug report. It says *which* outputs this change moved,
in which homes; whether that is right is a question for the reviewer. If it is
intended, re-freeze and commit the result with the change:

    uv run --group engine python tools/snapshot.py

If a moved output reflects a modelling decision, pin that decision with a
hand-derived block in ``tests/engine/manual/`` as well.
"""

from __future__ import annotations

import pytest

from tests.engine.frozen.store import CORPORA, compare, report


@pytest.mark.parametrize("corpus", CORPORA)
def test_engine_outputs_match_the_frozen_snapshot(corpus: str) -> None:
    moved, drift = compare(corpus)
    if moved or drift:
        pytest.fail(
            f"The frozen `{corpus}` snapshot no longer matches the engine.\n\n"
            + report(moved, drift)
            + "\nIf this is intended: uv run --group engine python tools/snapshot.py",
            pytrace=False,
        )
