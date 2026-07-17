"""Demonstration of the ``@topology`` / ``@state`` scenario framework.

Two base classes, two philosophies:

* :class:`CaseScenario` — a single fused cell. One ``@topology`` whose adapters
  carry their own readings (``Adapter.grid(price=0.30, power=1000)``); **pinned**
  expected values. The edge-case home (successor to
  ``test_engine_property_scenarios.py``).
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
    LawScenario,
    State,
    Topology,
    export_ratio_bounded,
    reconstructs_gross_power,
    state,
    topology,
)

# ---------------------------------------------------------------------------
# Reusable topology shapes (module-level → shared across scenario classes).
# ---------------------------------------------------------------------------


def _solar_shape(*, pv_exports: bool) -> Topology:
    """Grid + one PV, toggling only whether the PV is credited for export.

    No readings here — a LawScenario supplies those via ``@state``.
    """
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
# CaseScenario — fused, pinned edge cases (readings live on the adapters).
# ===========================================================================


class TestBatteryChargingSplit(CaseScenario):
    """Grid + PV + a battery charging from both, gross 4000 W.

    Import 1000 W (gross share 0.25) and PV 3000 W (share 0.75) feed a 500 W
    charge, split 125 W / 375 W. Each adapter carries its own reading; every
    expected value is written by hand.
    """

    @topology
    def solar_with_battery(self):
        return Topology(
            Adapter.grid(price=0.30, power=1000),
            Adapter.pv(1, lcoe=0.10, exports=True, export_comp=0.08, power=3000),
            Adapter.battery(1, charge_from=("grid", "pv1"), power=-500),
            Adapter.consumer(1, power=-800),
        )

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
        return (Adapter.grid(price=0.30, power=-500),)

    def test_gross_power_is_zero(self, power_insight):
        assert power_insight.gross_power == pytest.approx(0.0)

    def test_export_ratio_guards_to_zero(self, power_insight):
        assert power_insight.gross_power_export_ratio == pytest.approx(0.0)

    def test_consumption_goes_negative(self, power_insight):
        assert power_insight.combined_consumption == pytest.approx(-500.0)


class TestInvertedGridNoPrice(CaseScenario):
    """Inverted grid sensor, no price reading — an unavailable-input edge case.

    ``inverted=True`` flips the sign so a +600 reading is 600 W export; with no
    price reading the cost of electricity is undefined. Shows a per-adapter
    ``power`` reading combined with adapter config (``inverted``) on one line.
    """

    @topology
    def inverted_grid(self):
        return (
            Adapter.grid(power=600, inverted=True),  # +600 inverted -> 600 W export
            Adapter.pv(1, exports=True, export_comp=0.08, power=2000),
            Adapter.consumer(1, power=-1400),
        )

    def test_inverted_sign(self, power_insight):
        assert power_insight.combined_grid_import == pytest.approx(0.0)
        assert power_insight.combined_grid_export == pytest.approx(600.0)

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == pytest.approx(2000.0)

    def test_no_price_means_no_coe(self, power_insight):
        assert power_insight.combined_coe is None


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


def test_case_scenario_rejects_state_decorator():
    class WithState(CaseScenario):
        @topology
        def grid_only(self):
            return (Adapter.grid(price=0.30, power=100),)

        @state
        def extra(self):
            return State(grid=100, price=0.30)

    with pytest.raises(ValueError, match="readings go on the adapters"):
        WithState.scenario_cells()


def test_case_scenario_rejects_multiple_topologies():
    class TwoTopologies(CaseScenario):
        @topology
        def a(self):
            return (Adapter.grid(price=0.30, power=100),)

        @topology
        def b(self):
            return (Adapter.grid(price=0.30, power=200),)

    with pytest.raises(ValueError, match="exactly one"):
        TwoTopologies.scenario_cells()


def test_topology_rejects_missing_grid():
    with pytest.raises(ValueError, match="exactly one grid"):
        Topology(Adapter.pv(1))
