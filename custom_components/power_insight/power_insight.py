"""Modules to calculate the grid status."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
# from typing import Iterable
# from dataclasses import dataclass


# "grid_config": {
#   "grid_power_entity_inverted": false,
#   "grid_electricity_price_entity": "input_number.strompreis",
#   "grid_co2_intensity_entity": "sensor.electricity_maps_co2_intensitat",
#   "grid_power_entity": "sensor.enphase_gateway_122225053579_grid_power"

from homeassistant.const import CONF_NAME

from .const import (
    CONF_KEY,
    CONF_POWER_ENTITY, CONF_POWER_INVERTED, CONF_ELECTRICITY_PRICE,
    CONF_LCOE, CONF_CO2_INTENSITY,
    CONF_LCOS,
    CONF_EXPORTS_POWER, CONF_EXPORT_COMPENSATION,
)


_LOGGER = logging.getLogger(__name__)


class AdapterContainer:
    """Container for adapters."""

    def __init__(self) -> None:
        """Initialize instance."""
        self.adapters = []
        self.key_mapping = {}

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

        self.key_mapping[adapter.key] = adapter

    def get_by_key(self, key: str):
        """Return the adapter by key."""
        return self.key_mapping.get(key)


class ProductionAdapters(AdapterContainer):
    """Container for production adapters."""

    pass


class ConsumptionAdapters(AdapterContainer):
    """Container for production adapters."""

    pass


class PowerInsight:
    """Class used for the calculation of the power insights."""

    def __init__(self, grid_adapter: GridAdapter) -> None:
        """Initialize instance."""
        self.grid_adapter = grid_adapter
        self.prod_adapters = ProductionAdapters()
        self.cons_adapters = ConsumptionAdapters()

        if not isinstance(grid_adapter, GridAdapter):
            raise ValueError("Invalid adapter.")

    @property
    def entity_mapping(self) -> dict:
        """Return the adapter by it's key."""
        mapping = {}
        for entity in self.grid_adapter.source_entities:
            mapping[entity] = self.grid_adapter

        mapping.update(self.prod_adapters.entity_mapping)
        mapping.update(self.cons_adapters.entity_mapping)

        return mapping

    @property
    def source_entities_power(self) -> list[str]:
        """Return a list of all entities that affect power."""
        return (
            self.grid_adapter.source_entities_power
            + self.prod_adapters.source_entities_power
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
        entities = []
        for adapter in self._adapters:
            _entities = adapter.config.source_entities_co2
            entities.extend([e for e in _entities if e not in entities])

        return entities

    @property
    def power_providing_adapters(self) -> list[BasePowerAdapter]:
        """Return the adapters that provide power."""
        return [self.grid_adapter] + self.production_adapters

    @property
    def grid_import(self) -> float | None:
        """Return the power that is imported from the grid."""
        if (power := self.grid_adapter.import_power) is None:
            return None

        return power

    @property
    def grid_export(self) -> float | None:
        """Return the power that is returned to the grid."""
        if (power := self.grid_adapter.export_power) is None:
            return None

        return power

    @property
    def production(self) -> float | None:
        """Return the sum of power produced by the production adapters."""
        power = 0.0
        for adapter in self.prod_adapters:
            if (prod := adapter.production) is not None:
                power += prod
            else:
                return None

        return power

    @property
    def utilization(self) -> float | None:
        """Return the sum of power utilized by the production adapters."""
        power = 0.0
        for adapter in self.prod_adapters:
            if (cons := adapter.consumption) is not None:
                power += cons
            else:
                return None

        return power

    @property
    def total_power(self) -> float | None:
        """Return the sum of power that is available."""
        if (grid_import := self.grid_import) is None:
            return None

        if (production := self.production) is None:
            return None

        return grid_import + production

    @property
    def self_consumption(self) -> float | None:
        """Return the sum of power that is neither exported or utilized.

        This is the the power that is self consumed.

        """
        if (total_power := self.total_power) is None:
            return None

        if (power_utilized := self.utilization) is None:
            return None

        if (power_exported := self.grid_export) is None:
            return None

        return total_power - power_exported - power_utilized

    #
    # PRICES
    #

    @property
    def coe_rate(self) -> float | None:
        """Return the combined cost of electricity rate."""
        result = 0.0
        adapters = [self.grid_adapter] + self.prod_adapters.adapters
        for adapter in adapters:
            if (coe_rate := adapter.coe_rate) is None:
                return None

            result += coe_rate

        return result

    @property
    def coe(self) -> float | None:
        """Return the cost of electricity."""
        if (coe_rate := self.coe_rate) is None:
            return None

        if coe_rate == 0.0:
            return 0.0

        if (total_power := self.total_power) is None:
            return None
        else:
            total_power = self._to_kilo(total_power)

        return self._divide(coe_rate, total_power)

    @property
    def lcoe_rate(self) -> float | None:
        """Return the combined levelized cost of electricity rate."""
        result = 0.0
        adapters = [self.grid_adapter] + self.prod_adapters.adapters
        for adapter in adapters:
            if (lcoe_rate := adapter.lcoe_rate) is None:
                return None

            result += lcoe_rate

        return result

    @property
    def lcoe(self) -> float | None:
        """Return the levelized cost of electricity."""
        if (lcoe_rate := self.lcoe_rate) is None:
            return None

        if lcoe_rate == 0.0:
            return 0.0

        if (total_power := self.total_power) is None:
            return None
        else:
            total_power = self._to_kilo(total_power)

        return self._divide(lcoe_rate, total_power)

    @property
    def adapters_coo_rates(self):
        """Return the cost of consumption rates."""
        coo_rates = {}
        if (coe := self.coe) is None:
            return {}

        for adapter in self.prod_adapters:
            if (coo_rate := adapter.get_coo_rate(coe)) is None:
                coo_rates[adapter.key] = None
                continue

            coo_rates[adapter.key] = coo_rate

        return coo_rates

    @property
    def adapters_lcoo_rates(self):
        """Return the cost of consumption rates."""
        lcoo_rates = {}
        if (lcoe := self.lcoe) is None:
            return {}

        for adapter in self.prod_adapters:
            if (lcoo_rate := adapter.get_lcoo_rate(lcoe)) is None:
                lcoo_rates[adapter.key] = None
                continue

            lcoo_rates[adapter.key] = lcoo_rate

        return lcoo_rates

    #
    # TOTAL SHARES
    #

    @property
    def export_share(self) -> float | None:
        """Return the share of total power that is returned to the grid."""
        if (total_power := self.total_power) is None:
            return None

        if (grid_export := self.grid_export) is None:
            return None

        return self._divide(grid_export, total_power)

    @property
    def utilization_share(self) -> float | None:
        """Return the share of total power that is utilized."""
        if (total_power := self.total_power) is None:
            return None

        if (utilization_power := self.utilization) is None:
            return None

        return self._divide(utilization_power, total_power)

    @property
    def self_consumption_share(self) -> float | None:
        """Return the share of total power that is self consumed."""
        if (total_power := self.total_power) is None:
            return None

        if (self_consumption := self.self_consumption) is None:
            return None

        return self._divide(self_consumption, total_power)

    @property
    def applicable_utilization_share(self) -> float | None:
        """Return the share of total_power that is self consumed.

        This is the share of power that is utilized by the production adapters.

        """
        if (export_share := self.export_share) is None:
            return None

        if (utilization_share := self.utilization_share) is None:
            return None

        return self._divide(utilization_share, (1.0 - export_share))

    @property
    def applicable_self_consumption_share(self) -> float | None:
        """Return the share of total_power that is self consumed."""
        if (export_share := self.export_share) is None:
            return None

        if (self_cons_share := self.self_consumption_share) is None:
            return None

        return self._divide(self_cons_share, (1.0 - export_share))

    #
    # TOTAL POWER VALUES
    #

    @property
    def total_export_compensation_rate(self) -> float | None:
        """Total export compensation rate."""
        result = 0.0
        compensation_rates = self.adapters_export_compensation_rates
        for adapter in self.prod_adapters.adapters:
            if (rate := compensation_rates.get(adapter.key)) is None:
                return None

            result += rate

        return result

    @property
    def total_self_cons_saving_rate(self) -> float | None:
        """Total export compensation rate."""
        result = 0.0
        self_cons_saving_rates = self.adapters_self_cons_saving_rates
        for adapter in self.prod_adapters.adapters:
            if (rate := self_cons_saving_rates.get(adapter.key)) is None:
                return None

            result += rate

        return result

    @property
    def total_coo_rate(self) -> float | None:
        """Total export compensation rate."""
        result = 0.0
        coo_rates = self.adapters_coo_rates
        for adapter in self.prod_adapters.adapters:
            if (rate := coo_rates.get(adapter.key)) is None:
                return None

            result += rate

        return result

    @property
    def total_lcoo_rate(self) -> float | None:
        """Total export compensation rate."""
        result = 0.0
        lcoo_rates = self.adapters_lcoo_rates
        for adapter in self.prod_adapters.adapters:
            if (rate := lcoo_rates.get(adapter.key)) is None:
                return None

            result += rate

        return result

    @property
    def total_saving_rate(self) -> float | None:
        """Total export compensation rate."""
        result = 0.0
        saving_rates = self.adapters_saving_rates
        for adapter in self.prod_adapters.adapters:
            if (rate := saving_rates.get(adapter.key)) is None:
                return None

            result += rate

        return result

    @property
    def total_levelized_saving_rate(self) -> float | None:
        """Total export compensation rate."""
        result = 0.0
        levelized_saving_rates = self.adapters_levelized_saving_rates
        for adapter in self.prod_adapters.adapters:
            if (rate := levelized_saving_rates.get(adapter.key)) is None:
                return None

            result += rate

        return result

    #
    # ADAPTER SHARES
    #

    @property
    def adapters_total_power_shares(self) -> dict[str, float]:
        """Return the production adapter's share of total power.

        The fraction of total power that is generated by the adapter.

        """
        shares = {}
        if (total_power := self.total_power) is None:
            return {}

        for adapter in self.prod_adapters.adapters:
            if (production := adapter.production) is None:
                shares[adapter.key] = None
                continue

            shares[adapter.key] = self._divide(production, total_power)

        return shares

    @property
    def adapters_export_rates(self) -> dict[str, float]:
        """Return the production adapter's export rates.

        The fraction of generated power that is returned to the grid.
        Equals: production / returned to grid.

        How much of the power generated by the adapter is send to the grid.

        """
        export_rates = {}
        if (total_export_share := self.export_share) is None:
            return {}

        power_shares = self.adapters_total_power_shares
        export_shares = self.adapters_export_shares
        for adapter in self.prod_adapters.adapters:
            if (power_share := power_shares.get(adapter.key)) is None:
                export_rates[adapter.key] = None

            elif (export_share := export_shares.get(adapter.key)) is None:
                export_rates[adapter.key] = None

            else:
                value = export_share * total_export_share
                export_rates[adapter.key] = self._divide(value, power_share)

        return export_rates

    @property
    def adapters_export_shares(self) -> dict[str, float]:
        """Return the production adapter's share of exported power.

        The fraction of exported power that is generated by the adapter.

        How much of the total exported power is generated by the adapter.

        """
        shares = {}
        exports = {}
        total_share = 0.0

        total_power_shares = self.adapters_total_power_shares
        for adapter in self.prod_adapters.adapters:
            if not adapter.exports_power:
                shares[adapter.key] = 0.0
                continue

            if (share := total_power_shares.get(adapter.key)) is None:
                return {}

            total_share += share
            exports[adapter.key] = share

        for key, share in exports.items():
            shares[key] = self._divide(share, total_share)

        return shares

    # @property
    # def prod_adapters_abs_export_shares(self) -> dict[str, float]:
    #     """Return the production adapter's share of exported power.

    #     The fraction of exported power that is generated by the adapter.

    #     How much of the total exported power is generated by the adapter.

    #     """
    #     shares = {}
    #     exports = {}
    #     total_share = 0.0

    #     if (export_share := self.export_share) is None:
    #         return {}

    #     total_power_shares = self.adapters_total_power_shares
    #     for adapter in self.prod_adapters.adapters:
    #         if not adapter.exports_power:
    #             shares[adapter.key] = 0.0
    #             continue

    #         if (share := total_power_shares.get(adapter.key)) is None:
    #             return {}

    #         total_share += share
    #         exports[adapter.key] = share

    #     for key, share in exports.items():
    #         shares[key] = self._divide(share, total_share) * export_share

    #     return shares

    @property
    def adapters_export_power(self) -> dict[str, float]:
        """Return the production adapter's export power."""
        export_power = {}
        if (grid_export := self.grid_export) is None:
            return {}

        export_shares = self.adapters_export_shares
        for adapter in self.prod_adapters.adapters:
            if (export_share := export_shares.get(adapter.key)) is None:
                export_power[adapter.key] = None
            else:
                export_power[adapter.key] = grid_export * export_share

        return export_power

    @property
    def adapters_export_compensation_rates(self) -> dict[str, float]:
        """Return the export compensation rates."""
        compensation_rates = {}
        export_power = self.adapters_export_power
        for adapter in self.prod_adapters:
            if (power := export_power.get(adapter.key)) is None:
                compensation_rates[adapter.key] = None
                continue

            if (compensation := adapter.export_compensation) is None:
                compensation_rates[adapter.key] = None
                continue

            power = self._to_kilo(power)
            compensation_rates[adapter.key] = power * compensation

        return compensation_rates

    @property
    def adapters_self_cons_rates(self) -> dict[str, float]:
        """Return the relative export shares."""
        rates = {}
        applicable_share = self.applicable_self_consumption_share
        if applicable_share is None:
            return {}

        export_rates = self.adapters_export_rates
        for adapter in self.prod_adapters.adapters:
            if (export_rate := export_rates.get(adapter.key)) is None:
                rates[adapter.key] = None
                continue

            rates[adapter.key] = (1.0 - export_rate) * applicable_share

        return rates

    @property
    def adapters_self_cons_shares(self) -> dict[str, float]:
        """Return the absolute self consumption shares."""
        shares = {}
        if (self_cons_share := self.self_consumption_share) is None:
            return {}

        consumption_rates = self.adapters_self_cons_rates
        total_power_shares = self.adapters_total_power_shares
        for adapter in self.prod_adapters.adapters:
            if (cons_rate := consumption_rates.get(adapter.key)) is None:
                shares[adapter.key] = None
                continue

            if (power_share := total_power_shares.get(adapter.key)) is None:
                shares[adapter.key] = None
                continue

            shares[adapter.key] = self._divide(
                (cons_rate * power_share), self_cons_share
            )

        return shares

    @property
    def adapters_self_cons_power(self) -> dict[str, float]:
        """Return the self consumption power."""
        power = {}
        self_cons_rates = self.adapters_self_cons_rates
        for adapter in self.prod_adapters:
            self_cons_rate = self_cons_rates.get(adapter.key)
            if self_cons_rate is None:
                power[adapter.key] = None
                continue

            self_cons_power = adapter.get_power_from_share(self_cons_rate)
            if self_cons_power is None:
                power[adapter.key] = None
                continue

            power[adapter.key] = self_cons_power

        return power

    @property
    def adapters_self_cons_saving_rates(self) -> dict[str, float]:
        """Return the self consumption power."""
        saving_rates = {}
        if (coe := self.grid_adapter.coe) is None:
            return {}

        self_cons_power = self.adapters_self_cons_power
        for adapter in self.prod_adapters:
            if (power := self_cons_power.get(adapter.key)) is None:
                saving_rates[adapter.key] = None
                continue

            saving_rates[adapter.key] = self._to_kilo(power) * coe

        return saving_rates

    # NOTE: This is not required at the moment (Grid COE == Grid LCOE).
    # @property
    # def adapters_levelized_self_cons_saving_rates(self) -> dict[str, float]:
    #     """Return the self consumption power."""
    #     saving_rates = {}
    #     if (lcoe := self.grid_adapter.lcoe) is None:
    #         return {}

    #     self_cons_power = self.adapters_self_cons_power
    #     for adapter in self.prod_adapters:
    #         if (power := self_cons_power.get(adapter.key)) is None:
    #             saving_rates[adapter.key] = None
    #             continue

    #         saving_rates[adapter.key] = self._to_kilo(power) * lcoe

    #     return saving_rates

    @property
    def adapters_saving_rates(self) -> dict[str, float]:
        """Return the production adapter's total saving rates."""
        saving_rates = {}

        export_compensations = self.adapters_export_compensation_rates
        self_cons_savings = self.adapters_self_cons_saving_rates
        coo_rates = self.adapters_coo_rates

        for adapter in self.prod_adapters:
            if (coe_rate := adapter.coe_rate) is None:
                return {}

            if (earnings := export_compensations.get(adapter.key)) is None:
                return {}

            if (savings := self_cons_savings.get(adapter.key)) is None:
                return {}

            if (coo_rate := coo_rates.get(adapter.key)) is None:
                return {}

            saving_rates[adapter.key] = (
                earnings + savings - coo_rate - coe_rate
            )

        return saving_rates

    @property
    def adapters_levelized_saving_rates(self) -> dict[str, float]:
        """Return the production adapter's total levelized saving rates."""
        saving_rates = {}

        export_compensations = self.adapters_export_compensation_rates
        # Disabled see: adapters_levelized_self_cons_saving_rates
        # self_cons_savings = self.adapters_levelized_self_cons_saving_rates
        self_cons_savings = self.adapters_self_cons_saving_rates
        lcoo_rates = self.adapters_lcoo_rates

        for adapter in self.prod_adapters:
            if (lcoe_rate := adapter.lcoe_rate) is None:
                return {}

            if (earnings := export_compensations.get(adapter.key)) is None:
                return {}

            if (savings := self_cons_savings.get(adapter.key)) is None:
                return {}

            if (lcoo_rate := lcoo_rates.get(adapter.key)) is None:
                return {}

            saving_rates[adapter.key] = (
                earnings + savings - lcoo_rate - lcoe_rate
            )

        return saving_rates








    def get_adapter_by_entity(self, entity: str) -> AbstractBaseAdapter | None:
        """Return the adapter that corresponds to the entity."""
        return self.entity_mapping.get(entity)

    def set_value(self, entity_id: str, new_value: float | None) -> None:
        """Update the value of the given entity_id to new_value."""
        _LOGGER.debug(f"Trying to set value: `{new_value}` on {entity_id}")
        adapter = self.get_adapter_by_entity(entity_id)
        if adapter is not None:
            adapter.set_value(entity_id, new_value)
        else:
            _LOGGER.debug(f"No adapter registered for `{entity_id}`.")
            pass
            # raise ValueError(f"Adapter {adapter} not registered.")

    def register_adapter(self, adapter) -> None:
        """Register an adapter."""
        if isinstance(adapter, GridAdapter):
            self.grid_adapter = adapter

        elif isinstance(adapter, BaseGeneratorAdapter):
            self.prod_adapters.add(adapter)

        elif isinstance(adapter, BaseConsumerAdapter):
            self.cons_adapters.add(adapter)

        else:
            raise ValueError("Error adding the adapter to the registry.")

    def _to_kilo(self, power: float) -> float:
        """Convert the value into the kilo prefix."""
        if power == 0.0:
            return 0.0

        return power / 1000

    def _divide(self, to_divide: float, divide_by: float) -> float:
        """Divide value_1 by value_2."""
        if to_divide == 0.0:
            return 0.0

        return to_divide / divide_by


class AbstractBaseAdapter(ABC):
    """Abstract base adapter."""

    def __init__(self, key, verbose_name, **kwargs) -> None:
        """Initialize base adapter."""
        self.key = key
        self.verbose_name = verbose_name
        self._values = {}

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
    def source_entities_power(self) -> list[str]:
        """Return the source price entities for this adapter."""
        pass

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

    def set_value(self, entity_id, value) -> None:
        """Set the value for an entity."""
        self._values[entity_id] = value

    @classmethod
    @abstractmethod
    def from_config(cls, *args, **kwargs) -> BasePowerAdapter:
        """Initialize instance from a config entry."""
        pass


class BasePowerAdapter(AbstractBaseAdapter):
    """Base class representing a power adapter."""

    def __init__(
        self,
        key: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool = False,
        **kwargs,
    ) -> None:
        """Initialize power adapter."""
        super().__init__(key, verbose_name, **kwargs)

        self._power_entity = power_entity
        self._invert_power = power_entity_inverted
        self._values[power_entity] = None

    @property
    def source_entities_power(self) -> list[str]:
        """Return the source price entities for this adapter."""
        return [self._power_entity]

    @property
    def power(self) -> float | None:
        """Return the power in Watts."""
        power = self._values.get(self._power_entity)
        if power is not None:
            return power  # * -1

        return None


class GridAdapter(BasePowerAdapter):
    """Grid power adapter."""

    def __init__(
        self,
        key: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool = False,
        price_entity: str | None = None,
        co2_entity: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            key, verbose_name, power_entity, power_entity_inverted, **kwargs,
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
        return [self._price_entity]

    @property
    def source_entities_co2(self) -> list[str]:
        """Return the source co2 entities for this adapter."""
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

    @classmethod
    def from_config(cls, config: dict) -> GridAdapter:
        """Create instance from config."""
        return cls(
            key="grid",
            verbose_name="Grid",
            power_entity=config[CONF_POWER_ENTITY],
            power_entity_inverted=config.get(CONF_POWER_INVERTED),
            price_entity=config.get(CONF_ELECTRICITY_PRICE),
            co2_entity=config.get(CONF_CO2_INTENSITY),
        )


class BaseGeneratorAdapter(BasePowerAdapter):
    """Grid power adapter."""

    def __init__(
        self,
        key: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool = False,
        exports_power: bool = False,
        export_compensation: float = 0.0,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            key, verbose_name, power_entity, power_entity_inverted, **kwargs,
        )
        self.exports_power = exports_power
        self.export_compensation = export_compensation

    @property
    def source_entities_price(self) -> list:
        """Return the source power entities for this adapter."""
        return []

    @property
    def source_entities_co2(self) -> list:
        """Return the source co2 entities for this adapter."""
        return []

    @property
    def production(self) -> float | None:
        """Return the amount of power that is generated."""
        if self.power is not None:
            return self.power if self.power > 0 else 0

        return None

    @property
    def consumption(self) -> float | None:
        """Return the amount of power that is consumed."""
        if self.power is not None:
            return self.power * -1. if self.power < 0 else 0

        return None

    # @property
    # def exportable_power(self) -> float | None:
    #     """Return the exportable power."""
    #     if not self.exports_power:
    #         return 0.0

    #     if self.production is None:
    #         return None

    #     return self.production

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

    def get_power_from_share(self, share: float)  -> float | None:
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

    def _multiply_cons(self, value: float) -> float | None:
        """Return the rate for the given value."""
        if (cons := self.consumption) is None:
            return None

        if cons == 0.0:
            return 0.0

        return (cons / 1000) * value

    # @classmethod
    # def from_config(
    #         cls, key: str, verbose_name: str, config: dict
    # ) -> BaseGeneratorAdapter:
    #     """Create instance from config."""
    #     return cls(
    #         key,
    #         verbose_name,
    #         config.get(CONF_PV_POWER_ENTITY),
    #         power_entity_inverted=False,
    #         exports_power=False,
    #         export_compensation=0.0,
    #     )


class PvAdapter(BaseGeneratorAdapter):
    """Photovoltaic system adapter."""

    def __init__(
        self,
        key: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool,
        lcoe: float,
        lco2_intensity: float,
        exports_power: bool,
        export_compensation: float,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            key,
            verbose_name,
            power_entity,
            power_entity_inverted=power_entity_inverted,
            exports_power=exports_power,
            export_compensation=export_compensation,
            **kwargs,
        )
        self._lcoe = lcoe
        self._lco2_intensity = lco2_intensity

    @property
    def lcoe(self) -> float | None:
        """Return the levelized cost of electicity in Euro/kwh."""
        return self._lcoe

    @classmethod
    def from_config(cls, config: dict) -> PvAdapter:
        """Create instance from config."""
        return cls(
            key=config[CONF_KEY],
            verbose_name=config[CONF_NAME],
            power_entity=config[CONF_POWER_ENTITY],
            power_entity_inverted=config[CONF_POWER_INVERTED],
            lcoe=config[CONF_LCOE],
            lco2_intensity=config[CONF_CO2_INTENSITY],
            exports_power=config[CONF_EXPORTS_POWER],
            export_compensation=config[CONF_EXPORT_COMPENSATION],
        )


class BatteryAdapter(BaseGeneratorAdapter):
    """Battery adapter."""

    def __init__(
        self,
        key: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool,
        lcos: float,
        lco2_intensity: float,
        exports_power: bool,
        export_compensation: float,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            key,
            verbose_name,
            power_entity,
            power_entity_inverted=power_entity_inverted,
            exports_power=exports_power,
            export_compensation=export_compensation,
            **kwargs,
        )
        self._lcos = lcos
        self._lco2_intensity = lco2_intensity

    @property
    def lcoe(self) -> float | None:
        """Return the levelized cost of electicity in Euro/kwh."""
        return self._lcos

    @classmethod
    def from_config(cls, config: dict) -> BatteryAdapter:
        """Create instance from config."""
        return cls(
            key=config[CONF_KEY],
            verbose_name=config[CONF_NAME],
            power_entity=config[CONF_POWER_ENTITY],
            power_entity_inverted=config[CONF_POWER_INVERTED],
            lcos=config[CONF_LCOS],
            lco2_intensity=config[CONF_CO2_INTENSITY],
            exports_power=config[CONF_EXPORTS_POWER],
            export_compensation=config[CONF_EXPORT_COMPENSATION],
        )
        # TODO: add CONF_BAT_EFFICIENCY


class BaseConsumerAdapter(BasePowerAdapter):
    """Base adapter for consumers."""

    pass
