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
        return Topology(
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.battery("bat1", charge_from=("grid", "pv1")),
            Adapter.consumer("cons1"),
        )

    @state
    def midmorning(self):
        return State(grid=1000, pv1=3000, bat1=-500, cons1=-800, price=0.30)

    @expect
    def outputs(self):
        return {
            "gross_power": 4000.0,
            "combined_charging_power": 500.0,
            "storage_adapters_charging_source_shares": {
                "bat1": {"grid": 0.25, "pv1": 0.75}
            },
            "grid_adapters_charging_power": {"grid": 125.0},
            "storage_adapters_dynamic_lcoe": {"bat1": 0.15},
        }


class TestNamedAdapters(EngineTestScenario):
    """Descriptive uids read the same everywhere they are referenced.

    Every adapter's ``uid`` is required; it need not follow the ``pv1``/``bat1``
    convention used elsewhere. Here the same scenario as ``TestChargingSplit``
    uses ``east_roof`` / ``powerwall`` / ``house`` — the id at the adapter is
    exactly the key in ``State``, ``charge_from`` and the ``@expect`` map.
    """

    @topology
    def solar_with_battery(self):
        return Topology(
            Adapter.grid(),
            Adapter.pv("east_roof", lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.battery("powerwall", charge_from=("grid", "east_roof")),
            Adapter.consumer("house"),
        )

    @state
    def midmorning(self):
        return State(grid=1000, east_roof=3000, powerwall=-500, house=-800, price=0.30)

    @expect
    def outputs(self):
        return {
            "gross_power": 4000.0,
            "combined_charging_power": 500.0,
            "storage_adapters_charging_source_shares": {
                "powerwall": {"grid": 0.25, "east_roof": 0.75}
            },
            "grid_adapters_charging_power": {"grid": 125.0},
        }


class TestPureGridExportDegenerate(EngineTestScenario):
    """Export 500 W with no production: gross 0, consumption goes negative.

    Also shows the bare-tuple ``@topology`` return (no ``Topology(...)`` wrapper).
    """

    @topology
    def grid_only(self):
        return (Adapter.grid(),)

    @state
    def pure_export(self):
        return State(grid=-500, price=0.30)

    @expect
    def outputs(self):
        return {
            "combined_grid_import": 0.0,
            "combined_grid_export": 500.0,
            "gross_power": 0.0,
            "gross_power_export_ratio": 0.0,  # _divide(500, 0) guards to 0.0
            "combined_consumption": -500.0,
        }


class TestInvertedGridNoPrice(EngineTestScenario):
    """Inverted grid sensor, no price reading — an unavailable-input edge case.

    ``inverted=True`` (adapter config) flips the sign so a +600 reading is 600 W
    export; the state supplies no ``price``, so the cost of electricity is
    ``None``. An ``@expect`` value may itself be ``None``.
    """

    @topology
    def inverted_grid(self):
        return (
            Adapter.grid(inverted=True),
            Adapter.pv("pv1", exports=True, export_comp=0.08),
            Adapter.consumer("cons1"),
        )

    @state
    def midday(self):
        return State(grid=600, pv1=2000, cons1=-1400)  # +600 inverted -> 600 export

    @expect
    def outputs(self):
        return {
            "combined_grid_import": 0.0,
            "combined_grid_export": 600.0,
            "gross_power": 2000.0,
            "combined_coe": None,  # no price reading -> undefined
        }


# ===========================================================================
# @modify — variant cells from one base topology.
# ===========================================================================


class TestExportFlagIsResultNeutralWhenImporting(EngineTestScenario):
    """Toggling PV export credit must not change results while the grid imports.

    Base: 200 W import + 1000 W self-consumed PV. The ``@modify`` flips the PV to
    an exporting one — but nothing is exported (grid importing), so the ``@expect``
    map holds for both the base and variant cells (no overrides needed).
    """

    @topology
    def self_consume(self):
        return Topology(Adapter.grid(), Adapter.pv("pv1", lcoe=0.10))

    @state
    def importing(self):
        return State(grid=200, pv1=1000, price=0.30)

    @modify
    def as_exporting_pv(self):
        return Modify("pv1", exports=True, export_comp=0.08)

    @expect
    def outputs(self):
        return {
            "gross_power": 1200.0,
            "combined_consumption": 1200.0,
            "combined_export_compensation_rate": 0.0,
        }


class TestCorrectionFactorVariant(EngineTestScenario):
    """One config change, two outcomes: base rate unchanged, corrected rate not.

    The ``@expect`` map holds the base outcomes; the ``@modify`` overrides only
    the one property it changes (``combined_lcoe_rate_corrected``): base 0.40,
    variant 0.425. ``combined_lcoe_rate`` is correction-neutral, so it holds for
    both cells straight from the map.
    """

    @topology
    def base(self):
        return Topology(Adapter.grid(), Adapter.pv("pv1", lcoe=0.10))

    @state
    def midday(self):
        return State(grid=1000, pv1=1000, price=0.30)

    @expect
    def outputs(self):
        return {
            "gross_power": 2000.0,
            "combined_lcoe_rate": 0.40,
            "combined_lcoe_rate_corrected": 0.40,
        }

    @modify
    def corrected(self):
        return Modify("pv1", correction_factor=1.25).expect(
            combined_lcoe_rate_corrected=0.425
        )


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


# ===========================================================================
# Laws over a product as test_ methods (no @expect map).
# ===========================================================================


class TestExportConfigurationLaws(EngineTestScenario):
    """Same shape/config sweep, verified by laws rather than pinned values.

    No ``@expect`` map: the assertions are formulas/relationships that hold for
    every cell of the 2 topologies × 2 states product. ``test_property`` is inert
    (no map) — coverage comes entirely from these methods.
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
        return State(grid=-1000, pv1=2000, price=0.30)

    @state
    def morning(self):
        return State(grid=800, pv1=400, price=0.30)

    def test_gross_power_formula(self, power_insight, state):
        # Independent reconstruction from raw readings (export config-neutral).
        expected = max(state.grid, 0.0) + max(state.pv1, 0.0)
        assert power_insight.gross_power == pytest.approx(expected)

    def test_conservation(self, power_insight):
        assert power_insight.combined_consumption == pytest.approx(
            power_insight.gross_power - power_insight.combined_grid_export
        )

    def test_export_ratio_bounded(self, power_insight):
        ratio = power_insight.gross_power_export_ratio
        assert 0.0 <= ratio <= 1.0


# ===========================================================================
# Guardrails — collection-time validation (classes defined locally so pytest
# does not collect them; we call the collection helpers directly).
# ===========================================================================


def test_incompatible_state_is_rejected():
    class Broken(EngineTestScenario):
        @topology
        def grid_and_pv(self):
            return Topology(Adapter.grid(), Adapter.pv("pv1"))

        @state
        def has_a_battery(self):
            # bat1 has no adapter in the topology — silent zero-fill would hide
            # this; the framework must reject it instead.
            return State(grid=100, pv1=500, bat1=-200, price=0.30)

    with pytest.raises(ValueError, match="incompatible|unexpected"):
        Broken.scenario_cells()


def test_expect_rejects_unknown_scope():
    class BadScope(EngineTestScenario):
        @topology
        def only(self):
            return Topology(Adapter.grid(), Adapter.pv("pv1"))

        @state
        def s(self):
            return State(grid=100, pv1=200, price=0.30)

        @expect(state="typo")  # no state named "typo"
        def m(self):
            return {"gross_power": 300.0}

    with pytest.raises(ValueError, match="matches no state"):
        BadScope.decl_cases()


def test_cells_scope_matching_nothing_errors():
    from tests.engine.scenario_framework import Cell, _filter_cells_by_scope

    class Shape(EngineTestScenario):
        @topology
        def only(self):
            return Topology(Adapter.grid(), Adapter.pv("pv1"))

        @state
        def midday(self):
            return State(grid=100, pv1=200, price=0.30)

    scenario_cells = Shape.scenario_cells()
    assert isinstance(scenario_cells[0], Cell)
    with pytest.raises(ValueError, match="matches no state"):
        _filter_cells_by_scope(scenario_cells, (None, "typo"), "Shape.test_x")


def test_modify_rejects_unknown_target():
    class BadTarget(EngineTestScenario):
        @topology
        def grid_only(self):
            return (Adapter.grid(),)

        @state
        def s(self):
            return State(grid=100, price=0.30)

        @modify
        def touches_ghost(self):
            return Modify("pv9", lcoe=0.20)  # no such adapter

    with pytest.raises(ValueError, match="unknown adapter"):
        BadTarget.scenario_cells()


def test_topology_rejects_missing_grid():
    with pytest.raises(ValueError, match="exactly one grid"):
        Topology(Adapter.pv("pv1"))
