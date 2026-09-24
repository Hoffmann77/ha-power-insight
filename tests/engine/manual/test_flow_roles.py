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
    """Decision: an adapter reading exactly 0 W belongs to neither flow group
    (engine-calculations.md, "Conventions this builds on").

    The battery neither charges nor discharges, so it is not a source any row
    can name and not a sink with a row of its own.
    """

    grid = Grid(500)
    bat1 = Battery(0)
    plug = Consumer(-100)

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """Only the plug gets a provenance row, and it is all grid.

        The battery at 0 W must appear nowhere: not as a sink with a row of
        its own, and not as a source inside the plug's row. The grid is the
        only source, so the plug's 100 W come entirely from it.
        """
        return rows({"plug": {"grid": 100}})


class TestPvStandbyIsAnUnrestrictedSink(Home):
    """Decision: an unrestricted sink's row is the raw source mix, and a PV
    system drawing standby is a sink like any other (engine-calculations.md,
    "Conventions this builds on"; rule 3 of "Choosing among valid
    allocations").

    Nothing is restricted, so every sink — pv1's 20 W standby and the 780 W
    base load alike — draws grid and pv2 in the ratio they supply, 5 : 3.
    """

    grid = Grid(500)
    pv1 = Pv(-20)
    pv2 = Pv(300)

    @expect("sink_adapters_source_shares")
    def test_source_shares(self):
        """pv1's standby draw is a sink row with the plain 5 : 3 source mix.

        A PV system reading −20 W is drawing power, not producing negative
        power, so it gets a row like any consumer. Its 20 W come from the
        two sources in the ratio they supply (500 W grid : 300 W pv2), which
        is 12.5 W grid and 7.5 W pv2.
        """
        return rows({"pv1": {"grid": F(25, 2), "pv2": F(15, 2)}})

    @expect("home_base_load_source_shares")
    def test_base_load_source_shares(self):
        """The unmetered base load takes the same 5 : 3 mix as the standby.

        The base load is the 780 W the house uses without a meter on it
        (800 W supplied minus pv1's 20 W). With no restrictions in play, no
        sink is favoured, so it reads 5/8 grid and 3/8 pv2 too.
        """
        return {"grid": F(5, 8), "pv2": F(3, 8)}

    @expect("source_adapters_standby_power")
    def test_standby_power(self):
        """Each source is credited with the standby watts it supplied.

        The standby channel records, per source, how much power went into
        devices idling on standby: pv1's 20 W, split 5 : 3, is 12.5 W from
        the grid and 7.5 W from pv2.
        """
        return {"grid": F(25, 2), "pv2": F(15, 2)}
