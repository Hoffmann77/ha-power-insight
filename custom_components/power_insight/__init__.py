"""The Heat pump Signal integration."""

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .power_insight import (
    PowerInsight, GridAdapter, PvAdapter, BatteryAdapter,
)
from .const import PLATFORMS, CONF_GRID, CONF_PV, CONF_BAT


_LOGGER = logging.getLogger(__name__)


# GridInsights
# InHouseGrid
# HomePower Insights


type MyConfigEntry = ConfigEntry[MyData]


@dataclass
class MyData:
    """Runtime data definition."""

    power_insight: PowerInsight


async def async_setup_entry(hass: HomeAssistant, entry: MyConfigEntry) -> bool:
    """Init the Mygrid instance from the config entry."""
    grid_config = entry.data[CONF_GRID].copy()
    if options := entry.options[CONF_GRID]:
        grid_config.update(options)

    # Create PowerInsight instance
    power_insight = PowerInsight(
        GridAdapter.from_config(grid_config)
    )

    # Add pv-systems
    for key, pv_system in entry.data[CONF_PV].items():
        config = pv_system.copy()
        if options := entry.options[CONF_PV].get(key):
            config.update(options)

        power_insight.register_adapter(
            PvAdapter.from_config(config)
        )

    for key, battery in entry.data[CONF_BAT].items():
        config = battery.copy()
        if options := entry.options[CONF_BAT].get(key):
            config.update(options)

        power_insight.register_adapter(
            BatteryAdapter.from_config(config)
        )

    # Store the runtime data
    entry.runtime_data = MyData(power_insight)

    # Forward the Config Entry to the platform.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload the entry when it's updated.
    entry.async_on_unload(entry.add_update_listener(async_update_listener))

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
    if unload:
        pass

    return unload


# async def async_migrate_entry(
#         hass: HomeAssistant,
#         entry: MyConfigEntry,
# ) -> bool:
#     """Migrate old entry."""
#     if entry.version == 0:
#         pass
#         _LOGGER.info("Migration to version {config_entry.version} successful")

#     return True
