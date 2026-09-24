"""Savings: who is credited with the money local power saves.

A *saving* is booked per supplying device: what its power would have cost
from the grid, minus what it cost. A consumer running on that power gets an
*avoided cost* instead — the same euros, seen from the receiving end, which
must never be added to the saving. The unmetered *home base load* is
published through its own properties rather than as a device. Rates are in
EUR per hour; *levelized* figures price local power at its lifetime cost.
See "Savings are booked per device", "Corrections apply to prices, not to
results" and "The home base load is a device" in
``docs/dev/engine-calculations.md``.

Prices throughout: the grid tariff is 3/10 EUR/kWh and a PV system's LCOE
1/10 (the device default), unless a class says otherwise.
"""

from __future__ import annotations

from fractions import Fraction as F

from tests.engine.home import Battery, Consumer, Grid, Home, Pv, expect

PRICE = F(3, 10)


class TestConsumersGetAnAvoidedCost(Home):
    """Decision: a consumer gets an avoided cost, not a saving.

    The euros pv1 saves by feeding the house are its saving; the plug and the
    base load see the same euros as avoided cost, and the two are never
    summed. See "consumers do not get a saving, they get an avoided cost" in
    engine-calculations.md.
    """

    grid = Grid(200, price=PRICE)
    pv1 = Pv(600)
    plug = Consumer(-400)

    @expect("adapters_saving_rates")
    def test_saving(self):
        """Only pv1 has a saving; the plug has none.

        pv1's 600 W replace grid power: 0.6 kW × 3/10 = 9/50 EUR/h. Savings
        belong to the supplying device.
        """
        return {"pv1": F(9, 50)}

    @expect("combined_saving_rate")
    def test_combined_saving(self):
        """The house's total saving is pv1's saving, counted once.

        Adding the plug's avoided cost would count the same euros twice.
        """
        return F(9, 50)

    @expect("sink_adapters_avoided_cost_rates")
    def test_avoided_cost(self):
        """The plug avoided the grid price of its pv1 power.

        300 W of its 400 W came from pv1: 0.3 kW × 3/10 = 9/100 EUR/h.
        """
        return {"plug": F(9, 100)}

    @expect("home_base_load_avoided_cost_rate")
    def test_base_load_avoided_cost(self):
        """The base load avoided the same 9/100 EUR/h as the plug.

        It also draws 300 W of pv1. Plug and base load together avoid
        9/50 EUR/h, exactly pv1's saving.
        """
        return F(9, 100)


class TestBaseLoadHasItsOwnProperties(Home):
    """Decision: the base load has its own ``home_base_load_*`` properties.

    It never appears as a key in the ``sink_adapters_*`` maps, where an
    invented id could clash with a real device. See "the home base load gets
    its own properties, not a uid" in engine-calculations.md.
    """

    grid = Grid(500, price=PRICE)
    pv1 = Pv(0)
    plug = Consumer(-100)

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The provenance map has a row for the plug only.

        The base load is a sink too, but it is not listed here.
        """
        return {"plug": {"grid": 1}}

    @expect("sink_adapters_avoided_cost_rates")
    def test_avoided_cost(self):
        """The avoided-cost map also lists only the plug.

        The plug ran on the grid, so it avoided nothing.
        """
        return {"plug": 0}

    @expect("home_base_load_power")
    def test_base_load_power(self):
        """The base load's power is on its own property.

        500 W enter the house and the plug meters 100 W; the other 400 W are
        the base load.
        """
        return 400

    @expect("home_base_load_source_shares")
    def test_base_load_source_shares(self):
        """The base load's source mix is on its own property.

        pv1 is idle, so the base load is all grid.
        """
        return {"grid": 1}


class TestCorrectionFactorScalesTheLcoe(Home):
    """Decision: the correction factor scales the LCOE, not the finished saving.

    pv1's factor of 2 makes its energy twice as expensive, so its saving must
    go down. See "the factor multiplies the lcoe, never the finished number"
    in engine-calculations.md.
    """

    grid = Grid(200, price=PRICE)
    pv1 = Pv(600, correction_factor=2.0)

    @expect("adapters_levelized_saving_rates")
    def test_uncorrected(self):
        """Uncorrected, pv1 saves at its LCOE of 1/10.

        Its 600 W replace grid power: 0.6 kW × (3/10 − 1/10) = 3/25 EUR/h.
        """
        return {"pv1": F(3, 25)}

    @expect("adapters_levelized_saving_rates_corrected")
    def test_corrected(self):
        """Corrected, pv1 saves less, not more.

        The LCOE doubles to 2/10: 0.6 × (3/10 − 2/10) = 3/50 EUR/h. Doubling
        the saving instead would have given 6/25.
        """
        return {"pv1": F(3, 50)}


class TestBatteryFactorScalesItsOwnLcosOnly(Home):
    """Decision: a battery's factor scales its LCOS; its charging follows its sources.

    bat1 discharges at an LCOS of 1/10 corrected by 2. bat2 charges from pv1,
    whose LCOE of 1/10 is corrected by 3/2, and carries a factor of 3 of its
    own that must play no part: what bat2 pays to charge is pv1's energy, so
    pv1's factor prices it. Two batteries, because one cannot charge and
    discharge at once. See "the factor multiplies the lcoe, never the finished
    number" in engine-calculations.md.
    """

    grid = Grid(200, price=PRICE)
    pv1 = Pv(500, correction_factor=1.5)
    bat1 = Battery(400, lcos=F(1, 10), correction_factor=2.0)
    bat2 = Battery(-500, charge_from=(pv1,), correction_factor=3.0)

    @expect("adapters_levelized_saving_rates")
    def test_uncorrected(self):
        """Uncorrected, each battery is priced at its lifetime cost as entered.

        bat2 may only charge from pv1 and needs all of its 500 W, so the
        base load's 600 W come from the grid and bat1. bat1's 400 W displace
        grid power: 0.4 kW × (3/10 − 1/10) = 2/25 EUR/h. bat2 books its
        charging now: −0.5 kW × 1/10 = −1/20 EUR/h. pv1 only feeds the
        battery, and energy put into storage saves nothing until it comes
        out, so pv1 reads 0.
        """
        return {"bat1": F(2, 25), "bat2": F(-1, 20)}

    @expect("adapters_levelized_saving_rates_corrected")
    def test_corrected(self):
        """Corrected, bat1 saves less and bat2 pays pv1's corrected price.

        bat1's LCOS doubles to 1/5: 0.4 × (3/10 − 1/5) = 1/25 EUR/h, not the
        4/25 that doubling its saving would give. bat2 pays pv1's corrected
        LCOE of 3/20: −0.5 × 3/20 = −3/40 EUR/h. Applying bat2's own factor
        of 3 instead would have given −3/20.
        """
        return {"bat1": F(1, 25), "bat2": F(-3, 40)}

    @expect("source_adapters_lcoo_rates_corrected")
    def test_charging_cost(self):
        """bat2's operating cost is its charging, at pv1's corrected price.

        0.5 kW × 3/20 EUR/kWh = 3/40 EUR/h. The devices that only supply
        energy draw nothing and cost nothing to run.
        """
        return {"bat2": F(3, 40)}


class TestSavingsAreMeasuredWithoutTheDevice(Home):
    """Decision: a saving is measured against a home without the device.

    The house exports 300 W while pv1 also runs a 700 W plug. Without pv1
    those 700 W would have been imported, so they save the import tariff —
    not the 8 ct feed-in rate they could have been exported for. See "a
    saving is measured against a home without the device" in
    engine-calculations.md.
    """

    grid = Grid(-300, price=PRICE)
    pv1 = Pv(1000, exports=True, export_comp=F(2, 25))
    plug = Consumer(-700)

    @expect("adapters_saving_rates")
    def test_saving_rates(self):
        """The 700 W self-consumed save the import tariff.

        0.7 kW × 3/10 EUR/kWh = 21/100 EUR/h. At the feed-in rate it would
        have been 0.7 × 2/25 = 7/125, which is a different question.
        """
        return {"pv1": F(21, 100)}

    @expect("adapters_financial_return_rates")
    def test_financial_return_rates(self):
        """The exported 300 W are credited once, through the compensation.

        21/100 EUR/h saved plus 0.3 kW × 2/25 EUR/kWh = 3/125 EUR/h paid:
        117/500 EUR/h.
        """
        return {"pv1": F(117, 500)}
