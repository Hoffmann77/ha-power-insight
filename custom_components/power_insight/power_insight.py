"""Modules to calculate the grid status."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable
from dataclasses import dataclass, field

from .metrics import PowerMetric, PowerInput, PowerOutput, Load, Power
from .utils import division_zero

# "grid_config": {
#   "grid_power_entity_inverted": false,
#   "grid_electricity_price_entity": "input_number.strompreis",
#   "grid_co2_intensity_entity": "sensor.electricity_maps_co2_intensitat",
#   "grid_power_entity": "sensor.enphase_gateway_122225053579_grid_power"

from .const import (
    CONF_GRID_POWER, CONF_GRID_INVERTED, CONF_GRID_PRICE,
    CONF_GRID_CO2_INTENSITY, CONF_PV_POWER, CONF_LCOE, CONF_CO2_INTENSITY
)


@dataclass
class AdapterConfig:
    """Adapter configuration.

    Parameters
    ----------
    entities : list of str
        List of all entities used by the adapter.
    provides_power : bool
        Defines whether the adapter provides power.
        A `share` entity is created if the adapter provides power.
    Adapters that
        provide power


    Returns
    -------
    None
        DESCRIPTION.

    """


    entities: list[str] = field(default_factory=list)
    imports_power: bool = False
    exports_power: bool = False
    generates_power: bool = False
    consumes_power: bool = False

    source_entities_power: list[str] = field(default_factory=list)
    source_entities_price: list[str] = field(default_factory=list)
    source_entities_co2: list[str] = field(default_factory=list)

    total_power_entities: list[str] = field(default_factory=list)



# class AdapterRegistry:

#     def __init__(self) -> None:
#         """Initialize instance."""
#         self.adapters: list[BasePowerAdapter] = []
#         self.entity_adapter_dict: dict[str, BasePowerAdapter] = {}

#         self.power_importing_adapters: list[BasePowerAdapter] = []
#         self.power_exporting_adapters: list[BasePowerAdapter] = []
#         self.power_generating_adapters: list[BasePowerAdapter] = []
#         self.power_consuming_adapters: list[BasePowerAdapter] = []

#         self.source_entities_power: list[str] = []
#         self.source_entities_price: list[str] = []
#         self.source_entities_co2: list[str] = []

#     @property
#     def as_list(self) -> list[BasePowerAdapter]:
#         """Return all adapters as list."""
#         return self.adapters

#     def get_adapter(self, entity_id: str) -> BasePowerAdapter | None:
#         """Return the adapter that corresponds to the entity_id."""
#         return self._entity_adapter_dict.get(entity_id)

#     def register(self, adapter) -> None:
#         """Register an adapter."""
#         config = adapter.config

#         # Register the adapter
#         self.adapters.append(adapter)

#         # Register the source entities
#         self._extend_list(
#             self.source_entities_power, config.source_entities_power
#         )
#         self._extend_list(
#             self.source_entities_price, config.source_entities_price
#         )
#         self._extend_list(
#             self.source_entities_co2, config.source_entities_co2
#         )

#         # Categorize the adapters
#         if adapter.config.imports_power:
#             self.power_importing_adapters.append(adapter)
#         if adapter.config.exports_power:
#             self.power_exporting_adapters.append(adapter)
#         if adapter.config.generates_power:
#             self.power_generating_adapters.append(adapter)
#         if adapter.config.consumes_power:
#             self.power_consuming_adapters.append(adapter)

#         # Add the adapters to the entity adapter mapping
#         for entity in adapter.config.entities:
#             self.entity_adapter_dict[entity] = adapter




#     def _extend_list(self, to_extend: list, extend_with: list) -> list:
#         """Extend the given list without duplicates."""
#         return to_extend.extend(
#             [val for val in extend_with if val not in to_extend]
#         )





#     def get_source_entities_power(self) -> list[str]:
#         """Return all entities that affect the total power."""
#         entities = []
#         for adapter in self.adapters:
#             _entities = adapter.source_entities_power
#             entities.extend([e for e in _entities if e not in entities])

#         return entities

#     def get_source_entities_price(self) -> list[str]:
#         """Return all entities that affect the total price."""
#         entities = []
#         for adapter in self.adapters:
#             _entities = adapter.source_entities_price
#             entities.extend([e for e in _entities if e not in entities])

#         return entities

#     def get_source_entities_co2(self) -> list[str]:
#         """Return all entities that affect the total co2 intensity."""
#         entities = []
#         for adapter in self.adapters:
#             _entities = adapter.source_entities_co2
#             entities.extend([e for e in _entities if e not in entities])

#         return entities




#     def get_power_providing_adapters(self) -> list[BasePowerAdapter]:
#         """Return the adapters that provide power."""
#         adapters = []
#         for adapter in self.adapters:
#             config = adapter.config
#             if config.imports_power or config.generates_power:
#                 adapters.append(adapter)

#         return adapters


class PowerInsight:
    """Class used for the calculation of the power insights."""

    def __init__(self) -> None:
        """Initialize instance."""
        self._adapters: list[BasePowerAdapter] = []
        self._entity_adapter_dict: dict[str, BasePowerAdapter] = {}

        self.power_importing_adapters: list[BasePowerAdapter] = []
        self.power_exporting_adapters: list[BasePowerAdapter] = []
        self.power_generating_adapters: list[BasePowerAdapter] = []
        self.power_consuming_adapters: list[BasePowerAdapter] = []

    @property
    def source_entities_power(self) -> list[str]:
        """Return all entities that affect the total power."""
        entities = []
        for adapter in self._adapters:
            _entities = adapter.config.source_entities_power
            entities.extend([e for e in _entities if e not in entities])

        return entities

    @property
    def source_entities_price(self) -> list[str]:
        """Return all entities that affect the total price."""
        entities = []
        for adapter in self._adapters:
            _entities = adapter.config.source_entities_price
            entities.extend([e for e in _entities if e not in entities])

        return entities

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
        return self.power_importing_adapters.extend(
            self.power_generating_adapters
        )

    @property
    def total_input(self) -> float | None:
        """Return the total input power."""
        power = 0
        for adapter in self.power_importing_adapters:
            power += adapter.import_power
        for adapter in self.power_generating_adapters:
            power += adapter.production

        return power

    @property
    def total_output(self) -> float | None:
        """Return the total output."""
        power = 0
        for adapter in self.power_exporting_adapters:
            power += adapter.export_power
        # for adapter in self.power_consuming_adapters:
        #     power += adapter.consumption

        return power

    @property
    def consumption(self) -> float | None:
        """Return the consumption."""
        return self.total_input - self.total_output

#     @property
#     def shares(self):
#         """Return the shares."""
#         shares = {
#             "grid": division_zero(self._grid_import.power, self.total_input)
#         }
#         for name, val in self._production.items():
#             shares[name] = val.power / self.total_input

#         return shares

#     @property
#     def carbon_intensity(self):
#         """Return the carbon intensity."""
#         write_off = self._grid_import.co2_intensity * self.shares["grid"]
#         lifetime = write_off
#         for name, val in self._production.items():
#             # share = val[0] / self.total_input
#             lifetime += val.co2_intensity * self.shares[name]

#         return {"write_off": write_off, "lifetime": lifetime}

#     @property
#     def electricity_price(self):
#         """Return the electricity price."""
#         write_off = lifetime = self._grid_import.price * self.shares["grid"]
#         for name, val in self._production.items():
#             # share = val[0] / self.total_input
#             lifetime += val.price * self.shares[name]

#         return {"write_off": write_off, "lifetime": lifetime}

#     @property
#     def savings(self):
#         """Return the savings."""
#         savings = {}
#         for name, val in self._production.items():
#             grid_price = self._grid_import.price
#             savings[name] = {
#                 "write_off": grid_price * self.shares[name],
#                 "lifetime": (grid_price - val.price) * self.shares[name],
#             }

    def get_adapter(self, entity_id: str) -> BasePowerAdapter | None:
        """Return the adapter that corresponds to the entity_id."""
        return self._entity_adapter_dict.get(entity_id)

    def set_value(self, entity_id, new_value) -> None:
        """Update the value of the given entity_id to new_value."""
        adapter = self.get_adapter(entity_id)
        if adapter is not None:
            adapter.set_value(entity_id, new_value)
        else:
            # TODO: implement
            pass

    def register_adapter(self, adapter) -> None:
        """Register an adapter."""
        self._adapters.append(adapter)

        # Categorize the adapters
        if adapter.config.imports_power:
            self.power_importing_adapters.append(adapter)
        if adapter.config.exports_power:
            self.power_exporting_adapters.append(adapter)
        if adapter.config.generates_power:
            self.power_generating_adapters.append(adapter)
        if adapter.config.consumes_power:
            self.power_consuming_adapters.append(adapter)

        # Add the adapters to the entity adapter mapping
        for entity in adapter.config.entities:
            self._entity_adapter_dict[entity] = adapter






class BasePowerAdapter(ABC):
    """Base class representing a power adapter."""

    def __init__(
            self,
            name: str,
            power_entity: str,
            power_inverted: bool = False,
            price_entity: str | None = None,
            co2_entity: str | None = None,
    ) -> None:
        """Initialize instance."""
        self.name = name
        self._power_entity = power_entity
        self._power_inverted = power_inverted
        self._price_entity = price_entity
        self._co2_entity = co2_entity
        self._values = {
            power_entity: None,
            price_entity: None,
            co2_entity: None,
        }

    @property
    @abstractmethod
    def config(self) -> AdapterConfig:
        """Return the configuration for this adapter."""
        pass

    # @property
    # def entity_ids(self) -> Iterable[str]:
    #     """Return a list of entity_ids required by this adapter."""
    #     return list(self._values.keys())

    @property
    def power(self) -> float | None:
        """Return the power."""
        power = self._values.get(self._power_entity)
        if power is not None:
            return power * -1

        return None

    # @property
    # def price(self) -> float:
    #     """Return the price."""
    #     return self._values.get(self._price_entity)

    # @property
    # def co2_intensity(self) -> float:
    #     """Return the co2 internsity."""
    #     return self._values.get(self._co2_entity)

    def set_value(self, entity_id, value) -> None:
        """Set the value for an entity."""
        self._values[entity_id] = value

    def get_source_entities(self) -> list[str]:
        """Return the required source entities."""
        return [self._power_entity]

    @classmethod
    @abstractmethod
    def from_config(cls, config: dict) -> BasePowerAdapter:
        """Initialize instance from a config entry."""
        pass


class GridAdapter(BasePowerAdapter):
    """Grid power adapter."""

    @property
    def config(self) -> AdapterConfig:
        """Return the configuration for this adapter."""
        return AdapterConfig(
            entities=[self._power_entity],
            imports_power=True,
            exports_power=True,
            source_entities_power=[self._power_entity],
            source_entities_price=[self._price_entity],
            source_entities_co2=[self._co2_entity],
        )

    @property
    def import_power(self) -> float | None:
        """Return the import power."""
        if self.power is not None:
            return self.power if self.power > 0 else 0

        return None

    @property
    def export_power(self) -> float | None:
        """Return the export power."""
        if self.power is not None:
            return self.power if self.power < 0 else 0

        return None

    @classmethod
    def from_config(cls, name: str, config: dict) -> GridAdapter:
        """Create instance from config."""
        return cls(
            name,
            config.get(CONF_GRID_POWER),
            power_inverted=config.get(CONF_GRID_INVERTED),
            price_entity=config.get(CONF_GRID_PRICE),
            co2_entity=config.get(CONF_GRID_CO2_INTENSITY),
        )


class PowerSourceAdapter(BasePowerAdapter):
    """Grid power adapter."""

    @property
    def config(self) -> AdapterConfig:
        """Return the configuration for this adapter."""
        return AdapterConfig(
            entities=[self._power_entity],
            generates_power=True,
            consumes_power=False,
            source_entities_power=[self._power_entity],
        )

    @property
    def production(self) -> float:
        """Return the import power."""
        if self.power is not None:
            return self.power if self.power > 0 else 0

        return None

    # TODO: implement this feature. This allows to deduct the standby power
    # and the resulting costs from the savings.
    # @property
    # def consumption(self) -> float:
    #     """Return the export power."""
    #     if self.power is not None:
    #         return self.power if self.power < 0 else 0

    #     return None

    @classmethod
    def from_pv_config(cls, name: str, config: dict) -> PowerSourceAdapter:
        """Create instance from config."""
        return cls(
            name,
            config.get(CONF_PV_POWER),
            price_entity=config.get(CONF_LCOE),
            co2_entity=config.get(CONF_CO2_INTENSITY),
        )
