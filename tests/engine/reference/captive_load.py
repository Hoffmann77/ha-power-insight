"""Reference case: Captive load."""

from __future__ import annotations

from tests.engine.home import Consumer, Grid, Pv
from tests.engine.reference.case import F, ReferenceCase, Snapshot


class CaptiveLoad(ReferenceCase):
    """The same three devices, with the consumer now restricted to the PV system.
    This is the smallest wiring in which a restriction can be honoured at all —
    and the smallest in which one can fail, which is where the restriction
    deficit is first published.

    Shows:

    * A restricted sink is served from its allowed sources before anything
      unrestricted shares them.
    * Serving the captive sink first pushes the unrestricted base load onto the
      grid.
    * A draw the allowed sources cannot cover is still attributed, and the
      shortfall is reported as a restriction deficit.
    """

    case_id = "captive-load"
    title = "Captive load"

    grid = Grid()
    pv1 = Pv(lcoe=0.10)
    cons1 = Consumer(power_from=(pv1,))

    class CaptiveLoad(Snapshot):
        """pv1 makes more than cons1 draws, so cons1 runs on solar alone and the
        base load is pushed onto the grid.
        """

        grid = 800
        pv1 = 600
        cons1 = -500
        price = F(3, 10)

    class LoadExceeds(Snapshot):
        """cons1 draws 500 W but pv1 makes only 300 W: the missing 200 W came from
        a source it is not allowed to use.
        """

        grid = 800
        pv1 = 300
        cons1 = -500
        price = F(3, 10)
