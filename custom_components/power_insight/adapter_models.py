"""Adapter models for bridging HA config entry data to adapter instances."""

from __future__ import annotations

from dataclasses import dataclass, field

from .const import (
    CONF_POWER_ENTITY, CONF_POWER_ENTITY_INVERTED,
    CONF_ELECTRICITY_PRICE_ENTITY, CONF_CO2_INTENSITY_ENTITY,
    CONF_INITIAL_LCOE, CONF_INITIAL_CO2_INTENSITY,
    CONF_INITIAL_LCOS,
    CONF_CORRECTION_FACTOR,
    CONF_EXPORTS_POWER, CONF_EXPORT_COMPENSATION,
    CONF_CHARGE_FROM_ADAPTERS, CONF_POWER_FROM_ADAPTERS,
    CONF_LIFETIME_COST, CONF_LIFETIME_PRODUCTION, CONF_CO2_FOOTPRINT,
)
from .power_insight import (
    GridAdapter, PvAdapter, BatteryAdapter, ConsumerAdapter,
)


def _lcoe_from_lifetime(data: dict) -> float | None:
    """Derive a base LCOE/LCOS (EUR/kWh) from stored lifetime values.

    Used to backfill the immutable base intensity when it was never computed at
    create time (e.g. lifetime data was added later via reconfigure, which does
    not recompute the base). Mirrors ``calculate_lcoe`` in config_flow.py.
    """
    cost = data.get(CONF_LIFETIME_COST)
    production = data.get(CONF_LIFETIME_PRODUCTION)
    return (cost / production) if (cost and production) else None


def _co2_intensity_from_lifetime(data: dict) -> float | None:
    """Derive a base CO2 intensity (g/kWh) from stored lifetime values.

    Mirrors ``calculate_co2_intensity`` in config_flow.py.
    """
    footprint = data.get(CONF_CO2_FOOTPRINT)
    production = data.get(CONF_LIFETIME_PRODUCTION)
    return (footprint / production * 1000) if (footprint and production) else None


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
    lcoe: float | None
    lco2_intensity: float | None
    exports_power: bool
    export_compensation: float
    correction_factor: float = 1.0

    @classmethod
    def from_subentry(cls, subentry) -> PvAdapterModel:
        """Create model from a config subentry."""
        config = subentry.data["adapter"]["config"]
        # Backfill the base intensity from stored lifetime values when it was
        # never computed at create time (e.g. lifetime data added later via
        # reconfigure). No-op when the base is already set.
        lcoe = config.get(CONF_INITIAL_LCOE)
        if lcoe is None:
            lcoe = _lcoe_from_lifetime(subentry.data)
        lco2_intensity = config.get(CONF_INITIAL_CO2_INTENSITY)
        if lco2_intensity is None:
            lco2_intensity = _co2_intensity_from_lifetime(subentry.data)
        return cls(
            unique_id=subentry.subentry_id,
            name=subentry.title,
            power_entity=config[CONF_POWER_ENTITY],
            power_entity_inverted=config.get(CONF_POWER_ENTITY_INVERTED, False),
            lcoe=lcoe,
            lco2_intensity=lco2_intensity,
            exports_power=config.get(CONF_EXPORTS_POWER, False),
            export_compensation=config.get(CONF_EXPORT_COMPENSATION, 0.0),
            correction_factor=config.get(CONF_CORRECTION_FACTOR) or 1.0,
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
            correction_factor=self.correction_factor,
        )


@register_model("battery")
@dataclass
class BatteryAdapterModel:
    """Model for creating a BatteryAdapter from config entry data."""

    unique_id: str
    name: str
    power_entity: str
    power_entity_inverted: bool
    lcos: float | None
    lco2_intensity: float | None
    exports_power: bool
    export_compensation: float
    charge_from_adapters: list[str] = field(default_factory=list)
    correction_factor: float = 1.0

    @classmethod
    def from_subentry(cls, subentry) -> BatteryAdapterModel:
        """Create model from a config subentry."""
        config = subentry.data["adapter"]["config"]
        # Backfill the base intensity from stored lifetime values when it was
        # never computed at create time (e.g. lifetime data added later via
        # reconfigure). No-op when the base is already set.
        lcos = config.get(CONF_INITIAL_LCOS)
        if lcos is None:
            lcos = _lcoe_from_lifetime(subentry.data)
        lco2_intensity = config.get(CONF_INITIAL_CO2_INTENSITY)
        if lco2_intensity is None:
            lco2_intensity = _co2_intensity_from_lifetime(subentry.data)
        return cls(
            unique_id=subentry.subentry_id,
            name=subentry.title,
            power_entity=config[CONF_POWER_ENTITY],
            power_entity_inverted=config.get(CONF_POWER_ENTITY_INVERTED, False),
            lcos=lcos,
            lco2_intensity=lco2_intensity,
            exports_power=config.get(CONF_EXPORTS_POWER, False),
            export_compensation=config.get(CONF_EXPORT_COMPENSATION, 0.0),
            charge_from_adapters=config.get(CONF_CHARGE_FROM_ADAPTERS, []),
            correction_factor=config.get(CONF_CORRECTION_FACTOR) or 1.0,
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
            charge_from_adapters=self.charge_from_adapters,
            correction_factor=self.correction_factor,
        )


@register_model("consumer")
@dataclass
class ConsumerAdapterModel:
    """Model for creating a ConsumerAdapter from config entry data."""

    unique_id: str
    name: str
    power_entity: str
    power_entity_inverted: bool = False
    power_from_adapters: list[str] = field(default_factory=list)

    @classmethod
    def from_subentry(cls, subentry) -> ConsumerAdapterModel:
        """Create model from a config subentry."""
        config = subentry.data["adapter"]["config"]
        return cls(
            unique_id=subentry.subentry_id,
            name=subentry.title,
            power_entity=config[CONF_POWER_ENTITY],
            power_entity_inverted=config.get(CONF_POWER_ENTITY_INVERTED, False),
            power_from_adapters=config.get(CONF_POWER_FROM_ADAPTERS, []),
        )

    def create_adapter(self) -> ConsumerAdapter:
        """Create a ConsumerAdapter instance."""
        return ConsumerAdapter(
            unique_id=self.unique_id,
            verbose_name=self.name,
            power_entity=self.power_entity,
            power_entity_inverted=self.power_entity_inverted,
            power_from_adapters=self.power_from_adapters,
        )
