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
    """Decision: when the meter contradicts a restriction, the restriction is
    relaxed and the shortfall reported as a deficit (engine-calculations.md,
    "a broken restriction is reported, not hidden").

    cons1 may only use pv1, draws 500 W, and pv1 makes 300 W. The other 200 W
    came from somewhere — the grid, the only other source — and is reported as
    cons1's restriction deficit. The 600 W base load is all grid.
    """

    grid = Grid(800)
    pv1 = Pv(300)
    cons1 = Consumer(-500, power_from=(pv1,))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """cons1 is attributed the grid power it was not allowed to use.

        cons1 draws 500 W but pv1 makes only 300 W. The other 200 W must have
        come from the grid, so its row reads 300 W pv1 and 200 W grid rather
        than leaving 200 W unaccounted for.
        """
        return rows({"cons1": {"grid": 200, "pv1": 300}})

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """The 200 W cons1 took from a forbidden source is its deficit.

        This is how the engine tells the user that their energy manager is
        not doing what they configured: cons1 was set to run on pv1 alone.
        """
        return {"cons1": 200}

    @expect("home_base_load_source_shares")
    def test_base_load_source_shares(self):
        """The base load runs entirely on the grid.

        cons1 used every watt pv1 made, so the 600 W base load (1100 W
        supplied minus cons1's 500 W) has only the grid left.
        """
        return {"grid": 1, "pv1": 0}


class TestSinkWithOnlyIdleSourcesGetsZeros(Home):
    """Decision: a sink whose allowed sources are all idle collapses to an
    all-zeros row instead of being forced onto excluded sources, and its whole
    draw is reported as the deficit (engine-calculations.md, "a broken
    restriction is reported, not hidden").

    bat1 may only charge from pv1, which is drawing 20 W of standby and so is
    not a source at all. Nothing may be attributed to bat1; its 400 W is the
    deficit.
    """

    grid = Grid(1000)
    pv1 = Pv(-20)
    bat1 = Battery(-400, charge_from=(pv1,))
    cons1 = Consumer(-100)

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """bat1's row is all zeros; the unrestricted sinks run on the grid.

        bat1 may only charge from pv1, and pv1 is drawing standby rather
        than producing, so none of bat1's sources is supplying. The engine
        does not invent a grid supply for it: its row is all zeros. pv1's
        20 W standby and cons1's 100 W are unrestricted and all grid.
        """
        return rows({
            "pv1": {"grid": 20},
            "bat1": {"grid": 0},
            "cons1": {"grid": 100},
        })

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """bat1's whole 400 W draw is reported as its deficit.

        None of it could come from a source bat1 is allowed, so all of it is
        power that broke the restriction.
        """
        return {"bat1": 400}


class TestTheSinkWithSomewhereElseToGoYields(Home):
    """Decision: when no allocation honours every restriction, the most
    constrained sink is served first and the deficit falls on the sinks that
    had somewhere else to go (engine-calculations.md, "the sink with somewhere
    else to go is the one that yields").

    Three batteries want 300 W from east and west's 200 W. bat_c may only use
    east and takes all of it. bat_a and bat_b share west, 50 W each, and each
    takes its missing 50 W from the grid as a reported deficit.
    """

    grid = Grid(200)
    east = Pv(100)
    west = Pv(100)
    bat_a = Battery(-100, charge_from=(east, west))
    bat_b = Battery(-100, charge_from=(east, west))
    bat_c = Battery(-100, charge_from=(east,))

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The battery with one permitted source gets that source outright.

        The three batteries want 300 W of PV and only 200 W exist, so 100 W
        must come from the grid against someone's restriction. bat_c may use
        only east and takes all of it. bat_a and bat_b split west, 50 W each,
        and each takes its other 50 W from the grid.
        """
        return rows({
            "bat_a": {"grid": 50, "east": 0, "west": 50},
            "bat_b": {"grid": 50, "east": 0, "west": 50},
            "bat_c": {"grid": 0, "east": 100, "west": 0},
        })

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """The 100 W shortfall is blamed evenly on the two flexible batteries.

        bat_a and bat_b each report 50 W of deficit; bat_c, which had
        nowhere else to go, reports none.
        """
        return {"bat_a": 50, "bat_b": 50}


class TestExportIsRestrictedToExporters(Home):
    """Decision: ``exports_power=False`` is a hard routing restriction — an
    exporting grid is a sink allowed only the sources that may export
    (engine-calculations.md, "exports_power=False is a hard routing
    restriction").

    bat1 discharges 200 W but may not feed the grid, so the 300 W export is
    all pv1. cons1 is unrestricted and takes what is left: pv1's other 200 W
    and all of bat1.
    """

    grid = Grid(-300)
    pv1 = Pv(500, exports=True)
    bat1 = Battery(200, exports=False)
    cons1 = Consumer(-400)

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """The export takes nothing from the battery that may not export.

        An exporting grid is a sink, allowed only sources with
        ``exports=True``. So its 300 W are all pv1, although bat1 is
        discharging too. cons1 takes the rest: pv1's other 200 W and all
        200 W of bat1, half each.
        """
        return rows({
            "grid": {"pv1": 300, "bat1": 0},
            "cons1": {"pv1": 200, "bat1": 200},
        })
