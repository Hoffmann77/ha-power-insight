"""Power-flow decisions, each pinned by a hand-derived harness.

Every block in :class:`TestPowerFlow` pins exactly one decision the engine
makes about *where power goes* — one ``@topology``, one ``@state``, and the
``@expect_attribute`` claims that only hold if the decision is honoured. The
values are derived by hand from the decision, never read back from the
engine. Each block's ``@state`` docstring names its decision and the note in
``docs/dev/engine-calculations.md`` that states it, so a red test here reads as
"this decision no longer holds", not as "some number moved".

Add a block whenever a new decision is made about power flow, as the smallest
wiring that can tell the decision apart from its alternatives.
"""

from __future__ import annotations

from fractions import Fraction as F

from tests.engine.scenario_framework import (
    Adapter,
    EngineScenario,
    State,
    expect_attribute,
    state,
    topology,
)


def rows(watts: dict[str, dict[str, int]]) -> dict[str, dict[str, F]]:
    """A ``{sink: {source: watts}}`` table as the provenance rows it implies.

    Lets a block state its answer as the watts that flow — the form it is
    derived in — while the engine publishes each sink's row as shares.
    """
    return {
        sink: {source: F(w, sum(row.values())) for source, w in row.items()}
        for sink, row in watts.items()
    }


class TestPowerFlow(EngineScenario):
    """Where each sink's power comes from."""

    # ----------------------------------------------------------------------
    # Decision: what every valid allocation carries is never scaled away.

    @topology
    def plug_on_either_of_two_pv_systems(self):
        return (
            Adapter.grid(),
            Adapter.pv("east", exports=True),
            Adapter.pv("west", exports=True),
            Adapter.pv("carport", exports=True),
            Adapter.consumer("plug", power_from=("east", "west")),
        )

    @state
    def every_watt_spoken_for(self):
        """Decision: what every valid allocation carries is never scaled away
        (engine-calculations.md).

        The plug may use east or west, and needs neither in particular, so
        nothing is reserved for it on either. The carport may only feed the
        export, so all 200 W of it is the export's reserve. The export is
        offered more than its 1800 W and its offers are scaled down — but never
        below that 200 W, or the carport's leftover would be forced onto the
        plug, which may not use it.
        """
        return State(grid=-1800, east=1000, west=1000, carport=200, plug=-400)

    @expect_attribute("sink_adapters_source_shares")
    def test_every_watt_spoken_for_power_flow(self):
        """The carport's 200 W all goes to the export, which takes the other
        1600 W half from east and half from west; the plug takes its 400 W
        half from each of the two it may use."""
        return rows({
            "grid": {"east": 800, "west": 800, "carport": 200},
            "plug": {"east": 200, "west": 200, "carport": 0},
        })

    @expect_attribute("sink_adapters_restriction_deficit")
    def test_every_watt_spoken_for_restriction_deficit(self):
        """Every restriction can be honoured, so none is reported broken."""
        return {}
