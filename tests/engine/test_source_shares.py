"""Source-share scenario: the two-tier power-provenance attribution.

``PowerInsight.sink_adapters_source_shares`` answers "where does each drawing
adapter's power come from?" — ``{sink_uid: {source_uid: share}}``, each row
summing to 1 (or collapsing to all-zeros when the sink's allowed sources are all
idle). It is the single richest piece of engine logic, so it gets its own
scenario, one block per branch of the two-tier algorithm:

* **Priority tier** — sinks restricted to non-grid sources (a PV-only battery, a
  smart-plug consumer). Active *only while the grid is importing*: they get first
  pick of their allowed sources and can exhaust a scarce one.
* **Leftover tier** — grid-capable / unrestricted sinks (and *every* sink when
  the grid is not importing). They split what the priority tier left behind.

See ``scenario_framework.py`` for the block layout (``@topology`` → ``@state`` →
``test_`` methods, bound by source order). Expected values are derived by hand
from the shares in each docstring, not read back from the engine.

Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery ``+``
produce/discharge / ``-`` standby/charge; consumer ``-`` = load.
"""

from __future__ import annotations

import pytest

from tests.engine.scenario_framework import Adapter, EngineScenario, State, state, topology


class TestSourceShares(EngineScenario):
    """Power provenance under the two-tier ``sink_adapters_source_shares`` rule."""

    # -----------------------------------------------------------------------
    # Block 1 — grid importing: a PV-only battery (priority) drains the PV
    # first, pushing the unrestricted battery (leftover) onto the grid.
    # -----------------------------------------------------------------------

    @topology
    def grid_pv_two_batteries(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            # Restricted to PV -> priority tier while the grid imports.
            Adapter.battery("bat_solar", charge_from=("pv1",)),
            # Unrestricted -> leftover tier (can fall back on the grid).
            Adapter.battery("bat_flex"),
        )

    @state
    def import_and_solar(self):
        # Sources: grid 1000 W + pv1 1000 W -> gross 2000 W, each a 0.5 share.
        # Both batteries charge at 500 W (each a 0.25 sink share of gross).
        return State(grid=1000, pv1=1000, bat_solar=-500, bat_flex=-500, price=0.30)

    def test_priority_battery_takes_all_pv(self, power_insight):
        # bat_solar (priority) masks the 0.5/0.5 availability to PV only, so it
        # normalises to 100% pv1 and consumes 0.25 * 1.0 = 0.25 of the pv1 share.
        shares = power_insight.sink_adapters_source_shares
        assert shares["bat_solar"] == pytest.approx({"grid": 0.0, "pv1": 1.0})

    def test_leftover_battery_falls_back_to_grid(self, power_insight):
        # bat_flex draws the leftover availability: grid 0.5 (untouched) and the
        # 0.25 of pv1 the priority tier left -> normalise (0.5, 0.25) = 2/3, 1/3.
        shares = power_insight.sink_adapters_source_shares
        assert shares["bat_flex"] == pytest.approx({"grid": 2 / 3, "pv1": 1 / 3})

    def test_only_the_two_batteries_are_sinks(self, power_insight):
        assert set(power_insight.sink_adapters_source_shares) == {"bat_solar", "bat_flex"}

    # -----------------------------------------------------------------------
    # Block 2 — grid exporting: no import, so the priority tier is empty and
    # every sink shares the sources in a single pass (restriction still honoured).
    # The exporting grid is itself a sink, sourced from the PV mix.
    # -----------------------------------------------------------------------

    @topology
    def two_pv_two_batteries(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.pv("pv2", exports=True),
            Adapter.battery("bat_solar", charge_from=("pv1",)),
            Adapter.battery("bat_flex"),
        )

    @state
    def pure_solar_export(self):
        # Sources: pv1 2000 W + pv2 1000 W -> gross 3000 W (grid exports 1000 W,
        # so it is a sink, not a source). Availability: pv1 2/3, pv2 1/3.
        return State(
            grid=-1000, pv1=2000, pv2=1000, bat_solar=-500, bat_flex=-500, price=0.30
        )

    def test_grid_export_sourced_from_pv_mix(self, power_insight):
        # Unrestricted sink -> full availability: pv1 2/3, pv2 1/3.
        shares = power_insight.sink_adapters_source_shares
        assert shares["grid"] == pytest.approx({"pv1": 2 / 3, "pv2": 1 / 3})

    def test_restriction_still_honoured_without_priority(self, power_insight):
        # No grid import means no priority tier, but bat_solar's PV-only
        # restriction still masks it to pv1 in the single leftover pass.
        shares = power_insight.sink_adapters_source_shares
        assert shares["bat_solar"] == pytest.approx({"pv1": 1.0, "pv2": 0.0})

    def test_unrestricted_battery_matches_availability(self, power_insight):
        shares = power_insight.sink_adapters_source_shares
        assert shares["bat_flex"] == pytest.approx({"pv1": 2 / 3, "pv2": 1 / 3})

    # -----------------------------------------------------------------------
    # Block 3 — restricted sinks whose only allowed source is idle. The lone PV
    # is in standby (a sink, not a source), so a battery and a smart plug both
    # pinned to it collapse to an all-zeros row, while the unrestricted standby
    # PV draws from the grid.
    # -----------------------------------------------------------------------

    @topology
    def grid_with_idle_pv(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", exports=True),
            Adapter.consumer("cons_plug", power_from=("pv1",)),
            Adapter.battery("bat_dead", charge_from=("pv1",)),
        )

    @state
    def night_standby(self):
        # Only the grid provides (1000 W). pv1 draws 10 W standby -> a sink. The
        # plug (300 W) and battery (200 W) are pinned to the now-idle pv1.
        return State(grid=1000, pv1=-10, cons_plug=-300, bat_dead=-200, price=0.30)

    def test_restricted_to_idle_source_collapses_to_zero(self, power_insight):
        # pv1 is not a source, so masking to it leaves nothing: an all-zeros row
        # over the sole source index (grid), rather than a divide-by-zero.
        shares = power_insight.sink_adapters_source_shares
        assert shares["cons_plug"] == pytest.approx({"grid": 0.0})
        assert shares["bat_dead"] == pytest.approx({"grid": 0.0})

    def test_unrestricted_standby_pv_draws_from_grid(self, power_insight):
        shares = power_insight.sink_adapters_source_shares
        assert shares["pv1"] == pytest.approx({"grid": 1.0})
