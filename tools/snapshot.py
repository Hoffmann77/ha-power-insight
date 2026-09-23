"""Refresh everything the repository stores that the engine computes.

One command after any engine change:

    uv run --group engine python tools/snapshot.py

It rewrites two things, both committed:

``tests/engine/frozen/snapshots/*.json``
    The frozen engine outputs — the change detector. ``test_frozen.py`` fails
    whenever the engine no longer produces them.

``docs/spec/cases/*.json``
    The reference cases as the docs site shows them. ``test_corpus.py`` fails
    whenever they are stale.

Commit both with the change: the PR diff then shows exactly which engine
outputs the change moved.

Options::

    --check    Write nothing; print what moved as markdown and exit 1 if
               anything is stale (CI uses this for its job summary).
    --redraw   Also re-draw the generated corpus's homes. Rarely wanted: every
               generated home's outputs then show as new in the diff.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.engine.frozen import store  # noqa: E402
from tools import export_cases  # noqa: E402


def _stale_docs() -> list[str]:
    return sorted(
        name
        for name, content in export_cases.render().items()
        if not (export_cases.OUT / name).exists()
        or (export_cases.OUT / name).read_text() != content
    )


def check() -> int:
    stale = False
    sections = []
    for corpus in store.CORPORA:
        moved, drift = store.compare(corpus)
        if moved or drift:
            stale = True
            sections.append(f"### Frozen `{corpus}` corpus\n\n{store.report(moved, drift)}")
    docs = _stale_docs()
    if docs:
        stale = True
        sections.append(
            "### Reference-case docs\n\nOut of date: "
            + ", ".join(f"`{d}`" for d in docs)
            + "\n"
        )
    if not stale:
        print("Engine outputs match every frozen snapshot, and the docs are current.")
        return 0
    print("\n".join(sections))
    print("To accept: `uv run --group engine python tools/snapshot.py`, then commit.")
    return 1


def update(*, redraw: bool) -> int:
    store.SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    for corpus in store.CORPORA:
        if corpus == "generated" and (redraw or not store.load(corpus)):
            homes = store.draw_generated_homes()
        else:
            homes = store.homes_of(corpus)
        moved, _ = store.compare(corpus)
        store.snapshot_path(corpus).write_text(store.render(homes, corpus))
        print(f"froze {len(homes)} {corpus} homes ({len(moved)} output(s) moved)")
    export_cases.OUT.mkdir(parents=True, exist_ok=True)
    files = export_cases.render()
    for name, content in files.items():
        (export_cases.OUT / name).write_text(content)
    print(f"wrote {len(files)} reference-case files to docs/spec/cases")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--redraw", action="store_true")
    args = parser.parse_args()
    return check() if args.check else update(redraw=args.redraw)


if __name__ == "__main__":
    raise SystemExit(main())
