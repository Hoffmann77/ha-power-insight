"""Scenarios for the gross-power channel split (combined powers + ratios).

Gross power leaves the system through exactly four channels, each with a single
sink device type (see ``docs/concepts.md``):

    EXP export      -> grid            CHG charging -> batteries
    CON consumption -> consumers + the STB standby  -> PV systems
                       unmetered home load

The channel a sink belongs to is a pure function of its adapter identity, so the
combined powers are read straight off the containers — except CON, which is the
*residual* ``gross - export - charging - standby`` so it also captures the
unmetered home base load. The four ratios therefore partition gross power and
sum to 1 whenever every input is available.

Expected values are hand-derived from first principles (not read back from the
engine). Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery
``+`` produce/discharge / ``-`` standby/charge; consumer ``-`` = load.

Nothing here has been derived yet: every expectation is still a ``return TODO``
stub, which skips and claims nothing. Replace one with the value you worked out
from the ``@topology`` + ``@state`` above it and that line starts holding the
engine to it —::

    uv run pytest tests/engine/test_gross_power_ratios.py -rs

lists what is still open. Never paste an answer out of the engine's own output:
that records what the code already does, which proves nothing.
"""

from __future__ import annotations

import pytest

from tests.engine.scenario_framework import (
    TODO,
    Adapter,
    EngineScenario,
    State,
    expect_attribute as expect,
    state,
    topology,
)


class TestGrossPowerChannelSplit(EngineScenario):
    """The EXP / CON / CHG / STB split across representative snapshots."""

    # -- Import snapshot: charging + loads, no export, no standby ----------

    @topology
    def grid_pv_battery_consumer(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.battery("bat1", charge_from=("pv1",)),
            Adapter.consumer("cons1"),
        )

    @state
    def importing_and_charging(self):
        return State(grid=1000, pv1=2000, bat1=-500, cons1=-800, price=0.30)

    @expect("combined_grid_import")
    def test_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_combined_consumption(self):
        return TODO

    @expect("gross_power")
    def test_gross_power(self):
        return TODO

    @expect("gross_power_export_ratio")
    def test_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_gross_power_consumption_ratio(self):
        return TODO

    def test_ratios_sum_to_one(self, power_insight):
        total = (
            power_insight.gross_power_export_ratio
            + power_insight.gross_power_charging_ratio
            + power_insight.gross_power_standby_ratio
            + power_insight.gross_power_consumption_ratio
        )
        assert total == pytest.approx(1.0)

    # -- Export snapshot: export + standby + discharge --------------------

    @topology
    def grid_two_pv_battery_consumer(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.pv("pv2", exports=True),
            Adapter.battery("bat1", charge_from=("pv1",)),
            Adapter.consumer("cons1"),
        )

    @state
    def exporting_with_standby(self):
        return State(grid=-1500, pv1=3000, pv2=-100, bat1=500, cons1=-200, price=0.30)

    @expect("combined_grid_import")
    def test_export_combined_grid_import(self):
        return TODO

    @expect("combined_grid_export")
    def test_export_combined_grid_export(self):
        return TODO

    @expect("combined_production")
    def test_export_combined_production(self):
        return TODO

    @expect("combined_charging_power")
    def test_export_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_export_combined_discharging_power(self):
        return TODO

    @expect("combined_standby_power")
    def test_export_combined_standby_power(self):
        return TODO

    @expect("combined_consumption")
    def test_export_combined_consumption(self):
        return TODO

    @expect("gross_power")
    def test_export_gross_power(self):
        return TODO

    @expect("gross_power_export_ratio")
    def test_export_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_export_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_export_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_export_gross_power_consumption_ratio(self):
        return TODO

    def test_ratios_sum_to_one_export(self, power_insight):
        total = (
            power_insight.gross_power_export_ratio
            + power_insight.gross_power_charging_ratio
            + power_insight.gross_power_standby_ratio
            + power_insight.gross_power_consumption_ratio
        )
        assert total == pytest.approx(1.0)


class TestGrossPowerEdgeCases(EngineScenario):
    """Unavailability propagation and the zero-gross guard."""

    # -- An inflow sensor (the battery) is unavailable --------------------

    @topology
    def grid_pv_battery_consumer(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.battery("bat1", charge_from=("pv1",)),
            Adapter.consumer("cons1"),
        )

    @state
    def battery_unavailable(self):
        return State(grid=1000, pv1=2000, bat1=None, cons1=-800, price=0.30)

    @expect("gross_power")
    def test_unavailable_gross_power(self):
        return TODO

    @expect("combined_charging_power")
    def test_unavailable_combined_charging_power(self):
        return TODO

    @expect("combined_discharging_power")
    def test_unavailable_combined_discharging_power(self):
        return TODO

    @expect("combined_consumption")
    def test_unavailable_combined_consumption(self):
        return TODO

    @expect("gross_power_export_ratio")
    def test_unavailable_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_charging_ratio")
    def test_unavailable_gross_power_charging_ratio(self):
        return TODO

    @expect("gross_power_standby_ratio")
    def test_unavailable_gross_power_standby_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_unavailable_gross_power_consumption_ratio(self):
        return TODO

    # The two quantities that depend on no missing reading — they stay
    # available while the battery is down.

    @expect("combined_grid_import")
    def test_unavailable_combined_grid_import(self):
        return TODO

    @expect("combined_production")
    def test_unavailable_combined_production(self):
        return TODO

    # -- Pure-export snapshot: gross_power == 0 (divide-by-zero guard) -----

    @state
    def pure_export_zero_gross(self):
        return State(grid=-500, pv1=0, bat1=0, cons1=0, price=0.30)

    @expect("gross_power")
    def test_zero_gross_gross_power(self):
        return TODO

    @expect("combined_grid_export")
    def test_zero_gross_combined_grid_export(self):
        return TODO

    @expect("combined_consumption")
    def test_zero_gross_combined_consumption(self):
        return TODO

    @expect("gross_power_export_ratio")
    def test_zero_gross_gross_power_export_ratio(self):
        return TODO

    @expect("gross_power_consumption_ratio")
    def test_zero_gross_gross_power_consumption_ratio(self):
        return TODO
