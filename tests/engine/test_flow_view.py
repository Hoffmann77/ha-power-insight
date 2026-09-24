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

Four homes, one class each:

* :class:`TestEveryFlowRoleAtOnce` — group membership and disjointness.
* :class:`TestAnUnavailableInflowEmptiesTheShares` — the empty share vectors
  when an inflow sensor drops out.
* :class:`TestGrossPowerShares` — sources sum to 1, sinks need not (the
  remainder is the unmetered home load).
* :class:`TestZeroGrossPowerShares` — the zero-gross guard.
"""

from __future__ import annotations

import pytest

from tests.engine.home import Battery, Consumer, Grid, Home, Pv


def _uids(adapters):
    return {a.uid for a in adapters}


class TestEveryFlowRoleAtOnce(Home):
    """Every role at once, grid importing. Producing PV and a discharging
    battery are sources; standby PV, a charging battery and a load are sinks;
    an idle (0 W) consumer belongs to neither."""

    grid = Grid(500, price=0.30)
    pv1 = Pv(3000, exports=True)  # producing   -> source
    pv2 = Pv(-15)  # standby     -> sink
    bat1 = Battery(800)  # discharging -> source
    bat2 = Battery(-600)  # charging    -> sink
    cons1 = Consumer(-900)  # load        -> sink
    cons2 = Consumer(0)  # idle        -> neither

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


class TestAnUnavailableInflowEmptiesTheShares(Home):
    """pv2's sensor has dropped out, so the gross total is unreliable and the
    share vectors cannot be built: they collapse to empty. (That
    ``gross_power`` itself goes None is a published value, asserted by the
    pv-self-consumption reference case.)"""

    grid = Grid(500, price=0.30)
    pv1 = Pv(1000, exports=True)
    pv2 = Pv(None, exports=True)

    def test_source_shares_vector_is_empty(self, power_insight):
        arr, index = power_insight.source_adapters_gross_power_shares
        assert index == []
        assert arr == []


class TestGrossPowerShares(Home):
    """Sources sum to 1; sinks need not — the remainder is the unmetered home
    load. Grid 1000 W + pv1 1000 W make 2000 W gross, 0.5 each; the single
    500 W load meters 0.25 of it, and the other 0.75 is unmetered."""

    grid = Grid(1000, price=0.30)
    pv1 = Pv(1000, exports=True)
    cons1 = Consumer(-500)

    def test_source_shares_sum_to_one(self, power_insight):
        arr, index = power_insight.source_adapters_gross_power_shares
        assert index == ["grid", "pv1"]
        assert arr == pytest.approx([0.5, 0.5])
        assert sum(arr) == pytest.approx(1.0)

    def test_sink_shares_need_not_sum_to_one(self, power_insight):
        arr, index = power_insight.sink_adapters_gross_power_shares
        assert index == ["cons1"]
        assert arr == pytest.approx([0.25])  # remainder is home load


class TestZeroGrossPowerShares(Home):
    """Pure export: the grid exports 500 W while pv1 is idle, so no source
    provides and gross power is 0. The share properties must guard the
    division rather than raise, and the exporting grid's sink share collapses
    to 0."""

    grid = Grid(-500, price=0.30)
    pv1 = Pv(0, exports=True)

    def test_zero_gross_sink_share_guards_to_zero(self, power_insight):
        arr, index = power_insight.sink_adapters_gross_power_shares
        assert index == ["grid"]
        assert arr == pytest.approx([0.0])  # guarded, not a ZeroDivision

    def test_zero_gross_source_shares_empty(self, power_insight):
        arr, index = power_insight.source_adapters_gross_power_shares
        assert index == []
        assert arr == []
