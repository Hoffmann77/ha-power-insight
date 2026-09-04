"""Scenarios for the combined monetary rates and the per-source attribution.

Both families are implemented — every property below returns a real value — but
nobody has yet worked out by hand what those values *should* be, so each is an
``@expect_attribute`` method still returning :data:`TODO`: it skips, publishes
nothing, and claims nothing.

The topology and readings of each block are already chosen to exercise the
family, so deriving one is a one-line edit. Replace a ``TODO`` with the value
you worked out and that line starts holding the engine to it::

    uv run pytest tests/engine/test_engine_stubs.py -rs

reads as the worklist. Never paste an answer out of the engine's own output —
that records what the code already does, which proves nothing.

Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery ``+``
produce/discharge / ``-`` standby/charge; consumer ``-`` = load.
"""

from __future__ import annotations

from tests.engine.scenario_framework import (
    TODO,
    Adapter,
    EngineScenario,
    State,
    expect_attribute as expect,
    state,
    topology,
)


class TestCombinedRatesAndPrices(EngineScenario):
    """Combined monetary rates (EUR/h) and blended prices (EUR/kWh).

    A mixed self-consume + export snapshot so every term is non-trivial: grid
    import priced, PV producing at a known LCOE, and some of it exported for
    compensation.
    """

    @topology
    def grid_and_pv(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10, exports=True, export_comp=0.08),
        )

    @state
    def import_and_partial_export(self):
        # Import 500 W @ 0.30, PV 2000 W (part self-consumed, part exported).
        return State(grid=-500, pv1=2000, price=0.30)

    @expect("combined_coe")
    def test_combined_coe(self):
        return TODO

    @expect("combined_lcoe")
    def test_combined_lcoe(self):
        return TODO

    @expect("combined_export_compensation_rate")
    def test_combined_export_compensation_rate(self):
        return TODO

    @expect("combined_lcoe_rate")
    def test_combined_lcoe_rate(self):
        return TODO

    @expect("combined_financial_return_rate")
    def test_combined_financial_return_rate(self):
        return TODO


class TestSourceAdapterAttribution(EngineScenario):
    """Per-source split of each provider's output into export / consumption /
    charging / standby (watts, shares and ratios) plus the per-source rates.

    A battery charging from PV while PV also exports gives every branch a
    non-zero value to attribute.
    """

    @topology
    def grid_pv_battery(self):
        return (
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.battery("bat1", charge_from=("pv1",)),
        )

    @state
    def solar_charging_and_export(self):
        # PV 3000 W: some charges the 1000 W battery, rest exported (grid -1500).
        return State(grid=-1500, pv1=3000, bat1=-1000, price=0.30)

    @expect("source_adapters_consumption_power")
    def test_source_adapters_consumption_power(self):
        return TODO

    @expect("source_adapters_export_power")
    def test_source_adapters_export_power(self):
        return TODO

    @expect("source_adapters_charging_power")
    def test_source_adapters_charging_power(self):
        return TODO

    @expect("source_adapters_export_ratios")
    def test_source_adapters_export_ratios(self):
        return TODO

    @expect("source_adapters_dynamic_lcoe")
    def test_source_adapters_dynamic_lcoe(self):
        return TODO
