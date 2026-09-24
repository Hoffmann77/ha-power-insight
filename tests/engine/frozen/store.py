"""Frozen engine outputs: what the engine computed for a fixed set of homes.

This is the change detector. It makes no claim that any output is *right* — it
assumes the engine is, and records what it computes for a fixed set of homes.
A commit that moves any of those outputs fails ``test_frozen.py`` with a list
of exactly which outputs moved in which home. If the change is intended, the
contributor re-freezes (``uv run --group engine python tools/snapshot.py``) and
the PR diff shows the moved outputs for review. If the change reveals a
modelling decision, that decision gets a hand-derived block in
``tests/engine/manual/``.

Two corpora are frozen, one file each under ``snapshots/``:

``reference.json``
    Every snapshot of every reference case (``tests/engine/reference/``). The
    inputs come from those modules; they are copied into the file only so a
    diff reads on its own.

``generated.json``
    A fixed set of random homes. Their inputs are *stored* here and replayed —
    never regenerated on the fly — so changing the random generator can never
    make this file noisy. Re-drawing them is a deliberate act
    (``tools/snapshot.py --redraw``).

Values are rounded to 12 significant digits when stored and compared with a
relative tolerance of 1e-9, so float noise from an innocent refactor never
counts as a change while any real one does.
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass
from typing import Any, Iterator

from tests.engine.reference import CATALOG, REFERENCE_CASES
from tests.engine.home import Adapter, Cell, State, Topology

HERE = pathlib.Path(__file__).resolve().parent
SNAPSHOTS = HERE / "snapshots"

#: Every output recorded per home: the catalogued properties, plus engine
#: outputs a user sees that the catalog does not describe as values.
OUTPUTS: tuple[str, ...] = (
    *CATALOG["properties"],
    "sink_adapters_restriction_deficit",
)

#: How many generated homes are frozen, and the seed they were drawn with.
GENERATED_COUNT = 60
GENERATED_SEED = 20260924

REL_TOL = 1e-9
ABS_TOL = 1e-9


# ---------------------------------------------------------------------------
# Homes: inputs that can be stored as JSON and replayed.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrozenHome:
    """One frozen home: a name, a wiring and one snapshot of readings."""

    name: str
    adapters: tuple[Adapter, ...]
    readings: dict[str, float | None]
    price: float | None

    def outputs(self) -> dict[str, Any]:
        """Every recorded output, as the engine computes it now."""
        engine = Cell(
            Topology(*self.adapters), State(price=self.price, **self.readings)
        ).build_engine()
        return {name: encode(getattr(engine, name)) for name in OUTPUTS}

    def inputs_json(self) -> dict[str, Any]:
        return {
            "adapters": [_adapter_json(a) for a in self.adapters],
            "readings": {uid: _plain(w) for uid, w in self.readings.items()},
            "price": _plain(self.price),
        }

    @classmethod
    def from_json(cls, name: str, data: dict[str, Any]) -> "FrozenHome":
        return cls(
            name,
            tuple(_adapter_from_json(a) for a in data["adapters"]),
            dict(data["readings"]),
            data["price"],
        )


def _plain(value: Any) -> Any:
    """A number JSON can hold: reference cases write exact ``Fraction``s."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return float(value)


def _adapter_json(a: Adapter) -> dict[str, Any]:
    config = {k: list(v) if isinstance(v, tuple) else v for k, v in a.config.items()}
    return {
        "kind": a.kind,
        "uid": a.uid,
        "config": config,
        "inverted": a.inverted,
        "has_price": a.has_price,
    }


def _adapter_from_json(data: dict[str, Any]) -> Adapter:
    config = {k: tuple(v) if isinstance(v, list) else v for k, v in data["config"].items()}
    return Adapter(
        data["kind"], data["uid"], config, data["inverted"], data["has_price"]
    )


def reference_homes() -> list[FrozenHome]:
    """Every snapshot of every reference case, in ladder order."""
    homes = []
    for case in REFERENCE_CASES:
        for block in case.blocks():
            homes.append(
                FrozenHome(
                    f"{case.case_id}/{block.state.name}",
                    block.topology.adapters,
                    dict(block.state.readings),
                    block.state.price,
                )
            )
    return homes


def draw_generated_homes() -> list[FrozenHome]:
    """A fresh draw of the generated corpus. Only ``--redraw`` calls this."""
    from tests.engine.automatic.random_homes import random_homes

    return [
        FrozenHome(f"generated/{i:03d}", h.adapters, dict(h.readings), h.price)
        for i, h in enumerate(random_homes(GENERATED_COUNT, GENERATED_SEED))
    ]


# ---------------------------------------------------------------------------
# Values.
# ---------------------------------------------------------------------------


def encode(value: Any) -> Any:
    """An output as stored: numbers to 12 significant digits, maps sorted."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return {str(k): encode(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    number = float(f"{float(value):.12g}")
    return 0.0 if number == 0 else number  # never store -0.0


def changes(before: Any, after: Any, path: str = "") -> Iterator[tuple[str, Any, Any]]:
    """Every ``(path, before, after)`` where two stored outputs disagree."""
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            sub = f"{path}.{key}" if path else key
            if key not in before:
                yield sub, "(absent)", after[key]
            elif key not in after:
                yield sub, before[key], "(absent)"
            else:
                yield from changes(before[key], after[key], sub)
        return
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        if not isinstance(before, bool) and not isinstance(after, bool):
            if math.isclose(before, after, rel_tol=REL_TOL, abs_tol=ABS_TOL):
                return
    elif before == after:
        return
    yield path, before, after


# ---------------------------------------------------------------------------
# Snapshot files.
# ---------------------------------------------------------------------------


def snapshot_path(corpus: str) -> pathlib.Path:
    return SNAPSHOTS / f"{corpus}.json"


def load(corpus: str) -> dict[str, dict[str, Any]]:
    path = snapshot_path(corpus)
    if not path.exists():
        return {}
    return json.loads(path.read_text())["homes"]


def homes_of(corpus: str) -> list[FrozenHome]:
    """The homes a corpus freezes: reference from its modules, generated stored."""
    if corpus == "reference":
        return reference_homes()
    return [FrozenHome.from_json(name, entry) for name, entry in load(corpus).items()]


def render(homes: list[FrozenHome], corpus: str) -> str:
    """A corpus's snapshot file, as it should read for the engine now."""
    data = {
        "$comment": (
            "Frozen engine outputs — generated by tools/snapshot.py, never "
            "hand-edited. See tests/engine/frozen/store.py."
        ),
        "corpus": corpus,
        "homes": {
            home.name: {**home.inputs_json(), "outputs": home.outputs()}
            for home in homes
        },
    }
    return json.dumps(data, indent=1, sort_keys=False) + "\n"


CORPORA = ("reference", "generated")


@dataclass(frozen=True)
class Change:
    home: str
    output: str
    before: Any
    after: Any


def compare(corpus: str) -> tuple[list[Change], list[str]]:
    """What moved since the corpus was frozen: ``(output changes, other drift)``.

    Other drift is anything that is not an output moving — a home added,
    removed, or given different inputs — which re-freezing also resolves but
    which is not an engine change.
    """
    stored = load(corpus)
    moved: list[Change] = []
    drift: list[str] = []
    homes = homes_of(corpus)
    names = {h.name for h in homes}
    for name in sorted(set(stored) - names):
        drift.append(f"{name}: no longer in the corpus")
    for home in homes:
        entry = stored.get(home.name)
        if entry is None:
            drift.append(f"{home.name}: not frozen yet")
            continue
        if json.loads(json.dumps(home.inputs_json())) != {
            k: entry[k] for k in ("adapters", "readings", "price")
        }:
            drift.append(f"{home.name}: its inputs changed")
            continue
        now = home.outputs()
        for output in OUTPUTS:
            for path, before, after in changes(
                entry["outputs"].get(output, "(absent)"), now[output]
            ):
                full = f"{output}.{path}" if path else output
                moved.append(Change(home.name, full, before, after))
    return moved, drift


def report(moved: list[Change], drift: list[str], *, limit: int = 40) -> str:
    """A markdown summary of what moved, for a test failure or a CI summary."""
    lines: list[str] = []
    if moved:
        homes = sorted({c.home for c in moved})
        outputs = sorted({c.output.split(".")[0] for c in moved})
        lines += [
            f"**{len(moved)} engine output(s) changed** in {len(homes)} "
            f"frozen home(s), across {len(outputs)} propert(y/ies): "
            + ", ".join(f"`{o}`" for o in outputs),
            "",
            "| Home | Output | Frozen | Now |",
            "| --- | --- | --- | --- |",
        ]
        for c in moved[:limit]:
            lines.append(f"| `{c.home}` | `{c.output}` | {c.before} | {c.after} |")
        if len(moved) > limit:
            lines.append(f"| … | {len(moved) - limit} more | | |")
        lines.append("")
    if drift:
        lines += ["**Snapshot drift** (not an engine change):", ""]
        lines += [f"- {d}" for d in drift[:limit]]
        lines.append("")
    return "\n".join(lines)
