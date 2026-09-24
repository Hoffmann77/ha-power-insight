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

from tests.engine.home import Consumer, Grid, Home, expect


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
        """The provenance map is empty.

        No source supplies anything, so no sink has a row. Unlike with a
        missing meter this is known, so the map is published.
        """
        return {}


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
        """The provenance map is empty.

        The plug has no reading, so it has no row; the base load is published
        through its own properties.
        """
        return {}
