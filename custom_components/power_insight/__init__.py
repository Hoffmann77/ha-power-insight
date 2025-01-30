"""The Heat pump Signal integration."""

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .power_insight import PowerInsight, GridAdapter, PowerSourceAdapter
from .const import PLATFORMS, CONF_GRID, CONF_PV, CONF_LCOE


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
    power_insight = PowerInsight()

    if grid_config := entry.options.get(CONF_GRID):
        power_insight.register_grid(
            GridAdapter.from_config("grid", grid_config)
        )

    if pv_config := entry.options.get(CONF_PV):
        if data := entry.data.get(CONF_PV):
            pv_config.update(data)

        power_insight.register_power_source(
            PowerSourceAdapter.from_pv_config("pv_system", pv_config)
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
