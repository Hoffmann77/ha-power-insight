"""Modules to calculate the grid status."""

from __future__ import annotations

from typing import Iterable
from dataclasses import dataclass

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


class PowerInsight:

    def __init__(self) -> None:
        self._grid = None
        self._sources = []
        self._storages = []
        self._consumption = []
        self._loads = []

        self._entity_adapter_mapping = {}

    @property
    def total_input(self) -> float:
        """Return the total input power."""
        power = self._grid.import_power
        for source in self._sources:
            power += source.production

        return power

    @property
    def total_output(self):
        """Return the total output."""
        power = self._grid.export_power
        for source in self._sources:
            power += source.consumption

        return power

    @property
    def consumption(self):
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

    def set_value(self, entity_id, new_value) -> None:
        """Update the value of the given entity_id to new_value."""
        adapter = self._entity_adapter_mapping.get(entity_id)
        if adapter is not None:
            adapter.set_value(entity_id, new_value)
        else:
            # TODO: implement
            pass

    def regsiter_grid(self, grid_adapter) -> None:
        """Register a grid adapter."""
        self.grid_adapter = grid_adapter
        self._add_entity_adapter_mapping(grid_adapter)

    def register_power_source(self, pv_adapter) -> None:
        """Register a pv adapter."""
        self.pv_adapter = pv_adapter
        self._add_entity_adapter_mapping(pv_adapter)

    def _add_entity_adapter_mapping(self, adapter) -> None:
        """Add the entity_id adapter mapping."""
        self._entity_adapter_mapping.update(adapter.updaters)


class BasePowerAdapter:

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
    def entity_ids(self) -> Iterable[str]:
        """Return a list of entity_ids required by this adapter."""
        return list(self._values.keys())

    @property
    def updaters(
            self
    ) -> Iterable[str]:
        """Return the entities whose values are stored by this adapter."""
        return {key: self for key in self._values.keys()}

    @property
    def share_adapters(self):
        """Return the share adapters."""
        pass

    @property
    def power(self) -> float:
        """Return the import power."""
        power = self._values.get(self._power_entity)
        if power is not None:
            return power * -1

        return None

    @property
    def price(self) -> float:
        """Return the price."""
        return self._values.get(self._price_entity)

    @property
    def co2_intensity(self) -> float:
        """Return the co2 internsity."""
        return self._values.get(self._co2_entity)

    def set_value(self, entity_id, value):
        """Set the value for an entity."""
        self._values[entity_id] = value

    @classmethod
    def from_config(cls, config):
        """Init from config."""
        raise NotImplementedError("You must implement this method.")


class GridAdapter(BasePowerAdapter):
    """Grid power adapter."""

    @property
    def import_power(self) -> float:
        """Return the import power."""
        if self.power is not None:
            return self.power if self.power > 0 else 0

        return None

    @property
    def export_power(self) -> float:
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
    def production(self) -> float:
        """Return the import power."""
        if self.power is not None:
            return self.power if self.power > 0 else 0

        return None

    @property
    def consumption(self) -> float:
        """Return the export power."""
        if self.power is not None:
            return self.power if self.power < 0 else 0

        return None

    @classmethod
    def from_pv_config(cls, name: str, config: dict) -> PowerSourceAdapter:
        """Create instance from config."""
        return cls(
            name,
            config.get(CONF_PV_POWER),
            price_entity=config.get(CONF_LCOE),
            co2_entity=config.get(CONF_CO2_INTENSITY),
        )
