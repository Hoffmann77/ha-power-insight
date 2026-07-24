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

The expected values below are intentionally left as ``...`` to be filled in by
hand, derived from the @topology + @state each block declares.
"""

from __future__ import annotations

import pytest

from tests.engine.scenario_framework import Adapter, EngineScenario, State, state, topology


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

    def test_combined_powers(self, power_insight):
        assert power_insight.combined_grid_import == ...
        assert power_insight.combined_grid_export == ...
        assert power_insight.combined_production == ...
        assert power_insight.combined_charging_power == ...
        assert power_insight.combined_discharging_power == ...
        assert power_insight.combined_standby_power == ...
        assert power_insight.combined_consumption == ...

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == ...

    def test_channel_ratios(self, power_insight):
        assert power_insight.gross_power_export_ratio == ...
        assert power_insight.gross_power_charging_ratio == ...
        assert power_insight.gross_power_standby_ratio == ...
        assert power_insight.gross_power_consumption_ratio == ...

    def test_ratios_sum_to_one(self, power_insight):
        total = (
            power_insight.gross_power_export_ratio
            + power_insight.gross_power_charging_ratio
            + power_insight.gross_power_standby_ratio
            + power_insight.gross_power_consumption_ratio
        )
        assert total == pytest.approx(1.0)

    def test_applicable_consumption_ratio(self, power_insight):
        assert power_insight.gross_power_applicable_consumption_ratio == ...

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

    def test_combined_powers_export(self, power_insight):
        assert power_insight.combined_grid_import == ...
        assert power_insight.combined_grid_export == ...
        assert power_insight.combined_production == ...
        assert power_insight.combined_charging_power == ...
        assert power_insight.combined_discharging_power == ...
        assert power_insight.combined_standby_power == ...
        assert power_insight.combined_consumption == ...

    def test_gross_power_export(self, power_insight):
        assert power_insight.gross_power == ...

    def test_channel_ratios_export(self, power_insight):
        assert power_insight.gross_power_export_ratio == ...
        assert power_insight.gross_power_charging_ratio == ...
        assert power_insight.gross_power_standby_ratio == ...
        assert power_insight.gross_power_consumption_ratio == ...

    def test_ratios_sum_to_one_export(self, power_insight):
        total = (
            power_insight.gross_power_export_ratio
            + power_insight.gross_power_charging_ratio
            + power_insight.gross_power_standby_ratio
            + power_insight.gross_power_consumption_ratio
        )
        assert total == pytest.approx(1.0)

    def test_applicable_consumption_ratio_export(self, power_insight):
        assert power_insight.gross_power_applicable_consumption_ratio == ...


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

    def test_gross_and_dependent_channels_none(self, power_insight):
        assert power_insight.gross_power == ...
        assert power_insight.combined_charging_power == ...
        assert power_insight.combined_discharging_power == ...
        assert power_insight.combined_consumption == ...

    def test_ratios_none(self, power_insight):
        assert power_insight.gross_power_export_ratio == ...
        assert power_insight.gross_power_charging_ratio == ...
        assert power_insight.gross_power_standby_ratio == ...
        assert power_insight.gross_power_consumption_ratio == ...
        assert power_insight.gross_power_applicable_consumption_ratio == ...

    def test_independent_powers_still_available(self, power_insight):
        assert power_insight.combined_grid_import == ...
        assert power_insight.combined_production == ...

    # -- Pure-export snapshot: gross_power == 0 (divide-by-zero guard) -----

    @state
    def pure_export_zero_gross(self):
        return State(grid=-500, pv1=0, bat1=0, cons1=0, price=0.30)

    def test_zero_gross_guarded(self, power_insight):
        assert power_insight.gross_power == ...
        assert power_insight.combined_grid_export == ...
        assert power_insight.combined_consumption == ...
        assert power_insight.gross_power_export_ratio == ...
        assert power_insight.gross_power_consumption_ratio == ...
        assert power_insight.gross_power_applicable_consumption_ratio == ...
