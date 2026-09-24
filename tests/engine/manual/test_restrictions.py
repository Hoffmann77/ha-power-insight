"""Restrictions: what they mean, and what happens when one cannot hold.

A restriction limits the sources a sink may draw from: a battery's
``charge_from``, a consumer's ``power_from``, and — implicitly — the export,
which may only take power from devices allowed to export. The meters can
contradict a restriction (a "PV only" battery charging at night); the engine
then relaxes it, attributes the watts anyway, and reports the shortfall as the
sink's *restriction deficit* (``sink_adapters_restriction_deficit``, in
watts). See "a broken restriction is reported, not hidden" and
"``exports_power=False`` is a hard routing restriction" in
``docs/dev/engine-calculations.md``, and ``provenance.py`` for how the
expected provenance is written.
"""

from __future__ import annotations

from fractions import Fraction as F

from tests.engine.home import Battery, Consumer, Grid, Home, Pv, expect
from tests.engine.manual.provenance import rows


class TestBrokenRestrictionIsReported(Home):
    """Decision: a broken restriction is relaxed and reported as a deficit.

    cons1 may only use pv1, but draws 500 W while pv1 makes 300 W, so the
    other 200 W must be grid. See "a broken restriction is reported, not
    hidden" in engine-calculations.md.
    """

    grid = Grid(800)
    pv1 = Pv(300)
    cons1 = Consumer(-500, power_from=(pv1,))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """cons1 is given the grid power it was not allowed to use.

        pv1 covers only 300 W of cons1's 500 W, so the other 200 W are grid
        rather than left unaccounted for.
        """
        return rows({"cons1": {"grid": 200, "pv1": 300}})

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """The 200 W cons1 took from the grid is its deficit.

        This tells the user their energy manager is not doing what they
        configured: cons1 was meant to run on pv1 alone.
        """
        return {"cons1": 200}

    @expect("home_base_load_source_shares")
    def test_base_load_source_shares(self):
        """The base load runs entirely on the grid.

        cons1 used all of pv1, so the 600 W base load has only the grid left.
        """
        return {"grid": 1, "pv1": 0}


class TestASinkWithOnlyIdleSourcesIsRelaxed(Home):
    """Decision: a sink none of whose allowed sources supply is relaxed like
    any other broken restriction.

    bat1 may only use pv1, which is drawing standby rather than producing — a
    "PV only" battery topping up from the grid overnight. Its 400 W still came
    from somewhere: the grid. See "a broken restriction is reported, not
    hidden" in engine-calculations.md.
    """

    grid = Grid(1000, price=F(3, 10))
    pv1 = Pv(-20)
    bat1 = Battery(-400, charge_from=(pv1,))
    cons1 = Consumer(-100)

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """Every sink, bat1 included, runs on the grid.

        The grid is the only source, so bat1's 400 W, pv1's 20 W standby and
        cons1's 100 W are all grid.
        """
        return rows({
            "pv1": {"grid": 20},
            "bat1": {"grid": 400},
            "cons1": {"grid": 100},
        })

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """bat1's whole 400 W draw is its deficit.

        None of it could come from a source bat1 is allowed to use.
        """
        return {"bat1": 400}

    @expect("source_adapters_charging_power")
    def test_charging_power(self):
        """The charging channel carries all 400 W bat1 drew.

        It is charging, however the configuration says it should be powered,
        so it is not counted as household consumption.
        """
        return {"grid": 400}

    @expect("home_base_load_power")
    def test_home_base_load_power(self):
        """The base load is only what no meter measured.

        1000 W imported, less 20 + 400 + 100 W metered: 480 W. bat1's draw has
        a meter on it, so it is not part of the unmetered load.
        """
        return 480

    @expect("source_adapters_coo_rates")
    def test_operating_cost(self):
        """bat1 pays for what it charged.

        0.4 kW of grid at 3/10 EUR/kWh: 3/25 EUR/h. pv1's standby costs 0.02 kW
        at the same tariff: 3/500 EUR/h.
        """
        return {"pv1": F(3, 500), "bat1": F(3, 25)}


class TestTheSinkWithSomewhereElseToGoYields(Home):
    """Decision: when restrictions cannot all hold, the flexible sinks take the deficit.

    bat_c may only use east and gets all of it; bat_a and bat_b, which could
    use either, share west and take the shortfall. See "the sink with
    somewhere else to go is the one that yields" in engine-calculations.md.
    """

    grid = Grid(200)
    east = Pv(100)
    west = Pv(100)
    bat_a = Battery(-100, charge_from=(east, west))
    bat_b = Battery(-100, charge_from=(east, west))
    bat_c = Battery(-100, charge_from=(east,))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """bat_c gets its only permitted source, east, outright.

        The batteries want 300 W of PV but only 200 W exist. bat_a and bat_b
        get 50 W of west each and their other 50 W from the grid.
        """
        return rows({
            "bat_a": {"grid": 50, "east": 0, "west": 50},
            "bat_b": {"grid": 50, "east": 0, "west": 50},
            "bat_c": {"grid": 0, "east": 100, "west": 0},
        })

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """The 100 W shortfall is split evenly between bat_a and bat_b.

        Each reports 50 W; bat_c, which had nowhere else to go, reports none.
        """
        return {"bat_a": 50, "bat_b": 50}


class TestSameRestrictionSharesTheDeficit(Home):
    """Decision: sinks with the same restriction share a deficit in proportion to draw.

    cons1 and cons2 may both use only pv1 and pv2, and need 100 W more than
    the two make. Neither is more constrained, so neither takes the whole
    deficit. See "the sink with somewhere else to go is the one that yields" in
    engine-calculations.md.
    """

    grid = Grid(100)
    pv1 = Pv(100)
    pv2 = Pv(100)
    cons1 = Consumer(-100, power_from=(pv1, pv2))
    cons2 = Consumer(-200, power_from=(pv1, pv2))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """Both loads read the same mix: a third each of grid, pv1 and pv2.

        Together they get all 200 W of PV and the missing 100 W from the grid,
        split 100 : 200 by draw. So cons1 gets 100/3 W from each source and
        cons2 twice that.
        """
        return rows({
            "cons1": {"grid": F(100, 3), "pv1": F(100, 3), "pv2": F(100, 3)},
            "cons2": {"grid": F(200, 3), "pv1": F(200, 3), "pv2": F(200, 3)},
        })

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """The 100 W deficit is split 1 : 2, like the draws.

        cons1 reports 100/3 W and cons2 200/3 W. Blaming cons1 alone would
        treat the larger load as the more constrained one, which it is not.
        """
        return {"cons1": F(100, 3), "cons2": F(200, 3)}


class TestExportIsRestrictedToExporters(Home):
    """Decision: the export may only take power from devices allowed to export.

    bat1 has ``exports=False``, so the 300 W export is all pv1. See
    "exports_power=False is a hard routing restriction" in
    engine-calculations.md.
    """

    grid = Grid(-300)
    pv1 = Pv(500, exports=True)
    bat1 = Battery(200, exports=False)
    cons1 = Consumer(-400)

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The export takes nothing from bat1, which may not export.

        The export's 300 W are all pv1. cons1 takes the rest: pv1's other
        200 W and all 200 W of bat1.
        """
        return rows({
            "grid": {"pv1": 300, "bat1": 0},
            "cons1": {"pv1": 200, "bat1": 200},
        })



class TestAnExportNoDeviceMayFeedIsRelaxed(Home):
    """Decision: an export that no running device may feed is relaxed like any
    other broken restriction.

    bat1 may not export, yet the grid reads a 300 W export while bat1 is the
    only source. The 300 W still left the house, and bat1 is the only thing
    that can have supplied them. See "exports_power=False is a hard routing
    restriction" in engine-calculations.md.
    """

    grid = Grid(-300, price=F(3, 10))
    bat1 = Battery(500, exports=False, lcos=F(3, 20))
    plug = Consumer(-100)

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The export and the plug both run on bat1, the only source."""
        return rows({"grid": {"bat1": 300}, "plug": {"bat1": 100}})

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """The whole 300 W export is the deficit.

        None of it could come from a device allowed to export.
        """
        return {"grid": 300}

    @expect("source_adapters_export_power")
    def test_export_power(self):
        """The export channel carries the 300 W the meter saw leave."""
        return {"bat1": 300}

    @expect("home_base_load_power")
    def test_home_base_load_power(self):
        """The base load is what no meter measured: 500 − 300 − 100 = 100 W.

        The exported watts are not household consumption.
        """
        return 100

    @expect("adapters_saving_rates")
    def test_saving_rates(self):
        """bat1 saves the tariff only on what the house consumed.

        The plug's 100 W and the 100 W base load displaced imports: 0.2 kW at
        3/10 EUR/kWh is 3/50 EUR/h. The exported 300 W earn no saving, and no
        compensation either — bat1 may not export.
        """
        return {"bat1": F(3, 50)}