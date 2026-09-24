"""Reference case: Captive battery."""

from __future__ import annotations

from tests.engine.home import Battery, Consumer, Grid, Pv
from tests.engine.reference.case import F, ReferenceCase, Snapshot


class CaptiveBattery(ReferenceCase):
    """bat1 may only charge from pv1. That single restriction changes the answer
    in two opposite ways depending on whether pv1 is producing: when it is, the
    captive sink depletes it before anyone else may share it; when it is not,
    the sink has nowhere legal to draw from.

    Shows:

    * A captive sink is served from its allowed source before flexible sinks
      share it.
    * When every allowed source is idle the row collapses to zero rather than
      dividing by zero.
    * The unservable draw is reported as a restriction deficit.
    """

    case_id = "captive-battery"
    title = "Captive battery"

    grid = Grid()
    pv1 = Pv(lcoe=0.10, exports=True)
    bat1 = Battery(lcos=0.15, charge_from=(pv1,))
    cons1 = Consumer()

    class CaptiveDepletesFirst(Snapshot):
        """pv1 produces exactly what bat1 draws, so bat1 takes all of it."""

        grid = 500
        pv1 = 400
        bat1 = -400
        cons1 = -200
        price = F(3, 10)

    class SourceInStandby(Snapshot):
        """pv1 is drawing standby, so it is a sink; bat1's only allowed source
        does not exist.

        Open question: home_base_load_power includes the 400 W bat1 drew but
        could not legally be attributed, so the 'unmetered' load contains a
        device that has a meter on it. Its docstring says gross minus metered
        draw, which would be 580 W rather than 980 W.
        """

        grid = 1000
        pv1 = -20
        bat1 = -400
        cons1 = -100
        price = F(3, 10)
