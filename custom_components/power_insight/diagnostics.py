"""Diagnostics support for PowerInsight."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import CONF_RETIRED_ADAPTERS, DOMAIN
from .power_insight import (
    BaseConsumerAdapter,
    BatteryAdapter,
    GridAdapter,
    PowerInsight,
    PvAdapter,
)

if TYPE_CHECKING:
    from . import MyData


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[MyData]
) -> dict[str, Any]:
    """Return diagnostics for the config entry (hub level)."""
    power_insight: PowerInsight = entry.runtime_data.power_insight

    return {
        "options": entry.options,
        "data": {
            "retired_adapters": entry.data.get(CONF_RETIRED_ADAPTERS, []),
        },
        "adapters": _dump_all_adapters(power_insight),
        "hub_calculations": _dump_hub_calculations(power_insight),
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[MyData], device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a single device (hub or adapter)."""
    power_insight: PowerInsight = entry.runtime_data.power_insight

    identifier = next(
        (value for domain, value in device.identifiers if domain == DOMAIN), None
    )
    if identifier is None:
        return {}

    # Hub device.
    if identifier == entry.entry_id:
        return {
            "options": entry.options,
            "data": {"retired_adapters": entry.data.get(CONF_RETIRED_ADAPTERS, [])},
            "hub_calculations": _dump_hub_calculations(power_insight),
        }

    # Adapter device.
    adapter = _find_adapter(power_insight, identifier)
    if adapter is None:
        return {}

    return {"adapter": _dump_adapter(adapter, power_insight)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_adapter(power_insight: PowerInsight, uid: str):
    """Look up an adapter by uid, safe to call when grid_adapter is None."""
    if power_insight.grid_adapter is not None and power_insight.grid_adapter.uid == uid:
        return power_insight.grid_adapter

    for container in (
        power_insight.pv_system_adapters,
        power_insight.storage_adapters,
        power_insight.consumer_adapters,
    ):
        adapter = container.uid_mapping.get(uid)
        if adapter is not None:
            return adapter

    return None


def _dump_all_adapters(power_insight: PowerInsight) -> dict[str, Any]:
    """Return a snapshot of every registered adapter."""
    result: dict[str, Any] = {}

    if power_insight.grid_adapter is not None:
        result["grid"] = _dump_adapter(power_insight.grid_adapter, power_insight)

    result["pv_systems"] = [
        _dump_adapter(a, power_insight) for a in power_insight.pv_system_adapters
    ]
    result["batteries"] = [
        _dump_adapter(a, power_insight) for a in power_insight.storage_adapters
    ]
    result["consumers"] = [
        _dump_adapter(a, power_insight) for a in power_insight.consumer_adapters
    ]
    return result


def _dump_adapter(adapter, power_insight: PowerInsight) -> dict[str, Any]:
    """Return config, live input values, and calculated outputs for one adapter."""
    data: dict[str, Any] = {
        "uid": adapter.uid,
        "verbose_name": adapter.verbose_name,
        "power_entity": adapter._power_entity,
        "power_entity_inverted": adapter._invert_power,
        "raw_values": dict(adapter._values),
        "correction_factor": adapter.correction_factor,
    }

    if isinstance(adapter, GridAdapter):
        data["adapter_type"] = "grid"
        data["price_entity"] = adapter._price_entity
        data["co2_entity"] = adapter._co2_entity
        data["calculated"] = {
            "import_power_w": adapter.import_power,
            "export_power_w": adapter.export_power,
            "coe_eur_per_kwh": adapter.coe,
            "coe_rate_eur_per_h": adapter.coe_rate,
        }
    elif isinstance(adapter, PvAdapter):
        data["adapter_type"] = "pv_system"
        data["exports_power"] = adapter.exports_power
        data["export_compensation_eur_per_kwh"] = adapter.export_compensation
        data["lcoe_eur_per_kwh"] = adapter.lcoe
        data["calculated"] = {
            "production_w": adapter.production,
            "standby_w": adapter.consumption,
        }
    elif isinstance(adapter, BatteryAdapter):
        data["adapter_type"] = "battery"
        data["exports_power"] = adapter.exports_power
        data["export_compensation_eur_per_kwh"] = adapter.export_compensation
        data["lcos_eur_per_kwh"] = adapter.lcoe
        data["charge_from_adapter_uids"] = adapter.charge_from_adapters
        data["charge_from_adapter_names"] = [
            a.verbose_name
            for uid in adapter.charge_from_adapters
            if (a := _find_adapter(power_insight, uid)) is not None
        ]
        data["calculated"] = {
            "discharge_power_w": adapter.production,
            "charge_power_w": adapter.consumption,
        }
    elif isinstance(adapter, BaseConsumerAdapter):
        data["adapter_type"] = "consumer"
        data["calculated"] = {
            "consumption_w": adapter.consumption,
        }

    return data


def _dump_hub_calculations(power_insight: PowerInsight) -> dict[str, Any]:
    """Return a snapshot of hub-level derived values."""
    if power_insight.grid_adapter is None:
        return {"error": "no_grid_configured"}

    return {
        "gross_power_w": power_insight.gross_power,
        "combined_grid_import_w": power_insight.combined_grid_import,
        "combined_grid_export_w": power_insight.combined_grid_export,
        "combined_production_w": power_insight.combined_production,
        "combined_discharging_power_w": power_insight.combined_discharging_power,
        "combined_charging_power_w": power_insight.combined_charging_power,
        "combined_standby_power_w": power_insight.combined_standby_power,
        "combined_consumption_w": power_insight.combined_consumption,
        "combined_coe_eur_per_kwh": power_insight.combined_coe,
        "combined_lcoe_eur_per_kwh": power_insight.combined_lcoe,
        "combined_coe_rate_eur_per_h": power_insight.combined_coe_rate,
        "combined_lcoe_rate_eur_per_h": power_insight.combined_lcoe_rate,
        "combined_lcoe_rate_corrected_eur_per_h": power_insight.combined_lcoe_rate_corrected,
        "combined_coo_rate_eur_per_h": power_insight.combined_coo_rate,
        "combined_lcoo_rate_eur_per_h": power_insight.combined_lcoo_rate,
        "combined_lcoo_rate_corrected_eur_per_h": power_insight.combined_lcoo_rate_corrected,
        "combined_saving_rate_eur_per_h": power_insight.combined_saving_rate,
        "combined_levelized_saving_rate_eur_per_h": power_insight.combined_levelized_saving_rate,
        "combined_levelized_saving_rate_corrected_eur_per_h": power_insight.combined_levelized_saving_rate_corrected,
        "combined_financial_return_rate_eur_per_h": power_insight.combined_financial_return_rate,
        "combined_levelized_financial_return_rate_eur_per_h": power_insight.combined_levelized_financial_return_rate,
        "combined_levelized_financial_return_rate_corrected_eur_per_h": power_insight.combined_levelized_financial_return_rate_corrected,
        "gross_power_export_ratio": power_insight.gross_power_export_ratio,
        "gross_power_consumption_ratio": power_insight.gross_power_consumption_ratio,
        "gross_power_charging_ratio": power_insight.gross_power_charging_ratio,
        "gross_power_standby_ratio": power_insight.gross_power_standby_ratio,
    }
