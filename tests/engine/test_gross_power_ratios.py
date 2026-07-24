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
"""

from __future__ import annotations

import pytest

from tests.engine.scenario_framework import Adapter, EngineScenario, State, state, topology


class TestGrossPowerChannelSplit(EngineScenario):
    """The EXP / CON / CHG / STB split across representative snapshots."""

    # -- Import snapshot: charging + loads, no export, no standby ----------
    #
    # gross = import 1000 + PV 2000 + discharge 0 = 3000.
    #   EXP 0 | CHG |bat1| 500 | STB 0
    #   CON  = 3000 - 0 - 500 - 0 = 2500  (metered cons1 800 + home 1700)

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
        assert power_insight.combined_grid_import == 1000
        assert power_insight.combined_grid_export == 0
        assert power_insight.combined_production == 2000
        assert power_insight.combined_charging_power == 500
        assert power_insight.combined_discharging_power == 0
        assert power_insight.combined_standby_power == 0
        assert power_insight.combined_consumption == 2500

    def test_gross_power(self, power_insight):
        assert power_insight.gross_power == 3000

    def test_channel_ratios(self, power_insight):
        assert power_insight.gross_power_export_ratio == 0.0
        assert power_insight.gross_power_charging_ratio == pytest.approx(1 / 6)
        assert power_insight.gross_power_standby_ratio == 0.0
        assert power_insight.gross_power_consumption_ratio == pytest.approx(5 / 6)

    def test_ratios_sum_to_one(self, power_insight):
        total = (
            power_insight.gross_power_export_ratio
            + power_insight.gross_power_charging_ratio
            + power_insight.gross_power_standby_ratio
            + power_insight.gross_power_consumption_ratio
        )
        assert total == pytest.approx(1.0)

    def test_applicable_consumption_ratio(self, power_insight):
        # gross - export - charging = 2500; consumption 2500 -> 1.0 (no standby).
        assert power_insight.gross_power_applicable_consumption_ratio == pytest.approx(1.0)

    # -- Export snapshot: export + standby + discharge --------------------
    #
    # gross = import 0 + PV (3000 + 0) + discharge 500 = 3500.
    #   EXP 1500 | CHG 0 | STB |pv2| 100
    #   CON = 3500 - 1500 - 0 - 100 = 1900  (metered cons1 200 + home 1700)

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
        assert power_insight.combined_grid_import == 0
        assert power_insight.combined_grid_export == 1500
        assert power_insight.combined_production == 3000  # pv2 in standby -> 0
        assert power_insight.combined_charging_power == 0
        assert power_insight.combined_discharging_power == 500
        assert power_insight.combined_standby_power == 100
        assert power_insight.combined_consumption == 1900

    def test_gross_power_export(self, power_insight):
        assert power_insight.gross_power == 3500

    def test_channel_ratios_export(self, power_insight):
        assert power_insight.gross_power_export_ratio == pytest.approx(3 / 7)
        assert power_insight.gross_power_charging_ratio == 0.0
        assert power_insight.gross_power_standby_ratio == pytest.approx(1 / 35)
        assert power_insight.gross_power_consumption_ratio == pytest.approx(19 / 35)

    def test_ratios_sum_to_one_export(self, power_insight):
        total = (
            power_insight.gross_power_export_ratio
            + power_insight.gross_power_charging_ratio
            + power_insight.gross_power_standby_ratio
            + power_insight.gross_power_consumption_ratio
        )
        assert total == pytest.approx(1.0)

    def test_applicable_consumption_ratio_export(self, power_insight):
        # gross - export - charging = 2000; consumption 1900 -> 0.95.
        assert power_insight.gross_power_applicable_consumption_ratio == pytest.approx(0.95)


class TestGrossPowerEdgeCases(EngineScenario):
    """Unavailability propagation and the zero-gross guard."""

    # -- An inflow sensor (the battery) is unavailable --------------------
    #
    # gross and every channel that needs the battery go None; the standalone
    # provider readings that don't touch the battery stay available.

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
        assert power_insight.gross_power is None
        assert power_insight.combined_charging_power is None
        assert power_insight.combined_discharging_power is None
        assert power_insight.combined_consumption is None

    def test_ratios_none(self, power_insight):
        assert power_insight.gross_power_export_ratio is None
        assert power_insight.gross_power_charging_ratio is None
        assert power_insight.gross_power_standby_ratio is None
        assert power_insight.gross_power_consumption_ratio is None
        assert power_insight.gross_power_applicable_consumption_ratio is None

    def test_independent_powers_still_available(self, power_insight):
        assert power_insight.combined_grid_import == 1000
        assert power_insight.combined_production == 2000

    # -- Pure-export snapshot: gross_power == 0 ---------------------------
    #
    # Grid exporting 500 with nothing producing: gross 0 while export 500.
    # The ratios must guard the divide-by-zero (returning 0.0, not raising),
    # and the residual consumption clamps at 0 rather than going negative.

    @state
    def pure_export_zero_gross(self):
        return State(grid=-500, pv1=0, bat1=0, cons1=0, price=0.30)

    def test_zero_gross_guarded(self, power_insight):
        assert power_insight.gross_power == 0
        assert power_insight.combined_grid_export == 500
        assert power_insight.combined_consumption == 0.0  # clamped, not -500
        assert power_insight.gross_power_export_ratio == 0.0
        assert power_insight.gross_power_consumption_ratio == 0.0
        assert power_insight.gross_power_applicable_consumption_ratio == 0.0
