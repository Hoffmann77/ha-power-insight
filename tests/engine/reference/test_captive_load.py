"""Reference case: Captive load."""

from __future__ import annotations

from tests.engine.reference.case import F, ReferenceCase, expect  # noqa: F401
from tests.engine.scenario_framework import Adapter, State, state, topology

# `expect` is imported ready for the first answer derived here — see
# tests/engine/reference/case.py for how to write one.


class TestCaptiveLoad(ReferenceCase):
    """The same three devices, with the consumer now restricted to the string.
    This is the smallest wiring in which a restriction can be honoured at all —
    and the smallest in which one can fail, which is where the restriction
    deficit is first published.

    Decides:

    * A restricted sink is served from its allowed sources before anything
      unrestricted shares them.
    * Serving the captive sink first pushes the unrestricted base load onto the
      grid.
    * A draw the allowed sources cannot cover is still attributed, and the
      shortfall is reported as a restriction deficit.
    """

    case_id = "captive-load"
    title = "Captive load"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10),
            Adapter.consumer("cons1", power_from=("pv1",)),
        )

    # ----------------------------------------------------------------------

    @state
    def captive_load(self):
        """pv1 makes more than cons1 draws, so cons1 runs on solar alone and the
        base load is pushed onto the grid.
        """
        return State(grid=800, pv1=600, cons1=-500, price=F(3, 10))

    # Nothing derived for this snapshot yet. Add @expect methods here;
    # see tests/engine/reference/case.py.

    # ----------------------------------------------------------------------

    @state
    def load_exceeds(self):
        """cons1 draws 500 W but pv1 makes only 300 W: the missing 200 W came from
        a source it is not allowed to use.
        """
        return State(grid=800, pv1=300, cons1=-500, price=F(3, 10))

    # Nothing derived for this snapshot yet. Add @expect methods here;
    # see tests/engine/reference/case.py.
