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
    """Decision: the four channel costs add up to the cost of all gross power.

    This holds at marginal and at levelized prices. Nothing is restricted, so
    every sink gets the raw mix, 1/4 grid and 3/4 pv1. See "the channel cost
    buckets are the cost ledger" in engine-calculations.md.
    """

    grid = Grid(300, price=PRICE)
    pv1 = Pv(900)
    pv2 = Pv(-50)
    bat1 = Battery(-250)

    @expect("combined_consumption_cost_rate")
    def test_consumption_cost(self):
        """Consumption pays for its 225 W of grid power.

        The 900 W base load is 1/4 grid: 0.225 kW × 3/10 = 27/400 EUR/h. Its
        pv1 power is free at the margin.
        """
        return F(27, 400)

    @expect("combined_charging_cost_rate")
    def test_charging_cost(self):
        """Charging pays for bat1's 62.5 W of grid power.

        bat1 charges at 250 W, 1/4 of it grid: 0.0625 kW × 3/10 = 3/160 EUR/h.
        """
        return F(3, 160)

    @expect("combined_standby_cost_rate")
    def test_standby_cost(self):
        """Standby pays for pv2's 12.5 W of grid power.

        pv2 draws 50 W, 1/4 of it grid: 0.0125 kW × 3/10 = 3/800 EUR/h.
        """
        return F(3, 800)

    @expect("combined_export_cost_rate")
    def test_export_cost(self):
        """Export costs nothing.

        The grid is importing, so nothing is exported.
        """
        return 0

    @expect("combined_coe_rate")
    def test_coe_rate(self):
        """The marginal channel costs add up to the cost of the import.

        27/400 + 3/160 + 3/800 + 0 = 9/100 EUR/h, exactly 300 W at
        3/10 EUR/kWh: every watt bought is counted once.
        """
        return F(9, 100)

    @expect("combined_levelized_consumption_cost_rate")
    def test_levelized_consumption_cost(self):
        """Levelized, consumption also pays for its pv1 power.

        225 W of grid at 3/10 plus 675 W of pv1 at 1/10: 27/200 EUR/h.
        """
        return F(27, 200)

    @expect("combined_levelized_charging_cost_rate")
    def test_levelized_charging_cost(self):
        """Levelized, charging pays for its grid and pv1 power.

        62.5 W of grid at 3/10 plus 187.5 W of pv1 at 1/10: 3/80 EUR/h.
        """
        return F(3, 80)

    @expect("combined_levelized_standby_cost_rate")
    def test_levelized_standby_cost(self):
        """Levelized, standby pays for its grid and pv1 power.

        12.5 W of grid at 3/10 plus 37.5 W of pv1 at 1/10: 3/400 EUR/h.
        """
        return F(3, 400)

    @expect("combined_lcoe_rate")
    def test_lcoe_rate(self):
        """The levelized channel costs add up to the cost of all gross power.

        27/200 + 3/80 + 3/400 = 9/50 EUR/h: the import (0.09) plus pv1's
        900 W at 1/10 (0.09).
        """
        return F(9, 50)


class TestOperatingCostHasTwoViews(Home):
    """Decision: operating cost has a channel view and a device view.

    The channel view counts only battery charging; the device view counts
    what every PV system and battery itself draws, so pv1's standby shows up
    only there. See "operating cost has a channel view and a device view" in
    engine-calculations.md.
    """

    grid = Grid(300, price=PRICE)
    pv1 = Pv(-20)

    @expect("combined_charging_cost_rate")
    def test_charging_cost(self):
        """The channel view reads 0: no battery is charging.

        pv1's standby draw is not charging, so it does not count here.
        """
        return 0

    @expect("combined_device_operating_cost_rate")
    def test_device_operating_cost(self):
        """The device view counts pv1's standby draw.

        pv1's 20 W come from the grid: 0.02 kW × 3/10 = 3/500 EUR/h.
        """
        return F(3, 500)

    @expect("source_adapters_coo_rates")
    def test_per_device_operating_cost(self):
        """pv1's own operating cost is the whole 3/500 EUR/h.

        The device view is the sum of these per-device costs, and pv1 is the
        only PV system or battery.
        """
        return {"pv1": F(3, 500)}
