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
    # Create instance
    power_insight = PowerInsight(
        GridAdapter.from_config(
            key="grid", verbose_name="Grid", config=entry.options[CONF_GRID]
        )
    )

    # Add pv-system adapter
    if pv_config := entry.options.get(CONF_PV):
        if data := entry.data.get(CONF_PV):
            pv_config.update(data)

        power_insight.register_adapter(
            PvAdapter.from_config(
                key="pv_system", verbose_name="PV-System", config=pv_config
            )
        )

    # New
    # for key, config in entry.options[CONF_PV].items():
    #     if data := entry.data[CONF_PV].get(key):
    #         config.update(data)

    #     verbose_name = config[CONF_NAME]

    #     power_insight.register_adapter(
    #         PvAdapter.from_config(
    #             key=key, verbose_name=config[CONF_NAME], config=config
    #         )
    #     )




    # Add battery adapter
    if bat_config := entry.options.get(CONF_BAT):
        if data := entry.data.get(CONF_BAT):
            bat_config.update(data)

        power_insight.register_adapter(
            BatteryAdapter.from_config("battery", "Battery", bat_config)
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
