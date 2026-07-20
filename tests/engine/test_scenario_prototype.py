"""Demonstration of the ``@topology`` / ``@state`` scenario framework.

Both base classes share one authoring surface — ``@topology`` (adapters + config)
and ``@state`` (readings) — and differ only in how many cells they run:

* :class:`CaseScenario` — one topology × one state, **pinned** expected values.
  The edge-case home (successor to ``test_engine_property_scenarios.py``).
* :class:`LawScenario` — every topology × every state, **general** assertions
  (invariants + formulas over the injected ``state``). The sweep home
  (successor to ``test_power_insight_calculations.py``).

Run just this file::

    uv run pytest tests/engine/test_scenario_prototype.py -v
"""

from __future__ import annotations

import pytest

from tests.engine.scenario_framework import (
    Adapter,
    CaseScenario,
    DeclarativeScenario,
    LawScenario,
    Modify,
    State,
    Topology,
    cells,
    expect,
    export_ratio_bounded,
    modify,
    reconstructs_gross_power,
    state,
    topology,
)

# ---------------------------------------------------------------------------
# Reusable topology shapes (module-level → shared across scenario classes).
# ---------------------------------------------------------------------------


def _solar_shape(*, pv_exports: bool) -> Topology:
    """Grid + one PV, toggling only whether the PV is credited for export."""
    return Topology(
        Adapter.grid(),
        Adapter.pv(
            1,
            lcoe=0.10,
            exports=pv_exports,
            export_comp=0.08 if pv_exports else 0.0,
        ),
    )


# ===========================================================================
# CaseScenario — pinned edge cases (one topology × one state).
# ===========================================================================


class TestBatteryChargingSplit(CaseScenario):
    """Grid + PV + a battery charging from both, gross 4000 W.

    Import 1000 W (gross share 0.25) and PV 3000 W (share 0.75) feed a 500 W
    charge, split 125 W / 375 W. Every expected value is written by hand.
    """

    @topology
    def solar_with_battery(self):
        return Topology(
            Adapter.grid(),
            Adapter.pv(1, lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.battery(1, charge_from=("grid", "pv1")),
            Adapter.consumer(1),
        )

    @state
    def midmorning(self):
        return State(grid=1000, pv1=3000, bat1=-500, cons1=-800, price=0.30)

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == pytest.approx(4000.0)

    def test_combined_charging_power(self, power_insight):
        assert power_insight.combined_charging_power == pytest.approx(500.0)

    def test_charging_source_shares(self, power_insight):
        assert power_insight.storage_adapters_charging_source_shares == {
            "bat1": {"grid": pytest.approx(0.25), "pv1": pytest.approx(0.75)}
        }

    def test_grid_charging_power(self, power_insight):
        assert power_insight.grid_adapters_charging_power == {
            "grid": pytest.approx(125.0)
        }

    def test_dynamic_lcoe_blend(self, power_insight):
        # grid coe (price 0.30) * 0.25 + pv1 lcoe 0.10 * 0.75 = 0.15
        assert power_insight.storage_adapters_dynamic_lcoe == {
            "bat1": pytest.approx(0.15)
        }


class TestPureGridExportDegenerate(CaseScenario):
    """Export 500 W with no production: gross 0, consumption goes negative.

    A genuine edge case — exactly what CaseScenario is for, and exactly the kind
    of degenerate that would *break* the export-ratio invariant, so it must not
    live in a LawScenario family. Also demonstrates the bare-tuple ``@topology``
    return (no explicit ``Topology(...)`` wrapper).
    """

    @topology
    def grid_only(self):
        return (Adapter.grid(),)

    @state
    def pure_export(self):
        return State(grid=-500, price=0.30)

    def test_gross_power_is_zero(self, power_insight):
        assert power_insight.gross_power == pytest.approx(0.0)

    def test_export_ratio_guards_to_zero(self, power_insight):
        assert power_insight.gross_power_export_ratio == pytest.approx(0.0)

    def test_consumption_goes_negative(self, power_insight):
        assert power_insight.combined_consumption == pytest.approx(-500.0)


class TestInvertedGridNoPrice(CaseScenario):
    """Inverted grid sensor, no price reading — an unavailable-input edge case.

    ``inverted=True`` (adapter config) flips the sign so a +600 reading is 600 W
    export; the state supplies no ``price``, so the cost of electricity is
    undefined. Config lives on the adapter, the reading on the state.
    """

    @topology
    def inverted_grid(self):
        return (
            Adapter.grid(inverted=True),
            Adapter.pv(1, exports=True, export_comp=0.08),
            Adapter.consumer(1),
        )

    @state
    def midday(self):
        # +600 grid reading, inverted -> 600 W export; no price reading.
        return State(grid=600, pv1=2000, cons1=-1400)

    def test_inverted_sign(self, power_insight):
        assert power_insight.combined_grid_import == pytest.approx(0.0)
        assert power_insight.combined_grid_export == pytest.approx(600.0)

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == pytest.approx(2000.0)

    def test_no_price_means_no_coe(self, power_insight):
        assert power_insight.combined_coe is None


# ===========================================================================
# CaseScenario + @modify — variant cells from one base topology.
# ===========================================================================


class TestExportFlagIsResultNeutralWhenImporting(CaseScenario):
    """Toggling PV export credit must not change results while the grid imports.

    Base: 200 W import + 1000 W self-consumed PV. The ``@modify`` flips the PV to
    an exporting one — but nothing is exported (grid is importing), so every
    asserted property is identical across base and variant. No ``expect()``
    overrides: the pinned numbers hold for both cells.
    """

    @topology
    def self_consume(self):
        return Topology(Adapter.grid(), Adapter.pv(1, lcoe=0.10))

    @state
    def importing(self):
        return State(grid=200, pv1=1000, price=0.30)

    @modify
    def as_exporting_pv(self):
        return Modify("pv1", exports=True, export_comp=0.08)

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == pytest.approx(1200.0)

    def test_consumption(self, power_insight):
        assert power_insight.combined_consumption == pytest.approx(1200.0)

    def test_no_export_compensation(self, power_insight):
        assert power_insight.combined_export_compensation_rate == pytest.approx(0.0)


class TestCorrectionFactorVariant(CaseScenario):
    """One config change, two outcomes: base rate unchanged, corrected rate not.

    Base: 1000 W import @ 0.30 + 1000 W self-consumed PV (lcoe 0.10). The
    ``@modify`` sets the PV correction_factor to 1.25. ``combined_lcoe_rate`` is
    correction-neutral (same in both cells → a pinned assertion), while
    ``combined_lcoe_rate_corrected`` differs (base 0.40, variant 0.425) → read
    through the ``expected`` fixture.
    """

    @topology
    def base(self):
        return Topology(Adapter.grid(), Adapter.pv(1, lcoe=0.10))

    @state
    def midday(self):
        return State(grid=1000, pv1=1000, price=0.30)

    @modify
    def corrected(self):
        return Modify("pv1", correction_factor=1.25).expect(
            combined_lcoe_rate_corrected=0.425
        )

    def test_base_rate_is_correction_neutral(self, power_insight):
        # grid (1000/1000 * 0.30) + pv (1000/1000 * 0.10) = 0.40, both cells.
        assert power_insight.combined_lcoe_rate == pytest.approx(0.40)

    def test_corrected_rate(self, power_insight, expected):
        # base: 0.30*1.0 + 0.10*1.0 = 0.40; variant: 0.30 + 0.10*1.25 = 0.425.
        assert power_insight.combined_lcoe_rate_corrected == pytest.approx(
            expected("combined_lcoe_rate_corrected", 0.40)
        )


# ===========================================================================
# DeclarativeScenario — same scenario as TestCorrectionFactorVariant above, but
# expectations are data and the assertions are generated (no test_ methods).
# ===========================================================================


class TestCorrectionFactorDeclarative(DeclarativeScenario):
    """Data-driven twin of :class:`TestCorrectionFactorVariant`.

    The ``@expect`` map holds the base outcomes; the ``@modify`` overrides only
    the one property it changes. The framework generates one assertion per
    (cell, property): 3 properties × 2 cells = 6 checks, e.g.
    ``test_property[base-corrected-combined_lcoe_rate_corrected]``.
    """

    @topology
    def base(self):
        return Topology(Adapter.grid(), Adapter.pv(1, lcoe=0.10))

    @state
    def midday(self):
        return State(grid=1000, pv1=1000, price=0.30)

    @expect
    def outputs(self):
        return {
            "gross_power": 2000.0,
            "combined_lcoe_rate": 0.40,  # correction-neutral -> holds for both cells
            "combined_lcoe_rate_corrected": 0.40,  # base value
        }

    @modify
    def corrected(self):
        # Only the corrected rate shifts; gross_power & base rate carry over.
        return Modify("pv1", correction_factor=1.25).expect(
            combined_lcoe_rate_corrected=0.425
        )


class TestExportConfigScopedDeclarative(DeclarativeScenario):
    """Scoped ``@expect`` over a 2 topologies × 2 states product (4 cells).

    ``gross_power`` / ``combined_grid_export`` depend only on the state → scoped
    by state. ``combined_export_compensation_rate`` is 0 everywhere except the
    exporting PV at midday → a bare-``@expect`` default of 0, overridden for that
    one cell by a ``topology`` + ``state`` scope.
    """

    @topology
    def exporting(self):
        return Topology(
            Adapter.grid(), Adapter.pv(1, lcoe=0.10, exports=True, export_comp=0.08)
        )

    @topology
    def self_consume(self):
        return Topology(Adapter.grid(), Adapter.pv(1, lcoe=0.10, exports=False))

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
    # These coexist with the @expect maps: use a real assertion where a pinned
    # number is awkward (a relationship, is-None, a formula).

    @cells(state="midday")
    def test_export_does_not_exceed_gross(self, power_insight):
        # Runs only on the two midday cells (exporting + self_consume).
        assert power_insight.combined_grid_export <= power_insight.gross_power

    @cells(topology="exporting", state="midday")
    def test_only_exporting_midday_earns_compensation(self, power_insight):
        # Runs on exactly one cell — a code assertion, not a pinned value.
        assert power_insight.combined_export_compensation_rate > 0


class TestChargingSplitDeclarative(DeclarativeScenario):
    """Nested-dict expectations compare deeply and tolerantly (no @modify)."""

    @topology
    def solar_with_battery(self):
        return Topology(
            Adapter.grid(),
            Adapter.pv(1, lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.battery(1, charge_from=("grid", "pv1")),
            Adapter.consumer(1),
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


# ===========================================================================
# LawScenario — every topology × every state, general assertions.
# ===========================================================================


class TestExportConfiguration(LawScenario):
    """Same adapter shape, PV export credit on vs off × two physical states.

    2 topologies × 2 states = 4 cells. Every ``test_`` here holds across all
    four: the declared invariants, plus a gross-power formula over the raw
    readings (independent of the export config, which only affects *cost*
    attribution, not gross power).
    """

    INVARIANTS = [reconstructs_gross_power(), export_ratio_bounded()]

    @topology
    def pv_exports(self):
        return _solar_shape(pv_exports=True)

    @topology
    def pv_self_consumes(self):
        return _solar_shape(pv_exports=False)

    @state
    def midday(self):
        # PV 2000 W, grid exporting 1000 W.
        return State(grid=-1000, pv1=2000, price=0.30)

    @state
    def morning(self):
        # Importing 800 W, PV 400 W, all self-consumed.
        return State(grid=800, pv1=400, price=0.30)

    def test_gross_power_formula(self, power_insight, state):
        # Independent reconstruction: import + production (export config-neutral).
        expected = max(state.grid, 0.0) + max(state.pv1, 0.0)
        assert power_insight.gross_power == pytest.approx(expected)

    def test_consumption_is_gross_minus_export(self, power_insight):
        # Holds in every cell of this normal-regime family.
        assert power_insight.combined_consumption == pytest.approx(
            power_insight.gross_power - power_insight.combined_grid_export
        )


# ===========================================================================
# Guardrails — collection-time validation (classes defined locally so pytest
# does not collect them; we call scenario_cells() directly).
# ===========================================================================


def test_incompatible_state_is_rejected():
    class Broken(LawScenario):
        @topology
        def grid_and_pv(self):
            return Topology(Adapter.grid(), Adapter.pv(1))

        @state
        def has_a_battery(self):
            # bat1 has no adapter in the topology — silent zero-fill would hide
            # this; the framework must reject it instead.
            return State(grid=100, pv1=500, bat1=-200, price=0.30)

    with pytest.raises(ValueError, match="incompatible|unexpected"):
        Broken.scenario_cells()


def test_case_scenario_rejects_multiple_states():
    class TwoStates(CaseScenario):
        @topology
        def grid_only(self):
            return (Adapter.grid(),)

        @state
        def a(self):
            return State(grid=100, price=0.30)

        @state
        def b(self):
            return State(grid=200, price=0.30)

    with pytest.raises(ValueError, match="exactly one"):
        TwoStates.scenario_cells()


def test_topology_rejects_missing_grid():
    with pytest.raises(ValueError, match="exactly one grid"):
        Topology(Adapter.pv(1))


def test_law_scenario_rejects_modify():
    class WithModify(LawScenario):
        @topology
        def shape(self):
            return Topology(Adapter.grid(), Adapter.pv(1))

        @state
        def s(self):
            return State(grid=100, pv1=200, price=0.30)

        @modify
        def variant(self):
            return Modify("pv1", lcoe=0.20)

    with pytest.raises(ValueError, match="CaseScenario-only"):
        WithModify.scenario_cells()


def test_expect_rejects_unknown_scope():
    class BadScope(DeclarativeScenario):
        @topology
        def only(self):
            return Topology(Adapter.grid(), Adapter.pv(1))

        @state
        def s(self):
            return State(grid=100, pv1=200, price=0.30)

        @expect(state="typo")  # no state named "typo"
        def m(self):
            return {"gross_power": 300.0}

    with pytest.raises(ValueError, match="matches no state"):
        BadScope.decl_cases()


def test_declarative_rejects_cell_without_expectations():
    class Gap(DeclarativeScenario):
        @topology
        def only(self):
            return Topology(Adapter.grid(), Adapter.pv(1))

        @state
        def a(self):
            return State(grid=100, pv1=200, price=0.30)

        @state
        def b(self):
            return State(grid=50, pv1=100, price=0.30)

        @expect(state="a")  # nothing covers state "b"
        def just_a(self):
            return {"gross_power": 300.0}

    with pytest.raises(ValueError, match="no expected values"):
        Gap.decl_cases()


def test_cells_scope_matching_nothing_errors():
    # A @cells scope naming a nonexistent state must fail loudly rather than
    # silently produce a test method that runs against zero cells.
    from tests.engine.scenario_framework import Cell, _filter_cells_by_scope

    class Shape(LawScenario):
        @topology
        def only(self):
            return Topology(Adapter.grid(), Adapter.pv(1))

        @state
        def midday(self):
            return State(grid=100, pv1=200, price=0.30)

    scenario_cells = Shape.scenario_cells()
    assert isinstance(scenario_cells[0], Cell)
    with pytest.raises(ValueError, match="matches no state"):
        _filter_cells_by_scope(scenario_cells, (None, "typo"), "Shape.test_x")


def test_modify_rejects_unknown_target():
    class BadTarget(CaseScenario):
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
