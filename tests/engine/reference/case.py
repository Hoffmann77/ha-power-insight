"""The reference-case types: a wiring, its snapshots, and the answers you wrote.

A reference case is one small home, a handful of snapshots of it, and — for
each snapshot — a dict of *hand-derived* answers: what the engine ought to
publish, worked out from the model rather than read back from the code.
``tests/engine/test_reference_corpus.py`` asserts the engine against every
answer, and ``tools/export_cases.py`` publishes them to the docs site.

Writing an answer
-----------------

Answers live in the snapshot's ``answers`` dict, keyed by the property name as
``docs/spec/properties.json`` documents it::

    Snapshot(
        id="import_only",
        note="The house runs on the grid alone.",
        readings=dict(grid=1200),
        price=F(3, 10),
        answers={
            "gross_power": 1200,
            "combined_grid_export": 0,
            "home_base_load_source_shares": {"grid": 1},
            "combined_export_compensation_rate": None,
        },
    )

Three things a value can be, and they are all different:

``1200`` / ``F(8, 15)`` / ``{"grid": 1}``
    A derived answer. The engine must publish this. Write exact rationals as
    ``Fraction`` (aliased ``F``) when a decimal literal would not be exact;
    plain ints and floats are fine everywhere else, and are compared at the
    tolerance for the property's unit.

``None``
    Also a derived answer — that the engine should publish *nothing at all*
    here. The usual reason is an unavailable reading upstream. This is
    asserted just as strictly as a number.

*absent*
    Nobody has derived this one yet. No test is generated, and the docs render
    the slot as "not yet derived". Leaving a slot out is always safe.

There is no third state between right and wrong. A test that goes red means
either the engine is broken or your derivation was, and deciding which is the
point of the exercise — not something the corpus records an opinion about.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Mapping, Sequence

from tests.engine.scenario_framework import (
    Adapter,
    Cell,
    State,
    Topology,
    _check_compatible,
)

#: Alias for writing exact rationals inline: ``F(8, 15)``, ``F(3, 10)``.
F = Fraction

ROOT = pathlib.Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "docs" / "spec" / "properties.json"

#: The property catalog — what each published property means, its unit, and the
#: layer it belongs to. Answer keys are checked against it, so a typo in a
#: property name fails loudly instead of being silently ignored.
CATALOG: dict[str, Any] = json.loads(CATALOG_PATH.read_text())

#: Every property the corpus can carry an answer for, in catalog order (which
#: is dependency order: readings first, the monetary model last).
PROPERTIES: tuple[str, ...] = tuple(CATALOG["properties"])

#: A derived answer: a number, a (possibly nested) map of them, or ``None``
#: meaning the engine must publish nothing here.
Answer = Any


@dataclass(frozen=True)
class Snapshot:
    """One set of readings for a case's wiring, and the answers derived from it.

    ``readings`` must name *exactly* the adapter uids of the case's topology —
    a missing one would otherwise silently read as zero. ``None`` models an
    unavailable sensor; ``price`` is the grid tariff in EUR/kWh.
    """

    id: str
    note: str
    readings: Mapping[str, float | Fraction | None]
    price: float | Fraction | None = None
    answers: Mapping[str, Answer] = field(default_factory=dict)
    #: Set when the engine's answer here is an unresolved modelling choice
    #: rather than a settled one. Rendered as a callout on the docs page.
    open_question: str | None = None

    def __post_init__(self) -> None:
        unknown = sorted(set(self.answers) - set(PROPERTIES))
        if unknown:
            raise ValueError(
                f"snapshot {self.id!r} answers {unknown}, which "
                f"docs/spec/properties.json does not document — check the "
                f"spelling, or add the property to the catalog"
            )

    @property
    def derived(self) -> tuple[str, ...]:
        """The properties this snapshot has an answer for, in catalog order."""
        return tuple(p for p in PROPERTIES if p in self.answers)

    def state(self) -> State:
        return State(
            price=_as_float(self.price),
            name=self.id,
            **{uid: _as_float(v) for uid, v in self.readings.items()},
        )


@dataclass(frozen=True)
class Case:
    """One rung of the ladder: a wiring, why it exists, and its snapshots."""

    id: str
    title: str
    summary: str
    decides: Sequence[str]
    topology: Sequence[Adapter]
    snapshots: Sequence[Snapshot]

    def __post_init__(self) -> None:
        top = self.as_topology()
        ids = [s.id for s in self.snapshots]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"case {self.id!r} has duplicate snapshot ids {dupes}")
        # The scenario framework's safety rail, applied at import: a snapshot
        # that forgets an adapter fails at collection, not with a wrong number.
        for snap in self.snapshots:
            _check_compatible(top, snap.state())

    def as_topology(self) -> Topology:
        return Topology(*self.topology, name=self.id)

    def snapshot(self, snapshot_id: str) -> Snapshot:
        for snap in self.snapshots:
            if snap.id == snapshot_id:
                return snap
        raise KeyError(f"case {self.id!r} has no snapshot {snapshot_id!r}")

    def build_engine(self, snapshot: Snapshot | str) -> Any:
        """A fresh engine wired and fed exactly as this snapshot describes."""
        snap = self.snapshot(snapshot) if isinstance(snapshot, str) else snapshot
        return Cell(self.as_topology(), snap.state()).build_engine()


def _as_float(value: float | Fraction | None) -> float | None:
    """Readings reach the engine as floats; answers stay exact."""
    return None if value is None else float(value)
