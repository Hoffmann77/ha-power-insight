"""Stub scenarios for engine areas not yet implemented.

The recent engine refactor left whole property families as stubs (returning
``None``): the combined monetary rates / prices, and the per-source-adapter
attribution (export / consumption / charging / standby power, shares and ratios,
plus the per-source rates). Each is a large slice of code, so each gets a
scenario *now* — a real ``@topology`` / ``@state`` block that is already valid
(building the engine exercises the safety rail) and ``test_`` methods that
``pytest.skip`` with the property to fill in.

When a family is implemented, replace the ``skip`` with a hand-derived
assertion; the topology and readings are already chosen to exercise it. Keeping
these here documents the intended coverage and keeps the scenario count small
and deliberate rather than sprawling once the engine catches up.

Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery ``+``
produce/discharge / ``-`` standby/charge; consumer ``-`` = load.
"""

from __future__ import annotations

import pytest

from tests.engine.scenario_framework import Adapter, EngineScenario, State, state, topology


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

    def test_combined_coe(self, power_insight):
        pytest.skip("TODO: implement PowerInsight.combined_coe")

    def test_combined_lcoe(self, power_insight):
        pytest.skip("TODO: implement PowerInsight.combined_lcoe")

    def test_combined_export_compensation_rate(self, power_insight):
        pytest.skip("TODO: implement PowerInsight.combined_export_compensation_rate")

    def test_combined_lcoe_rate(self, power_insight):
        pytest.skip("TODO: implement PowerInsight.combined_lcoe_rate")

    def test_combined_financial_return_rate(self, power_insight):
        pytest.skip("TODO: implement PowerInsight.combined_financial_return_rate")


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

    def test_source_adapters_consumption_power(self, power_insight):
        pytest.skip("TODO: implement PowerInsight.source_adapters_consumption_power")

    def test_source_adapters_export_power(self, power_insight):
        pytest.skip("TODO: implement PowerInsight.source_adapters_export_power")

    def test_source_adapters_charging_power(self, power_insight):
        pytest.skip("TODO: implement PowerInsight.source_adapters_charging_power")

    def test_source_adapters_export_ratios(self, power_insight):
        pytest.skip("TODO: implement PowerInsight.source_adapters_export_ratios")

    def test_source_adapters_dynamic_lcoe(self, power_insight):
        pytest.skip("TODO: implement PowerInsight.source_adapters_dynamic_lcoe")
