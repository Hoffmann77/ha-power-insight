"""Demonstration of the ``@topology`` / ``@state`` scenario framework.

Every scenario subclasses :class:`EngineTestScenario` (the only base). Its cells
are the ``@topology`` × ``@state`` product (plus ``@modify`` variants), checked
by ``@expect`` data maps and/or ``test_`` methods. This one file shows the range:

* pinned single cell (one topology, one state, an ``@expect`` map);
* ``@modify`` variants (result-neutral, and result-changing via ``.expect``);
* a scoped product (``@expect(topology=, state=)``);
* laws as ``test_`` methods over the product (``@cells``-scoped or not).

Run just this file::

    uv run pytest tests/engine/test_scenario_prototype.py -v
"""

from __future__ import annotations

import pytest

from tests.engine.scenario_framework import (
    Adapter,
    EngineTestScenario,
    Modify,
    State,
    Topology,
    cells,
    expect,
    modify,
    state,
    topology,
)


# ===========================================================================
# Pinned single cell — one topology × one state, an @expect map.
# ===========================================================================


class TestSourcePowerShares(EngineTestScenario):
    """Grid + PV + a battery charging from both, gross 4000 W.

    Import 1000 W (gross share 0.25) and PV 3000 W (share 0.75) feed a 500 W
    charge, split 125 W / 375 W. Nested-dict expectations compare deeply and
    tolerantly.
    """

    @topology
    def (self):
        return (
            Adapter.grid(),
            Adapter.pv("pv_1", lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.pv("pv_2", lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.battery("bat_1", charge_from=("grid", "pv_1")),
            Adapter.battery("bat_2", charge_from=("grid", "pv_2")),
            Adapter.battery("bat_3", charge_from=("pv_1", "pv_2")),
            Adapter.consumer("cons_1", charge_from=("pv_1", "pv_2")),
        )

    # @state
    # def zero_import(self):
    #     return State(
    #         grid=400,
    #         pv_1=1000,
    #         pv_2=600,
    #         bat_1=-400,
    #         bat_2=-400,
    #         bat_3=-500,
    #         cons_1=-500,
    #         price=0.30,
    #     )

    # @state
    # def export(self):
    #     return State(
    #         grid=400,
    #         pv_1=1000,
    #         pv_2=600,
    #         bat_1=-400,
    #         bat_2=-400,
    #         bat_3=-500,
    #         cons_1=-500,
    #         price=0.30,
    #     )

    @state
    def charging_with_import(self):
        return State(
            grid=1200,
            pv_1=800,
            pv_2=500,
            bat_1=-400,
            bat_2=-400,
            bat_3=-600,
            cons_1=-600,
            price=0.30,
        )

    @state
    def charging_with_partial_import(self):
        return State(
            grid=400,
            pv_1=1000,
            pv_2=600,
            bat_1=-400,
            bat_2=-400,
            bat_3=-500,
            cons_1=-500,
            price=0.30,
        )

    @expect(state="charging_with_import")
    def outputs(self):
        return {
            "sink_adapters_source_shares": {
                "bat_1": {"grid": 1.0, "pv_1": 0.0},
                "bat_2": {"pv_1": 1.0, "pv_2": 0.0},
                "bat_3": {"pv_1": 0.615, "pv_2": 0.385},
                "cons_1": {"pv_1": 0.615, "pv_2": 0.385},
            },
        }

    @expect(state="charging_with_partial_import")
    def outputs(self):
        return {
            "sink_adapters_source_shares": {
                "bat_1": {"grid": 0.5, "pv_1": 0.5},
                "bat_2": {"grid": 0.5, "pv_2": 0.5},
                "bat_3": {"pv_1": 0.625, "pv_2": 0.375},
                "cons_1": {"pv_1": 0.625, "pv_2": 0.375},
            },
        }





