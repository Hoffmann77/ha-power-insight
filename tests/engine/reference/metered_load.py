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
    * A metered draw larger than what the sources supply is balanced by
      meeting in the middle: the sources move up, the load moves down, and
      the base load is exactly zero.
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
        """cons1 reads 400 W while the sources supply 300 W — the meters were
        sampled at different moments. No meter is trusted over another: the
        grid and pv1 move up by 8/7 and cons1 down by 6/7, to about 343 W on
        both sides, and the 100 W gap is the metering imbalance.
        """

        grid = 100
        pv1 = 200
        cons1 = -400
        price = F(3, 10)
