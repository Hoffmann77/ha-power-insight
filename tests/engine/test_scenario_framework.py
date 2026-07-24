"""Self-tests for the scenario framework's validation and source-order binding.

These guard the machinery the scenarios rely on: topology validation, the
state/topology compatibility rail, and the rule that a ``test_`` method binds to
the ``@topology`` / ``@state`` declared above it.
"""

from __future__ import annotations

import pytest

from tests.engine.scenario_framework import (
    Adapter,
    EngineScenario,
    State,
    Topology,
    bind_cell,
    state,
    topology,
)


# ---------------------------------------------------------------------------
# Topology validation.
# ---------------------------------------------------------------------------


def test_topology_requires_exactly_one_grid():
    with pytest.raises(ValueError, match="exactly one grid"):
        Topology(Adapter.pv("pv1"))


def test_topology_rejects_two_grids():
    with pytest.raises(ValueError, match="exactly one grid"):
        Topology(Adapter.grid(), Adapter.grid())


def test_topology_rejects_duplicate_uid():
    with pytest.raises(ValueError, match="duplicate adapter uid"):
        Topology(Adapter.grid(), Adapter.pv("pv1"), Adapter.pv("pv1"))


def test_topology_rejects_unknown_charge_from():
    with pytest.raises(ValueError, match="charge_from references unknown"):
        Topology(Adapter.grid(), Adapter.battery("bat1", charge_from=("pv9",)))


def test_topology_rejects_unknown_power_from():
    with pytest.raises(ValueError, match="power_from references unknown"):
        Topology(Adapter.grid(), Adapter.consumer("cons1", power_from=("pv9",)))


# ---------------------------------------------------------------------------
# State / topology compatibility rail (enforced when a test binds its block).
# ---------------------------------------------------------------------------


class _Incompatible(EngineScenario):
    @topology
    def wiring(self):
        return (Adapter.grid(), Adapter.pv("pv1"))

    @state
    def missing_pv(self):
        return State(grid=100)  # no pv1 reading

    def test_bind(self, power_insight):  # pragma: no cover - binding raises first
        pass


def test_state_must_match_topology_uids():
    fn = _Incompatible.__dict__["test_bind"]
    with pytest.raises(ValueError, match="missing readings"):
        bind_cell(_Incompatible, fn)


# ---------------------------------------------------------------------------
# Source-order binding: a test picks the nearest topology/state above it.
# ---------------------------------------------------------------------------


class _TwoBlocks(EngineScenario):
    @topology
    def first(self):
        return (Adapter.grid(), Adapter.pv("pv1"))

    @state
    def first_readings(self):
        return State(grid=100, pv1=200)

    def test_in_first_block(self, power_insight):
        pass

    @topology
    def second(self):
        return (Adapter.grid(), Adapter.battery("bat1"))

    @state
    def second_readings(self):
        return State(grid=100, bat1=-200)

    def test_in_second_block(self, power_insight):
        pass


def test_binding_follows_source_order():
    first = bind_cell(_TwoBlocks, _TwoBlocks.__dict__["test_in_first_block"])
    assert first.id == "first-first_readings"
    assert first.topology.uids == {"grid", "pv1"}

    second = bind_cell(_TwoBlocks, _TwoBlocks.__dict__["test_in_second_block"])
    assert second.id == "second-second_readings"
    assert second.topology.uids == {"grid", "bat1"}


class _NoBlockAbove(EngineScenario):
    def test_orphan(self, power_insight):
        pass

    @topology
    def wiring(self):
        return (Adapter.grid(),)

    @state
    def readings(self):
        return State(grid=100)


def test_test_before_any_block_is_an_error():
    fn = _NoBlockAbove.__dict__["test_orphan"]
    with pytest.raises(ValueError, match="no @topology declared above it"):
        bind_cell(_NoBlockAbove, fn)
