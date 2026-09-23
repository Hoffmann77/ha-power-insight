"""Edge-reading decisions, each pinned by a hand-derived harness.

What the engine publishes when a reading is missing or degenerate — a meter
that has dropped out, a house where nothing flows. Same shape as
``test_power_flow.py``: one block per decision, the smallest wiring that tells
the decision apart from its alternatives, values derived by hand.
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


class TestEdgeReadings(EngineScenario):
    """Missing and degenerate readings."""

    @topology
    def grid_only(self):
        return (Adapter.grid(),)

    # ----------------------------------------------------------------------
    # Decision: an unavailable meter collapses everything derived from it to
    # nothing, while a total over an empty device set stays zero.

    @state
    def meter_unavailable(self):
        """Decision: an unavailable meter collapses everything derived from it
        to nothing, while a total over an empty device set stays zero.

        The grid is the only inflow, so without it gross power is unknowable
        and so is everything built on it — published as nothing at all, never
        as a stale or invented number. Production, charging and standby are
        sums over devices this house does not have: the missing meter says
        nothing about them, so they stay a confident 0.
        """
        return State(grid=None, price=F(3, 10))

    @expect_attribute("gross_power")
    def test_meter_unavailable_gross_power(self):
        return None

    @expect_attribute("combined_grid_import")
    def test_meter_unavailable_combined_grid_import(self):
        return None

    @expect_attribute("combined_consumption")
    def test_meter_unavailable_combined_consumption(self):
        return None

    @expect_attribute("sink_adapters_source_shares")
    def test_meter_unavailable_sink_adapters_source_shares(self):
        return None

    @expect_attribute("combined_coe_rate")
    def test_meter_unavailable_combined_coe_rate(self):
        return None

    @expect_attribute("combined_production")
    def test_meter_unavailable_combined_production(self):
        """No PV system exists, so the sum over them is 0, known."""
        return 0

    @expect_attribute("combined_charging_power")
    def test_meter_unavailable_combined_charging_power(self):
        """No battery exists, so the sum over them is 0, known."""
        return 0

    @expect_attribute("combined_standby_power")
    def test_meter_unavailable_combined_standby_power(self):
        """No PV system exists, so the sum over them is 0, known."""
        return 0

    # ----------------------------------------------------------------------
    # Decision: zero gross power guards every ratio to zero, and with nothing
    # providing there is nothing to attribute.

    @state
    def export_with_nothing_producing(self):
        """Decision: zero gross power guards every ratio to zero rather than
        dividing by zero, and with nothing providing there is no provenance.

        The meter shows 500 W leaving while nothing produces — impossible, but
        exactly what unsynchronised sensors report for an instant. Gross power
        is 0, so the export ratio is 500 / 0 and the others 0 / 0; every one
        reads 0. No source is providing, so no sink has a row.
        """
        return State(grid=-500, price=F(3, 10))

    @expect_attribute("gross_power")
    def test_export_with_nothing_producing_gross_power(self):
        return 0

    @expect_attribute("gross_power_export_ratio")
    def test_export_with_nothing_producing_gross_power_export_ratio(self):
        return 0

    @expect_attribute("gross_power_consumption_ratio")
    def test_export_with_nothing_producing_gross_power_consumption_ratio(self):
        return 0

    @expect_attribute("gross_power_charging_ratio")
    def test_export_with_nothing_producing_gross_power_charging_ratio(self):
        return 0

    @expect_attribute("gross_power_standby_ratio")
    def test_export_with_nothing_producing_gross_power_standby_ratio(self):
        return 0

    @expect_attribute("sink_adapters_source_shares")
    def test_export_with_nothing_producing_sink_adapters_source_shares(self):
        return {}

    # ----------------------------------------------------------------------
    # Decision: a consumer dropping out does not make gross power unknowable.

    @topology
    def grid_and_a_plug(self):
        return (Adapter.grid(), Adapter.consumer("plug"))

    @state
    def plug_unavailable(self):
        """Decision: gross power is unknowable only when an *inflow* sensor —
        grid, PV or battery — is unavailable; a consumer dropping out does not
        invalidate it (engine-calculations.md, "gross power is None if any
        inflow sensor is unavailable").

        The grid still reads 500 W, so gross power and self-consumption are
        known. The plug's sensor is gone: it is in no flow group, so it has no
        row, and its draw is simply part of the 500 W base load.
        """
        return State(grid=500, plug=None, price=F(3, 10))

    @expect_attribute("gross_power")
    def test_plug_unavailable_gross_power(self):
        return 500

    @expect_attribute("combined_consumption")
    def test_plug_unavailable_combined_consumption(self):
        return 500

    @expect_attribute("home_base_load_power")
    def test_plug_unavailable_home_base_load_power(self):
        return 500

    @expect_attribute("sink_adapters_source_shares")
    def test_plug_unavailable_sink_adapters_source_shares(self):
        return {}
