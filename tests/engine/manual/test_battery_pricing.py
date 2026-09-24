"""Battery pricing: when a battery's energy is paid for, and at what price.

A battery charges on one mix of power and discharges it later, but the engine
only ever sees the current snapshot. So it books the cost of the energy when
the battery charges, and prices the discharge at the battery's flat *LCOS*
(levelized cost of storage, its lifetime cost per kWh delivered). Rates are
in EUR per hour; *marginal* figures count only what costs money right now,
*levelized* ones also price local power at its lifetime cost. See "a
battery's energy cost is booked when it charges" and "Prices for a
discharging battery" in ``docs/dev/engine-calculations.md``.

Prices throughout: the grid tariff is 3/10 EUR/kWh, a PV system's LCOE 1/10
and a battery's LCOS 3/20 (the device defaults).
"""

from __future__ import annotations

from fractions import Fraction as F

from tests.engine.home import Battery, Grid, Home, Pv, expect

PRICE = F(3, 10)


class TestBatteryPaysWhenItCharges(Home):
    """Decision: a battery's energy cost is booked when it charges, and its
    discharge is valued at the full tariff it displaces less only its own LCOS
    (engine-calculations.md, "a battery's energy cost is booked when it
    charges").

    The charging half. bat1 takes 400 W of a half-grid, half-pv1 mix: 200 W
    each. Its saving is minus what that cost: −0.2 × 3/10 at the margin, and
    −(0.2 × 3/10 + 0.2 × 1/10) levelized.
    """

    grid = Grid(500, price=PRICE)
    pv1 = Pv(500)
    bat1 = Battery(-400)

    @expect("adapters_saving_rates")
    def test_saving(self):
        """While charging, bat1's saving is negative: it pays for its grid power.

        Supply is half grid, half pv1, and bat1 takes 400 W of it: 200 W
        from the grid, which costs 0.2 kW × 3/10 = 3/50 EUR/h now, so its
        saving is −3/50. pv1 saves 0.3 × 3/10 = 9/100 for the 300 W of base
        load it serves; the 200 W it puts into the battery earn nothing yet.
        """
        return {"pv1": F(9, 100), "bat1": F(-3, 50)}

    @expect("adapters_levelized_saving_rates")
    def test_levelized_saving(self):
        """Levelized, bat1 also pays for the pv1 half of its charge.

        bat1: −(0.2 × 3/10 + 0.2 × 1/10) = −2/25 EUR/h. pv1 saves on its
        300 W of base load the tariff less its own LCOE:
        0.3 × (3/10 − 1/10) = 3/50.
        """
        return {"pv1": F(3, 50), "bat1": F(-2, 25)}


class TestBatteryDischargeSavesTheFullTariff(Home):
    """Decision: a battery's energy cost is booked when it charges, and its
    discharge is valued at the full tariff it displaces less only its own LCOS
    (engine-calculations.md, "a battery's energy cost is booked when it
    charges").

    The discharging half. pv1 is idle; bat1 discharges 300 W into a 500 W base
    load beside 200 W of grid, so it serves 300 W. Its energy was paid for
    when it charged, so at the margin it saves the full tariff: 0.3 × 3/10.
    Levelized it carries only its LCOS: 0.3 × (3/10 − 3/20). pv1 reads 0, not
    absent.
    """

    grid = Grid(200, price=PRICE)
    pv1 = Pv(0)
    bat1 = Battery(300)

    @expect("adapters_saving_rates")
    def test_saving(self):
        """While discharging, bat1 saves the full grid tariff.

        It serves 300 W of the house, and what that energy cost was already
        booked when it charged, so nothing is subtracted now:
        0.3 kW × 3/10 = 9/100 EUR/h. Idle pv1 is listed at 0 rather than
        left out, so its sensor stays available.
        """
        return {"pv1": 0, "bat1": F(9, 100)}

    @expect("adapters_levelized_saving_rates")
    def test_levelized_saving(self):
        """Levelized, bat1's saving is the tariff less its own LCOS.

        0.3 kW × (3/10 − 3/20) = 9/200 EUR/h. Idle pv1 again reads 0.
        """
        return {"pv1": 0, "bat1": F(9, 200)}


class TestDischargePriceIsTheFlatLcos(Home):
    """Decision: a discharging battery's dynamic price is its flat LCOS, and
    its marginal price is 0 — its energy cost was booked when it charged
    (engine-calculations.md, "the dynamic price falls back to the flat LCOS on
    discharge").

    The same home as the discharge above; only the sources appear, so idle
    pv1 does not.
    """

    grid = Grid(200, price=PRICE)
    pv1 = Pv(0)
    bat1 = Battery(300)

    @expect("source_adapters_dynamic_coe")
    def test_dynamic_coe(self):
        """At the margin, the discharging battery's power costs nothing.

        This map prices each supplying device right now. The grid costs its
        tariff, 3/10 EUR/kWh; bat1 costs 0, because its energy was paid for
        when it charged. Idle pv1 is not supplying, so it is not listed.
        """
        return {"grid": PRICE, "bat1": 0}

    @expect("source_adapters_dynamic_lcoe")
    def test_dynamic_lcoe(self):
        """Levelized, the discharging battery is priced at its flat LCOS.

        The grid still costs 3/10; bat1 costs its LCOS of 3/20 EUR/kWh,
        not the price of the mix it once charged on, which a single
        snapshot cannot know.
        """
        return {"grid": PRICE, "bat1": F(3, 20)}
