"""Prototype: ``@topology`` / ``@state`` scenario framework for engine tests.

This is a *design prototype* exploring a single framework that can host **all**
engine tests, replacing both the class-per-scenario edge-case file
(``test_engine_property_scenarios.py``) and the one-topology-many-readings sweep
(``test_power_insight_calculations.py``).

The framework separates the three axes that the older ``Device`` surface fused
together:

* **Topology** — which adapters exist and their static config (lcoe, export
  compensation, charge routing …). Declared with an ``@topology`` method.
* **State** — the readings (``grid=-1000, pv1=2000`` …). Declared with a
  ``@state`` method.
* **Expectation** — what a property should be, written in the ``test_`` methods.

Two base classes consume those axes with *different* semantics, because pinned
numbers and general laws want different treatment (see the module ``README`` at
the bottom of this file for the reasoning):

``CaseScenario``
    Exactly one topology × one state. ``test_`` methods hold **hand-written,
    pinned** expected values — the home for edge cases (zero gross power, pure
    export, unavailable sensors, adapter routing). Same authoring surface as
    ``LawScenario`` (``@topology`` + ``@state``), constrained to a single cell.
    Spiritual successor to ``test_engine_property_scenarios.py``, minus the
    preset indirection: adapter config lives inline on the ``Adapter`` call.

``LawScenario``
    The **cartesian product** of every topology × every state. ``test_`` methods
    must therefore hold assertions that *generalise* across the whole product —
    invariants, or formulas written over the current ``state``. This is the home
    for "one shape, many readings / config variants" sweeps. Because a pinned
    number is only valid in one cell, pinning is *not allowed* here; the product
    only makes sense for laws.

Collection-time safety rail: a ``state`` must supply a reading for *exactly* the
adapter uids its topology defines — no more, no less. A mismatch raises
``ValueError`` at collection instead of silently defaulting a missing adapter to
zero (which would let a state named ``midday_charging`` "pass" against a
battery-less topology while testing nothing).

Wiring: ``tests/engine/conftest.py`` calls :func:`generate_scenario_tests` from
``pytest_generate_tests`` and defines the ``power_insight`` / ``state`` /
``topology`` fixtures that the product is threaded through.
"""

from __future__ import annotations

import importlib.util
import itertools
import os
from dataclasses import dataclass, field
from typing import Any, Callable

import pytest

# ---------------------------------------------------------------------------
# Load the pure-Python engine directly (same importlib trick as the other
# engine-tier tests — no Home Assistant import).
# ---------------------------------------------------------------------------

_MODULE_PATH = os.path.join(
    os.path.dirname(__file__),
    os.pardir,
    os.pardir,
    "custom_components",
    "power_insight",
    "power_insight.py",
)
_spec = importlib.util.spec_from_file_location("power_insight", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

PowerInsight = _mod.PowerInsight
GridAdapter = _mod.GridAdapter
PvAdapter = _mod.PvAdapter
BatteryAdapter = _mod.BatteryAdapter
ConsumerAdapter = _mod.ConsumerAdapter

GRID_PRICE_ENTITY = "sensor.grid_price"
_KIND_PREFIX = {"grid": "grid", "pv": "pv", "battery": "bat", "consumer": "cons"}


# ---------------------------------------------------------------------------
# Adapter — a declarative spec with config inline at the call site (no presets).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Adapter:
    """One adapter's kind + static config. Build via the classmethod factories.

    Config lives here, visible at the topology definition, so an expected value
    that hinges on (say) ``export_comp`` is documented where it is used rather
    than hidden behind a preset key.
    """

    kind: str
    number: int
    config: dict[str, Any]
    inverted: bool = False
    has_price: bool = True  # whether the grid has a price source entity at all

    # -- factories --------------------------------------------------------

    @classmethod
    def grid(
        cls,
        *,
        inverted: bool = False,
        name: str = "Grid",
        has_price_entity: bool = True,
    ) -> Adapter:
        return cls("grid", 0, {"name": name}, inverted=inverted, has_price=has_price_entity)

    @classmethod
    def pv(
        cls,
        number: int = 1,
        *,
        lcoe: float | None = 0.10,
        lco2_intensity: float | None = 50.0,
        exports: bool = False,
        export_comp: float = 0.0,
        correction_factor: float = 1.0,
        inverted: bool = False,
        name: str | None = None,
    ) -> Adapter:
        return cls(
            "pv",
            number,
            {
                "name": name,
                "lcoe": lcoe,
                "lco2_intensity": lco2_intensity,
                "exports_power": exports,
                "export_compensation": export_comp,
                "correction_factor": correction_factor,
            },
            inverted=inverted,
        )

    @classmethod
    def battery(
        cls,
        number: int = 1,
        *,
        lcos: float | None = 0.15,
        lco2_intensity: float | None = 100.0,
        exports: bool = False,
        export_comp: float = 0.0,
        charge_from: tuple[str, ...] = (),
        inverted: bool = False,
        name: str | None = None,
    ) -> Adapter:
        return cls(
            "battery",
            number,
            {
                "name": name,
                "lcos": lcos,
                "lco2_intensity": lco2_intensity,
                "exports_power": exports,
                "export_compensation": export_comp,
                "charge_from_adapters": tuple(charge_from),
            },
            inverted=inverted,
        )

    @classmethod
    def consumer(
        cls,
        number: int = 1,
        *,
        inverted: bool = False,
        name: str | None = None,
    ) -> Adapter:
        return cls("consumer", number, {"name": name}, inverted=inverted)

    # -- derived ----------------------------------------------------------

    @property
    def uid(self) -> str:
        if self.kind == "grid":
            return "grid"
        return f"{_KIND_PREFIX[self.kind]}{self.number}"

    @property
    def power_entity(self) -> str:
        return f"sensor.{self.uid}_power"

    def build(self) -> Any:
        """Instantiate the real engine adapter (fresh, no readings)."""
        cfg = self.config
        if self.kind == "grid":
            return GridAdapter(
                unique_id=self.uid,
                verbose_name=cfg["name"],
                power_entity=self.power_entity,
                power_entity_inverted=self.inverted,
                price_entity=GRID_PRICE_ENTITY if self.has_price else None,
                co2_entity=None,
            )
        if self.kind == "pv":
            return PvAdapter(
                unique_id=self.uid,
                verbose_name=cfg["name"] or self.uid,
                power_entity=self.power_entity,
                power_entity_inverted=self.inverted,
                lcoe=cfg["lcoe"],
                lco2_intensity=cfg["lco2_intensity"],
                exports_power=cfg["exports_power"],
                export_compensation=cfg["export_compensation"],
                correction_factor=cfg["correction_factor"],
            )
        if self.kind == "battery":
            return BatteryAdapter(
                unique_id=self.uid,
                verbose_name=cfg["name"] or self.uid,
                power_entity=self.power_entity,
                power_entity_inverted=self.inverted,
                lcos=cfg["lcos"],
                lco2_intensity=cfg["lco2_intensity"],
                exports_power=cfg["exports_power"],
                export_compensation=cfg["export_compensation"],
                charge_from_adapters=list(cfg["charge_from_adapters"]),
            )
        if self.kind == "consumer":
            return ConsumerAdapter(
                unique_id=self.uid,
                verbose_name=cfg["name"] or self.uid,
                power_entity=self.power_entity,
                power_entity_inverted=self.inverted,
            )
        raise ValueError(f"unknown adapter kind {self.kind!r}")


# ---------------------------------------------------------------------------
# Topology + State
# ---------------------------------------------------------------------------


@dataclass
class Topology:
    """One device: exactly one grid plus any PV / battery / consumer adapters.

    Validated at construction: exactly one grid, unique uids, and every battery
    ``charge_from`` target present.
    """

    adapters: tuple[Adapter, ...]
    name: str = ""  # filled in from the @topology method name

    def __init__(self, *adapters: Adapter, name: str = "") -> None:
        self.adapters = tuple(adapters)
        self.name = name
        self._validate()

    def _validate(self) -> None:
        grids = [a for a in self.adapters if a.kind == "grid"]
        if len(grids) != 1:
            raise ValueError(f"topology needs exactly one grid, got {len(grids)}")
        uids = [a.uid for a in self.adapters]
        dupes = {u for u in uids if uids.count(u) > 1}
        if dupes:
            raise ValueError(f"duplicate adapter uid(s) {sorted(dupes)}")
        known = set(uids)
        for a in self.adapters:
            if a.kind == "battery":
                for src in a.config["charge_from_adapters"]:
                    if src not in known:
                        raise ValueError(
                            f"battery {a.uid!r} charge_from references unknown "
                            f"adapter {src!r}; known: {sorted(known)}"
                        )

    @property
    def uids(self) -> frozenset[str]:
        return frozenset(a.uid for a in self.adapters)

    def build_engine(self) -> Any:
        pi = PowerInsight()
        for a in self.adapters:
            pi.register_adapter(a.build())
        return pi


@dataclass(frozen=True)
class State:
    """A named set of readings: ``uid -> power`` plus the grid ``price``.

    ``State(grid=-1000, pv1=2000, price=0.30)``. ``price`` is reserved for the
    grid price (EUR/kWh); every other kwarg is an adapter uid -> power (W), with
    ``None`` modelling an unavailable sensor.
    """

    readings: dict[str, float | None]
    price: float | None = None
    name: str = ""  # filled in from the @state method name

    def __init__(
        self, *, price: float | None = None, name: str = "", **readings: float | None
    ) -> None:
        object.__setattr__(self, "readings", dict(readings))
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "name", name)

    def __getattr__(self, item: str) -> float | None:
        # Let formula tests write ``state.pv1`` for a reading.
        try:
            return self.readings[item]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(item) from exc


# ---------------------------------------------------------------------------
# Cell — one (topology, state) pair, ready to build an engine.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    topology: Topology
    state: State

    @property
    def id(self) -> str:
        return f"{self.topology.name}-{self.state.name}"

    def build_engine(self) -> Any:
        pi = self.topology.build_engine()
        for uid, value in self.state.readings.items():
            pi.set_value(f"sensor.{uid}_power", value)
        if self.state.price is not None:
            pi.set_value(GRID_PRICE_ENTITY, self.state.price)
        return pi


def _check_compatible(topology: Topology, state: State) -> None:
    """A state must name exactly the topology's adapter uids (safety rail)."""
    want = topology.uids
    have = frozenset(state.readings)
    if want != have:
        missing = sorted(want - have)
        extra = sorted(have - want)
        raise ValueError(
            f"state {state.name!r} is incompatible with topology "
            f"{topology.name!r}: missing readings {missing}, unexpected {extra}. "
            f"(A state must supply exactly the topology's uids {sorted(want)}.)"
        )


# ---------------------------------------------------------------------------
# @topology / @state decorators + collection.
# ---------------------------------------------------------------------------


def topology(fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Mark a method as supplying the scenario's topology.

    The method may return a :class:`Topology`, or just a tuple/list of
    :class:`Adapter` (wrapped into a ``Topology`` automatically).
    """
    fn._scenario_role = "topology"  # type: ignore[attr-defined]
    return fn


def state(fn: Callable[[Any], State]) -> Callable[[Any], State]:
    """Mark a method as returning a :class:`State` for the scenario."""
    fn._scenario_role = "state"  # type: ignore[attr-defined]
    return fn


def _collect(cls: type, role: str) -> list[Callable[[Any], Any]]:
    """Return the decorated methods of ``cls`` for ``role``, in source order."""
    found = []
    for name in dir(cls):
        try:
            attr = getattr(cls, name)
        except AttributeError:  # pragma: no cover - defensive
            continue
        if getattr(attr, "_scenario_role", None) == role:
            found.append(attr)
    found.sort(key=lambda f: f.__code__.co_firstlineno)
    return found


# ---------------------------------------------------------------------------
# Invariants — laws checked against every cell of a LawScenario.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Invariant:
    """A named law. ``check(power_insight)`` raises ``AssertionError`` if broken."""

    name: str
    check: Callable[[Any], None]


def reconstructs_gross_power() -> Invariant:
    """gross_power equals an *independent* reconstruction from raw readings.

    This is a differential check: the engine computes gross_power through its
    adapter chain; here we recompute it straight from the stored raw values, so
    a formula regression in the engine cannot hide behind a matching test.
    """

    def _check(pi: Any) -> None:
        gross = pi.gross_power
        if gross is None:
            return
        expected = 0.0
        for adapter in [pi.grid_adapter, *pi.pv_system_adapters, *pi.storage_adapters]:
            raw = adapter.power  # signed W, inversion already normalised
            if raw is None:
                return
            # grid: import only; pv/battery: production / discharge only.
            expected += max(raw, 0.0)
        assert gross == pytest.approx(expected), (
            f"gross_power {gross} != independent reconstruction {expected}"
        )

    return Invariant("reconstructs_gross_power", _check)


def export_ratio_bounded() -> Invariant:
    """gross_power_export_ratio stays in [0, 1] (or None) in the normal regime.

    NB: this is only a law for *physical* states (production >= export). Pure
    grid export with no production drives consumption negative — that degenerate
    belongs in a CaseScenario, not a LawScenario family.
    """

    def _check(pi: Any) -> None:
        ratio = pi.gross_power_export_ratio
        if ratio is None:
            return
        assert -1e-9 <= ratio <= 1 + 1e-9, f"export ratio {ratio} out of [0, 1]"

    return Invariant("export_ratio_bounded", _check)


# ---------------------------------------------------------------------------
# Base classes.
# ---------------------------------------------------------------------------


class _ScenarioBase:
    """Shared collection machinery. Not a base you use directly."""

    @classmethod
    def _topologies(cls) -> list[Topology]:
        out = []
        for fn in _collect(cls, "topology"):
            result = fn(cls())
            # A @topology method may return a Topology or just a tuple/list of
            # adapters — the bare tuple is wrapped here.
            topo = result if isinstance(result, Topology) else Topology(*result)
            topo.name = fn.__name__
            out.append(topo)
        return out

    @classmethod
    def _states(cls) -> list[State]:
        out = []
        for fn in _collect(cls, "state"):
            st = fn(cls())
            object.__setattr__(st, "name", fn.__name__)
            out.append(st)
        return out

    @classmethod
    def scenario_cells(cls) -> list[Cell]:  # overridden per base
        raise NotImplementedError


class CaseScenario(_ScenarioBase):
    """Exactly one topology × one state, with **pinned** expected values.

    The home for edge cases. Same authoring surface as :class:`LawScenario`
    (``@topology`` + ``@state``), but constrained to a single cell — a pinned
    number is only valid in one cell. Adding a second ``@state`` or ``@topology``
    is an error; sweep readings with a :class:`LawScenario` instead.
    """

    @classmethod
    def scenario_cells(cls) -> list[Cell]:
        topos = cls._topologies()
        states = cls._states()
        if len(topos) != 1 or len(states) != 1:
            raise ValueError(
                f"{cls.__name__} is a CaseScenario: expected exactly one "
                f"@topology and one @state, got {len(topos)} topologies and "
                f"{len(states)} states. Use LawScenario for a product."
            )
        _check_compatible(topos[0], states[0])
        return [Cell(topos[0], states[0])]


class LawScenario(_ScenarioBase):
    """Every topology × every state. ``test_`` methods must **generalise**.

    Because a cell's expected values differ, pin nothing here: write invariants
    (see :attr:`INVARIANTS`) or formulas over the injected ``state`` fixture.
    Multiple topologies should be *config variants of one adapter shape* (same
    uids) so every state stays compatible with every topology.
    """

    #: Laws checked against every cell by the built-in ``test_invariants``.
    INVARIANTS: list[Invariant] = []

    @classmethod
    def scenario_cells(cls) -> list[Cell]:
        topos = cls._topologies()
        states = cls._states()
        if not topos or not states:
            raise ValueError(
                f"{cls.__name__} needs at least one @topology and one @state"
            )
        cells = []
        for topo, st in itertools.product(topos, states):
            _check_compatible(topo, st)  # safety rail: no silent zero-fill
            cells.append(Cell(topo, st))
        return cells

    def test_invariants(self, power_insight: Any, state: State) -> None:
        """Assert every declared invariant against this cell."""
        if not self.INVARIANTS:
            pytest.skip("no INVARIANTS declared")
        for inv in self.INVARIANTS:
            try:
                inv.check(power_insight)
            except AssertionError as exc:
                raise AssertionError(f"[{inv.name}] {exc}") from exc


# ---------------------------------------------------------------------------
# pytest wiring — called from tests/engine/conftest.py.
# ---------------------------------------------------------------------------


def generate_scenario_tests(metafunc: Any) -> None:
    """Parametrize a scenario class's tests over its cells.

    Call from ``pytest_generate_tests``. No-op for non-scenario classes.
    """
    cls = getattr(metafunc, "cls", None)
    if cls is None or not (isinstance(cls, type) and issubclass(cls, _ScenarioBase)):
        return
    if "_scenario_cell" not in metafunc.fixturenames:
        return
    cells = cls.scenario_cells()
    metafunc.parametrize("_scenario_cell", cells, ids=[c.id for c in cells])
