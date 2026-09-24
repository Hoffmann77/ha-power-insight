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
    """Decision: an unavailable meter collapses everything derived from it to
    nothing, while a total over an empty device set stays zero
    (engine-calculations.md, "gross power is None if any inflow sensor is
    unavailable").

    The grid is the only inflow, so without it gross power is unknowable and
    so is everything built on it — published as nothing at all, never as a
    stale or invented number. Production, charging and standby are sums over
    devices this house does not have: the missing meter says nothing about
    them, so they stay a confident 0.
    """

    grid = Grid(None, price=F(3, 10))

    @expect("gross_power")
    def test_gross_power(self):
        """Gross power is unknown, so the engine publishes nothing.

        The grid meter is the house's only source and it has dropped out.
        Publishing 0 would claim the house draws nothing; ``None`` says the
        value cannot be known.
        """
        return None

    @expect("combined_grid_import")
    def test_combined_grid_import(self):
        """The grid import is read from the missing meter, so it is unknown."""
        return None

    @expect("combined_consumption")
    def test_combined_consumption(self):
        """Consumption is derived from gross power, so it is unknown too."""
        return None

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """Without gross power there is no provenance: nothing, not an empty map.

        An empty map would claim that no device drew anything; ``None`` says
        the answer is unknown.
        """
        return None

    @expect("combined_coe_rate")
    def test_combined_coe_rate(self):
        """The cost rate needs the import, so it is unknown rather than free.

        Publishing 0 EUR/h would claim the power cost nothing.
        """
        return None

    @expect("combined_production")
    def test_combined_production(self):
        """Total production is a known 0: the house has no PV system.

        It is a sum over the installed PV systems, and there are none, so
        the missing grid meter does not make it unknown.
        """
        return 0

    @expect("combined_charging_power")
    def test_combined_charging_power(self):
        """Total charging power is a known 0: the house has no battery.

        It is a sum over the installed batteries, and there are none.
        """
        return 0

    @expect("combined_standby_power")
    def test_combined_standby_power(self):
        """Total standby power is a known 0: the house has no PV system.

        Standby is what idle PV systems draw, and there are none installed.
        """
        return 0


class TestZeroGrossPowerGuardsEveryRatio(Home):
    """Decision: zero gross power guards every ratio to zero rather than
    dividing by zero, and with nothing providing there is no provenance
    (engine-calculations.md, "Gross power and its shares").

    The meter shows 500 W leaving while nothing produces — impossible, but
    exactly what unsynchronised sensors report for an instant. Gross power is
    0, so the export ratio is 500 / 0 and the others 0 / 0; every one reads 0.
    No source is providing, so no sink has a row.
    """

    grid = Grid(-500, price=F(3, 10))

    @expect("gross_power")
    def test_gross_power(self):
        """Gross power is 0: the grid is exporting and nothing produces.

        Gross power counts what sources supply. An exporting grid is not a
        source, and there is no other device, so the total is 0 — even
        though the meter reports 500 W leaving the house.
        """
        return 0

    @expect("gross_power_export_ratio")
    def test_gross_power_export_ratio(self):
        """The export ratio, 500 W / 0 W, is guarded to 0 instead of failing.

        The ratios say which fraction of gross power goes into each channel;
        with nothing supplied there is no fraction to publish but 0.
        """
        return 0

    @expect("gross_power_consumption_ratio")
    def test_gross_power_consumption_ratio(self):
        """The consumption ratio, 0 W / 0 W, is guarded to 0."""
        return 0

    @expect("gross_power_charging_ratio")
    def test_gross_power_charging_ratio(self):
        """The charging ratio, 0 W / 0 W, is guarded to 0."""
        return 0

    @expect("gross_power_standby_ratio")
    def test_gross_power_standby_ratio(self):
        """The standby ratio, 0 W / 0 W, is guarded to 0."""
        return 0

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """No source supplies anything, so no sink has a provenance row.

        Unlike with an unavailable meter the answer is known, so the map is
        published — empty.
        """
        return {}


class TestUnavailableConsumerKeepsGrossPower(Home):
    """Decision: gross power is unknowable only when an *inflow* sensor — grid,
    PV or battery — is unavailable; a consumer dropping out does not
    invalidate it (engine-calculations.md, "gross power is None if any inflow
    sensor is unavailable").

    The grid still reads 500 W, so gross power and self-consumption are known.
    The plug's sensor is gone: it is in no flow group, so it has no row, and
    its draw is simply part of the 500 W base load.
    """

    grid = Grid(500, price=F(3, 10))
    plug = Consumer(None)

    @expect("gross_power")
    def test_gross_power(self):
        """Gross power is still known: the missing plug is not a source.

        Gross power adds up what sources supply, and the grid still reads
        500 W. A consumer's reading never enters that sum.
        """
        return 500

    @expect("combined_consumption")
    def test_combined_consumption(self):
        """All 500 W supplied are consumed in the house."""
        return 500

    @expect("home_base_load_power")
    def test_home_base_load_power(self):
        """With the plug's reading gone, all 500 W count as base load.

        The base load is what the house uses without a working meter on it,
        and the plug's draw can no longer be told apart from the rest.
        """
        return 500

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The unavailable plug has no provenance row, so the map is empty.

        A device without a reading belongs to no flow group. The base load
        is published through its own properties, not in this map.
        """
        return {}
