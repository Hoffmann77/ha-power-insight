"""Flow roles: which devices count as sources and which as sinks.

Every snapshot, the engine sorts each device by the sign of its reading: a
device supplying power is a *source*, a device drawing power is a *sink*,
and a device at exactly 0 W is *idle* — neither. Everything else about
provenance and money is built on that sorting, so these decisions come
first. See "Conventions this builds on" in
``docs/dev/engine-calculations.md``, and ``provenance.py`` for how the
expected provenance is written.
"""

from __future__ import annotations

from fractions import Fraction as F

from tests.engine.home import Battery, Consumer, Grid, Home, Pv, expect
from tests.engine.manual.provenance import rows


class TestIdleAdapterIsInNoFlowGroup(Home):
    """Decision: a device reading exactly 0 W is neither a source nor a sink.

    The battery at 0 W must not show up anywhere in the provenance. See
    "Conventions this builds on" in engine-calculations.md.
    """

    grid = Grid(500)
    bat1 = Battery(0)
    plug = Consumer(-100)

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """Only the plug gets a row, and it is all grid.

        The idle battery is left out, so the grid is the only source for the
        plug's 100 W.
        """
        return rows({"plug": {"grid": 100}})


class TestPvStandbyIsAnUnrestrictedSink(Home):
    """Decision: PV standby is an ordinary sink, and unrestricted sinks get the raw mix.

    The grid supplies 500 W and pv2 300 W, so every sink draws them 5 : 3.
    See "Conventions this builds on" and rule 3 of "Choosing among valid
    allocations" in engine-calculations.md.
    """

    grid = Grid(500)
    pv1 = Pv(-20)
    pv2 = Pv(300)

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """pv1's standby draw gets the plain 5 : 3 source mix.

        At −20 W pv1 is drawing power, so it is a sink like any consumer: its
        20 W split into 12.5 W grid and 7.5 W pv2.
        """
        return rows({"pv1": {"grid": F(25, 2), "pv2": F(15, 2)}})

    @expect("home_base_load_source_shares")
    def test_base_load_source_shares(self):
        """The base load gets the same 5 : 3 mix.

        The 780 W base load (800 W supplied minus pv1's 20 W) is unrestricted
        too, so it reads 5/8 grid and 3/8 pv2.
        """
        return {"grid": F(5, 8), "pv2": F(3, 8)}

    @expect("source_adapters_standby_power")
    def test_standby_power(self):
        """Each source is credited with the standby power it supplied.

        pv1's 20 W of standby, split 5 : 3, is 12.5 W from the grid and 7.5 W
        from pv2.
        """
        return {"grid": F(25, 2), "pv2": F(15, 2)}
