"""Source-order scenario framework for ``PowerInsight`` engine tests.

This is the single testing framework for the pure-Python engine. A scenario is a
class that subclasses :class:`EngineScenario` and concentrates on *one* aspect of
the engine (source shares, the flow-view partition, a rate family, ...). Inside
it, methods appear in repeating **blocks**::

    @topology
    def some_wiring(self): ...        # which adapters exist + their static config

    @state
    def some_readings(self): ...      # the power/price readings for that wiring

    def test_foo(self, power_insight): ...   # binds to the block above
    def test_bar(self, power_insight): ...

    # -------------------------------------------------------------------
    #   next block

    @topology
    def other_wiring(self): ...
    @state
    def other_readings(self): ...
    def test_baz(self, power_insight): ...

Binding is by **source order**: each ``test_`` method runs against the
``@topology`` and ``@state`` declared closest above it (found via each method's
line number, ``__code__.co_firstlineno``). A block therefore reads top to bottom
as *wiring → readings → the assertions about them*; a comment line makes a handy
separator between blocks. Reusing a topology across two reading sets is just two
``@state``/``test_`` runs under one ``@topology``::

    @topology
    def wiring(self): ...

    @state
    def readings_a(self): ...
    def test_a(self, power_insight): ...

    @state
    def readings_b(self): ...        # same wiring, new readings
    def test_b(self, power_insight): ...

Each test receives a freshly built engine through the ``power_insight`` fixture
(and can also take ``state`` / ``topology`` for the raw block objects). Assertions
are hand-written expected values — derived from first principles, not read back
from the engine, so a regression flips the test red.

Approximation: tests compare with ``pytest.approx``. Exact expectations (``0.5``,
``2/3``, ``0.625``) use the default tolerance (relative ``1e-6``); shares/ratios
that need a rounded literal are compared to three decimal places
(``abs=1e-3``) — enough to catch any real regression while keeping the expected
value readable. Write a value as an exact fraction when you want it pinned
tighter than three decimals. See ``docs/dev/engine-calculations.md``.

Authoring surface
-----------------

* :func:`topology` — decorate a method returning a :class:`Topology` (or just a
  tuple of :class:`Adapter`, wrapped automatically). Exactly one grid.
* :func:`state` — decorate a method returning a :class:`State`: the ``uid ->
  power`` readings (watts) plus the grid ``price``. ``None`` power models an
  unavailable sensor.
* :class:`Adapter` — one adapter's kind + static config, via the ``grid`` /
  ``pv`` / ``battery`` / ``consumer`` factories. Config lives inline at the call
  site so an expected value that hinges on (say) ``export_comp`` is documented
  where it is used.
* :func:`expect_attribute` — an optional decorator for the common shape where a
  test just compares one engine attribute to a hand-written expected value.
  Instead of taking ``power_insight`` and asserting, the method takes only
  ``self`` and *returns* the expected value; ``@expect_attribute("<attribute>")``
  names the property to read back and compare against it. A plain
  ``def test_x(self, power_insight)`` still works for anything that needs finer
  control.

Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery ``+``
produce/discharge / ``-`` standby/charge; consumer ``-`` = load.

Safety rail: a ``@state`` must supply a reading for *exactly* the adapter uids of
the ``@topology`` it binds to — no more, no less. A mismatch raises ``ValueError``
at collection instead of silently defaulting a missing adapter to zero.

Wiring: ``tests/engine/conftest.py`` calls :func:`generate_scenario_tests` from
``pytest_generate_tests`` and defines the ``power_insight`` / ``state`` /
``topology`` fixtures each test is threaded through.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
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
FlowRole = _mod.FlowRole

GRID_PRICE_ENTITY = "sensor.grid_price"


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
    #: The adapter's unique id — exactly the key used in State(...), charge_from,
    #: power_from and expected-dict keys. The grid is always ``"grid"``.
    uid: str
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
    ) -> "Adapter":
        return cls(
            "grid", "grid", {"name": name}, inverted=inverted, has_price=has_price_entity
        )

    @classmethod
    def pv(
        cls,
        uid: str,
        *,
        lcoe: float | None = 0.10,
        lco2_intensity: float | None = 50.0,
        exports: bool = False,
        export_comp: float = 0.0,
        correction_factor: float = 1.0,
        inverted: bool = False,
        name: str | None = None,
    ) -> "Adapter":
        return cls(
            "pv",
            uid,
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
        uid: str,
        *,
        lcos: float | None = 0.15,
        lco2_intensity: float | None = 100.0,
        exports: bool = False,
        export_comp: float = 0.0,
        charge_from: tuple[str, ...] = (),
        inverted: bool = False,
        name: str | None = None,
    ) -> "Adapter":
        return cls(
            "battery",
            uid,
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
        uid: str,
        *,
        power_from: tuple[str, ...] = (),
        inverted: bool = False,
        name: str | None = None,
    ) -> "Adapter":
        return cls(
            "consumer",
            uid,
            {"name": name, "power_from_adapters": tuple(power_from)},
            inverted=inverted,
        )

    # -- derived ----------------------------------------------------------

    @property
    def power_entity(self) -> str:
        return f"sensor.{self.uid}_power"

    @property
    def power_source_uids(self) -> tuple[str, ...]:
        """The uids this adapter restricts its intake to (battery / consumer)."""
        if self.kind == "battery":
            return tuple(self.config["charge_from_adapters"])
        if self.kind == "consumer":
            return tuple(self.config["power_from_adapters"])
        return ()

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
                power_from_adapters=list(cfg["power_from_adapters"]),
            )
        raise ValueError(f"unknown adapter kind {self.kind!r}")


# ---------------------------------------------------------------------------
# Topology + State
# ---------------------------------------------------------------------------


@dataclass
class Topology:
    """One device: exactly one grid plus any PV / battery / consumer adapters.

    Validated at construction: exactly one grid, unique uids, and every battery
    ``charge_from`` / consumer ``power_from`` target present.
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
            for src in a.power_source_uids:
                if src not in known:
                    field = "charge_from" if a.kind == "battery" else "power_from"
                    raise ValueError(
                        f"{a.kind} {a.uid!r} {field} references unknown adapter "
                        f"{src!r}; known: {sorted(known)}"
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
        # Let formula-style tests write ``state.pv1`` for a reading.
        try:
            return self.readings[item]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(item) from exc


# ---------------------------------------------------------------------------
# Cell — one bound (topology, state) pair, ready to build an engine.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    topology: Topology
    state: State

    @property
    def id(self) -> str:
        parts = [self.topology.name, self.state.name]
        return "-".join(p for p in parts if p) or "cell"

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
# @topology / @state decorators + source-order binding.
# ---------------------------------------------------------------------------


def topology(fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Mark a method as supplying a block's topology.

    The method may return a :class:`Topology`, or just a tuple/list of
    :class:`Adapter` (wrapped into a ``Topology`` automatically).
    """
    fn._scenario_role = "topology"  # type: ignore[attr-defined]
    return fn


def state(fn: Callable[[Any], State]) -> Callable[[Any], State]:
    """Mark a method as returning a :class:`State` for the block."""
    fn._scenario_role = "state"  # type: ignore[attr-defined]
    return fn


def _assert_attribute_matches(actual: Any, expected: Any, *, abs_tol: float | None) -> None:
    """Assert ``actual`` (an engine attribute value) equals the ``expected`` map.

    A nested ``{row: {col: value}}`` mapping (e.g. ``sink_adapters_source_shares``)
    is compared row by row: the row set and every row's column set must match
    exactly, so a leaked or missing key fails loudly, while the values compare
    within ``abs_tol``. Anything else (a flat mapping, a sequence, a scalar) is
    compared in one go. ``abs_tol=None`` falls back to ``pytest.approx``'s default
    relative tolerance — use it for expectations written as exact fractions.
    """
    is_nested = (
        isinstance(expected, dict)
        and bool(expected)
        and all(isinstance(v, dict) for v in expected.values())
    )
    if is_nested:
        assert actual.keys() == expected.keys()
        for key, row in expected.items():
            assert actual[key] == pytest.approx(row, abs=abs_tol)
    else:
        assert actual == pytest.approx(expected, abs=abs_tol)


def expect_attribute(
    attribute: str, *, abs_tol: float | None = None
) -> Callable[[Callable], Callable]:
    """Turn a method that *returns* an expected value into a bound scenario test.

    The decorated method takes only ``self`` and returns the value
    ``power_insight.<attribute>`` should have for the block it binds to (source
    order, like any ``test_`` method). The engine's actual attribute is then
    compared against the returned value by :func:`_assert_attribute_matches`, so
    the body reads as *"``<attribute>`` should be this"* with no assertion
    boilerplate::

        @expect_attribute("sink_adapters_source_shares")
        def test_export_sourced_from_pv_mix(self):
            return {"grid": {"pv1": 2 / 3, "pv2": 1 / 3}, ...}

    Named ``expect_*`` rather than ``test_*`` on purpose: pytest would otherwise
    collect the decorator itself as a test.

    ``abs_tol`` sets the per-value absolute tolerance for the comparison (pass it
    when the expected map lists rounded literals); the default keeps
    ``pytest.approx``'s relative tolerance for expectations pinned as exact
    fractions.
    """

    def decorator(fn: Callable) -> Callable:
        def wrapper(self: Any, power_insight: Any) -> None:
            expected = fn(self)
            actual = getattr(power_insight, attribute)
            _assert_attribute_matches(actual, expected, abs_tol=abs_tol)

        # Copy identity for pytest's node id / docstring display, but do NOT set
        # ``__wrapped__`` — that would make ``inspect.signature`` follow through
        # to ``fn`` and hide the ``power_insight`` parameter pytest must inject.
        wrapper.__name__ = fn.__name__
        wrapper.__qualname__ = fn.__qualname__
        wrapper.__doc__ = fn.__doc__
        wrapper.__module__ = fn.__module__
        # The original method, so source-order binding reads its line number
        # rather than this wrapper's (see ``bind_cell``).
        wrapper._scenario_test_fn = fn  # type: ignore[attr-defined]
        wrapper._scenario_attribute = attribute  # type: ignore[attr-defined]
        return wrapper

    return decorator


def _role_methods(cls: type, role: str) -> list[tuple[int, str, Callable]]:
    """Return ``(lineno, name, fn)`` for this class's own methods of ``role``.

    Only the class body is inspected (``vars(cls)``), so blocks are scoped to the
    scenario that declares them; line numbers from another class/file are never
    compared. Sorted by source line.
    """
    found = []
    for name, obj in vars(cls).items():
        if callable(obj) and getattr(obj, "_scenario_role", None) == role:
            found.append((obj.__code__.co_firstlineno, name, obj))
    found.sort()
    return found


def _nearest_above(
    methods: list[tuple[int, str, Callable]], lineno: int, *, role: str, where: str
) -> tuple[str, Callable]:
    """Return the ``(name, fn)`` of the ``role`` method closest above ``lineno``."""
    candidates = [(ln, name, fn) for (ln, name, fn) in methods if ln < lineno]
    if not candidates:
        raise ValueError(
            f"{where}: no @{role} declared above it. Each test binds to the "
            f"@topology and @state above it — declare the block's @{role} first."
        )
    _, name, fn = max(candidates, key=lambda t: t[0])
    return name, fn


def bind_cell(cls: type, test_fn: Callable) -> Cell:
    """Bind a scenario ``test_`` method to its nearest topology + state block."""
    # A @test-decorated method is a wrapper; bind on the original method's line
    # number so the block layout is read from where the author wrote it.
    original = getattr(test_fn, "_scenario_test_fn", test_fn)
    lineno = original.__code__.co_firstlineno
    where = f"{cls.__name__}.{test_fn.__name__}"

    topo_name, topo_fn = _nearest_above(
        _role_methods(cls, "topology"), lineno, role="topology", where=where
    )
    state_name, state_fn = _nearest_above(
        _role_methods(cls, "state"), lineno, role="state", where=where
    )

    inst = cls()
    result = topo_fn(inst)
    topo = result if isinstance(result, Topology) else Topology(*result)
    topo.name = topo_name

    st = state_fn(inst)
    object.__setattr__(st, "name", state_name)

    _check_compatible(topo, st)
    return Cell(topo, st)


# ---------------------------------------------------------------------------
# Base class.
# ---------------------------------------------------------------------------


class EngineScenario:
    """Base for a scenario class concentrating on one engine aspect.

    Subclass it, then in source order declare repeating blocks of ``@topology``,
    ``@state`` and ``test_`` methods (see the module docstring). Each test binds
    to the block above it and receives a freshly built engine via the
    ``power_insight`` fixture.
    """


# ---------------------------------------------------------------------------
# pytest wiring — called from tests/engine/conftest.py.
# ---------------------------------------------------------------------------


def generate_scenario_tests(metafunc: Any) -> None:
    """Bind a scenario ``test_`` method to its (topology, state) block.

    Call from ``pytest_generate_tests``. No-op for non-scenario classes and for
    tests that request none of the block fixtures.
    """
    cls = getattr(metafunc, "cls", None)
    if cls is None or not (isinstance(cls, type) and issubclass(cls, EngineScenario)):
        return
    if "_scenario_cell" not in metafunc.fixturenames:
        return
    cell = bind_cell(cls, metafunc.function)
    # A single param per test: it binds to exactly one block. The id makes the
    # bound block visible in the test node (``test_x[topology-state]``).
    metafunc.parametrize("_scenario_cell", [cell], ids=[cell.id])
