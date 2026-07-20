"""``@topology`` / ``@state`` scenario framework for engine tests.

A single framework that hosts all engine tests, replacing both the
class-per-scenario edge-case file (``test_engine_property_scenarios.py``) and the
one-topology-many-readings sweep (``test_power_insight_calculations.py``).

It separates the axes that the older ``Device`` surface fused together:

* **Topology** — which adapters exist and their static config (lcoe, export
  compensation, charge routing …). Declared with an ``@topology`` method, one or
  more per scenario.
* **State** — the readings (``grid=-1000, pv1=2000`` …). Declared with a
  ``@state`` method, one or more per scenario.
* **Expectation** — what a property should be, as an ``@expect`` data map and/or
  a ``test_`` method.

A scenario subclasses :class:`EngineTestScenario` (the only base). Its cells are
the topology × state product, plus any ``@modify`` variants. Each cell is checked
by:

* **``@expect`` maps** — ``{property: value}`` data, optionally scoped by
  topology/state (see :func:`expect`); one assertion generated per (cell,
  property).
* **``test_`` methods** — ordinary pytest methods for bespoke assertions,
  optionally narrowed to a subset of cells with ``@cells`` (see :func:`cells`).

Use maps for the numeric bulk and methods for the awkward cases (``is None``,
relationships, formulas); a class may use either or both.

Collection-time safety rail: a ``state`` must supply a reading for *exactly* the
adapter uids its topology defines — no more, no less. A mismatch raises
``ValueError`` at collection instead of silently defaulting a missing adapter to
zero (which would let a state named ``midday_charging`` "pass" against a
battery-less topology while testing nothing).

Wiring: ``tests/engine/conftest.py`` calls :func:`generate_scenario_tests` from
``pytest_generate_tests`` and defines the ``power_insight`` / ``state`` /
``topology`` / ``expected`` fixtures the cells are threaded through.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field, replace
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
    #: Per-cell expected-value overrides, consulted via the ``expected`` fixture.
    #: Empty for a base cell; populated from a ``Modify.expect(...)`` on variants.
    expected: dict[str, Any] = field(default_factory=dict)
    #: Variant name (from a ``@modify``) appended to the id; ``None`` for a base.
    label: str | None = None

    @property
    def id(self) -> str:
        parts = [self.topology.name, self.state.name, self.label]
        return "-".join(p for p in parts if p)

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


def modify(fn: Callable[[Any], "Modify"]) -> Callable[[Any], "Modify"]:
    """Mark a method as returning a :class:`Modify` — a topology variant.

    Each ``@modify`` spins off an extra cell: the base topology with the
    modification applied, sharing the same ``@state``. The assertions (``@expect``
    entries and ``test_`` methods) run against the base cell *and* every variant.
    """
    fn._scenario_role = "modify"  # type: ignore[attr-defined]
    return fn


def expect(
    *args: Any, topology: str | None = None, state: str | None = None
) -> Any:
    """Mark a method as returning a ``{property_name: expected_value}`` map.

    EngineTestScenario only. Usable bare or scoped::

        @expect                         # applies to every cell (defaults)
        @expect(state="midday")         # only cells whose state is "midday"
        @expect(topology="exporting")   # only cells whose topology is "exporting"
        @expect(topology="exporting", state="midday")   # that one cell

    For a given cell the matching maps are merged least-specific first (bare →
    single-axis → both-axes), then any ``@modify`` variant overrides win. The
    framework generates one assertion per (cell, property):
    ``getattr(power_insight, property) == expected``.
    """

    def _mark(fn: Callable[[Any], dict]) -> Callable[[Any], dict]:
        fn._scenario_role = "expect"  # type: ignore[attr-defined]
        fn._expect_scope = (topology, state)  # type: ignore[attr-defined]
        return fn

    if args:
        if len(args) != 1 or not callable(args[0]) or topology or state:
            raise TypeError("@expect takes only keyword scopes: topology=, state=")
        return _mark(args[0])  # bare @expect usage
    return _mark  # @expect(...) usage


def cells(
    *, topology: str | None = None, state: str | None = None
) -> Callable[[Callable], Callable]:
    """Restrict a ``test_`` method to product cells matching this scope.

    Without it a test method runs against every cell of the product;
    ``@cells(topology="exporting")`` /
    ``@cells(state="midday")`` / ``@cells(topology="x", state="y")`` narrow it to
    the matching subset. Use it to add a bespoke assertion (``is None``, a
    relationship, a formula) for specific cells alongside the ``@expect`` maps.
    """

    def deco(fn: Callable) -> Callable:
        fn._cell_scope = (topology, state)  # type: ignore[attr-defined]
        return fn

    return deco


def _filter_cells_by_scope(
    cells_: list["Cell"],
    scope: tuple[str | None, str | None],
    where: str,
) -> list["Cell"]:
    topo_s, state_s = scope
    topo_names = {c.topology.name for c in cells_}
    state_names = {c.state.name for c in cells_}
    if topo_s is not None and topo_s not in topo_names:
        raise ValueError(
            f"{where}: @cells(topology={topo_s!r}) matches no topology; "
            f"known: {sorted(topo_names)}"
        )
    if state_s is not None and state_s not in state_names:
        raise ValueError(
            f"{where}: @cells(state={state_s!r}) matches no state; "
            f"known: {sorted(state_names)}"
        )
    return [
        c
        for c in cells_
        if (topo_s is None or c.topology.name == topo_s)
        and (state_s is None or c.state.name == state_s)
    ]


# ---------------------------------------------------------------------------
# Modify — attribute changes to the base topology, producing a variant cell.
# ---------------------------------------------------------------------------

# Friendly override key -> ("config" dict key | "field" attr, engine name).
_FRIENDLY_OVERRIDES: dict[str, tuple[str, str]] = {
    "name": ("config", "name"),
    "lcoe": ("config", "lcoe"),
    "lcos": ("config", "lcos"),
    "lco2_intensity": ("config", "lco2_intensity"),
    "exports": ("config", "exports_power"),
    "export_comp": ("config", "export_compensation"),
    "correction_factor": ("config", "correction_factor"),
    "charge_from": ("config", "charge_from_adapters"),
    "inverted": ("field", "inverted"),
    "has_price_entity": ("field", "has_price"),
}


class Modify:
    """A named topology variant: one or more adapter overrides + optional expects.

    ``Modify("pv1", correction_factor=1.25)`` overrides the ``pv1`` adapter.
    Chain ``.and_("grid", inverted=True)`` for a multi-adapter variant, and
    ``.expect(some_property=value)`` for the expected values this variant
    *changes* (properties it leaves alone keep the base cell's pinned numbers).
    """

    def __init__(self, target: str | None = None, **overrides: Any) -> None:
        self.changes: list[tuple[str, dict[str, Any]]] = []
        if target is not None:
            self.changes.append((target, overrides))
        elif overrides:
            raise ValueError("Modify(**overrides) needs a target uid")
        self.expected: dict[str, Any] = {}
        self.name: str = ""

    def and_(self, target: str, **overrides: Any) -> "Modify":
        """Also override another adapter as part of the same variant."""
        self.changes.append((target, overrides))
        return self

    def expect(self, **expected: Any) -> "Modify":
        """Declare the expected values this variant changes from the base."""
        self.expected.update(expected)
        return self


def _override_adapter(adapter: Adapter, overrides: dict[str, Any]) -> Adapter:
    config = dict(adapter.config)
    fields: dict[str, Any] = {}
    for key, value in overrides.items():
        if key not in _FRIENDLY_OVERRIDES:
            raise ValueError(
                f"unknown override {key!r}; allowed: {sorted(_FRIENDLY_OVERRIDES)}"
            )
        target, engine_key = _FRIENDLY_OVERRIDES[key]
        if key == "charge_from":
            value = tuple(value)
        if target == "config":
            config[engine_key] = value
        else:
            fields[engine_key] = value
    return replace(adapter, config=config, **fields)


def _apply_modify(topology: Topology, mod: Modify) -> Topology:
    adapters = list(topology.adapters)
    by_uid = {a.uid: i for i, a in enumerate(adapters)}
    for target, overrides in mod.changes:
        if target not in by_uid:
            raise ValueError(
                f"modify {mod.name!r} targets unknown adapter {target!r}; "
                f"known: {sorted(by_uid)}"
            )
        idx = by_uid[target]
        adapters[idx] = _override_adapter(adapters[idx], overrides)
    # Keep the base topology's name; the cell's ``label`` carries the variant.
    return Topology(*adapters, name=topology.name)


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
# Base class.
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
    def _modifies(cls) -> list[Modify]:
        out = []
        for fn in _collect(cls, "modify"):
            mod = fn(cls())
            mod.name = fn.__name__
            out.append(mod)
        return out

    @classmethod
    def _expect_specs(cls) -> list[tuple[str | None, str | None, dict[str, Any]]]:
        """Every ``@expect`` map with its ``(topology, state)`` scope."""
        specs = []
        for fn in _collect(cls, "expect"):
            topo_s, state_s = getattr(fn, "_expect_scope", (None, None))
            specs.append((topo_s, state_s, fn(cls())))
        return specs

    @classmethod
    def _variant_cells(cls, topo: Topology, st: State) -> list[Cell]:
        """The base cell for ``(topo, st)`` plus one per ``@modify``."""
        _check_compatible(topo, st)
        cells = [Cell(topo, st)]
        for mod in cls._modifies():
            variant = _apply_modify(topo, mod)
            _check_compatible(variant, st)  # config-only change keeps uids
            cells.append(Cell(variant, st, expected=mod.expected, label=mod.name))
        return cells

    @classmethod
    def _product_cells(cls) -> list[Cell]:
        """Every topology × every state (+ ``@modify`` variants). Declarative."""
        topos = cls._topologies()
        states = cls._states()
        if not topos or not states:
            raise ValueError(
                f"{cls.__name__} needs at least one @topology and one @state"
            )
        cells: list[Cell] = []
        for topo in topos:
            for st in states:
                cells.extend(cls._variant_cells(topo, st))
        return cells

    @classmethod
    def scenario_cells(cls) -> list[Cell]:
        return cls._product_cells()


# ---------------------------------------------------------------------------
# EngineTestScenario — expectations as data, assertions auto-generated.
# ---------------------------------------------------------------------------


def _approxify(value: Any) -> Any:
    """Wrap leaf numbers in ``pytest.approx`` while preserving dict/list shape.

    Lets a nested expected value like ``{"bat1": {"grid": 0.25}}`` compare
    tolerantly against the engine's floats via a plain ``==``.
    """
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, dict):
        return {k: _approxify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_approxify(v) for v in value)
    if isinstance(value, (int, float)):
        return pytest.approx(value)
    return value


@dataclass(frozen=True)
class _DeclCase:
    """One auto-generated assertion: property ``prop`` on ``cell`` == ``expected``."""

    cell: Cell
    prop: str
    expected: Any

    @property
    def id(self) -> str:
        return f"{self.cell.id}-{self.prop}"


class EngineTestScenario(_ScenarioBase):
    """The single scenario base: a topology × state product, checked two ways.

    Declare ``@topology`` + ``@state`` (+ optional ``@modify`` variants). Every
    cell of the product can then be checked by either or both of:

    * **``@expect`` maps** — ``{property_name: expected_value}`` data. The
      framework emits one assertion per (cell, property):
      ``getattr(power_insight, property) == expected`` (float-tolerant, deep on
      dicts). Maps may be scoped by topology and/or state (see :func:`expect`);
      for a cell the matching maps merge least-specific first, then a ``@modify``
      variant's ``Modify.expect(...)`` wins last. A property name appears once as
      a map key and ``getattr`` makes a typo fail loudly.
    * **``test_`` methods** — ordinary pytest methods taking ``power_insight`` /
      ``state`` / ``topology`` / ``expected``, for a bespoke assertion a pinned
      number handles badly (a relationship, ``is None``, a formula). Without a
      decorator a method runs against every cell; ``@cells(topology=, state=)``
      scopes it to a subset.

    A class may use only maps, only methods, or both. This subsumes the earlier
    single-cell (one topology/state) and product (many) styles.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # The generated ``test_property`` only makes sense with @expect maps.
        # For a pure test-method scenario, hide it so pytest does not report an
        # empty-parameter-set skip.
        if not _collect(cls, "expect"):
            cls.test_property = None  # type: ignore[assignment]

    @classmethod
    def decl_cases(cls) -> list[_DeclCase]:
        specs = cls._expect_specs()
        cells = cls.scenario_cells()
        if not specs:
            return []  # pure test-method scenario: nothing for @expect to check
        topo_names = {c.topology.name for c in cells}
        state_names = {c.state.name for c in cells}
        for topo_s, state_s, _ in specs:  # catch a mistyped scope early
            if topo_s is not None and topo_s not in topo_names:
                raise ValueError(
                    f"@expect(topology={topo_s!r}) matches no topology; "
                    f"known: {sorted(topo_names)}"
                )
            if state_s is not None and state_s not in state_names:
                raise ValueError(
                    f"@expect(state={state_s!r}) matches no state; "
                    f"known: {sorted(state_names)}"
                )

        cases: list[_DeclCase] = []
        for cell in cells:
            matches = [
                (topo_s, state_s, m)
                for (topo_s, state_s, m) in specs
                if (topo_s is None or topo_s == cell.topology.name)
                and (state_s is None or state_s == cell.state.name)
            ]
            # Merge least-specific first; ties keep source order (stable sort).
            matches.sort(key=lambda t: (t[0] is not None) + (t[1] is not None))
            full: dict[str, Any] = {}
            for _, _, m in matches:
                full.update(m)
            full.update(cell.expected)  # @modify variant overrides win last
            # A cell may legitimately carry no @expect entries (checked by a
            # test_ method instead), so an empty map is not an error here.
            for prop, value in full.items():
                cases.append(_DeclCase(cell, prop, value))
        return cases

    def test_property(self, _decl_case: _DeclCase) -> None:
        pi = _decl_case.cell.build_engine()
        actual = getattr(pi, _decl_case.prop)
        assert actual == _approxify(_decl_case.expected), (
            f"{_decl_case.prop} on cell {_decl_case.cell.id!r}: "
            f"got {actual!r}, expected {_decl_case.expected!r}"
        )


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
    # The built-in EngineTestScenario.test_property is driven by _decl_case.
    if "_decl_case" in metafunc.fixturenames:
        cases = cls.decl_cases()
        metafunc.parametrize("_decl_case", cases, ids=[c.id for c in cases])
        return
    # A bespoke test_ method runs over the cells, optionally scoped by @cells.
    if "_scenario_cell" not in metafunc.fixturenames:
        return
    scenario_cells = cls.scenario_cells()
    scope = getattr(metafunc.function, "_cell_scope", None)
    if scope is not None:
        where = f"{cls.__name__}.{metafunc.function.__name__}"
        scenario_cells = _filter_cells_by_scope(scenario_cells, scope, where)
    metafunc.parametrize(
        "_scenario_cell", scenario_cells, ids=[c.id for c in scenario_cells]
    )
