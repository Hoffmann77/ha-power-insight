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

from tests.engine.home import Consumer, Grid, Home, Pv, expect

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
