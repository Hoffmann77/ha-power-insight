"""Reference case: Battery basics."""

from __future__ import annotations

from tests.engine.home import Battery, Consumer, Grid, Pv
from tests.engine.reference.case import F, ReferenceCase, Snapshot


class BatteryBasics(ReferenceCase):
    """An unrestricted battery, which is the only device that changes which side
    of the diagram it sits on. Charging it is a sink like any other;
    discharging it is a source whose energy was paid for in the past, and a
    snapshot engine has to price that somehow.

    Shows:

    * A charging battery is a sink and takes the same raw mix as any other.
    * A discharging battery is a source priced at its flat levelized cost of
      storage.
    * Its marginal price is zero — the mix it charged on happened earlier,
      where a snapshot cannot see it.
    * An adapter reading exactly 0 W belongs to neither flow group.
    """

    case_id = "battery-basics"
    title = "Battery basics"

    grid = Grid()
    pv1 = Pv(lcoe=0.10)
    cons1 = Consumer()
    bat1 = Battery(lcos=0.15)

    class Charging(Snapshot):
        """bat1 charges from the mix, taking the same proportions as the metered
        load beside it.
        """

        grid = 800
        pv1 = 600
        cons1 = -500
        bat1 = -600
        price = F(3, 10)

    class Discharging(Snapshot):
        """The sun is down and bat1 has become a source, supplying two thirds of
        the house.
        """

        grid = 200
        pv1 = 0
        cons1 = -500
        bat1 = 400
        price = F(3, 10)

    class Idle(Snapshot):
        """bat1 sits at exactly 0 W: neither a source nor a sink, and absent from
        both groups.
        """

        grid = 900
        pv1 = 600
        cons1 = -500
        bat1 = 0
        price = F(3, 10)
