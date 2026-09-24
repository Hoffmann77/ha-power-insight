"""Edge readings: what the engine publishes when readings are missing or odd.

A sensor can drop out (its reading is ``None``), and unsynchronised sensors
can report a moment that cannot physically happen. The engine must then
publish *nothing* (``None``) where a value cannot be known, a confident 0
where it can, and never divide by zero. *Gross power* is the total all
sources supply; much of what the engine publishes is derived from it. See
"Gross power and its shares" in ``docs/dev/engine-calculations.md``.
"""

from __future__ import annotations

from fractions import Fraction as F

from tests.engine.home import Battery, Consumer, Grid, Home, Pv, expect


class TestUnavailableMeterPublishesNothing(Home):
    """Decision: a missing meter makes everything built on it unknown.

    Without the grid, gross power and everything derived from it is ``None``.
    Totals over devices the house does not have stay a known 0. See "gross
    power is None if any inflow sensor is unavailable" in
    engine-calculations.md.
    """

    grid = Grid(None, price=F(3, 10))

    @expect("gross_power")
    def test_gross_power(self):
        """Gross power is unknown, so it is ``None``.

        The grid is the only source and its meter is missing. Publishing 0
        would falsely claim the house draws nothing.
        """
        return None

    @expect("combined_grid_import")
    def test_combined_grid_import(self):
        """The grid import is unknown.

        It is read directly from the missing meter.
        """
        return None

    @expect("combined_consumption")
    def test_combined_consumption(self):
        """Consumption is unknown.

        It is derived from gross power, which is unknown.
        """
        return None

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """Provenance is ``None``, not an empty map.

        An empty map would claim that no device drew anything.
        """
        return None

    @expect("source_adapters_coe_rate")
    def test_source_coe_rate(self):
        """The per-source cost rates are ``None`` as a whole.

        A per-device map with no gross power behind it is unknowable, not
        empty: ``{}`` would read as "no such device".
        """
        return None

    @expect("combined_coe_rate")
    def test_combined_coe_rate(self):
        """The cost rate is unknown, not free.

        It needs the import; 0 EUR/h would claim the power cost nothing.
        """
        return None

    @expect("combined_production")
    def test_combined_production(self):
        """Production is a known 0: there is no PV system.

        It is a sum over PV systems, so the missing grid meter does not
        affect it.
        """
        return 0

    @expect("combined_charging_power")
    def test_combined_charging_power(self):
        """Charging power is a known 0: there is no battery.

        It is a sum over batteries, and there are none.
        """
        return 0

    @expect("combined_standby_power")
    def test_combined_standby_power(self):
        """Standby power is a known 0: there is no PV system.

        Standby is what idle PV systems draw, and there are none.
        """
        return 0


class TestZeroGrossPowerGuardsEveryRatio(Home):
    """Decision: with zero gross power every ratio is 0, not a division by zero.

    The grid reports a 500 W export while nothing produces: impossible, but
    unsynchronised sensors can report it for an instant. See "Gross power and
    its shares" in engine-calculations.md.
    """

    grid = Grid(-500, price=F(3, 10))

    @expect("gross_power")
    def test_gross_power(self):
        """Gross power is 0.

        An exporting grid is not a source and there is no other device, even
        though 500 W are reported leaving the house.
        """
        return 0

    @expect("gross_power_export_ratio")
    def test_gross_power_export_ratio(self):
        """The export ratio, 500 W / 0 W, is 0.

        With nothing supplied there is no fraction to publish, so the engine
        publishes 0 instead of failing.
        """
        return 0

    @expect("gross_power_consumption_ratio")
    def test_gross_power_consumption_ratio(self):
        """The consumption ratio, 0 W / 0 W, is 0.

        Gross power is 0, so the ratio is guarded instead of dividing by zero.
        """
        return 0

    @expect("gross_power_charging_ratio")
    def test_gross_power_charging_ratio(self):
        """The charging ratio, 0 W / 0 W, is 0.

        Gross power is 0, so the ratio is guarded instead of dividing by zero.
        """
        return 0

    @expect("gross_power_standby_ratio")
    def test_gross_power_standby_ratio(self):
        """The standby ratio, 0 W / 0 W, is 0.

        Gross power is 0, so the ratio is guarded instead of dividing by zero.
        """
        return 0

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The grid's row is all zeros.

        No source supplies anything, so the export drew nothing from anyone:
        a share of nothing is nothing. Unlike with a missing meter this is
        known, so the map is published.
        """
        return {"grid": {"grid": 0}}


class TestAnIdleDeviceKeepsItsKeys(Home):
    """Decision: a map keys every device of its family, and says what an
    idle one reads.

    A night-time snapshot: the house imports 500 W, the PV system and the
    battery read 0 W, and a plug draws 200 W. The idle devices keep their
    keys everywhere; what they read depends on the quantity. See "a map keys
    every device of its family" in engine-calculations.md.
    """

    grid = Grid(500, price=F(3, 10))
    pv1 = Pv(0)
    bat1 = Battery(0)
    plug = Consumer(-200)

    @expect("source_adapters_consumption_power")
    def test_consumption_power(self):
        """An amount reads 0 for an idle source.

        The grid supplies all 500 W of consumption; pv1 and bat1 supplied
        nothing, which is a true 0 W — not a missing value.
        """
        return {"grid": 500, "pv1": 0, "bat1": 0}

    @expect("source_adapters_consumption_ratios")
    def test_consumption_ratios(self):
        """A ratio over nothing reads 0.

        The grid's 500 W all went to consumption, a ratio of 1. pv1 produced
        nothing, so its ratio is 0 W over 0 W: by convention a share of
        nothing is nothing, so the sensor shows 0 % at night, not unknown.
        """
        return {"grid": 1, "pv1": 0, "bat1": 0}

    @expect("source_adapters_dynamic_lcoe")
    def test_dynamic_lcoe(self):
        """A price with nothing delivered reads nothing at all.

        The grid delivers at its tariff of 3/10 EUR/kWh. pv1 and bat1 deliver
        nothing, so they have no price: 0 would claim their energy was free.
        """
        return {"grid": F(3, 10), "pv1": None, "bat1": None}

    @expect("sink_adapters_coo_rates")
    def test_sink_coo_rates(self):
        """Every adapter has an operating cost, 0 unless it is drawing.

        The plug draws 0.2 kW of grid power at 3/10 EUR/kWh: 3/50 EUR/h. The
        grid, pv1 and bat1 draw nothing, so they cost a true 0.
        """
        return {"grid": 0, "pv1": 0, "bat1": 0, "plug": F(3, 50)}

    @expect("sink_adapters_consumption_shares")
    def test_consumption_shares(self):
        """Only consumers are keyed, each by its share of consumption.

        The plug draws 200 W of the 500 W consumed: 2/5. The rest is the
        unmetered base load, which has its own properties.
        """
        return {"plug": F(2, 5)}


class TestUnavailableConsumerKeepsGrossPower(Home):
    """Decision: a missing consumer reading does not make gross power unknown.

    Only a missing inflow sensor (grid, PV or battery) does. The plug's draw
    simply becomes part of the base load. See "gross power is None if any
    inflow sensor is unavailable" in engine-calculations.md.
    """

    grid = Grid(500, price=F(3, 10))
    plug = Consumer(None)

    @expect("gross_power")
    def test_gross_power(self):
        """Gross power is still 500 W.

        It adds up what sources supply, and a consumer is not a source.
        """
        return 500

    @expect("combined_consumption")
    def test_combined_consumption(self):
        """Consumption is 500 W.

        All the power supplied is used in the house.
        """
        return 500

    @expect("home_base_load_power")
    def test_home_base_load_power(self):
        """All 500 W count as base load.

        The plug's draw can no longer be told apart from the rest of the
        house.
        """
        return 500

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The plug's row is unknown.

        It has no reading, so where its power came from cannot be said — not
        even that it drew none. The grid is importing, not drawing, so its row
        is all zeros; the base load is published through its own properties.
        """
        return {"plug": None}


class TestAMissingPriceBlanksOnlyWhatNeedsIt(Home):
    """Decision: a missing grid tariff blanks only the values that need it.

    The house imports 300 W with no known tariff. pv1 makes 1000 W; bat1 may
    charge from pv1 only and takes 600 W of it; the plug draws the other 700 W:
    400 W of PV and the 300 W import. See "a missing price blanks only what
    needs it" in engine-calculations.md.
    """

    grid = Grid(300, price=None)
    pv1 = Pv(1000)
    bat1 = Battery(-600, charge_from=(pv1,))
    plug = Consumer(-700)

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """Provenance is untouched: routing never depends on a price.

        bat1 is all pv1. The plug has 400 W of pv1 and the 300 W import, so
        4/7 and 3/7.
        """
        return {"bat1": {"pv1": 1}, "plug": {"grid": F(3, 7), "pv1": F(4, 7)}}

    @expect("sink_adapters_lcoo_rates")
    def test_sink_lcoo_rates(self):
        """bat1's levelized cost is known; the plug's is not.

        bat1 draws 0.6 kW of pv1 at its LCOE of 1/10 EUR/kWh: 3/50 EUR/h, no
        tariff needed. The plug's 300 W of import needs the tariff, so its
        cost is unknown — and published as nothing, not guessed.
        """
        return {"bat1": F(3, 50), "plug": None}

    @expect("combined_coe_rate")
    def test_combined_coe_rate(self):
        """The cost of the import is unknown.

        300 W imported at an unknown tariff has no knowable cost.
        """
        return None

    @expect("adapters_saving_rates")
    def test_saving_rates(self):
        """pv1's saving needs the tariff; bat1's marginal cost does not.

        pv1 served 400 W that would otherwise have been imported, worth an
        unknown tariff. bat1 charged on PV, whose marginal price is 0 whatever
        the tariff, so it cost 0.
        """
        return {"pv1": None, "bat1": 0}
