"""Battery pricing: when a battery's energy is paid for, and at what price.

A battery charges on one mix of power and discharges it later, but the engine
only ever sees the current snapshot. So it books the cost of the energy when
the battery charges, and prices the discharge at the battery's flat *LCOS*
(levelized cost of storage, its lifetime cost per kWh delivered). Rates are
in EUR per hour; *marginal* figures count only what costs money right now,
*levelized* ones also price local power at its lifetime cost. See "a
battery's energy cost is booked when it charges", "a battery pays for local
energy what it was worth elsewhere" and "Prices for a discharging battery" in
``docs/dev/engine-calculations.md``.

What a battery pays for energy from a local source is what that energy would
have been worth in the home without the battery, every other reading as it
is: first it would have covered the grid import (the tariff), then been
exported up to the grid's export limit (the source's feed-in rate, if it may
export), and the rest curtailed (nothing). The source receives exactly what
the battery pays, so the home's combined saving never moves.

Prices throughout: the grid tariff is 3/10 EUR/kWh, a PV system's LCOE 1/10
and a battery's LCOS 3/20 (the device defaults); a feed-in rate is 2/25.
"""

from __future__ import annotations

from fractions import Fraction as F

from tests.engine.home import Battery, Grid, Home, Pv, expect

PRICE = F(3, 10)
FEED_IN = F(2, 25)


class TestBatteryPaysWhenItCharges(Home):
    """Decision: a battery pays for its energy when it charges.

    This is the charging half: bat1 takes 400 W, half grid and half pv1, and
    its saving is minus what that costs. The house imports 500 W at the same
    time, so without bat1 its 200 W of pv1 would have replaced import: they
    cost the tariff too, and pv1 is paid it. See "a battery's energy cost is
    booked when it charges" in engine-calculations.md.
    """

    grid = Grid(500, price=PRICE)
    pv1 = Pv(500)
    bat1 = Battery(-400)

    @expect("adapters_saving_rates")
    def test_saving(self):
        """While charging, bat1's saving is negative: all 400 W at the tariff.

        Its 200 W of grid cost 0.2 kW × 3/10 = 3/50 EUR/h. The import left
        once those are freed is 300 W, enough for all 200 W of pv1, so those
        cost 3/50 too: bat1 saves −3/25. pv1 saves 0.3 × 3/10 = 9/100 on the
        300 W of base load it serves, plus the 3/50 bat1 paid it: 3/20.
        """
        return {"pv1": F(3, 20), "bat1": F(-3, 25)}

    @expect("adapters_levelized_saving_rates")
    def test_levelized_saving(self):
        """Levelized, bat1 pays the same; pv1 carries its own LCOE on both parts.

        bat1: −3/25 EUR/h, as at the margin — what pv1's energy was worth
        elsewhere does not depend on what it cost pv1 to make. pv1: the tariff
        less its LCOE on its 500 W, 0.5 × (3/10 − 1/10) = 1/10.
        """
        return {"pv1": F(1, 10), "bat1": F(-3, 25)}

    @expect("combined_levelized_saving_rate")
    def test_combined_levelized_saving(self):
        """The payment only moves money between the two: the home saves as before.

        Before the battery paid its source, bat1 read −(0.2 × 3/10 + 0.2 ×
        1/10) = −2/25 and pv1 0.3 × (3/10 − 1/10) = 3/50: −1/50 in total.
        Now −3/25 + 1/10 = −1/50 — the same.
        """
        return F(-1, 50)


class TestStoredPvIsPricedAtItsFeedIn(Home):
    """Decision: a battery pays for local energy what it was worth elsewhere.

    Row 1 of the matrix: the house exports. pv1 makes 1300 W and may export at
    2/25 EUR/kWh: 300 W feed the base load, bat1 stores 600 W and 400 W are
    exported. Without bat1, those 600 W would have been exported too, so bat1
    pays pv1 the feed-in rate for them. See "a battery pays for local energy
    what it was worth elsewhere" in engine-calculations.md.
    """

    grid = Grid(-400, price=PRICE)
    pv1 = Pv(1300, exports=True, export_comp=FEED_IN)
    bat1 = Battery(-600)

    @expect("adapters_saving_rates")
    def test_saving(self):
        """bat1 pays the feed-in rate; pv1 earns it on top of the load it serves.

        bat1: −0.6 kW × 2/25 = −6/125 EUR/h. pv1: 0.3 × 3/10 = 9/100 for the
        base load, plus 6/125 from bat1: 69/500.
        """
        return {"pv1": F(69, 500), "bat1": F(-6, 125)}

    @expect("adapters_levelized_saving_rates")
    def test_levelized_saving(self):
        """Levelized, pv1 carries its LCOE on the stored watts, so it loses on them.

        bat1 still pays −6/125. pv1: 0.3 × (3/10 − 1/10) = 3/50 on the base
        load, and 0.6 × (2/25 − 1/10) = −3/250 on the stored watts — a feed-in
        rate below its LCOE is a fact about pv1, not about bat1: 6/125.
        """
        return {"pv1": F(6, 125), "bat1": F(-6, 125)}

    @expect("combined_saving_rate")
    def test_combined_saving(self):
        """The home saves only what pv1's base load avoided: 9/100 EUR/h.

        The payment cancels between the two devices: 69/500 − 6/125 = 9/100.
        """
        return F(9, 100)


class TestStoredPvCoversTheImportFirst(Home):
    """Decision: a battery pays for local energy what it was worth elsewhere.

    Rows 2 and 7 of the matrix: the house buys from the grid while bat1, which
    may charge from pv1 only, stores 800 W of it. Without bat1, 300 W of those
    would have replaced the import and 500 W would have been exported. See "a
    battery pays for local energy what it was worth elsewhere" in
    engine-calculations.md.
    """

    grid = Grid(300, price=PRICE)
    pv1 = Pv(1000, exports=True, export_comp=FEED_IN)
    bat1 = Battery(-800, charge_from=(pv1,))

    @expect("adapters_saving_rates")
    def test_saving(self):
        """3/8 of the stored watts at the tariff, 5/8 at the feed-in rate.

        That is 3/8 × 3/10 + 5/8 × 2/25 = 13/80 EUR/kWh, so bat1 pays
        0.8 × 13/80 = 13/100 EUR/h. pv1 serves 200 W of the 500 W base load:
        0.2 × 3/10 = 3/50, plus the 13/100: 19/100.
        """
        return {"pv1": F(19, 100), "bat1": F(-13, 100)}


class TestTheExportLimitCurtailsTheRest(Home):
    """Decision: a battery pays for local energy what it was worth elsewhere.

    The grid connection takes at most 800 W and already takes 500 W, so of the
    1000 W bat1 stores from pv1, only 300 W could have been exported without
    it; the other 700 W would have been curtailed and are worth nothing. See
    "a battery pays for local energy what it was worth elsewhere" in
    engine-calculations.md.
    """

    grid = Grid(-500, price=PRICE, export_limit=800)
    pv1 = Pv(1500, exports=True, export_comp=FEED_IN)
    bat1 = Battery(-1000)

    @expect("adapters_saving_rates")
    def test_saving(self):
        """Only the 300 W under the limit are paid, at the feed-in rate.

        0.3 kW × 2/25 = 3/125 EUR/h, which bat1 pays and pv1 earns. Nothing
        else is consumed in the house.
        """
        return {"pv1": F(3, 125), "bat1": F(-3, 125)}


class TestANegativeTariffIsPaidUnlessCurtailed(Home):
    """Decision: a battery pays for local energy what it was worth elsewhere.

    Row 3 of the matrix, curtailment off: the tariff is −1/20 EUR/kWh and the
    house imports 300 W while bat1 stores 300 W of pv1. Without bat1 those
    watts would have replaced import, losing the money the house is paid for
    importing — so bat1, which kept the house importing, is paid for them.
    See "a battery pays for local energy what it was worth elsewhere" in
    engine-calculations.md.
    """

    grid = Grid(300, price=F(-1, 20))
    pv1 = Pv(600)
    bat1 = Battery(-300, charge_from=(pv1,))

    @expect("adapters_saving_rates")
    def test_saving(self):
        """bat1 earns 0.3 × 1/20 = 3/200 EUR/h; pv1 pays it.

        pv1 also serves 300 W of the base load at the negative tariff,
        0.3 × (−1/20) = −3/200, and pays bat1 another 3/200: −3/100.
        """
        return {"pv1": F(-3, 100), "bat1": F(3, 200)}


class TestACurtailedPvSellsNoLowerThanNothing(Home):
    """Decision: a battery pays for local energy what it was worth elsewhere.

    Row 3 of the matrix, curtailment on: the same home as
    ``TestANegativeTariffIsPaidUnlessCurtailed``, but this home curtails pv1
    when its energy is worth less than nothing. Without bat1 it would have
    curtailed those 300 W, so they were worth nothing. Only the counterfactual
    is floored: what pv1 actually did is still valued as it happened. See "a
    battery pays for local energy what it was worth elsewhere" in
    engine-calculations.md.
    """

    grid = Grid(300, price=F(-1, 20))
    pv1 = Pv(600, curtails=True)
    bat1 = Battery(-300, charge_from=(pv1,))

    @expect("adapters_saving_rates")
    def test_saving(self):
        """bat1 pays nothing; pv1 keeps its loss on the load it really served.

        The stored watts are worth max(−1/20, 0) = 0. pv1's 300 W into the
        base load still displaced import at −1/20: −3/200 EUR/h.
        """
        return {"pv1": F(-3, 200), "bat1": 0}


class TestABatteryPaysAnotherBatteryTheSameWay(Home):
    """Decision: a battery pays for local energy what it was worth elsewhere.

    The rule holds for every local source, not only PV: bat2 stores 300 W of
    bat1's discharge while the house exports, and bat1 may export at 3/50
    EUR/kWh. Without bat2, those watts would have been exported. See "a
    battery pays for local energy what it was worth elsewhere" in
    engine-calculations.md.
    """

    grid = Grid(-200, price=PRICE)
    bat1 = Battery(500, exports=True, export_comp=F(3, 50))
    bat2 = Battery(-300, charge_from=(bat1,))

    @expect("adapters_saving_rates")
    def test_saving(self):
        """bat2 pays 0.3 kW × 3/50 = 9/500 EUR/h, and bat1 earns it.

        bat1 serves no load in the house, so the payment is all it saves.
        """
        return {"bat1": F(9, 500), "bat2": F(-9, 500)}


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
