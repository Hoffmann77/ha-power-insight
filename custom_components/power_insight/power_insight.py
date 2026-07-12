"""Modules to calculate the grid status."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import defaultdict


_LOGGER = logging.getLogger(__name__)

UNIT_PREFIXES = {None: 1, "k": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}


class AdapterContainer:
    """Container for adapters."""

    def __init__(self) -> None:
        """Initialize instance."""
        self.adapters = []
        self.uid_mapping = {}

    @property
    def source_entities(self) -> list[str]:
        """Return all source entities."""
        return self.source_entities_power

    @property
    def source_entities_power(self) -> list[str]:
        """Return the entities that affect power related attributes."""
        entities = []
        for adapter in self.adapters:
            entities += adapter.source_entities_power

        return entities

    @property
    def entity_mapping(self) -> dict:
        """Return the source entities mapped to the corresponding adapter."""
        mapping = {}
        for adapter in self.adapters:
            for entity in adapter.source_entities:
                mapping[entity] = adapter

        return mapping

    def __iter__(self):
        """Return iterator."""
        return iter(self.adapters)

    def add(self, adapter):
        """Add the given adapter."""
        self.adapters.append(adapter)

        self.uid_mapping[adapter.uid] = adapter

    # def get_by_key(self, uid: str):
    #     """Return the adapter by uid."""
    #     return self.uid_mapping.get(uid)


class PvSystemAdapters(AdapterContainer):
    """Container for production adapters."""

    pass


class BatteryAdapters(AdapterContainer):
    """Container for battery adapters."""

    pass


class ConsumerAdapters(AdapterContainer):
    """Container for production adapters."""

    pass


class PowerInsight:
    """Class used for the calculation of the power insights."""

    def __init__(self) -> None:
        """Initialize instance."""
        # Exactly one grid per entry, by design: one config entry models one
        # energy mix at a single grid connection. Multiple grid connections are
        # modelled as multiple config entries, so this stays a singular slot
        # (the config flow enforces it via the ``grid_already_configured`` guard).
        self.grid_adapter = None
        self.pv_system_adapters = PvSystemAdapters()
        self.storage_adapters = BatteryAdapters()
        self.consumer_adapters = ConsumerAdapters()

    @property
    def entity_mapping(self) -> dict:
        """Return the adapters by it's uid."""
        mapping = {}
        for entity in self.grid_adapter.source_entities:
            mapping[entity] = self.grid_adapter

        mapping.update(self.pv_system_adapters.entity_mapping)
        mapping.update(self.storage_adapters.entity_mapping)
        mapping.update(self.consumer_adapters.entity_mapping)

        return mapping

    @property
    def uid_mapping(self) -> dict:
        """Return the adapters by it's uid."""
        mapping = {
            self.grid_adapter.uid: self.grid_adapter
        }

        mapping.update(self.pv_system_adapters.uid_mapping)
        mapping.update(self.storage_adapters.uid_mapping)
        mapping.update(self.consumer_adapters.uid_mapping)

        return mapping

    # ------------------->
    # ADAPTER HELPERS --->
    # ------------------->

    @property
    def prod_adapters(self) -> list[str]:
        """Return the power producing adatpers."""
        return (
            self.pv_system_adapters.adapters
            + self.storage_adapters.adapters
        )

    @property
    def gross_power_adapters(self) -> list[BasePowerAdapter]:
        """Return the adapters that provide power."""
        return (
            [self.grid_adapter]
            + self.pv_system_adapters.adapters
            + self.storage_adapters.adapters
        )

    # ------------------->
    # SOURCE ENTITIES --->
    # ------------------->

    @property
    def source_entities(self) -> list[str]:
        """Return a list of all source entities."""
        return (
            self.source_entities_power
            + self.source_entities_price
            # + self.source_entities_co2
        )

    @property
    def source_entities_power(self) -> list[str]:
        """Return a list of all entities that affect power."""
        return (
            self.grid_adapter.source_entities_power
            + self.pv_system_adapters.source_entities_power
            + self.storage_adapters.source_entities_power
        )

    @property
    def source_entities_price(self) -> list[str]:
        """Return all entities that affect the total price."""
        return (
            self.grid_adapter.source_entities_price
        )

    @property
    def source_entities_co2(self) -> list[str]:
        """Return all entities that affect the total co2 intensity."""
        # entities = []
        # for adapter in self._adapters:
        #     _entities = adapter.config.source_entities_co2
        #     entities.extend([e for e in _entities if e not in entities])

        # return entities

        return (
            self.grid_adapter.source_entities_co2
        )

    # ------------------------->
    # COMBINED POWER VALUES --->
    # ------------------------->

    @property
    def combined_grid_import(self) -> float | None:
        """Sum of power imported from the grid."""
        if (power := self.grid_adapter.import_power) is None:
            return None

        return power

    @property
    def combined_grid_export(self) -> float | None:
        """Sum of power returned to the grid."""
        if (power := self.grid_adapter.export_power) is None:
            return None

        return power

    @property
    def combined_production(self) -> float | None:
        """Sum of power generated by the production adapters."""
        power = 0.0
        for adapter in self.pv_system_adapters:
            if (prod := adapter.production) is not None:
                power += prod
            else:
                return None

        return power

    @property
    def combined_charging_power(self) -> float | None:
        """Sum of power charged by battery adapters."""
        power = 0.0
        for adapter in self.storage_adapters:
            if (cons := adapter.consumption) is not None:
                power += cons
            else:
                return None

        return power

    @property
    def combined_discharging_power(self) -> float | None:
        """Sum of power discharged by the battery adapters."""
        power = 0.0
        for adapter in self.storage_adapters:
            if (prod := adapter.production) is not None:
                power += prod
            else:
                return None

        return power

    @property
    def combined_standby_power(self) -> float | None:
        """Sum of power consumed by the production adapters.

        This is the power that is consumed by the production adapters during
        nighttime. Its an additional power consumption and thereby split up
        into the cost of operations of the production adapters.

        """
        power = 0.0
        for adapter in self.pv_system_adapters:
            if (cons := adapter.consumption) is not None:
                power += cons
            else:
                return None

        return power

    @property
    def combined_consumption(self) -> float | None:
        """Sum of power consumed by electrical loads (W).

        Sum of power that is neither exported or utilized.

        This is the the power that is self consumed and therby
        generates avoided costs when produced by a production adapter.

        """
        if (gross_power := self.gross_power) is None:
            return None

        if (export_power := self.combined_grid_export) is None:
            return None

        if (charging_power := self.combined_charging_power) is None:
            return None

        if (standby_power := self.combined_standby_power) is None:
            return None

        return gross_power - export_power - charging_power - standby_power

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

        if (discharge := self.combined_discharging_power) is None:
            return None

        return grid_import + production + discharge

    # ------------------------->
    # GROSS POWER RATIOS --->
    # ------------------------->

    @property
    def gross_power_export_ratio(self) -> float | None:
        """Fraction of gross power that is returned to the grid.

        In conjunction with our Idealization that we only have one grid power sensor
        this describes the fraction of the combined produced power that is returned to the grid.

        Simple: How much of the generated power is returned to the grid.

        """
        if (gross_power := self.gross_power) is None:
            return None

        if (grid_export := self.combined_grid_export) is None:
            return None

        if grid_export and not gross_power:
            _LOGGER.warning("Data discrepancy: grid export without total power.")

        return self._divide(grid_export, gross_power)

    @property
    def gross_power_consumption_ratio(self) -> float | None:
        """Fraction of gross power that is self consumed.

        How much of the gross power is consumed.

        """
        if (gross_power := self.gross_power) is None:
            return None

        if (consumption := self.combined_consumption) is None:
            return None

        if consumption and not gross_power:
            _LOGGER.warning("Data discrepancy: self-consumption without gross power.")

        return self._divide(consumption, gross_power)

    @property
    def gross_power_standby_ratio(self) -> float | None:
        """Fraction of gross power that is used as standby power by adapters.

        How much of the gross power is stored in used to keep the adapters
        ready to produce energy.

        """
        if (gross_power := self.gross_power) is None:
            return None

        if (standby_power := self.combined_standby_power) is None:
            return None

        if standby_power and not gross_power:
            _LOGGER.warning("Data discrepancy: utilization without total power.")

        return self._divide(standby_power, gross_power)

    @property
    def gross_power_charging_ratio(self) -> float | None:
        """Fraction of gross power that is charged by storage adapters.

        How much of the gross power is stored in energy storages.

        """
        if (gross_power := self.gross_power) is None:
            return None

        if (charging_power := self.combined_charging_power) is None:
            return None

        if charging_power and not gross_power:
            _LOGGER.warning("Data discrepancy: utilization without total power.")

        return self._divide(charging_power, gross_power)

    # --------------------------------->
    # APPLICABLE GROSS POWER RATIOS --->
    # --------------------------------->

    # @property
    # def applicable_combined_charging_ratio(self) -> float | None:
    #     """Fraction of gross power that is charged by battery adapters.



    #     This is the share of power that is utilized by the production adapters.

    #     """
    #     if (export_share := self.gross_power_export_ratio) is None:
    #         return None

    #     if (utilization_share := self.combined_utilization_share) is None:
    #         return None

    #     return self._divide(utilization_share, (1.0 - export_share))


    # @property
    # def applicable_combined_utilization_ratio(self) -> float | None:
    #     """Return the share of total_power that is self consumed.

    #     This is the share of power that is utilized by the production adapters.

    #     """
    #     if (export_share := self.gross_power_export_ratio) is None:
    #         return None

    #     if (utilization_share := self.combined_utilization_share) is None:
    #         return None

    #     return self._divide(utilization_share, (1.0 - export_share))

    @property
    def gross_power_applicable_consumption_ratio(self) -> float | None:
        """Return the share of total_power that is self consumed."""
        if (export_ratio := self.gross_power_export_ratio) is None:
            return

        if (charging_ratio := self.gross_power_charging_ratio) is None:
            return None

        if (cons_ratio := self.gross_power_consumption_ratio) is None:
            return None

        return self._divide(cons_ratio, (1.0 - export_ratio - charging_ratio))

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

    # ----------------------------->
    # CORRECTION-FACTOR VARIANTS --->
    # ----------------------------->
    #
    # These mirror the base combined levelized rates but scale each adapter's
    # contribution by its (time-constant) correction factor. The base variants
    # above are left untouched so the accumulating sensors keep integrating the
    # base rate; correction is applied only to displayed values.

    @property
    def combined_lcoe_rate_corrected(self) -> float | None:
        """Combined levelized cost rate with per-adapter correction applied."""
        result = 0.0
        adapters = [self.grid_adapter] + self.prod_adapters
        for adapter in adapters:
            if (lcoe_rate := adapter.lcoe_rate) is None:
                return None

            result += lcoe_rate * adapter.correction_factor

        return result

    @property
    def combined_lcoo_rate_corrected(self) -> float | None:
        """Combined levelized operating cost rate with correction applied."""
        result = 0.0
        lcoo_rates = self.prod_adapters_lcoo_rates
        for adapter in self.prod_adapters:
            if (rate := lcoo_rates.get(adapter.uid)) is None:
                return None

            result += rate * adapter.correction_factor

        return result

    @property
    def combined_levelized_saving_rate_corrected(self) -> float | None:
        """Combined levelized cost savings rate with correction applied."""
        result = 0.0
        levelized_saving_rates = self.prod_adapters_levelized_cost_saving_rates
        for adapter in self.prod_adapters:
            if (rate := levelized_saving_rates.get(adapter.uid)) is None:
                return None

            result += rate * adapter.correction_factor

        return result

    @property
    def levelized_correction_factors(self) -> dict[str, float]:
        """Return ``uid -> correction_factor`` for prod adapters with an LCOE.

        Used by the combined accumulated levelized sensor to enumerate the
        active contributors whose per-adapter base totals it sums.
        """
        factors: dict[str, float] = {}
        for adapter in self.prod_adapters:
            if adapter.lcoe is not None:
                factors[adapter.uid] = adapter.correction_factor

        return factors

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

    # ----------------->
    # GRID ADAPTERS --->
    # ----------------->

    @property
    def grid_adapters_gross_power_shares(self) -> dict:
        """Return the grid adapter's share of total power.

        The fraction of total power that is imported by the adapter.

        """
        shares = {}
        if (gross_power := self.gross_power) is None:
            return {}

        if (grid_import := self.combined_grid_import) is None:
            return {}

        for adapter in [self.grid_adapter]:
            shares[adapter.uid] = self._divide(grid_import, gross_power)

        return shares

    @property
    def grid_adapters_consumption_ratios(self) -> dict:
        """Return the relative self consumption rate."""
        rates = {}
        # ???: use applicable share or not?
        applicable_share = self.gross_power_applicable_consumption_ratio
        if applicable_share is None:
            return {}

        for adapter in [self.grid_adapter]:
            rates[adapter.uid] = applicable_share

        return rates

    # @property
    # def grid_adapters_utilization_ratios(self) -> float | None:
    #     """Return the relative utilization rate."""
    #     rates = {}
    #     # ???: use applicable share or not?
    #     applicable_ratio = self.applicable_combined_utilization_ratio
    #     if applicable_ratio is None:
    #         return {}

    #     for adapter in [self.grid_adapter]:
    #         rates[adapter.uid] = applicable_ratio

    #     return rates

    @property
    def grid_adapters_consumption_shares(self) -> dict:
        """Return the relative self consumption shares."""
        shares = {}
        if (self_cons_share := self.gross_power_consumption_ratio) is None:
            return {}

        consumption_ratios = self.grid_adapters_consumption_ratios
        total_power_shares = self.grid_adapters_gross_power_shares
        for adapter in [self.grid_adapter]:
            if (cons_ratios := consumption_ratios.get(adapter.uid)) is None:
                shares[adapter.uid] = None
                continue

            if (power_share := total_power_shares.get(adapter.uid)) is None:
                shares[adapter.uid] = None
                continue

            shares[adapter.uid] = self._divide(
                (cons_ratios * power_share), self_cons_share
            )

        return shares

    # Replaced by charging_shares
    # @property
    # def grid_adapters_utilization_shares(self) -> float | None:
    #     """Return the relative utilization shares."""
    #     shares = {}
    #     if (utilization_share := self.combined_utilization_share) is None:
    #         return {}

    #     utilization_rates = self.grid_adapters_utilization_ratios
    #     total_power_shares = self.grid_adapters_gross_power_shares
    #     for adapter in [self.grid_adapter]:
    #         if (utilization_rate := utilization_rates.get(adapter.uid)) is None:
    #             shares[adapter.uid] = None
    #             continue

    #         if (power_share := total_power_shares.get(adapter.uid)) is None:
    #             shares[adapter.uid] = None
    #             continue

    #         shares[adapter.uid] = self._divide(
    #             (utilization_rate * power_share), utilization_share
    #         )

    #     return shares

    @property
    def grid_adapters_import_power(self) -> dict[str, float | None]:
        """Return the grid adapter's import power keyed by uid."""
        return {self.grid_adapter.uid: self.combined_grid_import}

    @property
    def grid_adapters_export_power(self) -> dict[str, float | None]:
        """Return the grid adapter's export power keyed by uid."""
        return {self.grid_adapter.uid: self.combined_grid_export}

    @property
    def grid_adapters_coe_rate(self) -> dict[str, float | None]:
        """Return the grid import cost rate (EUR/h) keyed by uid."""
        if (import_power := self.combined_grid_import) is None:
            return {self.grid_adapter.uid: None}
        if (coe := self.grid_adapter.coe) is None:
            return {self.grid_adapter.uid: None}
        return {self.grid_adapter.uid: (import_power / 1000) * coe}

    @property
    def grid_adapters_export_compensation_rate(self) -> dict[str, float | None]:
        """Return the grid export compensation rate (EUR/h) keyed by uid.

        Export physically happens at the (single) grid connection, so the
        combined export compensation is surfaced on the grid device.
        """
        return {self.grid_adapter.uid: self.combined_export_compensation_rate}

    # ----------------------->
    # PRODUCTION ADAPTERS --->
    # ----------------------->

    @property
    def prod_adapters_coo_rates(self):
        """Cost of consumption rates."""
        coo_rates = {}
        if (coe := self.combined_coe) is None:
            return {}

        for adapter in self.prod_adapters:
            if (coo_rate := adapter.get_coo_rate(coe)) is None:
                coo_rates[adapter.uid] = None
                continue

            coo_rates[adapter.uid] = coo_rate

        return coo_rates

    @property
    def prod_adapters_lcoo_rates(self):
        """Cost of consumption rates."""
        lcoo_rates = {}
        if (lcoe := self.combined_lcoe) is None:
            return {}

        for adapter in self.prod_adapters:
            if (lcoo_rate := adapter.get_lcoo_rate(lcoe)) is None:
                lcoo_rates[adapter.uid] = None
                continue

            lcoo_rates[adapter.uid] = lcoo_rate

        return lcoo_rates

    @property
    def prod_adapters_gross_power_shares(self) -> dict[str, float]:
        """Return the production adapter's share of total power.

        The fraction of total power that is generated by the adapter.

        """
        shares = {}
        if (total_power := self.gross_power) is None:
            return {}

        for adapter in self.prod_adapters:
            if (production := adapter.production) is None:
                shares[adapter.uid] = None
                continue

            shares[adapter.uid] = self._divide(production, total_power)

        return shares

    @property
    def prod_adapters_export_ratios(self) -> dict[str, float]:
        """Return the production adapter's export ratio.

        The fraction of generated power that is returned to the grid.
        Equals: production / returned to grid.

        How much of the power generated by the adapter is send to the grid.

        """
        export_ratios = {}
        if (total_export_share := self.gross_power_export_ratio) is None:
            return {}

        power_shares = self.prod_adapters_gross_power_shares
        export_shares = self.prod_adapters_export_shares
        for adapter in self.prod_adapters:
            if (power_share := power_shares.get(adapter.uid)) is None:
                export_ratios[adapter.uid] = None

            elif (export_share := export_shares.get(adapter.uid)) is None:
                export_ratios[adapter.uid] = None

            else:
                value = export_share * total_export_share
                export_ratios[adapter.uid] = self._divide(value, power_share)

        return export_ratios

    @property
    def prod_adapters_export_shares(self) -> dict[str, float]:
        """Return the production adapter's share of exported power.

        The fraction of exported power that is generated by the adapter.

        How much of the total exported power is generated by the adapter.

        """
        shares = {}
        exports = {}
        total_share = 0.0

        total_power_shares = self.prod_adapters_gross_power_shares
        for adapter in self.prod_adapters:
            if not adapter.exports_power:
                shares[adapter.uid] = 0.0
                continue

            if (share := total_power_shares.get(adapter.uid)) is None:
                return {}

            total_share += share
            exports[adapter.uid] = share

        for uid, share in exports.items():
            shares[uid] = self._divide(share, total_share)

        return shares

    @property
    def prod_adapters_export_power(self) -> dict[str, float]:
        """Return the production adapter's export power."""
        export_power = {}
        if (grid_export := self.combined_grid_export) is None:
            return {}

        export_shares = self.prod_adapters_export_shares
        for adapter in self.prod_adapters:
            if (export_share := export_shares.get(adapter.uid)) is None:
                export_power[adapter.uid] = None
            else:
                export_power[adapter.uid] = grid_export * export_share

        return export_power

    @property
    def prod_adapters_export_compensation_rates(self) -> dict[str, float]:
        """Return the export compensation rates."""
        compensation_rates = {}
        export_power = self.prod_adapters_export_power
        for adapter in self.prod_adapters:
            if (power := export_power.get(adapter.uid)) is None:
                compensation_rates[adapter.uid] = None
                continue

            if (compensation := adapter.export_compensation) is None:
                compensation_rates[adapter.uid] = None
                continue

            power = self._to_kilo(power)
            compensation_rates[adapter.uid] = power * compensation

        return compensation_rates

    @property
    def prod_adapters_charging_ratios(self) -> dict[str, float]:
        """Return the production adapter's charging ratio.

        The fraction of generated power that is charged by batteries.

        """
        charging_ratios = defaultdict(dict)

        if (combined_charging_ratio := self.gross_power_charging_ratio) is None:
            return {}

        gross_power_shares = self.prod_adapters_gross_power_shares
        charging_shares = self.prod_adapters_charging_shares

        for adapter in self.prod_adapters:
            if (power_share := gross_power_shares.get(adapter.uid)) is None:
                charging_ratios[adapter.uid] = None
                continue

            # No entry means no battery tracks this adapter as a source → ratio = 0.
            adapter_charging_shares = charging_shares.get(adapter.uid, {})
            charging_ratios[adapter.uid]  # initialise as empty dict via defaultdict
            for uid, charging_share in adapter_charging_shares.items():
                value = charging_share * combined_charging_ratio
                charging_ratios[adapter.uid][uid] = self._divide(value, power_share)

        return charging_ratios

    @property
    def prod_adapters_combined_charging_ratios(self) -> dict[str, float]:

        combined_charging_ratios = {}

        all_charging_ratios = self.prod_adapters_charging_ratios

        for adapter in self.prod_adapters:
            adapter_ratios = all_charging_ratios.get(adapter.uid)
            if adapter_ratios is None:
                combined_charging_ratios[adapter.uid] = None
                continue

            combined_ratio = 0.0
            for uid, charging_ratio in adapter_ratios.items():
                combined_ratio += charging_ratio

            combined_charging_ratios[adapter.uid] = combined_ratio

        return combined_charging_ratios

    @property
    def prod_adapters_charging_shares(self) -> dict[str, float]:
        """Return the production adapter's share of charging power.

        The fraction of charging power that is generated by the adapter.

        """
        charging_shares = defaultdict(dict)
        gross_power_shares = self.prod_adapters_gross_power_shares

        for battery in self.storage_adapters:
            if not (charge_from := battery.charge_from_adapters):
                continue

            # The grid contributes to the denominator when it is one of the
            # battery's configured sources. It has no own gross-power entry
            # here, so its share is seeded from the grid gross-power shares.
            if self.grid_adapter.uid in charge_from:
                total_share = self.grid_adapters_gross_power_shares.get(
                    self.grid_adapter.uid, 0.0
                )
            else:
                total_share = 0.0

            for adapter_uid in charge_from:
                if (share := gross_power_shares.get(adapter_uid)) is None:
                    charging_shares[adapter_uid][battery.uid] = 0.0
                    continue

                total_share += share
                charging_shares[adapter_uid][battery.uid] = share

            for adapter_uid in charge_from:
                share = charging_shares[adapter_uid][battery.uid]
                charging_shares[adapter_uid][battery.uid] = self._divide(share, total_share)

        return charging_shares

    # @property
    # def prod_adapters_charging_power(self) -> dict[str, float]:
    #     pass
    #     # TODO

    # @property
    # def prod_adapters_combined_charging_power(self) -> dict[str, float]:

    #     charging_power = {}
    #     if (combined_charging_power := self.combined_charging_power) is None:
    #         return {}

    #     export_shares = self.prod_adapters_export_shares
    #     for adapter in self.prod_adapters:
    #         if (export_share := export_shares.get(adapter.uid)) is None:
    #             export_power[adapter.uid] = None
    #         else:
    #             export_power[adapter.uid] = grid_export * export_share

    #     return export_power

    @property
    def prod_adapters_consumption_ratios(self) -> dict[str, float]:
        """Ratio of power that is self consumed."""
        consumption_ratios = {}
        applicable_ratio = self.gross_power_applicable_consumption_ratio
        if applicable_ratio is None:
            return {}

        export_ratios = self.prod_adapters_export_ratios
        combined_charging_ratios = self.prod_adapters_combined_charging_ratios

        for adapter in self.prod_adapters:
            if not (prod := adapter.production):
                consumption_ratios[adapter.uid] = prod
                continue

            if (export_ratio := export_ratios.get(adapter.uid)) is None:
                consumption_ratios[adapter.uid] = None
                continue

            if (charging_ratio := combined_charging_ratios.get(adapter.uid)) is None:
                consumption_ratios[adapter.uid] = None
                continue

            consumption_ratios[adapter.uid] = (
                (1.0 - export_ratio - charging_ratio) * applicable_ratio
            )

        return consumption_ratios

    @property
    def prod_adapters_consumption_shares(self) -> dict[str, float]:
        """Return the absolute self consumption shares.

        How much of the combined consumption power is produdec by this adapter.

        """
        consumption_shares = {}
        if (combined_cons_ratio := self.gross_power_consumption_ratio) is None:
            return {}

        consumption_ratios = self.prod_adapters_consumption_ratios
        gross_power_shares = self.prod_adapters_gross_power_shares
        for adapter in self.prod_adapters:
            if (cons_ratio := consumption_ratios.get(adapter.uid)) is None:
                consumption_shares[adapter.uid] = None
                continue

            if (power_share := gross_power_shares.get(adapter.uid)) is None:
                consumption_shares[adapter.uid] = None
                continue

            consumption_shares[adapter.uid] = self._divide(
                (cons_ratio * power_share), combined_cons_ratio
            )

        return consumption_shares

    @property
    def prod_adapters_consumption_power(self) -> dict[str, float]:
        """Return the self consumption power."""
        consumption_power = {}
        consumption_ratios = self.prod_adapters_consumption_ratios
        for adapter in self.prod_adapters:
            consumption_ratio = consumption_ratios.get(adapter.uid)
            if consumption_ratio is None:
                consumption_power[adapter.uid] = None
                continue

            cons_power = adapter.get_power_from_ratio(consumption_ratio)
            if cons_power is None:
                consumption_power[adapter.uid] = None
                continue

            consumption_power[adapter.uid] = cons_power

        return consumption_power

    @property
    def prod_adapters_avoided_cost_rates(self) -> dict[str, float]:
        """Return the self consumption power."""
        avoided_cost_rates = {}
        if (coe := self.grid_adapter.coe) is None:
            return {}

        cons_power = self.prod_adapters_consumption_power
        for adapter in self.prod_adapters:
            if (power := cons_power.get(adapter.uid)) is None:
                avoided_cost_rates[adapter.uid] = None
                continue

            avoided_cost_rates[adapter.uid] = self._to_kilo(power) * coe

        return avoided_cost_rates

    # NOTE: This is not required at the moment (Grid COE == Grid LCOE).
    # @property
    # def prod_adapters_levelized_self_cons_saving_rates(self) -> dict[str, float]:
    #     """Return the self consumption power."""
    #     saving_rates = {}
    #     if (lcoe := self.grid_adapter.lcoe) is None:
    #         return {}

    #     self_cons_power = self.prod_adapters_consumption_power
    #     for adapter in self.prod_adapters:
    #         if (power := self_cons_power.get(adapter.uid)) is None:
    #             saving_rates[adapter.uid] = None
    #             continue

    #         saving_rates[adapter.uid] = self._to_kilo(power) * lcoe

    #     return saving_rates

    @property
    def prod_adapters_cost_saving_rates(self) -> dict[str, float]:
        """Return the production adapter's total saving rates."""
        saving_rates = {}

        export_compensations = self.prod_adapters_export_compensation_rates
        avoided_costs = self.prod_adapters_avoided_cost_rates
        coo_rates = self.prod_adapters_coo_rates

        for adapter in self.prod_adapters:
            if (coe_rate := adapter.coe_rate) is None:
                return {}

            if (earnings := export_compensations.get(adapter.uid)) is None:
                return {}

            if (avoided := avoided_costs.get(adapter.uid)) is None:
                return {}

            if (coo_rate := coo_rates.get(adapter.uid)) is None:
                return {}

            saving_rates[adapter.uid] = (
                earnings + avoided - coo_rate - coe_rate
            )

        return saving_rates

    @property
    def prod_adapters_levelized_cost_saving_rates(self) -> dict[str, float]:
        """Return the production adapter's total levelized saving rates."""
        saving_rates = {}

        export_compensations = self.prod_adapters_export_compensation_rates
        # Disabled see: adapters_levelized_self_cons_saving_rates
        # self_cons_savings = self.prod_adapters_levelized_self_cons_saving_rates
        avoided_costs = self.prod_adapters_avoided_cost_rates
        lcoo_rates = self.prod_adapters_lcoo_rates

        for adapter in self.prod_adapters:
            if (lcoe_rate := adapter.lcoe_rate) is None:
                return {}

            if (earnings := export_compensations.get(adapter.uid)) is None:
                return {}

            if (avoided := avoided_costs.get(adapter.uid)) is None:
                return {}

            if (lcoo_rate := lcoo_rates.get(adapter.uid)) is None:
                return {}

            saving_rates[adapter.uid] = (
                earnings + avoided - lcoo_rate - lcoe_rate
            )

        return saving_rates

    # -------------------->
    # STORAGE ADAPTERS --->
    # -------------------->

    @property
    def storage_adapters_dynamic_coe(self) -> dict[str, float | None]:
        dynamic_coe = {}
        source_shares = self.storage_adapters_charging_source_shares

        for storage in self.storage_adapters:
            sources = source_shares.get(storage.uid, {})
            if not sources:
                # No configured charge sources: the charging mix is unknown, so
                # the blended cost is left undefined (uid stays absent -> None).
                continue

            blended = 0.0

            for source_uid, share in sources.items():
                adapter = self.get_adapter_by_uid(source_uid)
                if adapter is None or adapter.coe is None:
                    dynamic_coe[storage.uid] = None
                    break

                blended += adapter.coe * share
            else:
                # No break: every source resolved to a value.
                dynamic_coe[storage.uid] = blended

        return dynamic_coe

    @property
    def storage_adapters_dynamic_lcoe(self) -> dict[str, float | None]:
        dynamic_lcoe = {}
        source_shares = self.storage_adapters_charging_source_shares

        for storage in self.storage_adapters:
            sources = source_shares.get(storage.uid, {})
            if not sources:
                # No configured charge sources: the charging mix is unknown, so
                # the blended cost is left undefined (uid stays absent -> None).
                continue

            blended = 0.0

            for source_uid, share in sources.items():
                adapter = self.get_adapter_by_uid(source_uid)
                if adapter is None or adapter.lcoe is None:
                    dynamic_lcoe[storage.uid] = None
                    break

                blended += adapter.lcoe * share
            else:
                # No break: every source resolved to a value.
                dynamic_lcoe[storage.uid] = blended

        return dynamic_lcoe

    @property
    def storage_adapters_coo_rates(self):
        """Cost of consumption rates."""
        coo_rates = {}
        dynamic_coe = self.storage_adapters_dynamic_coe
        for adapter in self.storage_adapters:
            if (coe_rate := dynamic_coe.get(adapter.uid)) is None:
                coo_rates[adapter.uid] = None
                continue

            if (coo_rate := adapter.get_coo_rate(coe_rate)) is None:
                coo_rates[adapter.uid] = None
                continue

            coo_rates[adapter.uid] = coo_rate

        return coo_rates

    @property
    def storage_adapters_lcoo_rates(self):
        """Cost of consumption rates."""
        lcoo_rates = {}
        dynamic_lcoe = self.storage_adapters_dynamic_lcoe
        for adapter in self.storage_adapters:
            if (lcoe_rate := dynamic_lcoe.get(adapter.uid)) is None:
                lcoo_rates[adapter.uid] = None
                continue

            if (lcoo_rate := adapter.get_lcoo_rate(lcoe_rate)) is None:
                lcoo_rates[adapter.uid] = None
                continue

            lcoo_rates[adapter.uid] = lcoo_rate

        return lcoo_rates

    @property
    def storage_adapters_gross_power_shares(self) -> dict[str, float]:
        """Return the production adapter's share of total power.

        The fraction of total power that is generated by the adapter.

        """
        shares = {}
        if (total_power := self.gross_power) is None:
            return {}

        for adapter in self.storage_adapters:
            if (production := adapter.production) is None:
                shares[adapter.uid] = None
                continue

            shares[adapter.uid] = self._divide(production, total_power)

        return shares

    @property
    def storage_adapters_export_ratios(self) -> dict[str, float]:
        """Return the production adapter's export ratio.

        The fraction of generated power that is returned to the grid.
        Equals: production / returned to grid.

        How much of the power generated by the adapter is send to the grid.

        """
        export_ratios = {}
        if (total_export_share := self.gross_power_export_ratio) is None:
            return {}

        power_shares = self.storage_adapters_gross_power_shares
        export_shares = self.storage_adapters_export_shares
        for adapter in self.storage_adapters:
            if (power_share := power_shares.get(adapter.uid)) is None:
                export_ratios[adapter.uid] = None

            elif (export_share := export_shares.get(adapter.uid)) is None:
                export_ratios[adapter.uid] = None

            else:
                value = export_share * total_export_share
                export_ratios[adapter.uid] = self._divide(value, power_share)

        return export_ratios

    @property
    def storage_adapters_export_shares(self) -> dict[str, float]:
        """Return the production adapter's share of exported power.

        The fraction of exported power that is generated by the adapter.

        How much of the total exported power is generated by the adapter.

        """
        shares = {}
        exports = {}
        total_share = 0.0

        total_power_shares = self.storage_adapters_gross_power_shares
        for adapter in self.storage_adapters:
            if not adapter.exports_power:
                shares[adapter.uid] = 0.0
                continue

            if (share := total_power_shares.get(adapter.uid)) is None:
                return {}

            total_share += share
            exports[adapter.uid] = share

        for uid, share in exports.items():
            shares[uid] = self._divide(share, total_share)

        return shares

    @property
    def storage_adapters_export_power(self) -> dict[str, float]:
        """Return the production adapter's export power."""
        export_power = {}
        if (grid_export := self.combined_grid_export) is None:
            return {}

        export_shares = self.storage_adapters_export_shares
        for adapter in self.storage_adapters:
            if (export_share := export_shares.get(adapter.uid)) is None:
                export_power[adapter.uid] = None
            else:
                export_power[adapter.uid] = grid_export * export_share

        return export_power

    @property
    def storage_adapters_export_compensation_rates(self) -> dict[str, float]:
        """Return the export compensation rates."""
        compensation_rates = {}
        export_power = self.storage_adapters_export_power
        for adapter in self.storage_adapters:
            if (power := export_power.get(adapter.uid)) is None:
                compensation_rates[adapter.uid] = None
                continue

            if (compensation := adapter.export_compensation) is None:
                compensation_rates[adapter.uid] = None
                continue

            power = self._to_kilo(power)
            compensation_rates[adapter.uid] = power * compensation

        return compensation_rates

    @property
    def storage_adapters_charging_ratios(self) -> dict[str, float]:
        """Return the production adapter's charging ratio.

        The fraction of generated power that is charged by batteries.

        """
        charging_ratios = defaultdict(dict)

        if (combined_charging_ratio := self.gross_power_charging_ratio) is None:
            return {}

        gross_power_shares = self.storage_adapters_gross_power_shares
        charging_shares = self.storage_adapters_charging_shares

        for adapter in self.storage_adapters:
            if (power_share := gross_power_shares.get(adapter.uid)) is None:
                charging_ratios[adapter.uid] = None
                continue

            # No entry means no battery tracks this adapter as a source → ratio = 0.
            adapter_charging_shares = charging_shares.get(adapter.uid, {})
            charging_ratios[adapter.uid]  # initialise as empty dict via defaultdict
            for uid, charging_share in adapter_charging_shares.items():
                value = charging_share * combined_charging_ratio
                charging_ratios[adapter.uid][uid] = self._divide(value, power_share)

        return charging_ratios

    @property
    def storage_adapters_combined_charging_ratios(self) -> dict[str, float]:

        combined_charging_ratios = {}

        all_charging_ratios = self.storage_adapters_charging_ratios

        for adapter in self.storage_adapters:
            adapter_ratios = all_charging_ratios.get(adapter.uid)
            if adapter_ratios is None:
                combined_charging_ratios[adapter.uid] = None
                continue

            combined_ratio = 0.0
            for uid, charging_ratio in adapter_ratios.items():
                combined_ratio += charging_ratio

            combined_charging_ratios[adapter.uid] = combined_ratio

        return combined_charging_ratios

    @property
    def storage_adapters_charging_shares(self) -> dict[str, float]:
        """Return the production adapter's share of charging power.

        The fraction of charging power that is generated by the adapter.

        """
        charging_shares = defaultdict(dict)
        gross_power_shares = self.storage_adapters_gross_power_shares

        for battery in self.storage_adapters:
            if not (charge_from := battery.charge_from_adapters):
                continue

            # The grid contributes to the denominator when it is one of the
            # battery's configured sources. It has no own gross-power entry
            # here, so its share is seeded from the grid gross-power shares.
            if self.grid_adapter.uid in charge_from:
                total_share = self.grid_adapters_gross_power_shares.get(
                    self.grid_adapter.uid, 0.0
                )
            else:
                total_share = 0.0

            for adapter_uid in charge_from:
                if (share := gross_power_shares.get(adapter_uid)) is None:
                    charging_shares[adapter_uid][battery.uid] = 0.0
                    continue

                total_share += share
                charging_shares[adapter_uid][battery.uid] = share

            for adapter_uid in charge_from:
                share = charging_shares[adapter_uid][battery.uid]
                charging_shares[adapter_uid][battery.uid] = self._divide(share, total_share)

        return charging_shares

    @property
    def storage_adapters_charging_source_shares(self):
        """Return ``{battery_uid: {source_uid: share}}``.

        ``share`` is the fraction of the battery's charging power supplied by
        that source, weighting each configured source by its share of gross
        power. A battery's sources are the adapters listed in its
        ``charge_from_adapters`` (grid and/or PV — batteries are never
        selectable as a source). Batteries with no configured sources are
        omitted: their charging mix is unknown.
        """
        source_shares = defaultdict(dict)

        # uid -> share of gross power, spanning every possible source. The
        # production shares already cover PV; the grid is added explicitly.
        gross_shares = (
            self.grid_adapters_gross_power_shares
            | self.prod_adapters_gross_power_shares
        )

        for battery in self.storage_adapters:
            sources = battery.charge_from_adapters
            if not sources:
                continue

            weights = {
                uid: (weight if (weight := gross_shares.get(uid)) is not None else 0.0)
                for uid in sources
            }
            total = sum(weights.values())
            for uid, weight in weights.items():
                source_shares[battery.uid][uid] = self._divide(weight, total)

        return source_shares

    # @property
    # def storage_adapters_charging_power(self) -> dict[str, float]:
    #     pass
    #     # TODO

    # @property
    # def storage_adapters_combined_charging_power(self) -> dict[str, float]:

    #     charging_power = {}
    #     if (combined_charging_power := self.combined_charging_power) is None:
    #         return {}

    #     export_shares = self.storage_adapters_export_shares
    #     for adapter in self.storage_adapters:
    #         if (export_share := export_shares.get(adapter.uid)) is None:
    #             export_power[adapter.uid] = None
    #         else:
    #             export_power[adapter.uid] = grid_export * export_share

    #     return export_power

    @property
    def storage_adapters_consumption_ratios(self) -> dict[str, float]:
        """Ratio of power that is self consumed."""
        consumption_ratios = {}
        applicable_ratio = self.gross_power_applicable_consumption_ratio
        if applicable_ratio is None:
            return {}

        export_ratios = self.storage_adapters_export_ratios
        combined_charging_ratios = self.storage_adapters_combined_charging_ratios

        for adapter in self.storage_adapters:
            if not (prod := adapter.production):
                consumption_ratios[adapter.uid] = prod
                continue

            if (export_ratio := export_ratios.get(adapter.uid)) is None:
                consumption_ratios[adapter.uid] = None
                continue

            if (charging_ratio := combined_charging_ratios.get(adapter.uid)) is None:
                consumption_ratios[adapter.uid] = None
                continue

            consumption_ratios[adapter.uid] = (
                (1.0 - export_ratio - charging_ratio) * applicable_ratio
            )

        return consumption_ratios

    @property
    def storage_adapters_consumption_shares(self) -> dict[str, float]:
        """Return the absolute self consumption shares.

        How much of the combined consumption power is produdec by this adapter.

        """
        consumption_shares = {}
        if (combined_cons_ratio := self.gross_power_consumption_ratio) is None:
            return {}

        consumption_ratios = self.storage_adapters_consumption_ratios
        gross_power_shares = self.storage_adapters_gross_power_shares
        for adapter in self.storage_adapters:
            if (cons_ratio := consumption_ratios.get(adapter.uid)) is None:
                consumption_shares[adapter.uid] = None
                continue

            if (power_share := gross_power_shares.get(adapter.uid)) is None:
                consumption_shares[adapter.uid] = None
                continue

            consumption_shares[adapter.uid] = self._divide(
                (cons_ratio * power_share), combined_cons_ratio
            )

        return consumption_shares

    @property
    def storage_adapters_consumption_power(self) -> dict[str, float]:
        """Return the self consumption power."""
        consumption_power = {}
        consumption_ratios = self.storage_adapters_consumption_ratios
        for adapter in self.storage_adapters:
            consumption_ratio = consumption_ratios.get(adapter.uid)
            if consumption_ratio is None:
                consumption_power[adapter.uid] = None
                continue

            cons_power = adapter.get_power_from_ratio(consumption_ratio)
            if cons_power is None:
                consumption_power[adapter.uid] = None
                continue

            consumption_power[adapter.uid] = cons_power

        return consumption_power

    @property
    def storage_adapters_avoided_cost_rates(self) -> dict[str, float]:
        """Return the self consumption power."""
        avoided_cost_rates = {}
        if (coe := self.grid_adapter.coe) is None:
            return {}

        cons_power = self.storage_adapters_consumption_power
        for adapter in self.storage_adapters:
            if (power := cons_power.get(adapter.uid)) is None:
                avoided_cost_rates[adapter.uid] = None
                continue

            avoided_cost_rates[adapter.uid] = self._to_kilo(power) * coe

        return avoided_cost_rates

    # NOTE: This is not required at the moment (Grid COE == Grid LCOE).
    # @property
    # def storage_adapters_levelized_self_cons_saving_rates(self) -> dict[str, float]:
    #     """Return the self consumption power."""
    #     saving_rates = {}
    #     if (lcoe := self.grid_adapter.lcoe) is None:
    #         return {}

    #     self_cons_power = self.storage_adapters_consumption_power
    #     for adapter in self.storage_adapters:
    #         if (power := self_cons_power.get(adapter.uid)) is None:
    #             saving_rates[adapter.uid] = None
    #             continue

    #         saving_rates[adapter.uid] = self._to_kilo(power) * lcoe

    #     return saving_rates

    @property
    def storage_adapters_cost_saving_rates(self) -> dict[str, float]:
        """Return the production adapter's total saving rates."""
        saving_rates = {}

        export_compensations = self.storage_adapters_export_compensation_rates
        avoided_costs = self.storage_adapters_avoided_cost_rates
        coo_rates = self.storage_adapters_coo_rates

        for adapter in self.storage_adapters:
            if (coe_rate := adapter.coe_rate) is None:
                return {}

            if (earnings := export_compensations.get(adapter.uid)) is None:
                return {}

            if (avoided := avoided_costs.get(adapter.uid)) is None:
                return {}

            if (coo_rate := coo_rates.get(adapter.uid)) is None:
                return {}

            saving_rates[adapter.uid] = (
                earnings + avoided - coo_rate - coe_rate
            )

        return saving_rates

    @property
    def storage_adapters_levelized_cost_saving_rates(self) -> dict[str, float]:
        """Return the production adapter's total levelized saving rates."""
        saving_rates = {}

        export_compensations = self.storage_adapters_export_compensation_rates
        # Disabled see: adapters_levelized_self_cons_saving_rates
        # self_cons_savings = self.storage_adapters_levelized_self_cons_saving_rates
        avoided_costs = self.storage_adapters_avoided_cost_rates
        lcoo_rates = self.storage_adapters_lcoo_rates

        for adapter in self.storage_adapters:
            if (lcoe_rate := adapter.lcoe_rate) is None:
                return {}

            if (earnings := export_compensations.get(adapter.uid)) is None:
                return {}

            if (avoided := avoided_costs.get(adapter.uid)) is None:
                return {}

            if (lcoo_rate := lcoo_rates.get(adapter.uid)) is None:
                return {}

            saving_rates[adapter.uid] = (
                earnings + avoided - lcoo_rate - lcoe_rate
            )

        return saving_rates

    # ----------------------->
    # CONSUMPTION ADAPTERS --->
    # ----------------------->

    @property
    def cons_adapter_total_power_shares(self) -> dict:
        """Return the grid adapter's share of total power.

        The fraction of total power that is imported by the adapter.

        """
        shares = {}
        if (total_power := self.gross_power) is None:
            return {}

        for adapter in self.consumer_adapters.adapters:
            if (consumption := adapter.consumption) is None:
                shares[adapter.uid] = None
                continue

            shares[adapter.uid] = self._divide(consumption, total_power)

        return shares

    @property
    def cons_adapters_consumption_share(self):
        """Return the self consumption shares."""
        shares = {}
        if (self_cons_share := self.gross_power_consumption_ratio) is None:
            return {}

        total_power_shares = self.cons_adapter_total_power_shares
        for adapter in self.consumer_adapters.adapters:
            if (power_share := total_power_shares.get(adapter.uid)) is None:
                shares[adapter.uid] = None
                continue

            shares[adapter.uid] = self._divide(power_share, self_cons_share)

        return shares

    @property
    def cons_adapters_source_shares(self):
        """Return the source distribution."""
        shares = {}
        power_adapter_cons_shares = (
            self.prod_adapters_consumption_shares
            | self.grid_adapters_consumption_shares
        )

        for cons_adapter in self.consumer_adapters.adapters:
            _shares = {}
            for power_adapter in self.gross_power_adapters:
                if (power_adapter_cons_share := power_adapter_cons_shares.get(power_adapter.uid)) is None:
                    _shares[power_adapter.uid] = None
                    continue

                _shares[power_adapter.uid] = power_adapter_cons_share

            shares[cons_adapter.uid] = _shares

        return shares

    @property
    def cons_adapters_coo_rates(self):
        """Cost of consumption rates."""
        coo_rates = {}
        if (coe := self.combined_coe) is None:
            return {}

        for adapter in self.consumer_adapters.adapters:
            if (coo_rate := adapter.get_coo_rate(coe)) is None:
                coo_rates[adapter.uid] = None
                continue

            coo_rates[adapter.uid] = coo_rate

        return coo_rates

    @property
    def cons_adapters_lcoo_rates(self):
        """Cost of consumption rates."""
        lcoo_rates = {}
        if (lcoe := self.combined_lcoe) is None:
            return {}

        for adapter in self.consumer_adapters.adapters:
            if (lcoo_rate := adapter.get_lcoo_rate(lcoe)) is None:
                lcoo_rates[adapter.uid] = None
                continue

            lcoo_rates[adapter.uid] = lcoo_rate

        return lcoo_rates

    # ----------------------------------------------------------------->
    # CHANNEL ATTRIBUTION — CHARGING (CHG) & STANDBY (STB)
    #
    # ┌────────────────────────────────────────────────────────────────┐
    # │ CLAUDE-GENERATED — please review the attribution model.         │
    # │                                                                 │
    # │ Provider-side ratio/share for the charging and standby          │
    # │ channels, mirroring the existing consumption/export properties: │
    # │                                                                 │
    # │   ratio[p] = provider_channel_power[p] / provider_output[p]     │
    # │   share[p] = provider_channel_power[p] / combined_channel_power  │
    # │                                                                 │
    # │ provider_output is grid import for the grid, production for      │
    # │ PV/battery. CHG uses real source routing (charge_from_adapters); │
    # │ STB has no routing and is modelled as drawn proportionally from  │
    # │ the gross-power pool (so every provider's STB ratio equals the   │
    # │ global gross_power_standby_ratio and its STB share equals its    │
    # │ gross-power share).                                             │
    # └────────────────────────────────────────────────────────────────┘
    # ----------------------------------------------------------------->

    @property
    def _provider_charging_powers(self) -> dict[str, float] | None:
        """Return ``{provider_uid: watts contributed to battery charging}``.

        Each battery's charging power (``battery.consumption``) is split across
        its configured sources using ``storage_adapters_charging_source_shares``.
        Providers that are not a charge source for any battery are absent, so a
        ``.get(uid, 0.0)`` yields 0.0 for them. Returns ``None`` when any
        battery's charging power is unavailable or gross power is unknown (the
        source split is undefined without it).
        """
        if self.gross_power is None:
            return None

        source_shares = self.storage_adapters_charging_source_shares
        powers: dict[str, float] = defaultdict(float)
        for battery in self.storage_adapters:
            if (charging := battery.consumption) is None:
                return None
            for source_uid, share in source_shares.get(battery.uid, {}).items():
                powers[source_uid] += charging * share

        return dict(powers)

    @property
    def _provider_standby_powers(self) -> dict[str, float | None] | None:
        """Return ``{provider_uid: watts contributed to device standby}``.

        Standby has no routing configuration, so the combined standby power is
        attributed to providers in proportion to their share of gross power.
        Returns ``None`` when the combined standby power or gross power is
        unavailable; a provider maps to ``None`` when its own gross-power share
        is unavailable.
        """
        if self.gross_power is None:
            return None
        if (standby := self.combined_standby_power) is None:
            return None

        gross_shares = (
            self.grid_adapters_gross_power_shares
            | self.prod_adapters_gross_power_shares
            | self.storage_adapters_gross_power_shares
        )
        powers: dict[str, float | None] = {}
        for uid, share in gross_shares.items():
            powers[uid] = None if share is None else standby * share

        return powers

    # --- Grid ---

    @property
    def grid_adapters_charging_ratios(self) -> dict[str, float | None]:
        """Fraction of grid import that goes to battery charging."""
        if (powers := self._provider_charging_powers) is None:
            return {}
        if (grid_import := self.combined_grid_import) is None:
            return {}

        uid = self.grid_adapter.uid
        return {uid: self._divide(powers.get(uid, 0.0), grid_import)}

    @property
    def grid_adapters_charging_shares(self) -> dict[str, float | None]:
        """Grid's share of the total battery-charging power."""
        if (powers := self._provider_charging_powers) is None:
            return {}
        if (combined := self.combined_charging_power) is None:
            return {}

        uid = self.grid_adapter.uid
        return {uid: self._divide(powers.get(uid, 0.0), combined)}

    @property
    def grid_adapters_standby_ratios(self) -> dict[str, float | None]:
        """Fraction of grid import that goes to device standby."""
        powers = self._provider_standby_powers
        if powers is None:
            return {}

        uid = self.grid_adapter.uid
        if (standby := powers.get(uid)) is None:
            return {}
        if (grid_import := self.combined_grid_import) is None:
            return {}

        return {uid: self._divide(standby, grid_import)}

    @property
    def grid_adapters_standby_shares(self) -> dict[str, float | None]:
        """Grid's share of the total standby power."""
        powers = self._provider_standby_powers
        if powers is None:
            return {}
        if (combined := self.combined_standby_power) is None:
            return {}

        uid = self.grid_adapter.uid
        if (standby := powers.get(uid)) is None:
            return {}

        return {uid: self._divide(standby, combined)}

    # --- Production (PV) ---

    @property
    def prod_adapters_charging_channel_ratios(self) -> dict[str, float | None]:
        """Fraction of each PV system's production that goes to charging."""
        if (powers := self._provider_charging_powers) is None:
            return {}

        ratios: dict[str, float | None] = {}
        for adapter in self.prod_adapters:
            if (prod := adapter.production) is None:
                ratios[adapter.uid] = None
                continue
            ratios[adapter.uid] = self._divide(powers.get(adapter.uid, 0.0), prod)

        return ratios

    @property
    def prod_adapters_charging_channel_shares(self) -> dict[str, float | None]:
        """Each PV system's share of the total battery-charging power."""
        if (powers := self._provider_charging_powers) is None:
            return {}
        if (combined := self.combined_charging_power) is None:
            return {}

        shares: dict[str, float | None] = {}
        for adapter in self.prod_adapters:
            shares[adapter.uid] = self._divide(powers.get(adapter.uid, 0.0), combined)

        return shares

    @property
    def prod_adapters_standby_ratios(self) -> dict[str, float | None]:
        """Fraction of each PV system's production that goes to standby."""
        powers = self._provider_standby_powers
        if powers is None:
            return {}

        ratios: dict[str, float | None] = {}
        for adapter in self.prod_adapters:
            standby = powers.get(adapter.uid)
            prod = adapter.production
            if standby is None or prod is None:
                ratios[adapter.uid] = None
                continue
            ratios[adapter.uid] = self._divide(standby, prod)

        return ratios

    @property
    def prod_adapters_standby_shares(self) -> dict[str, float | None]:
        """Each PV system's share of the total standby power."""
        powers = self._provider_standby_powers
        if powers is None:
            return {}
        if (combined := self.combined_standby_power) is None:
            return {}

        shares: dict[str, float | None] = {}
        for adapter in self.prod_adapters:
            standby = powers.get(adapter.uid)
            shares[adapter.uid] = (
                None if standby is None else self._divide(standby, combined)
            )

        return shares

    # --- Storage (battery) ---
    # Same as the production variants above, iterating the storage adapters so
    # the battery device reads from ``storage_adapters_*`` like its other sensors.

    @property
    def storage_adapters_charging_channel_ratios(self) -> dict[str, float | None]:
        """Fraction of each battery's discharge that goes to charging."""
        if (powers := self._provider_charging_powers) is None:
            return {}

        ratios: dict[str, float | None] = {}
        for adapter in self.storage_adapters:
            if (prod := adapter.production) is None:
                ratios[adapter.uid] = None
                continue
            ratios[adapter.uid] = self._divide(powers.get(adapter.uid, 0.0), prod)

        return ratios

    @property
    def storage_adapters_charging_channel_shares(self) -> dict[str, float | None]:
        """Each battery's share of the total battery-charging power."""
        if (powers := self._provider_charging_powers) is None:
            return {}
        if (combined := self.combined_charging_power) is None:
            return {}

        shares: dict[str, float | None] = {}
        for adapter in self.storage_adapters:
            shares[adapter.uid] = self._divide(powers.get(adapter.uid, 0.0), combined)

        return shares

    @property
    def storage_adapters_standby_ratios(self) -> dict[str, float | None]:
        """Fraction of each battery's discharge that goes to standby."""
        powers = self._provider_standby_powers
        if powers is None:
            return {}

        ratios: dict[str, float | None] = {}
        for adapter in self.storage_adapters:
            standby = powers.get(adapter.uid)
            prod = adapter.production
            if standby is None or prod is None:
                ratios[adapter.uid] = None
                continue
            ratios[adapter.uid] = self._divide(standby, prod)

        return ratios

    @property
    def storage_adapters_standby_shares(self) -> dict[str, float | None]:
        """Each battery's share of the total standby power."""
        powers = self._provider_standby_powers
        if powers is None:
            return {}
        if (combined := self.combined_standby_power) is None:
            return {}

        shares: dict[str, float | None] = {}
        for adapter in self.storage_adapters:
            standby = powers.get(adapter.uid)
            shares[adapter.uid] = (
                None if standby is None else self._divide(standby, combined)
            )

        return shares

    #
    # Utility methods
    #

    def get_adapter_by_entity(self, entity: str) -> AbstractBaseAdapter | None:
        """Return the adapter that corresponds to the entity."""
        return self.entity_mapping.get(entity)

    def get_adapter_by_uid(self, uid: str):
        return self.uid_mapping.get(uid)

    def set_value(self, entity_id: str, new_value: float | None) -> bool:
        """Update the value of the given entity_id to new_value.

        Returns True if the stored value changed, False if it was already
        identical.  EventHandler uses this to suppress unnecessary custom events
        when a source entity fires state_changed but the numeric value is the same.
        """
        _LOGGER.debug(f"Trying to set value: `{new_value}` on {entity_id}")
        adapter = self.get_adapter_by_entity(entity_id)
        if adapter is not None:
            return adapter.set_value(entity_id, new_value)
        _LOGGER.debug(f"No adapter registered for `{entity_id}`.")
        return False

    def register_adapter(self, adapter) -> None:
        """Register an adapter."""
        if isinstance(adapter, GridAdapter):
            self.grid_adapter = adapter
            _LOGGER.debug(f"Registered Grid adapter: {adapter}.")

        elif isinstance(adapter, PvAdapter):
            self.pv_system_adapters.add(adapter)
            _LOGGER.debug(f"Registered PV-System adapter: {adapter}.")

        elif isinstance(adapter, BatteryAdapter):
            self.storage_adapters.add(adapter)
            _LOGGER.debug(f"Registered Battery adapter: {adapter}.")

        elif isinstance(adapter, BaseConsumerAdapter):
            self.consumer_adapters.add(adapter)
            _LOGGER.debug(f"Registered consumption adapter: {adapter}.")

        else:
            raise ValueError(f"Error registering adapter `{adapter}`.")

    def _to_kilo(self, power: float) -> float:
        """Convert the value into the kilo prefix."""
        if power == 0.0:
            return 0.0

        return power / 1000

    def _divide(self, to_divide: float, divide_by: float) -> float:
        """Divide ``to_divide`` by ``divide_by``, guarding both operands.

        Returns ``0.0`` when the numerator is zero or the denominator is zero
        (or falsy). Guarding the denominator prevents ``ZeroDivisionError`` in
        the ratio properties for degenerate states — e.g. a pure grid-export
        reading where ``gross_power`` is ``0.0`` while ``grid_export > 0``.
        """
        if to_divide == 0.0 or not divide_by:
            return 0.0

        return to_divide / divide_by





class AbstractBaseAdapter(ABC):
    """Abstract base adapter."""

    def __init__(self, unique_id, verbose_name, **kwargs) -> None:
        """Initialize base adapter."""
        self.uid = unique_id
        self.verbose_name = verbose_name
        self._values = {}

    @property
    def correction_factor(self) -> float:
        """Return the levelized-cost correction factor (1.0 unless overridden).

        Adapters with an editable lifetime cost (PV/battery) override this with
        ``current_lcoe / default_lcoe``. The factor is time-constant, so it can
        be applied to an accumulated base total to retroactively rescale it.
        """
        return 1.0

    # @property
    # def source_entities(self) -> list[str]:
    #     """Return the source entities for this adapter."""
    #     return (
    #         self.source_entities_power
    #         + self.source_entities_price
    #         + self.source_entities_co2
    #     )

    # @property
    # @abstractmethod
    # def source_entities_power(self) -> list[str]:
    #     """Return the source price entities for this adapter."""
    #     pass

    # @property
    # @abstractmethod
    # def source_entities_price(self) -> list[str]:
    #     """Return the source power entities for this adapter."""
    #     pass

    # @property
    # @abstractmethod
    # def source_entities_co2(self) -> list[str]:
    #     """Return the source co2 entities for this adapter."""
    #     pass

    def set_value(self, entity_id, value) -> bool:
        """Set the value for an entity, returning True if it changed."""
        changed = self._values.get(entity_id) != value
        self._values[entity_id] = value
        return changed


class BasePowerAdapter(AbstractBaseAdapter):
    """Base class representing a power adapter."""

    def __init__(
        self,
        unique_id: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool = False,
        **kwargs,
    ) -> None:
        """Initialize power adapter."""
        super().__init__(unique_id, verbose_name, **kwargs)

        self._power_entity = power_entity
        self._invert_power = power_entity_inverted
        self._values[power_entity] = None

    @property
    def source_entities(self) -> list[str]:
        """Return the source entities for this adapter."""
        return (
            self.source_entities_power
        )

    @property
    def source_entities_power(self) -> list[str]:
        """Return the source price entities for this adapter."""
        return [self._power_entity]

    @property
    def power(self) -> float | None:
        """Return the power in Watts.

        Applies the ``power_entity_inverted`` flag so a source sensor using the
        opposite sign convention is normalised to this integration's convention
        (grid: + import / - export; pv/battery: + producing / - consuming).
        """
        power = self._values.get(self._power_entity)
        if power is None:
            return None

        return -power if self._invert_power else power

    def _multiply_cons(self, value: float) -> float | None:
        """Return ``value`` scaled by this adapter's consumption (in kW).

        Only meaningful on adapters that expose a ``consumption`` property
        (production and consumer adapters); it is defined here so both share a
        single implementation.
        """
        if (cons := self.consumption) is None:
            return None

        if cons == 0.0:
            return 0.0

        return (cons / 1000) * value


class BasePowerProvidingAdapter(BasePowerAdapter):

    @property
    def source_entities(self) -> list[str]:
        """Return the source entities for this adapter."""
        return (
            self.source_entities_power
            + self.source_entities_price
            + self.source_entities_co2
        )

    @property
    @abstractmethod
    def source_entities_price(self) -> list[str]:
        """Return the source power entities for this adapter."""
        pass

    @property
    @abstractmethod
    def source_entities_co2(self) -> list[str]:
        """Return the source co2 entities for this adapter."""
        pass


class GridAdapter(BasePowerProvidingAdapter):
    """Grid power adapter."""

    ADAPTER_TYPES = ("grid",)

    def __init__(
        self,
        unique_id: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool = False,
        price_entity: str | None = None,
        co2_entity: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            unique_id, verbose_name, power_entity, power_entity_inverted, **kwargs,
        )
        self._price_entity = price_entity
        if self._price_entity is not None:
            self._values[self._price_entity] = None

        self._co2_entity = co2_entity
        if self._co2_entity is not None:
            self._values[self._co2_entity] = None

    @property
    def source_entities_price(self) -> list[str]:
        """Return the source power entities for this adapter."""
        if self._price_entity is None:
            return []

        return [self._price_entity]

    @property
    def source_entities_co2(self) -> list[str]:
        """Return the source co2 entities for this adapter."""
        if self._co2_entity is None:
            return []

        return [self._co2_entity]

    @property
    def import_power(self) -> float | None:
        """Return the power imported from the grid."""
        if self.power is not None:
            return self.power if self.power > 0. else 0.

        return None

    @property
    def export_power(self) -> float | None:
        """Return the power exported to the grid."""
        if self.power is not None:
            return self.power * -1. if self.power < 0. else 0.

        return None

    @property
    def coe(self) -> float | None:
        """Return the cost of electicity in Euro/kwh."""
        if (_entity := self._price_entity) is None:
            return None

        return self._values.get(_entity)

    @property
    def coe_rate(self) -> float | None:
        """Return the cost of electicity rate in Euro/h."""
        if (coe := self.coe) is None:
            return None

        if (power := self.import_power) is None:
            return None
        elif power == 0.0:
            return 0.0

        return (power / 1000) * coe

    @property
    def lcoe(self) -> float | None:
        """Return the levelized cost of electicity in Euro/kwh."""
        return self.coe

    @property
    def lcoe_rate(self) -> float | None:
        """Return the levelized cost of electicity rate in Euro/h."""
        if (lcoe := self.lcoe) is None:
            return None

        if (power := self.import_power) is None:
            return None
        elif power == 0.0:
            return 0.0

        return (power / 1000) * lcoe

    @property
    def co2_intensity(self) -> float | None:
        """Return the co2 intensity g/kwh."""
        pass

    @property
    def co2_intensity_rate(self) -> float | None:
        """Return the co2 intensity rate in g/h."""
        pass

    @property
    def lco2_intensity(self) -> float | None:
        """Return the levelized co2 intensity g/kwh."""
        pass

    @property
    def lco2_intensity_rate(self) -> float | None:
        """Return the levelized co2 intensity rate in g/h."""
        pass

class BaseProductionAdapter(BasePowerProvidingAdapter):
    """Grid power adapter."""

    def __init__(
        self,
        unique_id: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool = False,
        exports_power: bool = False,
        export_compensation: float = 0.0,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            unique_id, verbose_name, power_entity, power_entity_inverted, **kwargs,
        )
        self.exports_power = exports_power
        self.export_compensation = export_compensation

    @property
    def source_entities_price(self) -> list:
        """Return the source price entities for this adapter."""
        return []

    @property
    def source_entities_co2(self) -> list:
        """Return the source co2 entities for this adapter."""
        return []

    @property
    def production(self) -> float | None:
        """Return the amount of power that is generated."""
        if self.power is not None:
            return self.power if self.power > 0. else 0.

        return None

    @property
    def consumption(self) -> float | None:
        """Return the amount of power that is consumed."""
        if self.power is not None:
            return self.power * -1. if self.power < 0. else 0.

        return None

    # @property
    # def exportable_power(self) -> float | None:
    #     """Return the exportable power."""
    #     if not self.exports_power:
    #         return 0.0

    #     if self.combined_production is None:
    #         return None

    #     return self.combined_production

    @property
    def coe(self) -> float | None:
        """Return the cost of electicity in Euro/kwh."""
        return 0.0

    @property
    def coe_rate(self) -> float | None:
        """Return the cost of electicity rate in Euro/h."""
        if (coe := self.coe) is None:
            return None

        return self._multiply_prod(coe)

    @property
    def lcoe(self) -> float | None:
        """Return the levelized cost of electicity in Euro/kwh."""
        return self.coe

    @property
    def lcoe_rate(self) -> float | None:
        """Return the levelized cost of electicity rate in Euro/h."""
        if (lcoe := self.lcoe) is None:
            return None

        return self._multiply_prod(lcoe)

    @property
    def co2_intensity(self) -> float | None:
        """Return the co2 intensity g/kwh."""
        return 0.0

    @property
    def co2_intensity_rate(self) -> float | None:
        """Return the co2 intensity rate in g/h."""
        if (co2_intensity := self.co2_intensity) is None:
            return None

        return self._multiply_prod(co2_intensity)

    @property
    def lco2_intensity(self) -> float | None:
        """Return the levelized co2 intensity g/kwh."""
        return 0.0

    @property
    def lco2_intensity_rate(self) -> float | None:
        """Return the levelized co2 intensity rate in g/h."""
        if (lco2_intensity := self.lco2_intensity) is None:
            return None

        return self._multiply_prod(lco2_intensity)

    def get_power_from_ratio(self, share: float)  -> float | None:
        """Return the power."""
        if (production := self.production) is None:
            return None

        return production * share

    def get_coo_rate(self, coe: float) -> float | None:
        """Return the cost of operations rate."""
        return self._multiply_cons(coe)

    def get_lcoo_rate(self, lcoe: float) -> float | None:
        """Return the cost of operations rate."""
        return self._multiply_cons(lcoe)

    def _multiply_prod(self, value: float) -> float | None:
        """Return the given value multiplied with the consumption."""
        if (prod := self.production) is None:
            return None

        if prod == 0.0:
            return 0.0

        return (prod / 1000) * value


class PvAdapter(BaseProductionAdapter):
    """Photovoltaic system adapter."""

    ADAPTER_TYPES = ("pv_system",)

    def __init__(
        self,
        unique_id: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool,
        lcoe: float | None,
        lco2_intensity: float | None,
        exports_power: bool,
        export_compensation: float,
        correction_factor: float = 1.0,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            unique_id,
            verbose_name,
            power_entity,
            power_entity_inverted=power_entity_inverted,
            exports_power=exports_power,
            export_compensation=export_compensation,
            **kwargs,
        )
        self._lcoe = lcoe
        self._lco2_intensity = lco2_intensity
        self._correction_factor = correction_factor

    @property
    def lcoe(self) -> float | None:
        """Return the (base) levelized cost of electicity in Euro/kwh."""
        return self._lcoe

    @property
    def correction_factor(self) -> float:
        """Return the levelized-cost correction factor for this PV system."""
        return self._correction_factor

class BatteryAdapter(BaseProductionAdapter):
    """Battery adapter."""

    ADAPTER_TYPES = ("battery",)

    def __init__(
        self,
        unique_id: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool,
        lcos: float | None,
        lco2_intensity: float | None,
        exports_power: bool,
        export_compensation: float,
        charge_from_adapters: list[str] | None = None,
        correction_factor: float = 1.0,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            unique_id,
            verbose_name,
            power_entity,
            power_entity_inverted=power_entity_inverted,
            exports_power=exports_power,
            export_compensation=export_compensation,
            **kwargs,
        )
        self._lcos = lcos
        self._lco2_intensity = lco2_intensity
        # Normalise: None (field not yet configured) becomes an empty list.
        self.charge_from_adapters: list[str] = (
            charge_from_adapters if charge_from_adapters is not None else []
        )
        self._correction_factor = correction_factor

    @property
    def lcoe(self) -> float | None:
        """Return the (base) levelized cost of electicity in Euro/kwh."""
        return self._lcos

    @property
    def correction_factor(self) -> float:
        """Return the levelized-cost correction factor for this battery."""
        return self._correction_factor

class BaseConsumerAdapter(BasePowerAdapter):
    """Base adapter for consumers."""

    def __init__(
        self,
        unique_id: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool = False,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            unique_id, verbose_name, power_entity, power_entity_inverted, **kwargs,
        )

    @property
    def consumption(self) -> float | None:
        """Return the amount of power that is consumed."""
        if self.power is not None:
            return self.power * -1. if self.power < 0 else 0

        return None

    def get_coo_rate(self, coe: float) -> float | None:
        """Return the cost of operations rate."""
        return self._multiply_cons(coe)

    def get_lcoo_rate(self, lcoe: float) -> float | None:
        """Return the cost of operations rate."""
        return self._multiply_cons(lcoe)


class ConsumerAdapter(BaseConsumerAdapter):

    pass
