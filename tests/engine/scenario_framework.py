"""Source-order scenario framework for ``PowerInsight`` engine tests.

The plain data it works with — :class:`Adapter`, :class:`Topology`,
:class:`State`, :class:`Cell` — and the :func:`matches` comparator live in
``tests/engine/home.py``, beside the declarative homes, and are re-exported
here. A scenario is a class that subclasses :class:`EngineScenario` and concentrates on *one* aspect of
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
* :func:`matches` — the one comparator the whole tier comes down to. Maps
  compare key set first at every level; ``None`` matches only ``None``, never a
  zero.
* :func:`scenario_blocks` — reads a scenario class back out as its
  ``(topology, state, expectations)`` blocks, using the same source-order rules
  the tests bind by, without running pytest or building an engine. This is how
  the reference cases in ``tests/engine/reference/`` read their wiring and
  snapshots out for the documentation site.

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

from dataclasses import dataclass
from typing import Any, Callable

from tests.engine.home import (  # noqa: F401 - re-exported for the scenarios
    Adapter,
    Cell,
    State,
    Topology,
    check_compatible,
    matches,
    show,
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



def _assert_attribute_matches(
    actual: Any,
    expected: Any,
    *,
    abs_tol: float | None,
    attribute: str = "",
    state: State | None = None,
) -> None:
    """Assert an engine attribute equals ``expected``.

    The failure names the snapshot as well as the two values. A wrong number
    on its own does not tell you which of the engine and the expectation to go
    and look at; the readings it came from usually do.
    """
    where = f"{attribute}\n" if attribute else ""
    readings = ""
    if state is not None:
        readings = (
            "  readings: "
            + ", ".join(f"{k}={show(v)}" for k, v in state.readings.items())
            + f", price={show(state.price)}\n"
        )
    assert matches(expected, actual, abs_tol=abs_tol), (
        f"\n{where}{readings}\n"
        f"  expected: {show(expected)}\n"
        f"  actual:   {show(actual)}\n"
    )


def expect_attribute(
    attribute: str,
    *,
    abs_tol: float | None = None,
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
        def wrapper(self: Any, power_insight: Any, state: State) -> None:
            expected = fn(self)
            actual = getattr(power_insight, attribute)
            _assert_attribute_matches(
                actual, expected, abs_tol=abs_tol, attribute=attribute, state=state
            )

        # Copy identity for pytest's node id / docstring display, but do NOT set
        # ``__wrapped__`` — that would make ``inspect.signature`` follow through
        # to ``fn`` and hide the ``power_insight`` / ``state`` parameters pytest
        # must inject.
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

    check_compatible(topo, st)
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
# Reading a scenario back out — the same binding, without running pytest.
# ---------------------------------------------------------------------------
#
# A scenario class already says everything about a snapshot: the wiring, the
# readings, and — through ``@expect_attribute`` — what each property should be.
# ``scenario_blocks`` walks that structure with the *same* source-order rules
# the tests bind by, so anything generated from a scenario (the published
# reference cases, say) reads the snapshots exactly as the tests bind them.
#
# Nothing here builds or touches an engine. Expected values come from calling
# the ``@expect_attribute`` methods, which take only ``self``.


@dataclass(frozen=True)
class Expectation:
    """One ``@expect_attribute`` method: the property, and the value it claims."""

    attribute: str
    value: Any
    method: str


@dataclass(frozen=True)
class Block:
    """One ``@topology`` + ``@state`` pair, and the expectations bound to it.

    ``expectations`` holds the value each ``@expect_attribute`` method claims.
    """

    topology: Topology
    state: State
    expectations: tuple[Expectation, ...] = ()

    @property
    def cell(self) -> Cell:
        return Cell(self.topology, self.state)


def _expect_methods(cls: type) -> list[tuple[int, str, Callable]]:
    """Every ``@expect_attribute`` method, by the line the author wrote it on."""
    found = []
    for name, obj in vars(cls).items():
        attribute = getattr(obj, "_scenario_attribute", None)
        if attribute is None:
            continue
        original = getattr(obj, "_scenario_test_fn", obj)
        found.append((original.__code__.co_firstlineno, name, obj))
    found.sort()
    return found


def scenario_blocks(cls: type) -> list[Block]:
    """Every ``(topology, state, expectations)`` block of a scenario class.

    One block per ``@state``, in source order, each carrying the ``@topology``
    above it and every ``@expect_attribute`` method that binds to it — by
    exactly the rule :func:`bind_cell` uses, so a block here is the same
    snapshot the corresponding tests run against.

    A ``@state`` with no ``@expect_attribute`` method under it still gets a
    block, with no expectations — the reference cases are made of nothing
    else.

    Plain ``test_`` methods are skipped: they assert something bespoke rather
    than claiming a value for a named property, so there is nothing to read
    out of them.
    """
    inst = cls()
    topo_methods = _role_methods(cls, "topology")
    state_methods = _role_methods(cls, "state")

    bound: dict[str, list[Expectation]] = {name: [] for _, name, _ in state_methods}
    for lineno, name, fn in _expect_methods(cls):
        where = f"{cls.__name__}.{name}"
        state_name, _ = _nearest_above(state_methods, lineno, role="state", where=where)
        # The undecorated method: it takes only ``self`` and returns the
        # expected value. The wrapper pytest calls wants an engine too, and
        # reading a scenario back out must never build one.
        derive = getattr(fn, "_scenario_test_fn", fn)
        value = derive(inst)
        bound[state_name].append(Expectation(fn._scenario_attribute, value, name))

    blocks = []
    for lineno, state_name, state_fn in state_methods:
        where = f"{cls.__name__}.{state_name}"
        topo_name, topo_fn = _nearest_above(
            topo_methods, lineno, role="topology", where=where
        )
        result = topo_fn(inst)
        topo = result if isinstance(result, Topology) else Topology(*result)
        topo.name = topo_name
        st = state_fn(inst)
        object.__setattr__(st, "name", state_name)
        check_compatible(topo, st)
        blocks.append(
            Block(topo, st, tuple(bound[state_name]))
        )
    return blocks


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
