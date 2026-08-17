"""Grid only.

One meter and nothing else. Every published property still has a value here,
which makes this the cheapest place in the corpus to settle what the engine
does at the edges: a single source, a house that draws nothing, and a sensor
that has dropped out.

What this case pins down:

* With no local device, the whole gross power is the unmetered home base load.
* A sink with one available source has a provenance row of exactly one.
* Marginal and levelized cost agree while the grid is the only source.
* An unavailable reading collapses the derived values rather than defaulting to
  zero.
"""

from __future__ import annotations

from tests.engine.reference.case import F, Case, Snapshot
from tests.engine.scenario_framework import Adapter

CASE = Case(
    id="grid-only",
    title="Grid only",
    summary=(
        "One meter and nothing else. Every published property still has a value here, "
        "which makes this the cheapest place in the corpus to settle what the engine does "
        "at the edges: a single source, a house that draws nothing, and a sensor that has "
        "dropped out."
    ),
    decides=[
        "With no local device, the whole gross power is the unmetered home base load.",
        "A sink with one available source has a provenance row of exactly one.",
        "Marginal and levelized cost agree while the grid is the only source.",
        (
            "An unavailable reading collapses the derived values rather than defaulting to "
            "zero."
        ),
    ],
    topology=[
        Adapter.grid(),
    ],
    snapshots=[
        Snapshot(
            id="import_only",
            note="The house runs on the grid alone; every watt is unmetered base load.",
            readings=dict(grid=1200),
            price=F(3, 10),
            answers={
                # Layer 1 — the totals. One source, so the grid reading *is*
                # the gross power, and with no local device every other
                # channel total is a sum over an empty set.
                "gross_power": 1200,
                "combined_grid_import": 1200,
                "combined_grid_export": 0,
                "combined_production": 0,
                "combined_charging_power": 0,
                "combined_discharging_power": 0,
                "combined_standby_power": 0,
                # Residual: 1200 − 0 export − 0 charging − 0 standby.
                "combined_consumption": 1200,
                # Nothing is metered, so the whole draw is unmetered.
                "home_base_load_power": 1200,
                # Layer 2 — provenance. The base load has exactly one source
                # available to it, so its row is that source at 1.
                "home_base_load_source_shares": {"grid": 1},
                # Layer 3 — the channel split. Everything self-consumed.
                "gross_power_export_ratio": 0,
                "gross_power_consumption_ratio": 1,
                "gross_power_charging_ratio": 0,
                "gross_power_standby_ratio": 0,
                # 1200 / (1200 − 0 export − 0 charging): no standby to lose.
                "gross_power_applicable_consumption_ratio": 1,
                # Layer 4 — money. 1.2 kW at 0.30 EUR/kWh, and marginal equals
                # levelized while the grid is the only source.
                "combined_coe_rate": F(9, 25),
                "combined_lcoe_rate": F(9, 25),
                # Nothing local supplied the CON channel, so nothing was
                # avoided; nothing was generated or stored, so nothing saved.
                "combined_avoided_cost_rate": 0,
                "combined_saving_rate": 0,
                "combined_export_compensation_rate": 0,
                #
                # Still to derive here: the map-shaped properties
                # (sink_adapters_source_shares, sink_adapters_restriction_deficit,
                # source_adapters_export_power / _export_shares / _standby_power,
                # source_adapters_dynamic_coe / _dynamic_lcoe). Their *key sets*
                # are part of the answer — whether a source with nothing to
                # attribute appears as a zero row or not at all — so they are
                # a modelling decision, not arithmetic.
            },
        ),
        Snapshot(
            id="grid_idle",
            note=(
                "The meter reads exactly 0 W: gross power is zero and every ratio has to "
                "survive it."
            ),
            readings=dict(grid=0),
            price=F(3, 10),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
        Snapshot(
            id="grid_unavailable",
            note=(
                "The grid sensor has dropped out. Nothing downstream of it can be "
                "answered."
            ),
            readings=dict(grid=None),
            price=F(3, 10),
            open_question=(
                "combined_saving_rate publishes 0 EUR/h here while every other rate in "
                "layer 4 correctly publishes nothing. Zero is a claim — that the house "
                "saved exactly nothing this snapshot — and the engine is in no position to "
                "make it with the only meter unavailable."
            ),
            answers={
                # Nothing derived yet. Add `"property": value` entries as you
                # work them out; see tests/engine/reference/case.py.
            },
        ),
    ],
)
