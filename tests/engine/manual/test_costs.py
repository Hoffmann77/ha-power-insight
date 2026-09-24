"""Costs: what the power the house uses costs, and how that cost is split.

Every watt of *gross power* (all power supplied, from the grid and local
devices) goes into exactly one *channel*: consumption, charging, standby or
export. Costs are split the same way, and every figure comes in two flavours:
*marginal* (``coe``: only what costs money right now — the grid tariff; local
generation is free) and *levelized* (``lcoe``: local generation priced at
its lifetime cost per kWh too). Rates are in EUR per hour at the current
power. See "Cost follows the channels" in ``docs/dev/engine-calculations.md``.

Prices throughout: the grid tariff is 3/10 EUR/kWh and a PV system's LCOE
1/10 (the device default).
"""

from __future__ import annotations

from fractions import Fraction as F

from tests.engine.home import Battery, Grid, Home, Pv, expect

PRICE = F(3, 10)


class TestChannelCostsAreTheLedger(Home):
    """Decision: the four channel cost buckets are the cost ledger — they add
    up to the cost of gross power, at marginal and at levelized prices
    (engine-calculations.md, "the channel cost buckets are the cost ledger").

    Nothing is restricted, so every sink takes the raw mix: grid 1/4, pv1 3/4
    of 1200 W. Consumption (the 900 W base load) gets 225 W grid and 675 W
    pv1; charging (bat1's 250 W) 62.5 and 187.5; standby (pv2's 50 W) 12.5 and
    37.5. At the margin only grid watts cost anything: 0.225, 0.0625 and
    0.0125 kW × 3/10. Levelized, pv1 adds 1/10 per kWh.
    """

    grid = Grid(300, price=PRICE)
    pv1 = Pv(900)
    pv2 = Pv(-50)
    bat1 = Battery(-250)

    @expect("combined_consumption_cost_rate")
    def test_consumption_cost(self):
        """The consumption channel pays for its 225 W of grid power.

        The 900 W base load takes the raw mix, a quarter of it from the grid:
        0.225 kW × 3/10 EUR/kWh = 27/400 EUR/h. Its 675 W of pv1 cost nothing
        at the margin.
        """
        return F(27, 400)

    @expect("combined_charging_cost_rate")
    def test_charging_cost(self):
        """The charging channel pays for bat1's 62.5 W of grid power.

        bat1 charges at 250 W, a quarter of it from the grid:
        0.0625 kW × 3/10 = 3/160 EUR/h.
        """
        return F(3, 160)

    @expect("combined_standby_cost_rate")
    def test_standby_cost(self):
        """The standby channel pays for pv2's 12.5 W of grid power.

        pv2 draws 50 W of standby, a quarter of it from the grid:
        0.0125 kW × 3/10 = 3/800 EUR/h.
        """
        return F(3, 800)

    @expect("combined_export_cost_rate")
    def test_export_cost(self):
        """Nothing is exported, so the export channel costs nothing."""
        return 0

    @expect("combined_coe_rate")
    def test_coe_rate(self):
        """The four marginal channel costs add up to the cost of the import.

        27/400 + 3/160 + 3/800 + 0 = 9/100 EUR/h, which is exactly the
        300 W import at 3/10 EUR/kWh: every watt bought lands in one channel,
        none twice and none missing.
        """
        return F(9, 100)

    @expect("combined_levelized_consumption_cost_rate")
    def test_levelized_consumption_cost(self):
        """Levelized, the consumption channel also pays for its pv1 power.

        225 W of grid at 3/10 plus 675 W of pv1 at its LCOE of 1/10:
        0.225 × 3/10 + 0.675 × 1/10 = 27/200 EUR/h.
        """
        return F(27, 200)

    @expect("combined_levelized_charging_cost_rate")
    def test_levelized_charging_cost(self):
        """Levelized, charging pays for 62.5 W of grid and 187.5 W of pv1.

        0.0625 × 3/10 + 0.1875 × 1/10 = 3/80 EUR/h.
        """
        return F(3, 80)

    @expect("combined_levelized_standby_cost_rate")
    def test_levelized_standby_cost(self):
        """Levelized, standby pays for 12.5 W of grid and 37.5 W of pv1.

        0.0125 × 3/10 + 0.0375 × 1/10 = 3/400 EUR/h.
        """
        return F(3, 400)

    @expect("combined_lcoe_rate")
    def test_lcoe_rate(self):
        """The levelized channel costs add up to the cost of all gross power.

        27/200 + 3/80 + 3/400 = 9/50 EUR/h, which is the 300 W import at
        3/10 plus pv1's 900 W at 1/10: 0.09 + 0.09.
        """
        return F(9, 50)


class TestOperatingCostHasTwoViews(Home):
    """Decision: operating cost has a channel view (charging alone) and a
    device view (every PV system's and battery's own draw); overnight they
    disagree (engine-calculations.md, "operating cost has a channel view and a
    device view").

    Nothing charges, so the charging channel costs nothing. pv1 draws 20 W of
    standby, all of it from the grid: 0.02 kW × 3/10 = 3/500 EUR/h, which the
    device view counts and the channel view does not.
    """

    grid = Grid(300, price=PRICE)
    pv1 = Pv(-20)

    @expect("combined_charging_cost_rate")
    def test_charging_cost(self):
        """The channel view reads 0: no battery is charging.

        The charging channel counts only power going into batteries, and
        there is none here, so pv1's standby draw does not show up in it.
        """
        return 0

    @expect("combined_device_operating_cost_rate")
    def test_device_operating_cost(self):
        """The device view counts pv1's standby draw.

        It adds up what every PV system and battery itself draws. pv1's 20 W
        of standby come from the grid: 0.02 kW × 3/10 = 3/500 EUR/h.
        """
        return F(3, 500)

    @expect("source_adapters_coo_rates")
    def test_per_device_operating_cost(self):
        """pv1's own operating cost is the whole 3/500 EUR/h.

        The per-device operating costs are what the device view is the sum
        of; with one PV system, all of it is pv1's.
        """
        return {"pv1": F(3, 500)}
