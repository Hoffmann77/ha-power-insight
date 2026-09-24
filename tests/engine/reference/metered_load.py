"""Reference case: Metered load."""

from __future__ import annotations

from tests.engine.home import Consumer, Grid, Pv
from tests.engine.reference.case import F, ReferenceCase, Snapshot


class MeteredLoad(ReferenceCase):
    """A consumer with a meter on it, next to the unmetered remainder. The base
    load stops being the whole house and becomes what is left after the metered
    draw — including when the meters disagree and there is nothing left.

    Shows:

    * A metered consumer gets its own provenance row; the remainder is the home
      base load.
    * A metered draw larger than gross power clamps the base load to zero
      rather than going negative.
    * A zeroed base load still publishes a share row, of zeros.
    """

    case_id = "metered-load"
    title = "Metered load"

    grid = Grid()
    pv1 = Pv(lcoe=0.10)
    cons1 = Consumer()

    class LoadAndBase(Snapshot):
        """cons1 draws 500 W of the 1400 W entering the house; the other 900 W is
        unmetered.
        """

        grid = 800
        pv1 = 600
        cons1 = -500
        price = F(3, 10)

    class OverMetered(Snapshot):
        """cons1 reads more than the sources supply — the meters disagree, and the
        base load has nowhere to go but zero.
        """

        grid = 100
        pv1 = 200
        cons1 = -400
        price = F(3, 10)
