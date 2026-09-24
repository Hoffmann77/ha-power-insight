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
    """Decision: a consumer running on PV is the same saved euro as the PV
    supplying it — credited to the PV as a saving and to the consumer only as
    an avoided cost, never both summed (engine-calculations.md, "consumers do
    not get a saving, they get an avoided cost").

    The raw mix is grid 1/4, pv1 3/4 of 800 W. The plug (400 W) and the base
    load (400 W) each take 300 W of pv1, avoiding 0.3 × 3/10 each. pv1 is
    credited with all 600 W: 0.6 × 3/10 — the same euro, counted once on each
    side. The plug has no saving entry at all.
    """

    grid = Grid(200, price=PRICE)
    pv1 = Pv(600)
    plug = Consumer(-400)

    @expect("adapters_saving_rates")
    def test_saving(self):
        """Only pv1 has a saving; the plug has no entry at all.

        pv1 supplies 600 W to the house that would otherwise have come from
        the grid: 0.6 kW × 3/10 = 9/50 EUR/h. Savings belong to supplying
        devices, so the plug does not appear.
        """
        return {"pv1": F(9, 50)}

    @expect("combined_saving_rate")
    def test_combined_saving(self):
        """The house's total saving is pv1's saving, counted once.

        Adding the plug's avoided cost on top would count the same euros
        twice, so the total is 9/50 EUR/h.
        """
        return F(9, 50)

    @expect("sink_adapters_avoided_cost_rates")
    def test_avoided_cost(self):
        """The plug avoided the grid price of the pv1 power it used.

        The plug draws 400 W, three quarters of it (300 W) from pv1, which
        would have cost 0.3 kW × 3/10 = 9/100 EUR/h from the grid.
        """
        return {"plug": F(9, 100)}

    @expect("home_base_load_avoided_cost_rate")
    def test_base_load_avoided_cost(self):
        """The base load avoided the same 9/100 EUR/h as the plug.

        It too draws 400 W, 300 W of it from pv1. Plug and base load
        together avoid 9/50 EUR/h — exactly pv1's saving, seen from the other
        side.
        """
        return F(9, 100)


class TestBaseLoadHasItsOwnProperties(Home):
    """Decision: the home base load is published through its own
    ``home_base_load_*`` properties and never as a key in the
    ``sink_adapters_*`` maps (engine-calculations.md, "the home base load gets
    its own properties, not a uid").

    No sun: the plug draws 100 W and the other 400 W are the base load, all
    from the grid. The sink maps name the plug alone.
    """

    grid = Grid(500, price=PRICE)
    pv1 = Pv(0)
    plug = Consumer(-100)

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The provenance map has a row for the plug and nothing else.

        The base load is a sink too, but it has no row here under an
        invented id — any such id could clash with a real device's name.
        """
        return {"plug": {"grid": 1}}

    @expect("sink_adapters_avoided_cost_rates")
    def test_avoided_cost(self):
        """The avoided-cost map also names only the plug.

        The plug ran on the grid, so it avoided nothing: 0 EUR/h.
        """
        return {"plug": 0}

    @expect("home_base_load_power")
    def test_base_load_power(self):
        """The base load's power is published on its own property.

        500 W enter the house and the plug meters 100 W of it; the other
        400 W are the unmetered base load.
        """
        return 400

    @expect("home_base_load_source_shares")
    def test_base_load_source_shares(self):
        """The base load's source mix is published on its own property.

        With pv1 idle the grid is the only source, so the base load is all
        grid.
        """
        return {"grid": 1}


class TestCorrectionFactorScalesTheLcoe(Home):
    """Decision: a device's correction factor multiplies its LCOE inside the
    saving, never the finished saving (engine-calculations.md, "the factor
    multiplies the lcoe, never the finished number").

    pv1's lifetime cost was edited so its energy costs twice as much. All
    600 W of it serve the 800 W base load. Uncorrected, it saves
    0.6 × (3/10 − 1/10) = 3/25; corrected, 0.6 × (3/10 − 2/10) = 3/50 — less,
    as dearer energy must. Scaling the result would have said 6/25.
    """

    grid = Grid(200, price=PRICE)
    pv1 = Pv(600, correction_factor=2.0)

    @expect("adapters_levelized_saving_rates")
    def test_uncorrected(self):
        """Before the correction, pv1 saves at its configured LCOE of 1/10.

        Its 600 W replace grid power at 3/10 and cost 1/10 to make:
        0.6 kW × (3/10 − 1/10) = 3/25 EUR/h.
        """
        return {"pv1": F(3, 25)}

    @expect("adapters_levelized_saving_rates_corrected")
    def test_corrected(self):
        """After doubling its cost, pv1 saves less, not more.

        The factor of 2 doubles the LCOE to 2/10 inside the bracket:
        0.6 × (3/10 − 2/10) = 3/50 EUR/h. Doubling the finished saving
        instead would have claimed 6/25 — dearer energy saving more.
        """
        return {"pv1": F(3, 50)}
