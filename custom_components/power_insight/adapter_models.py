"""Adapter models for bridging HA config entry data to adapter instances."""

from __future__ import annotations

from dataclasses import dataclass, field

from .const import (
    CONF_POWER_ENTITY, CONF_POWER_ENTITY_INVERTED,
    CONF_ELECTRICITY_PRICE_ENTITY, CONF_CO2_INTENSITY_ENTITY,
    CONF_INITIAL_LCOE, CONF_INITIAL_CO2_INTENSITY,
    CONF_INITIAL_LCOS,
    CONF_EXPORTS_POWER, CONF_EXPORT_COMPENSATION,
    CONF_CHARGE_FROM_GRID, CONF_CHARGE_FROM_ADAPTERS,
)
from .power_insight import (
    GridAdapter, PvAdapter, BatteryAdapter, ConsumerAdapter,
)


ADAPTER_MODELS: dict[str, type] = {}


def register_model(adapter_type: str):
    """Register an adapter model class for the given adapter type string."""
    def decorator(cls):
        ADAPTER_MODELS[adapter_type] = cls
        return cls
    return decorator


@register_model("grid")
@dataclass
class GridAdapterModel:
    """Model for creating a GridAdapter from config entry data."""

    unique_id: str
    name: str
    power_entity: str
    power_entity_inverted: bool = False
    price_entity: str | None = None
    co2_entity: str | None = None

    @classmethod
    def from_subentry(cls, subentry) -> GridAdapterModel:
        """Create model from a config subentry."""
        config = subentry.data["adapter"]["config"]
        return cls(
            unique_id=subentry.subentry_id,
            name=subentry.title,
            power_entity=config[CONF_POWER_ENTITY],
            power_entity_inverted=config.get(CONF_POWER_ENTITY_INVERTED, False),
            price_entity=config.get(CONF_ELECTRICITY_PRICE_ENTITY),
            co2_entity=config.get(CONF_CO2_INTENSITY_ENTITY),
        )

    def create_adapter(self) -> GridAdapter:
        """Create a GridAdapter instance."""
        return GridAdapter(
            unique_id=self.unique_id,
            verbose_name=self.name,
            power_entity=self.power_entity,
            power_entity_inverted=self.power_entity_inverted,
            price_entity=self.price_entity,
            co2_entity=self.co2_entity,
        )


@register_model("pv_system")
@dataclass
class PvAdapterModel:
    """Model for creating a PvAdapter from config entry data."""

    unique_id: str
    name: str
    power_entity: str
    power_entity_inverted: bool
    lcoe: float
    lco2_intensity: float
    exports_power: bool
    export_compensation: float

    @classmethod
    def from_subentry(cls, subentry) -> PvAdapterModel:
        """Create model from a config subentry."""
        config = subentry.data["adapter"]["config"]
        return cls(
            unique_id=subentry.subentry_id,
            name=subentry.title,
            power_entity=config[CONF_POWER_ENTITY],
            power_entity_inverted=config[CONF_POWER_ENTITY_INVERTED],
            lcoe=config[CONF_INITIAL_LCOE],
            lco2_intensity=config[CONF_INITIAL_CO2_INTENSITY],
            exports_power=config[CONF_EXPORTS_POWER],
            export_compensation=config[CONF_EXPORT_COMPENSATION],
        )

    def create_adapter(self) -> PvAdapter:
        """Create a PvAdapter instance."""
        return PvAdapter(
            unique_id=self.unique_id,
            verbose_name=self.name,
            power_entity=self.power_entity,
            power_entity_inverted=self.power_entity_inverted,
            lcoe=self.lcoe,
            lco2_intensity=self.lco2_intensity,
            exports_power=self.exports_power,
            export_compensation=self.export_compensation,
        )


@register_model("battery")
@dataclass
class BatteryAdapterModel:
    """Model for creating a BatteryAdapter from config entry data."""

    unique_id: str
    name: str
    power_entity: str
    power_entity_inverted: bool
    lcos: float
    lco2_intensity: float
    exports_power: bool
    export_compensation: float
    charge_from_grid: bool = True
    charge_from_adapters: list[str] = field(default_factory=list)

    @classmethod
    def from_subentry(cls, subentry) -> BatteryAdapterModel:
        """Create model from a config subentry."""
        config = subentry.data["adapter"]["config"]
        return cls(
            unique_id=subentry.subentry_id,
            name=subentry.title,
            power_entity=config[CONF_POWER_ENTITY],
            power_entity_inverted=config[CONF_POWER_ENTITY_INVERTED],
            lcos=config[CONF_INITIAL_LCOS],
            lco2_intensity=config[CONF_INITIAL_CO2_INTENSITY],
            exports_power=config[CONF_EXPORTS_POWER],
            export_compensation=config[CONF_EXPORT_COMPENSATION],
            charge_from_grid=config.get(CONF_CHARGE_FROM_GRID, True),
            charge_from_adapters=config.get(CONF_CHARGE_FROM_ADAPTERS, []),
        )

    def create_adapter(self) -> BatteryAdapter:
        """Create a BatteryAdapter instance."""
        return BatteryAdapter(
            unique_id=self.unique_id,
            verbose_name=self.name,
            power_entity=self.power_entity,
            power_entity_inverted=self.power_entity_inverted,
            lcos=self.lcos,
            lco2_intensity=self.lco2_intensity,
            exports_power=self.exports_power,
            export_compensation=self.export_compensation,
            charge_from_grid=self.charge_from_grid,
            charge_from_adapters=self.charge_from_adapters,
        )


@register_model("consumer")
@dataclass
class ConsumerAdapterModel:
    """Model for creating a ConsumerAdapter from config entry data."""

    unique_id: str
    name: str
    power_entity: str
    power_entity_inverted: bool = False

    @classmethod
    def from_subentry(cls, subentry) -> ConsumerAdapterModel:
        """Create model from a config subentry."""
        config = subentry.data["adapter"]["config"]
        return cls(
            unique_id=subentry.subentry_id,
            name=subentry.title,
            power_entity=config[CONF_POWER_ENTITY],
            power_entity_inverted=config[CONF_POWER_ENTITY_INVERTED],
        )

    def create_adapter(self) -> ConsumerAdapter:
        """Create a ConsumerAdapter instance."""
        return ConsumerAdapter(
            unique_id=self.unique_id,
            verbose_name=self.name,
            power_entity=self.power_entity,
            power_entity_inverted=self.power_entity_inverted,
        )
