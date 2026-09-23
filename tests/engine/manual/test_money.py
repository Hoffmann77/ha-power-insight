"""Monetary decisions, each pinned by a hand-derived harness.

Same shape as ``test_power_flow.py``: every block in :class:`TestMoney` pins
one decision from "The monetary model" in ``docs/dev/engine-calculations.md``,
as the smallest home that tells it apart from its alternatives, with values
derived by hand — the arithmetic is in each docstring.

Prices throughout: the grid tariff is 3/10 EUR/kWh, a PV system's LCOE 1/10
and a battery's LCOS 3/20 (the ``Adapter`` defaults), unless a block says
otherwise.
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

PRICE = F(3, 10)


class TestMoney(EngineScenario):
    """What power costs, what it saves, and who gets the credit."""

    # ----------------------------------------------------------------------
    # Decision: the channel cost buckets are the cost ledger.

    @topology
    def every_channel_but_export(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1"),
            Adapter.pv("pv2"),
            Adapter.battery("bat1"),
        )

    @state
    def consumption_charging_and_standby(self):
        """Decision: the four channel cost buckets are the cost ledger — they
        add up to the cost of gross power, at marginal and at levelized prices
        (engine-calculations.md, "the channel cost buckets are the cost
        ledger").

        Nothing is restricted, so every sink takes the raw mix: grid 1/4, pv1
        3/4 of 1200 W. Consumption (the 900 W base load) gets 225 W grid and
        675 W pv1; charging (bat1's 250 W) 62.5 and 187.5; standby (pv2's 50 W)
        12.5 and 37.5. At the margin only grid watts cost anything:
        0.225, 0.0625 and 0.0125 kW × 3/10. Levelized, pv1 adds 1/10 per kWh.
        """
        return State(grid=300, pv1=900, pv2=-50, bat1=-250, price=PRICE)

    @expect_attribute("combined_consumption_cost_rate")
    def test_consumption_charging_and_standby_consumption_cost(self):
        return F(27, 400)

    @expect_attribute("combined_charging_cost_rate")
    def test_consumption_charging_and_standby_charging_cost(self):
        return F(3, 160)

    @expect_attribute("combined_standby_cost_rate")
    def test_consumption_charging_and_standby_standby_cost(self):
        return F(3, 800)

    @expect_attribute("combined_export_cost_rate")
    def test_consumption_charging_and_standby_export_cost(self):
        return 0

    @expect_attribute("combined_coe_rate")
    def test_consumption_charging_and_standby_coe_rate(self):
        """27/400 + 3/160 + 3/800 = 9/100: the 300 W import at 3/10."""
        return F(9, 100)

    @expect_attribute("combined_levelized_consumption_cost_rate")
    def test_consumption_charging_and_standby_levelized_consumption_cost(self):
        """0.225 × 3/10 + 0.675 × 1/10."""
        return F(27, 200)

    @expect_attribute("combined_levelized_charging_cost_rate")
    def test_consumption_charging_and_standby_levelized_charging_cost(self):
        return F(3, 80)

    @expect_attribute("combined_levelized_standby_cost_rate")
    def test_consumption_charging_and_standby_levelized_standby_cost(self):
        return F(3, 400)

    @expect_attribute("combined_lcoe_rate")
    def test_consumption_charging_and_standby_lcoe_rate(self):
        """27/200 + 3/80 + 3/400 = 9/50: 0.3 kW × 3/10 plus 0.9 kW × 1/10."""
        return F(9, 50)

    # ----------------------------------------------------------------------
    # Decision: operating cost has a channel view and a device view.

    @topology
    def pv_at_night(self):
        return (Adapter.grid(), Adapter.pv("pv1"))

    @state
    def standby_overnight(self):
        """Decision: operating cost has a channel view (charging alone) and a
        device view (every PV system's and battery's own draw); overnight they
        disagree (engine-calculations.md, "operating cost has a channel view
        and a device view").

        Nothing charges, so the charging channel costs nothing. pv1 draws 20 W
        of standby, all of it from the grid: 0.02 kW × 3/10 = 3/500 EUR/h, which
        the device view counts and the channel view does not.
        """
        return State(grid=300, pv1=-20, price=PRICE)

    @expect_attribute("combined_charging_cost_rate")
    def test_standby_overnight_charging_cost(self):
        return 0

    @expect_attribute("combined_device_operating_cost_rate")
    def test_standby_overnight_device_operating_cost(self):
        return F(3, 500)

    @expect_attribute("source_adapters_coo_rates")
    def test_standby_overnight_per_device_operating_cost(self):
        return {"pv1": F(3, 500)}

    # ----------------------------------------------------------------------
    # Decision: a battery's energy cost is booked when it charges.

    @topology
    def pv_and_battery(self):
        return (Adapter.grid(), Adapter.pv("pv1"), Adapter.battery("bat1"))

    @state
    def battery_charging(self):
        """Decision: a battery's energy cost is booked when it charges, and its
        discharge is valued at the full tariff it displaces less only its own
        LCOS (engine-calculations.md, "a battery's energy cost is booked when
        it charges").

        Charging half. bat1 takes 400 W of a half-grid, half-pv1 mix: 200 W
        each. Its saving is minus what that cost: −0.2 × 3/10 at the margin,
        and −(0.2 × 3/10 + 0.2 × 1/10) levelized.
        """
        return State(grid=500, pv1=500, bat1=-400, price=PRICE)

    @expect_attribute("adapters_saving_rates")
    def test_battery_charging_saving(self):
        """pv1 serves 300 W of the 600 W base load, free at the margin:
        0.3 × 3/10. bat1 pays for its 200 W of grid."""
        return {"pv1": F(9, 100), "bat1": F(-3, 50)}

    @expect_attribute("adapters_levelized_saving_rates")
    def test_battery_charging_levelized_saving(self):
        """pv1: 0.3 × (3/10 − 1/10). bat1: −(0.06 + 0.02)."""
        return {"pv1": F(3, 50), "bat1": F(-2, 25)}

    @state
    def battery_discharging(self):
        """Decision (continued): the discharge half, same wiring.

        pv1 is idle; bat1 discharges 300 W into a 500 W base load beside 200 W
        of grid, so it serves 300 W. Its energy was paid for when it charged,
        so at the margin it saves the full tariff: 0.3 × 3/10. Levelized it
        carries only its LCOS: 0.3 × (3/10 − 3/20). pv1 reads 0, not absent.
        """
        return State(grid=200, pv1=0, bat1=300, price=PRICE)

    @expect_attribute("adapters_saving_rates")
    def test_battery_discharging_saving(self):
        return {"pv1": 0, "bat1": F(9, 100)}

    @expect_attribute("adapters_levelized_saving_rates")
    def test_battery_discharging_levelized_saving(self):
        return {"pv1": 0, "bat1": F(9, 200)}

    # ----------------------------------------------------------------------
    # Decision: the dynamic price falls back to the flat LCOS on discharge.

    @state
    def discharge_prices(self):
        """Decision: a discharging battery's dynamic price is its flat LCOS,
        and its marginal price is 0 — its energy cost was booked when it
        charged (engine-calculations.md, "the dynamic price falls back to the
        flat LCOS on discharge").

        Same wiring and readings as the discharge above; only the sources
        appear, so idle pv1 does not.
        """
        return State(grid=200, pv1=0, bat1=300, price=PRICE)

    @expect_attribute("source_adapters_dynamic_coe")
    def test_discharge_prices_dynamic_coe(self):
        return {"grid": PRICE, "bat1": 0}

    @expect_attribute("source_adapters_dynamic_lcoe")
    def test_discharge_prices_dynamic_lcoe(self):
        return {"grid": PRICE, "bat1": F(3, 20)}

    # ----------------------------------------------------------------------
    # Decision: consumers do not get a saving, they get an avoided cost.

    @topology
    def plug_beside_a_pv_system(self):
        return (Adapter.grid(), Adapter.pv("pv1"), Adapter.consumer("plug"))

    @state
    def plug_running_partly_on_pv(self):
        """Decision: a consumer running on PV is the same saved euro as the PV
        supplying it — credited to the PV as a saving and to the consumer only
        as an avoided cost, never both summed (engine-calculations.md,
        "consumers do not get a saving, they get an avoided cost").

        The raw mix is grid 1/4, pv1 3/4 of 800 W. The plug (400 W) and the
        base load (400 W) each take 300 W of pv1, avoiding 0.3 × 3/10 each.
        pv1 is credited with all 600 W: 0.6 × 3/10 — the same euro, counted
        once on each side. The plug has no saving entry at all.
        """
        return State(grid=200, pv1=600, plug=-400, price=PRICE)

    @expect_attribute("adapters_saving_rates")
    def test_plug_running_partly_on_pv_saving(self):
        return {"pv1": F(9, 50)}

    @expect_attribute("combined_saving_rate")
    def test_plug_running_partly_on_pv_combined_saving(self):
        return F(9, 50)

    @expect_attribute("sink_adapters_avoided_cost_rates")
    def test_plug_running_partly_on_pv_avoided_cost(self):
        return {"plug": F(9, 100)}

    @expect_attribute("home_base_load_avoided_cost_rate")
    def test_plug_running_partly_on_pv_base_load_avoided_cost(self):
        return F(9, 100)

    # ----------------------------------------------------------------------
    # Decision: the home base load gets its own properties, not a uid.

    @state
    def plug_on_the_grid(self):
        """Decision: the home base load is published through its own
        ``home_base_load_*`` properties and never as a key in the
        ``sink_adapters_*`` maps (engine-calculations.md, "the home base load
        gets its own properties, not a uid").

        Same wiring, no sun: the plug draws 100 W and the other 400 W are the
        base load, all from the grid. The sink maps name the plug alone.
        """
        return State(grid=500, pv1=0, plug=-100, price=PRICE)

    @expect_attribute("sink_adapters_source_shares")
    def test_plug_on_the_grid_power_flow(self):
        return {"plug": {"grid": 1}}

    @expect_attribute("sink_adapters_avoided_cost_rates")
    def test_plug_on_the_grid_avoided_cost(self):
        return {"plug": 0}

    @expect_attribute("home_base_load_power")
    def test_plug_on_the_grid_base_load_power(self):
        return 400

    @expect_attribute("home_base_load_source_shares")
    def test_plug_on_the_grid_base_load_shares(self):
        return {"grid": 1}

    # ----------------------------------------------------------------------
    # Decision: a correction factor multiplies the LCOE, never the result.

    @topology
    def pv_with_an_edited_lifetime_cost(self):
        return (Adapter.grid(), Adapter.pv("pv1", correction_factor=2.0))

    @state
    def dearer_pv_saves_less(self):
        """Decision: a device's correction factor multiplies its LCOE inside
        the saving, never the finished saving (engine-calculations.md, "the
        factor multiplies the lcoe, never the finished number").

        pv1's lifetime cost was edited so its energy costs twice as much. All
        600 W of it serve the 800 W base load. Uncorrected, it saves
        0.6 × (3/10 − 1/10) = 3/25; corrected, 0.6 × (3/10 − 2/10) = 3/50 —
        less, as dearer energy must. Scaling the result would have said 6/25.
        """
        return State(grid=200, pv1=600, price=PRICE)

    @expect_attribute("adapters_levelized_saving_rates")
    def test_dearer_pv_saves_less_uncorrected(self):
        return {"pv1": F(3, 25)}

    @expect_attribute("adapters_levelized_saving_rates_corrected")
    def test_dearer_pv_saves_less_corrected(self):
        return {"pv1": F(3, 50)}
