"""Set up the PowerInsight integration."""

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import issue_registry as ir
from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_UNAVAILABLE

from .const import (
    CONF_CHARGE_FROM_ADAPTERS,
    DOMAIN,
    PLATFORMS,
)
from .exceptions import (
    BatteryChargeSourcesNotConfigured,
    ensure_battery_charge_sources,
)
from .utils import state_to_value
from .power_insight import PowerInsight
from .event_handler import EventHandler
from .adapter_models import ADAPTER_MODELS


_LOGGER = logging.getLogger(__name__)


type MyConfigEntry = ConfigEntry[MyData]


@dataclass
class MyData:
    """Runtime data definition."""

    power_insight: PowerInsight
    event_handler: EventHandler


async def async_setup_entry(hass: HomeAssistant, entry: MyConfigEntry) -> bool:
    """Init the Mygrid instance from the config entry."""
    power_insight = PowerInsight()

    for subentry in entry.subentries.values():
        adapter_type = subentry.data["adapter"].get("adapter_type")
        if not adapter_type:
            continue

        model_cls = ADAPTER_MODELS.get(adapter_type)
        if model_cls is None:
            _LOGGER.warning("Unknown adapter type %r in subentry %s — skipping.", adapter_type, subentry.subentry_id)
            continue

        model = model_cls.from_subentry(subentry)
        power_insight.register_adapter(model.create_adapter())
    
    if power_insight.grid_adapter is None:
        # Without a grid connection nothing can be calculated; raise a repair
        # issue and set up with no tracked entities. The shared tail below still
        # runs so the platform (and its empty sensor set) loads cleanly.
        ir.async_create_issue(
            hass,
            DOMAIN,
            "no_grid_configured",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="no_grid_configured",
            translation_placeholders={"entry_title": entry.title},
        )
        source_entities: list[str] = []
    else:
        # Grid is present — dismiss any previously raised issue.
        ir.async_delete_issue(hass, DOMAIN, "no_grid_configured")

        # Raise a repair issue for each battery adapter whose
        # charge_from_adapters contains stale references (i.e. adapters that
        # have since been removed).
        valid_source_ids = {
            sub.subentry_id
            for sub in entry.subentries.values()
            if sub.data.get("adapter", {}).get("adapter_type") in ("grid", "pv_system")
        }
        for subentry in entry.subentries.values():
            if subentry.data.get("adapter", {}).get("adapter_type") != "battery":
                continue
            charge_from = subentry.data["adapter"]["config"].get(CONF_CHARGE_FROM_ADAPTERS, [])

            # A battery with no charge source cannot charge from anything — an
            # explicit misconfiguration, not a shorthand for the full mix. Flag
            # it with a repair issue (and self-clear it once sources are set).
            try:
                ensure_battery_charge_sources(subentry.title, charge_from)
            except BatteryChargeSourcesNotConfigured as err:
                _LOGGER.warning("%s", err)
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    f"battery_no_charge_source_{subentry.subentry_id}",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="battery_no_charge_source",
                    translation_placeholders={"battery_name": subentry.title},
                )
                continue
            ir.async_delete_issue(
                hass, DOMAIN, f"battery_no_charge_source_{subentry.subentry_id}"
            )

            if any(source_id not in valid_source_ids for source_id in charge_from):
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    f"reconfigure_battery_{subentry.subentry_id}",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="reconfigure_battery_adapters",
                    translation_placeholders={"battery_name": subentry.title},
                )

        source_entities = power_insight.source_entities

        # Try to get the states of the entity ids to provide initial data.
        for entity_id in source_entities:
            state_obj = hass.states.get(entity_id)
            if state_obj:
                # Set initial data if the state is available.
                if state_obj.state != STATE_UNAVAILABLE:
                    value = state_to_value(state_obj)
                    power_insight.set_value(entity_id, value)

    # --- Shared setup tail (runs for both the grid and no-grid paths) ---
    event_handler = EventHandler(hass, entry.entry_id, power_insight)
    event_handler.track_entities(source_entities)
    entry.runtime_data = MyData(power_insight, event_handler)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    # The ``set_value`` service is registered as a platform entity service in
    # sensor.py (async_setup_entry), so HA handles entity-target resolution.

    return True


async def async_update_listener(
    hass: HomeAssistant, entry: MyConfigEntry
) -> None:
    """Handle config_entry updates."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: MyConfigEntry
) -> bool:
    """Unload the config entries."""
    unload = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    data = entry.runtime_data
    event_handler = data.event_handler
    event_handler.untrack_entities()

    return unload


async def async_migrate_entry(
    hass: HomeAssistant, entry: MyConfigEntry,
) -> bool:
    """Migrate the config entry to a newer version."""
    if entry.version == 1 and entry.minor_version < 2:
        _migrate_options_to_scopes(hass, entry)

    return True


def _migrate_options_to_scopes(hass: HomeAssistant, entry: MyConfigEntry) -> None:
    """Convert the old flat options to the v2 per-scope schema.

    Pre-release, so history is not preserved — only behaviour is roughly kept:
    the old global selection is distributed into each scope, intersected with
    what that scope supports. See docs/options-flow-redesign.md.
    """
    # Imported here to avoid a circular import at module load.
    from .const import SCOPES, SCOPE_SUPPORTED_OPTIONS

    old = entry.options or {}

    # Already in the v2 per-scope shape (e.g. created by the current flow): just
    # stamp the version, never rewrite the user's selection.
    if "scopes" in old:
        if entry.minor_version != 2:
            hass.config_entries.async_update_entry(entry, minor_version=2)
        return

    leaves = set(
        old.get("calculate_instantaneous_rates", [])
        + old.get("calculate_instantaneous_saving_rates", [])
        + old.get("calculate_accumulated_entities", [])
    )
    if old.get("enable_power_shares"):
        leaves |= {
            "enable_distribution_ratios",
            "enable_distribution_shares",
            "enable_charging_source_shares",
            "enable_power_source_shares",
        }
    # Watt sensors were always-on before the redesign — keep them.
    leaves.add("enable_distribution_power")
    # Export compensation used to ride on the cost-rate keys.
    if "calculate_cost_rates" in leaves:
        leaves.add("enable_export_compensation_rate")
    if "accumulate_cost_rates" in leaves:
        leaves.add("accumulate_export_compensation")

    new_options = {
        "schema": 2,
        "scopes": {
            scope: sorted(leaves & SCOPE_SUPPORTED_OPTIONS[scope])
            for scope in SCOPES
        },
        "debug_power_entities": bool(old.get("debug_power_entities", False)),
    }
    hass.config_entries.async_update_entry(
        entry, options=new_options, minor_version=2
    )
