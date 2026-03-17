"""Set up the PowerInsight integration."""

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import issue_registry as ir
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.exceptions import ConfigEntryNotReady


from .const import DOMAIN, PLATFORMS
from .utils import state_to_value
from .power_insight import (
    DEVICE_ADAPTERS, PowerInsight, EventHandler,
)


_LOGGER = logging.getLogger(__name__)


type MyConfigEntry = ConfigEntry[MyData]


@dataclass
class MyData:
    """Runtime data definition."""

    power_insight: PowerInsight
    event_handler: EventHandler


async def async_setup_entry(hass: HomeAssistant, entry: MyConfigEntry) -> bool:
    """Init the Mygrid instance from the config entry."""
    #grid_adapter_data = entry.data["adapter"].copy()
    #grid_adapter = DEVICE_ADAPTERS["grid"]

    # power_insight = PowerInsight(
    #     grid_adapter.from_entry(
    #         unique_id=entry.entry_id,
    #         name="Grid",
    #         config=grid_adapter_data["config"],
    #     )
    # )

    power_insight = PowerInsight()

    for subentry in entry.subentries.values():
        adapter_data = subentry.data["adapter"].copy()
        adapter_type = adapter_data.get("adapter_type")
        if not adapter_type:
            continue

        adapter_cls = DEVICE_ADAPTERS.get(adapter_type)
        if adapter_cls is None:
            _LOGGER.warning("Unknown adapter type %r in subentry %s — skipping.", adapter_type, subentry.subentry_id)
            continue

        power_insight.register_adapter(
            adapter_cls.from_entry(
                unique_id=subentry.subentry_id,
                name=subentry.title,
                config=adapter_data["config"],
            )
        )
    
    if power_insight.grid_adapter is None:
        ir.async_create_issue(
        hass,
        DOMAIN,
        "no_grid_configured",
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="no_grid_configured",
        translation_placeholders={"entry_title": entry.title},
        )
        raise ConfigEntryNotReady("grid_not_configured")
    
    # Grid is present — dismiss any previously raised issue
    ir.async_delete_issue(hass, DOMAIN, "no_grid_configured")

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


async def async_migrate_entry(
    hass: HomeAssistant, entry: MyConfigEntry,
) -> bool:
    """Migrate the old config entry to a newer version."""
    if entry.version > 1:
        pass

    return True
