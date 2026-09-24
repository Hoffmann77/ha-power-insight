"""The reference-case base class: a fixed home that can publish itself.

A reference case is a small, fixed home — one wiring and a few snapshots of
readings — shown on the documentation site with everything the engine
computes for it. The cases are a **showcase**, not a specification: the
numbers on a page are whatever the engine produced for those readings at that
version of the code, recomputed by ``tools/snapshot.py`` and frozen into
each docs version when it is cut. What the engine *ought* to do is pinned
elsewhere — each decision by a hand-derived class in ``tests/engine/manual/``,
every property's formula and the laws they obey in ``tests/engine/automatic/``.

Writing a case
--------------

A case declares its devices like any home (``tests/engine/home.py``), but
without readings — those differ from snapshot to snapshot, so each
:class:`Snapshot` inside the case supplies them::

    class GridOnly(ReferenceCase):
        \"\"\"One meter and nothing else. ...

        Shows:

        * With no local device, the whole gross power is the home base load.
        \"\"\"

        case_id = "grid-only"
        title = "Grid only"

        grid = Grid()

        class ImportOnly(Snapshot):
            \"\"\"The house runs on the grid alone; every watt is base load.\"\"\"

            grid = 1200
            price = F(3, 10)

That is the whole source. A snapshot names a reading for exactly the case's
devices (``None`` for an unavailable sensor) plus the grid ``price``, and its
published id is its class name in snake_case (``import_only``). The prose lives
in docstrings — the case's is the page summary (everything above its
``Shows:`` list), a snapshot's is the caption under its card, and a paragraph
opening ``Open question:`` becomes a callout.
"""

from __future__ import annotations

import inspect
import json
import pathlib
import re
from fractions import Fraction
from typing import Any, ClassVar

from tests.engine.home import (
    NO_READING,
    Cell,
    Device,
    Grid,
    State,
    check_compatible,
    declared_devices,
    wiring,
)

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


class Snapshot:
    """One set of readings for a reference case: ``uid = watts`` attributes
    plus the grid ``price``. Its docstring is the caption under its card."""

    price: ClassVar[float | None] = None

    @classmethod
    def id(cls) -> str:
        """The published id: the class name in snake_case."""
        return re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()

    @classmethod
    def state(cls) -> State:
        readings = {
            name: value
            for name, value in vars(cls).items()
            if not name.startswith("_") and name != "price"
        }
        return State(price=cls.price, name=cls.id(), **readings)


class ReferenceCase:
    """One rung of the ladder: a wiring, what it shows, and its snapshots.

    Subclasses set :attr:`case_id` and :attr:`title`, declare their devices
    without readings, then one :class:`Snapshot` per set of readings. See the
    module docstring. A case is checked when its class is created: its wiring
    like any home's, and every snapshot against it.
    """

    #: The published id — the docs page slug.
    case_id: ClassVar[str] = ""
    #: Human-readable name, shown as the page title.
    title: ClassVar[str] = ""
    #: The case's devices and snapshots, in declaration order.
    devices: ClassVar[tuple[Device, ...]] = ()
    snapshots: ClassVar[tuple[type[Snapshot], ...]] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.devices = declared_devices(cls)
        cls.snapshots = tuple(
            obj
            for obj in vars(cls).values()
            if isinstance(obj, type) and issubclass(obj, Snapshot)
        )
        topology = wiring(cls, cls.devices, base=ReferenceCase)
        clash = [d.uid for d in cls.devices if d.uid in dir(Snapshot)]
        if clash:
            raise TypeError(
                f"{cls.__name__}: a device may not be called {clash}, which a "
                f"Snapshot already uses"
            )
        read = [d.uid for d in cls.devices if d.power is not NO_READING]
        if read:
            raise TypeError(
                f"{cls.__name__}: {read} carry a reading — a case's readings "
                f"belong in its snapshots, so declare the devices bare"
            )
        if any(isinstance(d, Grid) and d.price is not None for d in cls.devices):
            raise TypeError(
                f"{cls.__name__}: the grid price is a reading — set it on each "
                f"snapshot as 'price = ...'"
            )
        for snapshot in cls.snapshots:
            try:
                check_compatible(topology, snapshot.state())
            except ValueError as exc:
                raise TypeError(f"{cls.__name__}.{snapshot.__name__}: {exc}") from None

    @classmethod
    def cells(cls) -> list[Cell]:
        """Every snapshot as a (topology, state) pair, in source order."""
        topology = wiring(cls, cls.devices, base=ReferenceCase)
        return [Cell(topology, snapshot.state()) for snapshot in cls.snapshots]

    @classmethod
    def summary(cls) -> str:
        """The page summary: the class docstring above its ``Shows:`` list."""
        return _prose(cls.__doc__)[0]

    @classmethod
    def shows(cls) -> tuple[str, ...]:
        """What this case illustrates about the engine, from ``Shows:``."""
        return _prose(cls.__doc__)[1]

    @classmethod
    def publish(cls) -> dict:
        """This case as the documentation site consumes it.

        One entry per snapshot, each carrying the wiring, the readings, and
        every catalogued property as the engine computes it right now.
        """
        if not cls.case_id or not cls.title:
            raise ValueError(f"{cls.__name__} must set both case_id and title")
        if not cls.snapshots:
            raise ValueError(f"{cls.__name__} declares no Snapshot to publish")
        cells = cls.cells()
        return {
            "id": cls.case_id,
            "title": cls.title,
            "summary": cls.summary(),
            "shows": list(cls.shows()),
            "topology": [_adapter(a) for a in cells[0].topology.adapters],
            "states": [
                _snapshot(snapshot, cell)
                for snapshot, cell in zip(cls.snapshots, cells)
            ],
        }


# ---------------------------------------------------------------------------
# Turning a snapshot into published JSON.
# ---------------------------------------------------------------------------


def _snapshot(snapshot: type[Snapshot], cell: Cell) -> dict:
    note, open_question = _state_prose(snapshot)
    engine = cell.build_engine()
    entry = {
        "id": cell.state.name,
        "note": note,
        "readings": {uid: _rat(v) for uid, v in cell.state.readings.items()},
        "price": _rat(cell.state.price),
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
# its class docstring, a snapshot's caption in its :class:`Snapshot`'s. There
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


def _state_prose(snapshot: type[Snapshot]) -> tuple[str, str | None]:
    """A snapshot's docstring split into ``(note, open_question)``.

    The note is the caption under the snapshot card. A paragraph opening
    ``Open question:`` marks a snapshot where which answer is *right* has not
    been settled — rendered as a callout, and collected onto the section index.
    """
    doc = inspect.cleandoc(snapshot.__doc__ or "")
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
