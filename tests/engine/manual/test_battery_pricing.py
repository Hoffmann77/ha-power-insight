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
    """Decision: a battery pays for its energy when it charges.

    This is the charging half: bat1 takes 400 W, half grid and half pv1, and
    its saving is minus what that costs. See "a battery's energy cost is
    booked when it charges" in engine-calculations.md.
    """

    grid = Grid(500, price=PRICE)
    pv1 = Pv(500)
    bat1 = Battery(-400)

    @expect("adapters_saving_rates")
    def test_saving(self):
        """While charging, bat1's saving is negative.

        Its 200 W of grid cost 0.2 kW × 3/10 = 3/50 EUR/h, so it saves −3/50.
        pv1 saves 0.3 × 3/10 = 9/100 on the 300 W of base load it serves; its
        power into bat1 earns nothing yet.
        """
        return {"pv1": F(9, 100), "bat1": F(-3, 50)}

    @expect("adapters_levelized_saving_rates")
    def test_levelized_saving(self):
        """Levelized, bat1 also pays for its pv1 half.

        bat1: −(0.2 × 3/10 + 0.2 × 1/10) = −2/25 EUR/h. pv1 saves the tariff
        less its LCOE on 300 W: 0.3 × (3/10 − 1/10) = 3/50.
        """
        return {"pv1": F(3, 50), "bat1": F(-2, 25)}


class TestBatteryDischargeSavesTheFullTariff(Home):
    """Decision: a discharging battery saves the full tariff, less only its LCOS.

    This is the discharging half: bat1 serves 300 W of the house, and its
    energy was already paid for when it charged. See "a battery's energy cost
    is booked when it charges" in engine-calculations.md.
    """

    grid = Grid(200, price=PRICE)
    pv1 = Pv(0)
    bat1 = Battery(300)

    @expect("adapters_saving_rates")
    def test_saving(self):
        """While discharging, bat1 saves the full grid tariff.

        0.3 kW × 3/10 = 9/100 EUR/h. Idle pv1 reads 0 rather than being left
        out, so its sensor stays available.
        """
        return {"pv1": 0, "bat1": F(9, 100)}

    @expect("adapters_levelized_saving_rates")
    def test_levelized_saving(self):
        """Levelized, bat1 saves the tariff less its LCOS.

        0.3 kW × (3/10 − 3/20) = 9/200 EUR/h. Idle pv1 again reads 0.
        """
        return {"pv1": 0, "bat1": F(9, 200)}


class TestDischargePriceIsTheFlatLcos(Home):
    """Decision: a discharging battery costs 0 at the margin and its LCOS levelized.

    Its energy cost was booked when it charged. Same home as above, but these
    maps list only supplying devices, so idle pv1 is absent. See "the dynamic
    price falls back to the flat LCOS on discharge" in engine-calculations.md.
    """

    grid = Grid(200, price=PRICE)
    pv1 = Pv(0)
    bat1 = Battery(300)

    @expect("source_adapters_dynamic_coe")
    def test_dynamic_coe(self):
        """At the margin, bat1's power costs nothing.

        The grid costs its tariff, 3/10 EUR/kWh; bat1 costs 0 because it paid
        when it charged. Idle pv1 is not listed.
        """
        return {"grid": PRICE, "bat1": 0}

    @expect("source_adapters_dynamic_lcoe")
    def test_dynamic_lcoe(self):
        """Levelized, bat1 is priced at its flat LCOS.

        bat1 costs 3/20 EUR/kWh, not the price of the mix it charged on, which
        a single snapshot cannot know.
        """
        return {"grid": PRICE, "bat1": F(3, 20)}
