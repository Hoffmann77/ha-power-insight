"""Flow-view scenarios: the dynamic source/sink partition and its share vectors.

The engine classifies every adapter each snapshot by its signed power
(:class:`FlowRole`) and groups them into ``source_adapters`` / ``sink_adapters``
(grid folded in direction-aware) plus the behind-the-meter ``local_*`` subsets.
``source_/sink_adapters_gross_power_shares`` express each adapter as a fraction
of gross power. These underpin the source-share attribution, so they get pinned
down on their own.

Everything here is deliberately *not* a published value, which is why it lives
outside ``reference/`` rather than in it. The grouping properties return adapter
objects and the share properties return a ``(vector, uid index)`` pair — neither
is a shape ``docs/spec/properties.json`` can catalogue or a sensor can render,
so there is no property name to state these under and no reference case that
could assert them. What *is* a published value is asserted only by the corpus:
that ``gross_power`` totals its sources, goes ``None`` when an inflow meter
drops out, and reads 0 under pure export are the reference cases' to make, and
this file no longer repeats them.

Two aspects, one class each:

* :class:`TestFlowPartition` — group membership and disjointness, and the empty
  share vectors when an inflow sensor drops out.
* :class:`TestGrossPowerShares` — the share vectors: sources sum to 1, sinks need
  not (the remainder is the unmetered home load), and the zero-gross guard.

Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery ``+``
produce/discharge / ``-`` standby/charge; consumer ``-`` = load.
"""

from __future__ import annotations

import pytest

from tests.engine.scenario_framework import (
    Adapter,
    EngineScenario,
    State,
    state,
    topology,
)


def _uids(adapters):
    return {a.uid for a in adapters}


class TestFlowPartition(EngineScenario):
    """Which adapters land in source / sink / grid, and gross-power totalling."""

    # -----------------------------------------------------------------------
    # Block 1 — every role at once (grid importing). Producing PV and a
    # discharging battery are sources; standby PV, a charging battery and a load
    # are sinks; an idle (0 W) consumer belongs to neither.
    # -----------------------------------------------------------------------

    @topology
    def all_roles(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),  # producing -> source
            Adapter.pv("pv2"),  # standby   -> sink
            Adapter.battery("bat1"),  # discharging -> source
            Adapter.battery("bat2"),  # charging  -> sink
            Adapter.consumer("cons1"),  # load      -> sink
            Adapter.consumer("cons2"),  # idle      -> neither
        )

    @state
    def midday_mixed(self):
        return State(
            grid=500,
            pv1=3000,
            pv2=-15,
            bat1=800,
            bat2=-600,
            cons1=-900,
            cons2=0,
            price=0.30,
        )

    def test_sources_include_importing_grid(self, power_insight):
        # source_adapters is grid-inclusive: the grid joins while importing.
        assert _uids(power_insight.source_adapters) == {"grid", "pv1", "bat1"}

    def test_local_sources_exclude_grid(self, power_insight):
        assert _uids(power_insight.local_source_adapters) == {"pv1", "bat1"}

    def test_sinks_are_standby_charging_and_load(self, power_insight):
        assert _uids(power_insight.sink_adapters) == {"pv2", "bat2", "cons1"}

    def test_grid_stays_in_its_own_group(self, power_insight):
        assert _uids(power_insight.grid_adapters) == {"grid"}

    def test_source_and_sink_groups_are_disjoint(self, power_insight):
        assert not (
            _uids(power_insight.source_adapters) & _uids(power_insight.sink_adapters)
        )

    def test_idle_adapter_is_in_no_flow_group(self, power_insight):
        grouped = _uids(power_insight.source_adapters) | _uids(
            power_insight.sink_adapters
        )
        assert "cons2" not in grouped

    # -----------------------------------------------------------------------
    # Block 2 — an inflow sensor is unavailable, so the share vectors cannot be
    # built and collapse to empty. (That ``gross_power`` itself goes None is a
    # published value, asserted by the pv-self-consumption reference case.)
    # -----------------------------------------------------------------------

    @topology
    def grid_and_two_pv(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.pv("pv2", exports=True),
        )

    @state
    def one_pv_unavailable(self):
        # pv2's sensor has dropped out (None) -> the gross total is unreliable.
        return State(grid=500, pv1=1000, pv2=None, price=0.30)

    def test_source_shares_vector_is_empty(self, power_insight):
        arr, index = power_insight.source_adapters_gross_power_shares
        assert index == []
        assert arr == []


class TestGrossPowerShares(EngineScenario):
    """The gross-power share vectors and their guards."""

    # -----------------------------------------------------------------------
    # Block 1 — sources sum to 1; sinks need not (the remainder is the
    # unmetered home load).
    # -----------------------------------------------------------------------

    @topology
    def grid_pv_consumer(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.consumer("cons1"),
        )

    @state
    def half_and_half(self):
        # Sources: grid 1000 W + pv1 1000 W -> gross 2000 W (each 0.5). A single
        # 500 W load meters 0.25 of gross; the other 0.75 is unmetered.
        return State(grid=1000, pv1=1000, cons1=-500, price=0.30)

    def test_source_shares_sum_to_one(self, power_insight):
        arr, index = power_insight.source_adapters_gross_power_shares
        assert index == ["grid", "pv1"]
        assert arr == pytest.approx([0.5, 0.5])
        assert sum(arr) == pytest.approx(1.0)

    def test_sink_shares_need_not_sum_to_one(self, power_insight):
        arr, index = power_insight.sink_adapters_gross_power_shares
        assert index == ["cons1"]
        assert arr == pytest.approx([0.25])  # remainder is home load

    # -----------------------------------------------------------------------
    # Block 2 — pure export: no source provides, so gross power is 0. The share
    # properties must guard the division rather than raise, and the exporting
    # grid's sink share collapses to 0.
    # -----------------------------------------------------------------------

    @topology
    def grid_and_pv(self):
        return (Adapter.grid(), Adapter.pv("pv1", exports=True))

    @state
    def export_with_idle_pv(self):
        # Grid exports 500 W while pv1 is idle: no source, gross 0 W, one sink.
        return State(grid=-500, pv1=0, price=0.30)

    def test_zero_gross_sink_share_guards_to_zero(self, power_insight):
        arr, index = power_insight.sink_adapters_gross_power_shares
        assert index == ["grid"]
        assert arr == pytest.approx([0.0])  # guarded, not a ZeroDivision

    def test_zero_gross_source_shares_empty(self, power_insight):
        arr, index = power_insight.source_adapters_gross_power_shares
        assert index == []
        assert arr == []
