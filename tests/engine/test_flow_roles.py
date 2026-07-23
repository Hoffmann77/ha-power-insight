"""Tests for the flow-view scaffolding (FlowRole + source/sink/grid groups).

These pin down the *base structure* of the dynamic flow concept: an adapter's
per-snapshot ``flow_role`` and the engine's ``source_adapters`` /
``sink_adapters`` / ``grid_adapters`` groupings. Nothing in the engine consumes
these yet — they are additive scaffolding — so the tests only assert the
classification and membership rules, not any downstream result.

Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery ``+``
produce/discharge / ``-`` standby/charge; consumer ``-`` = load.
"""

from __future__ import annotations

import pytest

from tests.engine.engine_property_framework import (
    Device,
    EngineScenario,
    FlowRole,
    build_engine,
)


def _uids(adapters):
    """Return the set of uids for a list of adapters (order-independent)."""
    return {adapter.uid for adapter in adapters}


# ---------------------------------------------------------------------------
# flow_role classification, per adapter kind
# ---------------------------------------------------------------------------


class TestFlowRoleClassification:
    """Each adapter kind maps its signed power to the right FlowRole."""

    @pytest.mark.parametrize(
        ("preset", "power", "expected"),
        [
            # Grid: + import -> source, - export -> sink.
            ("grid", 1000, FlowRole.SOURCE),
            ("grid", -1000, FlowRole.SINK),
            ("grid", 0, FlowRole.IDLE),
            ("grid", None, FlowRole.UNKNOWN),
            # PV: + produce -> source, - standby -> sink.
            ("pv_with_export", 3000, FlowRole.SOURCE),
            ("pv_with_export", -20, FlowRole.SINK),
            ("pv_with_export", 0, FlowRole.IDLE),
            ("pv_with_export", None, FlowRole.UNKNOWN),
            # Battery: + discharge -> source, - charge -> sink.
            ("battery", 800, FlowRole.SOURCE),
            ("battery", -800, FlowRole.SINK),
            ("battery", 0, FlowRole.IDLE),
            ("battery", None, FlowRole.UNKNOWN),
            # Consumer: - load -> sink; a positive reading can never be a
            # source, so it is reported IDLE.
            ("consumer", -500, FlowRole.SINK),
            ("consumer", 500, FlowRole.IDLE),
            ("consumer", 0, FlowRole.IDLE),
            ("consumer", None, FlowRole.UNKNOWN),
        ],
    )
    def test_flow_role(self, preset, power, expected):
        # Every scenario needs exactly one grid. When the adapter under test is
        # itself the grid, that single grid carries the reading; otherwise a
        # neutral (unavailable) grid is added alongside.
        if preset == "grid":
            engine = build_engine([Device("grid", power=power)])
            adapter = engine.grid_adapter
        else:
            engine = build_engine(
                [Device("grid", power=None), Device(preset, 1, power=power)]
            )
            adapter = engine._non_grid_adapters[0]

        assert adapter.flow_role is expected

    def test_inverted_power_flips_role(self):
        """The inversion flag is applied before classification."""
        # power=600 with inverted=True is 600 W export -> sink.
        engine = build_engine([Device("grid", power=600, inverted=True)])
        assert engine.grid_adapter.flow_role is FlowRole.SINK


# ---------------------------------------------------------------------------
# Group membership across a mixed device
# ---------------------------------------------------------------------------


class TestMixedFlowGroups(EngineScenario):
    """A device exercising every role at once.

    * pv1  producing        -> source
    * pv2  standby (drawing) -> sink
    * bat1 discharging       -> source
    * bat2 charging          -> sink
    * cons1 load             -> sink
    * cons2 idle (0 W)       -> neither
    * pv3  unavailable       -> neither
    """

    DEVICES = [
        Device("grid", power=500, price=0.30),
        Device("pv_with_export", 1, power=3000),
        Device("pv_no_export", 2, power=-15),
        Device("battery", 1, power=800),
        Device("battery", 2, power=-600),
        Device("consumer", 1, power=-900),
        Device("consumer", 2, power=0),
        Device("pv_no_export", 3, power=None),
    ]

    def test_source_adapters(self, power_insight):
        assert _uids(power_insight.source_adapters) == {"pv1", "bat1"}

    def test_sink_adapters(self, power_insight):
        assert _uids(power_insight.sink_adapters) == {"pv2", "bat2", "cons1"}

    def test_grid_adapters(self, power_insight):
        assert _uids(power_insight.grid_adapters) == {"grid"}

    def test_grid_excluded_from_flow_groups(self, power_insight):
        """The grid is never placed in source/sink, only in its own group."""
        assert "grid" not in _uids(power_insight.source_adapters)
        assert "grid" not in _uids(power_insight.sink_adapters)

    def test_idle_and_unknown_in_neither_group(self, power_insight):
        """Idle (0 W) and unavailable adapters drop out of both flow groups."""
        grouped = _uids(power_insight.source_adapters) | _uids(
            power_insight.sink_adapters
        )
        assert "cons2" not in grouped  # idle
        assert "pv3" not in grouped     # unavailable

    def test_inflow_adapters_includes_importing_grid(self, power_insight):
        """Grid imports here (+500 W), so it joins the inflow side."""
        assert _uids(power_insight.inflow_adapters) == {"grid", "pv1", "bat1"}

    def test_outflow_adapters_excludes_importing_grid(self, power_insight):
        """An importing grid is not on the outflow side."""
        assert _uids(power_insight.outflow_adapters) == {"pv2", "bat2", "cons1"}

    def test_inflow_outflow_disjoint(self, power_insight):
        """Direction-aware folding keeps the two grid-inclusive groups disjoint."""
        assert not (
            _uids(power_insight.inflow_adapters)
            & _uids(power_insight.outflow_adapters)
        )


# ---------------------------------------------------------------------------
# The grid stays in its own group regardless of direction
# ---------------------------------------------------------------------------


class TestGridExportingStillOwnGroup(EngineScenario):
    """An exporting grid is a sink by role but still lives in grid_adapters."""

    DEVICES = [
        Device("grid", power=-1200, price=0.30),
        Device("pv_with_export", 1, power=4000),
    ]

    def test_grid_role_is_sink(self, power_insight):
        assert power_insight.grid_adapter.flow_role is FlowRole.SINK

    def test_grid_group_membership(self, power_insight):
        assert _uids(power_insight.grid_adapters) == {"grid"}

    def test_grid_not_in_sink_adapters(self, power_insight):
        assert "grid" not in _uids(power_insight.sink_adapters)

    def test_outflow_adapters_includes_exporting_grid(self, power_insight):
        """Grid exports here (-1200 W), so it joins the outflow side."""
        assert _uids(power_insight.outflow_adapters) == {"grid"}

    def test_inflow_adapters_excludes_exporting_grid(self, power_insight):
        """An exporting grid is not on the inflow side; only pv1 sources here."""
        assert _uids(power_insight.inflow_adapters) == {"pv1"}
