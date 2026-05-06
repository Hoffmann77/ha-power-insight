"""Tests for PowerInsight core calculation logic.

Four scenarios of increasing complexity:
  1. Grid + PV  (excess production → exporting)
  2. Grid + PV + Battery  (all consumed, no export)
  3. Grid + PV + Battery + Consumer  (consumer cost allocation)
  4. Grid + PV_1 + PV_2  (multiple adapters of same class)

Each scenario class defines ENTITY_VALUES as a nested dict:

    ENTITY_VALUES = {
        "case_name": {"sensor.entity_id": value, ...},
        ...
    }

The ``entity_values`` fixture is parametrized over every key so that all
test methods run once per named case.  Test methods compute expected results
directly from ``entity_values`` — adding a new test case requires only a
single new entry in ENTITY_VALUES, no changes to test methods.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

# Import power_insight.py directly (bypassing the package __init__.py
# which depends on Home Assistant).
_MODULE_PATH = os.path.join(
    os.path.dirname(__file__),
    os.pardir,
    "custom_components",
    "power_insight",
    "power_insight.py",
)
_spec = importlib.util.spec_from_file_location("power_insight", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

PowerInsight = _mod.PowerInsight
GridAdapter = _mod.GridAdapter
PvAdapter = _mod.PvAdapter
BatteryAdapter = _mod.BatteryAdapter
ConsumerAdapter = _mod.ConsumerAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_power_insight(adapters, entity_values):
    """Create a PowerInsight instance, register adapters, and set entity values."""
    pi = PowerInsight()
    for adapter in adapters:
        pi.register_adapter(adapter)
    for entity_id, value in entity_values.items():
        pi.set_value(entity_id, value)
    return pi


def create_grid(unique_id, power_entity, price_entity):
    return GridAdapter(
        unique_id=unique_id,
        verbose_name=unique_id.upper(),
        power_entity=power_entity,
        price_entity=price_entity,
    )


def create_pv(unique_id, power_entity, lcoe, lco2_intensity, exports_power, export_compensation):
    return PvAdapter(
        unique_id=unique_id,
        verbose_name=unique_id.upper(),
        power_entity=power_entity,
        power_entity_inverted=False,
        lcoe=lcoe,
        lco2_intensity=lco2_intensity,
        exports_power=exports_power,
        export_compensation=export_compensation,
    )


def create_battery(unique_id, power_entity, lcos, lco2_intensity, exports_power, export_compensation):
    return BatteryAdapter(
        unique_id=unique_id,
        verbose_name=unique_id.upper(),
        power_entity=power_entity,
        power_entity_inverted=False,
        lcos=lcos,
        lco2_intensity=lco2_intensity,
        exports_power=exports_power,
        export_compensation=export_compensation,
    )


def create_consumer(unique_id, power_entity):
    return ConsumerAdapter(
        unique_id=unique_id,
        verbose_name=unique_id.upper(),
        power_entity=power_entity,
    )


# ===================================================================
# Scenario 1 — Grid + PV  (PV overproducing → exporting to grid)
# ===================================================================

class TestDefaultScenarios:
    """Grid + PV with excess production (exporting)."""

    EXPORT_COMPENSATION = "sensor.export_compensation"

    GRID_1_PRICE_ENTITY = "sensor.grid_1_price"
    GRID_1_POWER_ENTITY = "sensor.grid_1_power"
    PV_1_POWER_ENTITY = "sensor.pv_1_power"
    PV_2_POWER_ENTITY = "sensor.pv_2_power"
    PV_3_POWER_ENTITY = "sensor.pv_3_power"
    BAT_1_POWER_ENTITY = "sensor.bat_1_power"
    BAT_2_POWER_ENTITY = "sensor.bat_2_power"
    CONS_1_POWER_ENTITY = "sensor.cons_1_power"
    CONS_2_POWER_ENTITY = "sensor.cons_2_power"

    ENTITY_VALUES = {
        "morning": {
            GRID_1_PRICE_ENTITY: 0.3,
            GRID_1_POWER_ENTITY: 1000.0,
            PV_1_POWER_ENTITY: 200.0,
            PV_2_POWER_ENTITY: 0.0,
            PV_3_POWER_ENTITY: -25.0,       # No sun yet, standby power
            BAT_1_POWER_ENTITY: 200.0,      # low on charge, discharging
            BAT_2_POWER_ENTITY: 0.0,        # empty
            CONS_1_POWER_ENTITY: 1000.0,    # heating
        },
        "midday": {
            GRID_1_PRICE_ENTITY: 0.3,
            GRID_1_POWER_ENTITY: -4000.0,   # Lot of excess power
            PV_1_POWER_ENTITY: 3000.0,
            PV_2_POWER_ENTITY: 2000.0,
            PV_3_POWER_ENTITY: 1000.0,
            BAT_1_POWER_ENTITY: -1000.0,    # charging
            BAT_2_POWER_ENTITY: -1000.0,    # charging
            CONS_1_POWER_ENTITY: 0.0,
        },
        "evening": {
            GRID_1_PRICE_ENTITY: 0.3,
            GRID_1_POWER_ENTITY: 0.0,
            PV_1_POWER_ENTITY: -50.0,       # No sun yet, standby power
            PV_2_POWER_ENTITY: 0.0,         # Litte sun, net zero
            PV_3_POWER_ENTITY: 0.0,
            BAT_1_POWER_ENTITY: 1000.0,     # discharging
            BAT_2_POWER_ENTITY: 800.0,      # discharging
            CONS_1_POWER_ENTITY: 1000.0,    # heating
        },
    }

    ADAPTERS = (
        GridAdapter(
            unique_id="grid_1",
            verbose_name="Grid-1",
            power_entity=GRID_1_POWER_ENTITY,
            price_entity=GRID_1_PRICE_ENTITY,
        ),
        PvAdapter(
            unique_id="pv_system_1",
            verbose_name="PV-System-1",
            power_entity=PV_1_POWER_ENTITY,
            power_entity_inverted=False,
            lcoe=0.1,
            lco2_intensity=35.0,
            exports_power=True,
            export_compensation=0.08,
        ),
        PvAdapter(
            unique_id="pv_system_2",
            verbose_name="PV-System-2",
            power_entity=PV_2_POWER_ENTITY,
            power_entity_inverted=False,
            lcoe=0.15,
            lco2_intensity=40.0,
            exports_power=True,
            export_compensation=0.08,
        ),
        PvAdapter(
            unique_id="pv_system_3",
            verbose_name="PV-System-3",
            power_entity=PV_3_POWER_ENTITY,
            power_entity_inverted=False,
            lcoe=0.2,
            lco2_intensity=50.0,
            exports_power=False,
            export_compensation=0.00,
        ),
        BatteryAdapter(
            unique_id="battery_1",
            verbose_name="Battery-1",
            power_entity=BAT_1_POWER_ENTITY,
            power_entity_inverted=False,
            lcos=0.15,
            lco2_intensity=50.0,
            exports_power=False,
            export_compensation=0.08,
            charge_from_grid=False,
            charge_from_adapters=[],
        ),
        BatteryAdapter(
            unique_id="battery_2",
            verbose_name="Battery-2",
            power_entity=BAT_2_POWER_ENTITY,
            power_entity_inverted=False,
            lcos=0.15,
            lco2_intensity=50.0,
            exports_power=False,
            export_compensation=0.08,
            charge_from_grid=False,
            charge_from_adapters=[],
        ),
    )

    @pytest.fixture(params=list(ENTITY_VALUES))
    def entity_values(self, request):
        return self.ENTITY_VALUES[request.param]

    @pytest.fixture()
    def test_case(self, request):
        # entity_values is parameterized, so its param is accessible via the parent fixture's node
        return request.node.callspec.params["entity_values"]

    @pytest.fixture()
    def power_insight(self, entity_values):
        return build_power_insight(self.ADAPTERS, entity_values)

    #
    # TESTS --------------------------------------------------------------->
    #

    def test_combined_grid_import(
            self, power_insight, entity_values, test_case
    ) -> None:
        """Power imported from the grid."""
        results = {
            "morning": 0.0,
            "midday": 0.0,
            "evening": 0.0,
        }

        assert power_insight.combined_grid_import == results[test_case]




    @property
    def combined_grid_export(self) -> float | None:
        """Power returned to the grid."""
        if (power := self.grid_adapter.export_power) is None:
            return None

        return power

    @property
    def combined_production(self) -> float | None:
        """Sum of power generated by the production adapters."""
        power = 0.0
        for adapter in self.prod_adapters:
            if (prod := adapter.production) is not None:
                power += prod
            else:
                return None

        return power

    @property
    def combined_consumption(self) -> float | None:
        """Sum of power consumed by electrical loads (W).

        Sum of power that is neither exported or utilized.

        This is the the power that is self consumed.

        """
        if (total_power := self.gross_power) is None:
            return None

        if (power_utilized := self.combined_utilization) is None:
            return None

        if (power_exported := self.combined_grid_export) is None:
            return None

        return total_power - power_exported - power_utilized

    @property
    def combined_utilization(self) -> float | None:
        """Sum of power utilized by production adapters (W).

        E.g. standby power of inverters or charging power of energy storages.

        """
        power = 0.0
        for adapter in self.prod_adapters:
            if (cons := adapter.consumption) is not None:
                power += cons
            else:
                return None

        return power

    @property
    def gross_power(self) -> float | None:
        """Sum of all power entering the system (W).

        The total power available to the system before export and
        utilization are accounted for.

        """
        if (grid_import := self.combined_grid_import) is None:
            return None

        if (production := self.combined_production) is None:
            return None

        return grid_import + production

    # ------------------------->
    # COMBINED POWER RATIOS --->
    # ------------------------->

    @property
    def combined_export_ratio(self) -> float | None:
        """Fraction of total available power that is returned to the grid.

        In conjunction with our Idealization that we only have one grid power sensor
        this describes the fraction of the combined produced power that is returned to the grid.

        Simple: How much of the generated power is returned to the grid.

        """
        if (total_power := self.gross_power) is None:
            return None

        if (grid_export := self.combined_grid_export) is None:
            return None

        if grid_export and not total_power:
            _LOGGER.warning("Data discrepancy: grid export without total power.")

        return self._divide(grid_export, total_power)

    @property
    def combined_consumption_ratio(self) -> float | None:
        """Return the share of total power that is self consumed.

        How much of the gross power is consumed.

        """
        if (gross_power := self.gross_power) is None:
            return None

        if (consumption := self.combined_consumption) is None:
            return None

        if consumption and not gross_power:
            _LOGGER.warning("Data discrepancy: self-consumption without total power.")

        return self._divide(consumption, gross_power)

    @property
    def combined_utilization_ratio(self) -> float | None:
        """Share of total power that is utilized.

        How much of the gross power is utilized.

        """
        if (total_power := self.gross_power) is None:
            return None

        if (utilization_power := self.combined_utilization) is None:
            return None

        if utilization_power and not total_power:
            _LOGGER.warning("Data discrepancy: utilization without total power.")

        return self._divide(utilization_power, total_power)

    @property
    def applicable_combined_utilization_ratio(self) -> float | None:
        """Return the share of total_power that is self consumed.

        This is the share of power that is utilized by the production adapters.

        """
        if (export_share := self.combined_export_ratio) is None:
            return None

        if (utilization_share := self.combined_utilization_share) is None:
            return None

        return self._divide(utilization_share, (1.0 - export_share))

    @property
    def applicable_consumption_ratio(self) -> float | None:
        """Return the share of total_power that is self consumed."""
        if (export_share := self.combined_export_ratio) is None:
            return None

        if (self_cons_share := self.combined_consumption_ratio) is None:
            return None

        return self._divide(self_cons_share, (1.0 - export_share))

    # --------------------------->
    # COMBINED MONETARY RATES --->
    # --------------------------->

    @property
    def combined_export_compensation_rate(self) -> float | None:
        """Combined export compensation rate."""
        result = 0.0
        compensation_rates = self.prod_adapters_export_compensation_rates
        for adapter in self.prod_adapters:
            if (rate := compensation_rates.get(adapter.uid)) is None:
                return None

            result += rate

        return result

    @property
    def combined_avoided_cost_rate(self) -> float | None:
        """Combined avoided cost by self consumption cost rate."""
        result = 0.0
        self_cons_saving_rates = self.prod_adapters_avoided_cost_rates
        for adapter in self.prod_adapters:
            if (rate := self_cons_saving_rates.get(adapter.uid)) is None:
                return None

            result += rate

        return result

    @property
    def combined_coe_rate(self) -> float | None:
        """Combined cost of electricity rate."""
        result = 0.0
        adapters = [self.grid_adapter] + self.prod_adapters
        for adapter in adapters:
            if (coe_rate := adapter.coe_rate) is None:
                return None

            result += coe_rate

        return result

    @property
    def combined_lcoe_rate(self) -> float | None:
        """Combined levelized cost of electricity rate."""
        result = 0.0
        adapters = [self.grid_adapter] + self.prod_adapters
        for adapter in adapters:
            if (lcoe_rate := adapter.lcoe_rate) is None:
                return None

            result += lcoe_rate

        return result

    @property
    def combined_coo_rate(self) -> float | None:
        """Total export compensation rate."""
        result = 0.0
        coo_rates = self.prod_adapters_coo_rates
        for adapter in self.prod_adapters:
            if (rate := coo_rates.get(adapter.uid)) is None:
                return None

            result += rate

        return result

    @property
    def combined_lcoo_rate(self) -> float | None:
        """Total export compensation rate."""
        result = 0.0
        lcoo_rates = self.prod_adapters_lcoo_rates
        for adapter in self.prod_adapters:
            if (rate := lcoo_rates.get(adapter.uid)) is None:
                return None

            result += rate

        return result

    @property
    def combined_saving_rate(self) -> float | None:
        """Total export compensation rate."""
        result = 0.0
        saving_rates = self.prod_adapters_cost_saving_rates
        for adapter in self.prod_adapters:
            if (rate := saving_rates.get(adapter.uid)) is None:
                return None

            result += rate

        return result

    @property
    def combined_levelized_saving_rate(self) -> float | None:
        """Total export compensation rate."""
        result = 0.0
        levelized_saving_rates = self.prod_adapters_levelized_cost_saving_rates
        for adapter in self.prod_adapters:
            if (rate := levelized_saving_rates.get(adapter.uid)) is None:
                return None

            result += rate

        return result

    # ------------------->
    # COMBINED PRICES --->
    # ------------------->

    @property
    def combined_coe(self) -> float | None:
        """Cost of electricity."""
        if (coe_rate := self.combined_coe_rate) is None:
            return None

        if coe_rate == 0.0:
            return 0.0

        if (gross_power := self.gross_power) is None:
            return None
        else:
            gross_power = self._to_kilo(gross_power)

        return self._divide(coe_rate, gross_power)

    @property
    def combined_lcoe(self) -> float | None:
        """Levelized cost of electricity."""
        if (lcoe_rate := self.combined_lcoe_rate) is None:
            return None

        if lcoe_rate == 0.0:
            return 0.0

        if (total_power := self.gross_power) is None:
            return None
        else:
            total_power = self._to_kilo(total_power)

        return self._divide(lcoe_rate, total_power)






class TestExtendedScenarios:
    """Grid + PV with excess production (exporting)."""

    EXPORT_COMPENSATION = "sensor.export_compensation"

    GRID_1_PRICE_ENTITY = "sensor.grid_1_price"
    GRID_1_POWER_ENTITY = "sensor.grid_1_power"
    PV_1_POWER_ENTITY = "sensor.pv_1_power"
    PV_2_POWER_ENTITY = "sensor.pv_2_power"
    PV_3_POWER_ENTITY = "sensor.pv_3_power"
    PV_4_POWER_ENTITY = "sensor.pv_4_power"
    BAT_1_POWER_ENTITY = "sensor.bat_1_power"
    BAT_2_POWER_ENTITY = "sensor.bat_2_power"
    BAT_3_POWER_ENTITY = "sensor.bat_3_power"
    CONS_1_POWER_ENTITY = "sensor.cons_1_power"

    ENTITY_VALUES = {
        "morning": {
            GRID_1_PRICE_ENTITY: 0.3,
            GRID_1_POWER_ENTITY: 1000.0,
            PV_1_POWER_ENTITY: 200.0,
            PV_2_POWER_ENTITY: 0.0,
            PV_3_POWER_ENTITY: -25.0,       # No sun yet, standby power
            PV_4_POWER_ENTITY: -25.0,       # No sun yet, standby power
            BAT_1_POWER_ENTITY: 200.0,      # low on charge, discharging
            BAT_2_POWER_ENTITY: 0.0,        # empty
            BAT_3_POWER_ENTITY: 0.0,        # empty
            CONS_1_POWER_ENTITY: 1000.0,    # heating
        },
        "midday": {
            GRID_1_PRICE_ENTITY: 0.3,
            GRID_1_POWER_ENTITY: -4000.0,   # Lot of excess power
            PV_1_POWER_ENTITY: 3000.0,
            PV_2_POWER_ENTITY: 2000.0,
            PV_3_POWER_ENTITY: 1000.0,
            PV_4_POWER_ENTITY: 1000.0,
            BAT_1_POWER_ENTITY: -1000.0,    # charging
            BAT_2_POWER_ENTITY: -1000.0,    # charging
            BAT_3_POWER_ENTITY: -500.0,     # charging
            CONS_1_POWER_ENTITY: 0.0,
        },
        "evening": {
            GRID_1_PRICE_ENTITY: 0.3,
            GRID_1_POWER_ENTITY: 0.0,
            PV_1_POWER_ENTITY: -50.0,       # No sun yet, standby power
            PV_2_POWER_ENTITY: 0.0,         # Litte sun, net zero
            PV_3_POWER_ENTITY: 0.0,
            PV_4_POWER_ENTITY: 200.0,
            BAT_1_POWER_ENTITY: 1000.0,     # discharging
            BAT_2_POWER_ENTITY: 800.0,      # discharging
            BAT_3_POWER_ENTITY: 0.0,        # empty
            CONS_1_POWER_ENTITY: 1000.0,    # heating
        },
        # High energy price: try to sell as much energy to the grid as possible
        # "high_price": {
        #     GRID_1_PRICE_ENTITY = 0.3,
        #     GRID_1_POWER_ENTITY: 1000.0,
        #     PV_1_POWER_ENTITY: 300.0,
        #     PV_2_POWER_ENTITY: 100.0,
        #     PV_3_POWER_ENTITY: 0.0,         # Litte sun, net zero
        #     PV_4_POWER_ENTITY: -20.0,       # No sun yet, standby power
        #     BAT_1_POWER_ENTITY: 100.0,      # low on charge, discharging
        #     BAT_2_POWER_ENTITY: 0.0,        # empty
        #     CONS_1_POWER_ENTITY: 1000.0,    # heating
        # },

        # # Negative price: try to receive all power from the grid
        # "negative_price": {
        #     GRID_1_PRICE_ENTITY = 0.3,
        #     GRID_1_POWER_ENTITY: 1000.0,
        #     PV_1_POWER_ENTITY: 300.0,
        #     PV_2_POWER_ENTITY: 100.0,
        #     PV_3_POWER_ENTITY: 0.0,         # Litte sun, net zero
        #     PV_4_POWER_ENTITY: -20.0,       # No sun yet, standby power
        #     BAT_1_POWER_ENTITY: 100.0,      # low on charge, discharging
        #     BAT_2_POWER_ENTITY: 0.0,        # empty
        #     CONS_1_POWER_ENTITY: 1000.0,    # heating
        # },
    }

    ADAPTERS = (
        GridAdapter(
            unique_id="grid_1",
            verbose_name="Grid-1",
            power_entity=GRID_1_POWER_ENTITY,
            price_entity=GRID_1_PRICE_ENTITY,
        ),
        PvAdapter(
            unique_id="pv_system_1",
            verbose_name="PV-System-1",
            power_entity=PV_1_POWER_ENTITY,
            power_entity_inverted=False,
            lcoe=0.1,
            lco2_intensity=35.0,
            exports_power=True,
            export_compensation=0.08,
        ),
        PvAdapter(
            unique_id="pv_system_2",
            verbose_name="PV-System-2",
            power_entity=PV_2_POWER_ENTITY,
            power_entity_inverted=False,
            lcoe=0.15,
            lco2_intensity=40.0,
            exports_power=True,
            export_compensation=0.08,
        ),
        PvAdapter(
            unique_id="pv_system_3",
            verbose_name="PV-System-3",
            power_entity=PV_3_POWER_ENTITY,
            power_entity_inverted=False,
            lcoe=0.2,
            lco2_intensity=50.0,
            exports_power=True,
            export_compensation=0.08,
        ),
        PvAdapter(
            unique_id="pv_system_4",
            verbose_name="PV-System-4",
            power_entity=PV_4_POWER_ENTITY,
            power_entity_inverted=False,
            lcoe=0.2,
            lco2_intensity=50.0,
            exports_power=False,
            export_compensation=0.0,
        ),
        BatteryAdapter(
            unique_id="battery_1",
            verbose_name="Battery-1",
            power_entity=BAT_1_POWER_ENTITY,
            power_entity_inverted=False,
            lcos=0.15,
            lco2_intensity=50.0,
            exports_power=False,
            export_compensation=0.08,
            charge_from_grid=False,
            charge_from_adapters=[],
        ),
        BatteryAdapter(
            unique_id="battery_2",
            verbose_name="Battery-2",
            power_entity=BAT_2_POWER_ENTITY,
            power_entity_inverted=False,
            lcos=0.15,
            lco2_intensity=50.0,
            exports_power=False,
            export_compensation=0.08,
            charge_from_grid=False,
            charge_from_adapters=[],
        ),
        BatteryAdapter(
            unique_id="battery_3",
            verbose_name="Battery-3",
            power_entity=BAT_2_POWER_ENTITY,
            power_entity_inverted=False,
            lcos=0.15,
            lco2_intensity=50.0,
            exports_power=False,
            export_compensation=0.08,
            charge_from_grid=False,
            charge_from_adapters=[],
        ),
    )

    @pytest.fixture(params=list(ENTITY_VALUES))
    def entity_values(self, request):
        return self.ENTITY_VALUES[request.param]

    @pytest.fixture()
    def test_case(self, request):
        # entity_values is parameterized, so its param is accessible via the parent fixture's node
        return request.node.callspec.params["entity_values"]

    @pytest.fixture()
    def power_insight(self, entity_values):
        return build_power_insight(self.ADAPTERS, entity_values)

    #
    # TESTS --------------------------------------------------------------->
    #




















    #

    def test_grid_adapters_consumption_shares(
            self, power_insight, entity_values, test_case
    ):
        results = {
            "morning": {
                "grid_1": 0.0,
                "pv_system_1": 0.0,
                "pv_system_2": 0.0,
                "pv_system_3": 0.0,
                "pv_system_4": 0.0,
                "battery_1": 0.0,
                "battery_2": 0.0,
                "battery_3": 0.0,
                "consumer_1": 0.0,
            },
            "midday": {
            },
            "evening": {
            },
        }
        assert power_insight.combined_grid_import == results[test_case]










    def test_combined_grid_import(self, power_insight, entity_values, test_case):
        results = {
            "import": 1000.0,
            "export": 0.0,
            "net_zero": 0.0,
            "nighttime": 500.0,
        }
        assert power_insight.combined_grid_import == results[test_case]

    def test_combined_grid_export(self, power_insight, entity_values, test_case):
        results = {
            "import": 0.0,
            "export": 2000.0,
            "net_zero": 3000.0,
            "nighttime": 0.0,
        }

        assert power_insight.combined_grid_export == results[test_case]

    def test_combined_production(self, power_insight, entity_values, test_case):

        results = {
            "import": 4000.0,
            "export": 4000.0,
            "net_zero": 4000.0,
            "nighttime": 1000.0,
        }

        assert power_insight.combined_production == results[test_case]

    def test_gross_power(self, power_insight, entity_values, test_case):

        results = {
            "import": 5000.0,
            "export": 4000.0,
            "net_zero": 4000.0,
            "nighttime": 1500.0,
        }

        assert power_insight.gross_power == results[test_case]

    def test_combined_utilization(self, power_insight, entity_values, test_case):
        results = {
            "import": 0.0,
            "export": 1000.0,
            "net_zero": 0.0,
            "nighttime": 50.0,
        }

        assert power_insight.combined_utilization == results[test_case]

    def test_combined_consumption(self, power_insight, entity_values, test_case):
        results = {
            "import": 5000.0,
            "export": 1000.0,
            "net_zero": 1000.0,
            "nighttime": 1450.0,
        }

        assert power_insight.combined_consumption == results[test_case]

    def test_combined_consumption_ratio(self, power_insight, entity_values, test_case):
        results = {
            "import": 0.8,
            "export": 1000.0,
            "net_zero": 1000.0,
            "nighttime": 1450.0,
        }

        assert power_insight.combined_consumption_ratio == results[test_case]

    def test_combined_utizilation_ratio(self, power_insight, entity_values, test_case):
        results = {
            "import": 0.0,
            "export": 0.25,
            "net_zero": 0.0,
            "nighttime": 0.0,
        }

        assert power_insight.combined_utizilation_ratio == results[test_case]


    # def test_total_power(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     pv_power = entity_values[self.PV_ENTITY]
    #     assert power_insight.total_power == pytest.approx(grid_import + pv_power)

    # def test_self_consumption(self, power_insight, entity_values):
    #     grid_import = max(entity_values[self.GRID_ENTITY], 0)
    #     grid_export = max(-entity_values[self.GRID_ENTITY], 0)
    #     pv_power = entity_values[self.PV_ENTITY]
    #     total_power = grid_import + pv_power
    #     assert power_insight.self_consumption == pytest.approx(total_power - grid_export)

    #
    # Consumption shares
    #

    def test_grid_adapters_consumption_shares(self, power_insight, entity_values, test_case):
        results = {
            "import": {
                "grid": 0.2,
            },
            "export": {
                "grid": 0.0,
            },
            "net_zero": {
                "grid": 0.0,
            },
            "nighttime": {
                "grid": 0.345,
            },
        }
        assert power_insight.grid_adapters_consumption_shares == pytest.approx(results[test_case])

    def test_prod_adapters_consumption_shares(self, power_insight, entity_values, test_case):
        results = {
            "import": {
                "pv_system": 0.4,
                "battery": 0.4,
            },
            "export": {
                "pv_system": 1.0,
                "battery": 0.0,
            },
            "net_zero": {
                "pv_system": 0.0,
                "battery": 1.0,
            },
            "nighttime": {
                "pv_system": 0.0,
                "battery": 0.69,
            },
        }
        assert power_insight.prod_adapters_consumption_shares == results[test_case]

        #
        # Consumption ratios
        #

        # def test_grid_adapters_consumption_ratios(self, power_insight, entity_values, test_case):
        #     results = {
        #         "import": {
        #             "grid": 0.2,
        #         },
        #         "export": {
        #             "grid": 0.0,
        #         },
        #         "net_zero": {
        #             "grid": 0.0,
        #         },
        #         "nighttime": {
        #             "grid": 0.345,
        #         },
        #     }
        #     assert power_insight.grid_adapters_consumption_ratios == results[test_case]

        # def test_prod_adapters_consumption_ratios(self, power_insight, entity_values, test_case):
        #     results = {
        #         "import": {
        #             "pv_system": 0.4,
        #             "battery": 0.4,
        #         },
        #         "export": {
        #             "pv_system": 1.0,
        #             "battery": 0.0,
        #         },
        #         "net_zero": {
        #             "pv_system": 0.0,
        #             "battery": 1.0,
        #         },
        #         "nighttime": {
        #             "pv_system": 0.0,
        #             "battery": 0.69,
        #         },
        #     }
        #     assert power_insight.prod_adapters_consumption_ratios == results[test_case]



    # def test_prod_adapters_avoided_cost_rates(self, power_insight, entity_values, test_case):
    #     results = {
    #         "import": {
    #             "pv_system": 1,
    #             "battery": 1,
    #         },
    #         "export": {
    #             "pv_system": 1,
    #             "battery": 1,
    #         },
    #         "net_zero": {
    #             "pv_system": 1,
    #             "battery": 1,
    #         },
    #         "nighttime": {
    #             "pv_system": 1,
    #             "battery": 1,
    #         },
    #     }
    #     assert power_insight.prod_adapters_avoided_cost_rates == results[test_case]
