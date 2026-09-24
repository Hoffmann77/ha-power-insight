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


class TestSinkWithOnlyIdleSourcesGetsZeros(Home):
    """Decision: a sink none of whose allowed sources supply gets a row of zeros.

    bat1 may only use pv1, which is drawing standby, so nothing is attributed
    to bat1 and its whole draw is the deficit. See "a broken restriction is
    reported, not hidden" in engine-calculations.md.
    """

    grid = Grid(1000)
    pv1 = Pv(-20)
    bat1 = Battery(-400, charge_from=(pv1,))
    cons1 = Consumer(-100)

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """bat1's row is all zeros; the other sinks run on the grid.

        The engine does not invent a grid supply for bat1. pv1's 20 W standby
        and cons1's 100 W are unrestricted and all grid.
        """
        return rows({
            "pv1": {"grid": 20},
            "bat1": {"grid": 0},
            "cons1": {"grid": 100},
        })

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """bat1's whole 400 W draw is its deficit.

        None of it could come from a source bat1 is allowed to use.
        """
        return {"bat1": 400}


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
