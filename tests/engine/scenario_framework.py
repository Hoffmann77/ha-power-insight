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
(and can also take ``state`` / ``topology`` for the raw block objects).

The hand-derived decision harnesses in ``tests/engine/manual/`` do not use the
source-order binding: each is one declarative home, see ``tests/engine/home.py``.

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
* :func:`matches` — the one comparator the whole tier comes down to. Maps
  compare key set first at every level; ``None`` matches only ``None``, never a
  zero.
* :func:`scenario_blocks` — reads a scenario class back out as its
  ``(topology, state)`` blocks, using the same source-order rules
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
    lineno = test_fn.__code__.co_firstlineno
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
# A scenario class already says everything about a snapshot: the wiring and
# the readings. ``scenario_blocks`` walks that structure with the *same*
# source-order rules the tests bind by, so anything generated from a scenario
# (the published reference cases, say) reads the snapshots exactly as the
# tests bind them. Nothing here builds or touches an engine.


@dataclass(frozen=True)
class Block:
    """One ``@topology`` + ``@state`` pair."""

    topology: Topology
    state: State

    @property
    def cell(self) -> Cell:
        return Cell(self.topology, self.state)


def scenario_blocks(cls: type) -> list[Block]:
    """Every ``(topology, state)`` block of a scenario class.

    One block per ``@state``, in source order, each carrying the ``@topology``
    above it — by exactly the rule :func:`bind_cell` uses, so a block here is
    the same snapshot the corresponding tests run against.
    """
    inst = cls()
    topo_methods = _role_methods(cls, "topology")
    blocks = []
    for lineno, state_name, state_fn in _role_methods(cls, "state"):
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
        blocks.append(Block(topo, st))
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
