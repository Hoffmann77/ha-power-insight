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


class TestChargingSplit(EngineTestScenario):
    """Grid + PV + a battery charging from both, gross 4000 W.

    Import 1000 W (gross share 0.25) and PV 3000 W (share 0.75) feed a 500 W
    charge, split 125 W / 375 W. Nested-dict expectations compare deeply and
    tolerantly.
    """

    @topology
    def solar_with_battery(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv_1", lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.battery("bat_1", charge_from=("grid", "pv1")),
            Adapter.battery("bat_2", charge_from=("pv1")),
            Adapter.consumer("cons_1"),
        )

    @state
    def midmorning(self):
        return State(
            grid=1500,
            pv_1=800,
            bat_1=-500,
            bat_2=-500,
            cons_1=-800,
            price=0.30,
        )

    @expect
    def outputs(self):
        return {
            "gross_power": 2000.0,
            "combined_charging_power": 1000.0,
            "storage_adapters_charging_source_shares": {
                "bat_1": {"grid": 1.0, "pv_1": 0.0},
                "bat_2": {"pv_1": 1.0},
            },
            "grid_adapters_charging_power": {"grid": 125.0},
            "storage_adapters_dynamic_lcoe": {"bat1": 0.15},
        }



# ===========================================================================
# Scoped @expect over a product + bespoke @cells-scoped test methods.
# ===========================================================================


class TestExportConfigScoped(EngineTestScenario):
    """2 topologies × 2 states (4 cells) with scoped maps and scoped methods.

    ``gross_power`` / ``combined_grid_export`` depend only on the state → scoped
    by state. ``combined_export_compensation_rate`` is 0 everywhere except the
    exporting PV at midday → a bare-``@expect`` default of 0 overridden for that
    one cell. Two ``test_`` methods add code assertions on subsets of the product.
    """

    @topology
    def exporting(self):
        return Topology(
            Adapter.grid(), Adapter.pv("pv1", lcoe=0.10, exports=True, export_comp=0.08)
        )

    @topology
    def self_consume(self):
        return Topology(Adapter.grid(), Adapter.pv("pv1", lcoe=0.10, exports=False))

    @state
    def midday(self):
        return State(grid=-1000, pv1=2000, price=0.30)  # PV exports 1000 W

    @state
    def morning(self):
        return State(grid=800, pv1=400, price=0.30)  # importing, all self-consumed

    @expect(state="midday")
    def at_midday(self):
        return {"gross_power": 2000.0, "combined_grid_export": 1000.0}

    @expect(state="morning")
    def at_morning(self):
        return {"gross_power": 1200.0, "combined_grid_export": 0.0}

    @expect
    def no_export_compensation_by_default(self):
        return {"combined_export_compensation_rate": 0.0}

    @expect(topology="exporting", state="midday")
    def exporting_midday(self):
        # (1000 W / 1000) * 0.08 EUR/kWh — only this cell earns compensation.
        return {"combined_export_compensation_rate": 0.08}

    # --- bespoke test methods, scoped to a subset of the product -----------

    @cells(state="midday")
    def test_export_does_not_exceed_gross(self, power_insight):
        assert power_insight.combined_grid_export <= power_insight.gross_power

    @cells(topology="exporting", state="midday")
    def test_only_exporting_midday_earns_compensation(self, power_insight):
        assert power_insight.combined_export_compensation_rate > 0

