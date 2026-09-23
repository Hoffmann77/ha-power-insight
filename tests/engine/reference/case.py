"""The reference-case base class: a fixed home that can publish itself.

A reference case is a small, fixed home — one wiring and a few snapshots of
readings — shown on the documentation site with everything the engine
computes for it. The cases are a **showcase**, not a specification: the
numbers on a page are whatever the engine produced for those readings at that
version of the code, recomputed by ``tools/export_cases.py`` and frozen into
each docs version when it is cut. What the engine *ought* to do is pinned
elsewhere — each decision by a hand-derived block in ``tests/engine/manual/``,
every property's formula and the laws they obey in ``tests/engine/automatic/``.

Writing a case
--------------

::

    class GridOnly(ReferenceCase):
        \"\"\"One meter and nothing else. ...

        Shows:

        * With no local device, the whole gross power is the home base load.
        \"\"\"

        case_id = "grid-only"
        title = "Grid only"

        @topology
        def wiring(self):
            return (Adapter.grid(),)

        @state
        def import_only(self):
            \"\"\"The house runs on the grid alone; every watt is base load.\"\"\"
            return State(grid=1200, price=F(3, 10))

That is the whole source. The prose lives in docstrings — the class's is the
page summary (everything above its ``Shows:`` list), a ``@state``'s is the
caption under its snapshot card, and a paragraph opening ``Open question:``
becomes a callout — and :meth:`ReferenceCase.publish` reads the structure back
out with the same source-order binding the engine tests bind by.
"""

from __future__ import annotations

import inspect
import json
import pathlib
from fractions import Fraction
from typing import Any

from tests.engine.scenario_framework import Block, scenario_blocks

#: Alias for writing exact rationals inline: ``F(8, 15)``, ``F(3, 10)``.
F = Fraction

ROOT = pathlib.Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "docs" / "spec" / "properties.json"

#: The property catalog — what each published property means, its unit, and the
#: layer it belongs to.
CATALOG: dict[str, Any] = json.loads(CATALOG_PATH.read_text())

#: Every property a case publishes, in catalog order (which is dependency
#: order: readings first, the monetary model last).
PROPERTIES: tuple[str, ...] = tuple(CATALOG["properties"])


class ReferenceCase:
    """One rung of the ladder: a wiring, what it shows, and its snapshots.

    Subclasses set :attr:`case_id` and :attr:`title`, then declare one
    ``@topology`` and one or more ``@state`` methods. See the module docstring.
    """

    #: The published id — the docs page slug.
    case_id: str = ""
    #: Human-readable name, shown as the page title.
    title: str = ""

    @classmethod
    def summary(cls) -> str:
        """The page summary: the class docstring above its ``Shows:`` list."""
        return _prose(cls.__doc__)[0]

    @classmethod
    def shows(cls) -> tuple[str, ...]:
        """What this case illustrates about the engine, from ``Shows:``."""
        return _prose(cls.__doc__)[1]

    @classmethod
    def blocks(cls) -> list[Block]:
        """Every ``(topology, state)`` block, in source order."""
        return scenario_blocks(cls)

    @classmethod
    def publish(cls) -> dict:
        """This case as the documentation site consumes it.

        One entry per snapshot, each carrying the wiring, the readings, and
        every catalogued property as the engine computes it right now.
        """
        if not cls.case_id or not cls.title:
            raise ValueError(f"{cls.__name__} must set both case_id and title")
        blocks = cls.blocks()
        if not blocks:
            raise ValueError(f"{cls.__name__} declares no @state to publish")
        return {
            "id": cls.case_id,
            "title": cls.title,
            "summary": cls.summary(),
            "shows": list(cls.shows()),
            "topology": [_adapter(a) for a in blocks[0].topology.adapters],
            "states": [_snapshot(cls, block) for block in blocks],
        }


# ---------------------------------------------------------------------------
# Turning a block into published JSON.
# ---------------------------------------------------------------------------


def _snapshot(cls: type, block: Block) -> dict:
    note, open_question = _state_prose(cls, block.state.name)
    engine = block.cell.build_engine()
    entry = {
        "id": block.state.name,
        "note": note,
        "readings": {uid: _rat(v) for uid, v in block.state.readings.items()},
        "price": _rat(block.state.price),
        "results": [
            {"property": prop, "value": _encode(getattr(engine, prop))}
            for prop in PROPERTIES
        ],
    }
    if open_question:
        entry["open_question"] = open_question
    return entry


def _adapter(adapter: Any) -> dict:
    cfg = {k: v for k, v in adapter.config.items() if v is not None and k != "name"}
    for key, value in list(cfg.items()):
        if isinstance(value, float):
            cfg[key] = _rat(value)
        elif isinstance(value, tuple):
            cfg[key] = list(value)
    if adapter.kind == "grid":
        cfg["has_price_entity"] = adapter.has_price
    return {"uid": adapter.uid, "kind": adapter.kind, "config": cfg}


def _rat(value: Any) -> Any:
    """A number as an exact rational string — "1200", "-600", "8/15".

    The engine computes in floats; written as the nearest fraction with a
    denominator up to a million, ``0.4444444444444444`` reads as ``4/9`` and a
    float's last-digit noise never reaches the page.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(Fraction(value).limit_denominator(1_000_000))


def _encode(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    return _rat(value)


# ---------------------------------------------------------------------------
# Docstrings as prose.
# ---------------------------------------------------------------------------
#
# The page text lives where the thing it describes lives: a case's summary in
# its class docstring, a snapshot's caption in its ``@state`` method's. There
# is no second place to keep them in step with.


def _prose(doc: str | None) -> tuple[str, tuple[str, ...]]:
    """A class docstring split into ``(summary, shows)``.

    Everything above a ``Shows:`` line is the summary; the ``*`` bullets below
    it are what the case shows, each rewrapped onto one line.
    """
    summary: list[str] = []
    shows: list[str] = []
    in_shows = False
    for line in inspect.cleandoc(doc or "").splitlines():
        stripped = line.strip()
        if stripped.casefold() == "shows:":
            in_shows = True
            continue
        if not in_shows:
            summary.append(stripped)
        elif stripped.startswith("* "):
            shows.append(stripped[2:])
        elif stripped and shows:
            # A bullet wrapped onto the next line.
            shows[-1] += " " + stripped
    return _join(summary), tuple(shows)


def _state_prose(cls: type, state_name: str) -> tuple[str, str | None]:
    """A ``@state`` docstring split into ``(note, open_question)``.

    The note is the caption under the snapshot card. A paragraph opening
    ``Open question:`` marks a snapshot where which answer is *right* has not
    been settled — rendered as a callout, and collected onto the section index.
    """
    doc = inspect.cleandoc(getattr(cls, state_name).__doc__ or "")
    note: list[str] = []
    question: list[str] = []
    target = note
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped.casefold().startswith("open question:"):
            target = question
            stripped = stripped.split(":", 1)[1].strip()
        target.append(stripped)
    return _join(note), _join(question) or None


def _join(lines: list[str]) -> str:
    """Wrapped source lines back into one paragraph per blank-line group."""
    paragraphs: list[list[str]] = [[]]
    for line in lines:
        if line:
            paragraphs[-1].append(line)
        elif paragraphs[-1]:
            paragraphs.append([])
    return "\n\n".join(" ".join(p) for p in paragraphs if p)
