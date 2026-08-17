"""Reference case: Metered load."""

from __future__ import annotations

from tests.engine.reference.case import F, ReferenceCase, expect  # noqa: F401
from tests.engine.scenario_framework import Adapter, State, state, topology

# `expect` is imported ready for the first answer derived here — see
# tests/engine/reference/case.py for how to write one.


class TestMeteredLoad(ReferenceCase):
    """A consumer with a meter on it, next to the unmetered remainder. The base
    load stops being the whole house and becomes what is left after the metered
    draw — including when the meters disagree and there is nothing left.

    Decides:

    * A metered consumer gets its own provenance row; the remainder is the home
      base load.
    * A metered draw larger than gross power clamps the base load to zero
      rather than going negative.
    * A zeroed base load still publishes a share row, of zeros.
    """

    case_id = "metered-load"
    title = "Metered load"

    @topology
    def wiring(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10),
            Adapter.consumer("cons1"),
        )

    # ----------------------------------------------------------------------

    @state
    def load_and_base(self):
        """cons1 draws 500 W of the 1400 W entering the house; the other 900 W is
        unmetered.
        """
        return State(grid=800, pv1=600, cons1=-500, price=F(3, 10))

    # Nothing derived for this snapshot yet. Add @expect methods here;
    # see tests/engine/reference/case.py.

    # ----------------------------------------------------------------------

    @state
    def over_metered(self):
        """cons1 reads more than the sources supply — the meters disagree, and the
        base load has nowhere to go but zero.
        """
        return State(grid=100, pv1=200, cons1=-400, price=F(3, 10))

    # Nothing derived for this snapshot yet. Add @expect methods here;
    # see tests/engine/reference/case.py.
