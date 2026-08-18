"""The reference-case base class: a scenario that can publish itself.

A reference case is an ordinary :class:`EngineScenario` — the same
``@topology`` / ``@state`` / source-order binding every other engine test uses
— with two things added: an id and title that name its page on the
documentation site, and the ability to hand that page its own contents.

Writing a case
--------------

::

    class GridOnly(ReferenceCase):
        \"\"\"One meter and nothing else. Every published property still has a
        value here, which makes this the cheapest place in the corpus to settle
        what the engine does at the edges.

        Decides:

        * With no local device, the whole gross power is the home base load.
        * A sink with one available source has a provenance row of exactly one.
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

        @expect("gross_power")
        def test_gross_power(self):
            return 1200

        @expect("home_base_load_source_shares")
        def test_base_load_provenance(self):
            return {"grid": 1}

Everything the docs page needs is in there. The prose lives in docstrings — the
class's is the page summary, a ``@state``'s is the caption under its snapshot
card — and :meth:`ReferenceCase.publish` reads the whole structure back out
using the same source-order binding the tests bind by. So the published page
cannot describe a snapshot differently from the way it is asserted.

Writing an answer
-----------------

An ``@expect("<property>")`` method takes only ``self`` and returns the value
the engine ought to publish, worked out **from the model** rather than read
back from the code. That direction is the whole point: a corpus generated from
the implementation can only confirm the implementation does what it does, while
one derived independently can say it is wrong.

Return ``None`` to claim the engine should publish *nothing at all* here — the
usual reason being an unavailable reading upstream. That is asserted just as
strictly as a number, and never matches a zero.

Write exact rationals as ``Fraction`` (aliased ``F``) where a decimal literal
would not be exact. Comparison tolerance comes from the property's unit in
``docs/spec/properties.json``, so a share written as a rounded literal is not
failed for being rounded.

Not deriving something is free. Every property the catalog documents already
has a stub on every snapshot, returning :data:`TODO`::

    @expect("gross_power_export_ratio")
    def test_import_only_gross_power_export_ratio(self):
        return TODO

A stub skips rather than fails, and publishes nothing — it claims nothing,
because nobody has claimed anything. Replace the ``TODO`` with the value you
worked out and that one line starts holding the engine to it. The skip carries
the catalog's definition and steps for the property, so::

    uv run pytest tests/engine/reference/test_grid_only.py -rs

reads as a worklist with the instructions already in it.

Never paste an answer out of a failing test's ``actual:`` line — that records
what the code already does, which proves nothing and quietly turns the corpus
into a changelog.
"""

from __future__ import annotations

import inspect
import json
import pathlib
from fractions import Fraction
from typing import Any, Callable

from tests.engine.scenario_framework import (
    TODO as TODO,  # re-exported: cases import it from here alongside @expect
    Block,
    EngineScenario,
    expect_attribute,
    scenario_blocks,
)

#: Alias for writing exact rationals inline: ``F(8, 15)``, ``F(3, 10)``.
F = Fraction

ROOT = pathlib.Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "docs" / "spec" / "properties.json"

#: The property catalog — what each published property means, its unit, and the
#: layer it belongs to. Property names are checked against it at decoration
#: time, so a typo fails at import rather than publishing a slot the docs
#: cannot render.
CATALOG: dict[str, Any] = json.loads(CATALOG_PATH.read_text())

#: Every property a case can publish, in catalog order (which is dependency
#: order: readings first, the monetary model last).
PROPERTIES: tuple[str, ...] = tuple(CATALOG["properties"])

# How close a hand-derived answer has to be, by unit. Shares and ratios are
# written as rounded literals on paper, so three decimals is the bar; money is
# quoted to the cent-per-hour; watts should come out exact.
TOLERANCE = {
    "share": 1e-3,
    "ratio": 1e-3,
    "EUR/h": 1e-4,
    "EUR/kWh": 1e-4,
    "W": 1e-6,
}


def expect(prop: str) -> Callable[[Callable], Callable]:
    """Claim a value for one published property, at its unit's tolerance.

    Thin wrapper over :func:`expect_attribute`: it looks the property up in the
    catalog, so the tolerance is the one that unit deserves and a misspelled
    name raises here rather than silently publishing a slot nothing can render.

    A method still returning :data:`TODO` skips, and the skip carries the
    catalog's own description of what to derive — run ``pytest -rs`` over a case
    and the report is a worklist with the definitions already in it.
    """
    try:
        doc = CATALOG["properties"][prop]
    except KeyError:
        raise ValueError(
            f"{prop!r} is not documented in docs/spec/properties.json — check "
            f"the spelling, or add the property to the catalog"
        ) from None
    return expect_attribute(
        prop, abs_tol=TOLERANCE.get(doc["unit"]), todo_reason=_todo_reason(prop, doc)
    )


def _todo_reason(prop: str, doc: dict) -> str:
    """What to tell somebody who is about to sit down and derive this one."""
    lines = [f"derive {prop} ({doc['unit']}) — {doc['definition']}"]
    if doc.get("formula"):
        lines.append(f"  formula: {doc['formula']}")
    for i, step in enumerate(doc.get("derivation_steps", ()), start=1):
        lines.append(f"  {i}. {step}")
    return "\n".join(lines)


class ReferenceCase(EngineScenario):
    """One rung of the ladder: a wiring, why it exists, and its snapshots.

    Subclasses set :attr:`case_id` and :attr:`title`, then declare blocks
    exactly as any scenario does. See the module docstring for the shape.
    """

    #: The published id — the docs page slug, and the first half of every test
    #: node id for this case.
    case_id: str = ""
    #: Human-readable name, shown as the page title.
    title: str = ""

    @classmethod
    def summary(cls) -> str:
        """The page summary: the class docstring above its ``Decides:`` list."""
        return _prose(cls.__doc__)[0]

    @classmethod
    def decides(cls) -> tuple[str, ...]:
        """The modelling choices this case pins down, from ``Decides:``."""
        return _prose(cls.__doc__)[1]

    @classmethod
    def blocks(cls) -> list[Block]:
        """Every ``(topology, state, expectations)`` block, in source order."""
        return scenario_blocks(cls)

    @classmethod
    def publish(cls) -> dict:
        """This case as the documentation site consumes it.

        One entry per snapshot that claims at least one value, each carrying
        the wiring, the readings, and only the properties somebody actually
        derived. A property nobody has worked out here is simply absent — the
        corpus publishes answers, not an inventory of the questions.
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
            "decides": list(cls.decides()),
            "topology": [_adapter(a) for a in blocks[0].topology.adapters],
            "states": [_snapshot(cls, block) for block in blocks],
        }


# ---------------------------------------------------------------------------
# Turning a block into published JSON.
# ---------------------------------------------------------------------------


def _snapshot(cls: type, block: Block) -> dict:
    note, open_question = _state_prose(cls, block.state.name)
    entry = {
        "id": block.state.name,
        "note": note,
        "readings": {uid: _rat(v) for uid, v in block.state.readings.items()},
        "price": _rat(block.state.price),
        "expectations": [
            {"property": exp.attribute, "value": _encode(exp.value)}
            for exp in sorted(
                block.expectations, key=lambda e: PROPERTIES.index(e.attribute)
            )
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

    Every number on a published page is a string for the same reason the
    answers are written as fractions: these are the engine's specification and
    have to stay comparable by hand, which a JSON float is not.
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
    """A class docstring split into ``(summary, decides)``.

    Everything above a ``Decides:`` line is the summary; the ``*`` bullets
    below it are the decisions, each rewrapped onto one line.
    """
    summary: list[str] = []
    decides: list[str] = []
    in_decides = False
    for line in inspect.cleandoc(doc or "").splitlines():
        stripped = line.strip()
        if stripped.rstrip(":").casefold() == "decides" and stripped.endswith(":"):
            in_decides = True
            continue
        if not in_decides:
            summary.append(stripped)
        elif stripped.startswith("* "):
            decides.append(stripped[2:])
        elif stripped and decides:
            # A bullet wrapped onto the next line.
            decides[-1] += " " + stripped
    return _join(summary), tuple(decides)


def _state_prose(cls: type, state_name: str) -> tuple[str, str | None]:
    """A ``@state`` docstring split into ``(note, open_question)``.

    The note is the caption under the snapshot card. A paragraph opening
    ``Open question:`` marks a snapshot where the engine produces an answer but
    which answer is *right* has not been settled — rendered as a callout, and
    collected onto the section index.
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
