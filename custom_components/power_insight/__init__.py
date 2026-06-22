"""Set up the PowerInsight integration."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.helpers import issue_registry as ir, entity_registry as er
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import STATE_UNAVAILABLE

from .const import (
    CONF_CHARGE_FROM_ADAPTERS,
    CONF_RETIRED_ADAPTERS,
    DOMAIN,
    PLATFORMS,
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
        ir.async_create_issue(
            hass,
            DOMAIN,
            "no_grid_configured",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="no_grid_configured",
            translation_placeholders={"entry_title": entry.title},
        )
        event_handler = EventHandler(hass, entry.entry_id, power_insight)
        event_handler.track_entities([])
        entry.runtime_data = MyData(power_insight, event_handler)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(async_update_listener))
        return True

    # Grid is present — dismiss any previously raised issue.
    ir.async_delete_issue(hass, DOMAIN, "no_grid_configured")

    # Raise a repair issue for each battery adapter whose charge_from_adapters
    # contains stale references (i.e. adapters that have since been removed).
    valid_source_ids = {
        sub.subentry_id
        for sub in entry.subentries.values()
        if sub.data.get("adapter", {}).get("adapter_type") in ("grid", "pv_system")
    }
    for subentry in entry.subentries.values():
        if subentry.data.get("adapter", {}).get("adapter_type") != "battery":
            continue
        charge_from = subentry.data["adapter"]["config"].get(CONF_CHARGE_FROM_ADAPTERS, [])
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

    event_handler = EventHandler(hass, entry.entry_id, power_insight)

    event_handler.track_entities(source_entities)

    entry.runtime_data = MyData(power_insight, event_handler)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    async def handle_set_value(call: ServiceCall):
        entity_id = call.data["entity_id"]
        value = call.data["value"]

        # Look up your entity
        entity = hass.data[DOMAIN]["entities"].get(entity_id)
        if entity:
            await entity.async_set_value(value)

    hass.services.async_register(
        DOMAIN,
        "set_value",
        handle_set_value,
    )

    return True


async def async_update_listener(
    hass: HomeAssistant, entry: MyConfigEntry
) -> bool:
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


# Per-adapter levelized accumulated sensor keys whose final value is frozen
# into the retired-adapter ledger on removal (see sensor.py).
LEVELIZED_TOTAL_KEYS = (
    "total_levelized_operating_costs",
    "total_levelized_cost_savings",
)


def _snapshot_retired_adapter(
    hass: HomeAssistant,
    entry: MyConfigEntry,
    subentry: ConfigSubentry,
) -> None:
    """Freeze a removed PV/battery adapter's levelized totals into the ledger.

    The per-adapter accumulated sensors already display ``base × correction``,
    so snapshotting their live state captures the final corrected contribution.
    This keeps the combined levelized totals from dropping when an end-of-life
    device is removed.
    """
    ent_reg = er.async_get(hass)
    totals: dict[str, float] = {}
    for key in LEVELIZED_TOTAL_KEYS:
        unique_id = f"{entry.entry_id}_{subentry.subentry_id}_{key}"
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
        if entity_id is None:
            continue
        state = hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, "unknown"):
            continue
        try:
            totals[key] = float(state.state)
        except (ValueError, TypeError):
            continue

    if not totals:
        return

    ledger = list(entry.data.get(CONF_RETIRED_ADAPTERS, []))
    ledger.append(
        {
            "subentry_id": subentry.subentry_id,
            "adapter_type": subentry.data.get("adapter", {}).get("adapter_type"),
            "title": subentry.title,
            "retired_at": datetime.now(UTC).isoformat(),
            "totals": totals,
        }
    )
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_RETIRED_ADAPTERS: ledger}
    )


async def async_remove_subentry(
    hass: HomeAssistant,
    entry: MyConfigEntry,
    subentry: ConfigSubentry,
) -> None:
    """Snapshot retired levelized totals and raise battery repair issues."""
    removed_type = subentry.data.get("adapter", {}).get("adapter_type")

    # Freeze a removed end-of-life PV/battery adapter's contribution.
    if removed_type in ("pv_system", "battery"):
        _snapshot_retired_adapter(hass, entry, subentry)

    if removed_type not in ("grid", "pv_system"):
        return

    removed_id = subentry.subentry_id
    for remaining in entry.subentries.values():
        if remaining.data.get("adapter", {}).get("adapter_type") != "battery":
            continue
        charge_from = remaining.data["adapter"]["config"].get(CONF_CHARGE_FROM_ADAPTERS, [])
        if removed_id in charge_from:
            ir.async_create_issue(
                hass,
                DOMAIN,
                f"reconfigure_battery_{remaining.subentry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="reconfigure_battery_adapters",
                translation_placeholders={"battery_name": remaining.title},
            )


async def async_migrate_entry(
    hass: HomeAssistant, entry: MyConfigEntry,
) -> bool:
    """Migrate the old config entry to a newer version."""
    if entry.version > 1:
        pass

    return True
