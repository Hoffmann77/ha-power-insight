"""Config flow for Enphase gateway integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.const import CONF_NAME

from .const import (
    DOMAIN,

    CONF_COSTS_OL,
    CONF_PROD_OL,
    CONF_CO2_FOOTPRINT,

    CONF_LCOE,
    CONF_LCOE_CF,
    CONF_LCOS,
    CONF_LCOS_CF,
    CONF_CO2_INTENSITY,
    CONF_CO2_INTENSITY_CF,





    # FINAL
    CONF_ENABLE_PV,
    CONF_ENABLE_BAT,
    CONF_NUM_PV,
    CONF_NUM_BAT,
    CONF_NUM_LOADS,

    # Grid
    CONF_GRID,
    CONF_GRID_POWER,
    CONF_GRID_INVERTED,
    CONF_GRID_PRICE,
    CONF_GRID_IMPORT_PRICE,
    CONF_GRID_EXPORT_PRICE,
    CONF_GRID_CO2_INTENSITY,

    # PV
    CONF_PV,
    CONF_PV_POWER,

    # Battery
    CONF_BAT,
    CONF_BAT_SOC,
    CONF_BAT_POWER,
    CONF_BAT_INVERTED,
    CONF_BAT_EFFICIENCY,



    CONF_LOAD_TOGGLE,
    CONF_LOAD_CONSUMPTION,
    CONF_LOAD_CONSUMPTION_INVERTED,
    CONF_LOAD_STATIC_THRESHOLD,
    CONF_LOAD_DELAY,
)

# from .signals import SIGNALS


_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Heat pump coordinator."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.title = None
        self.config = None
        self.data = {}
        self.options = {}

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the user step.

        Allows the user to specify a name and enable the desired signals.

        """
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        if user_input is not None:
            data = user_input
            title = data.pop(CONF_NAME)

            if data[CONF_ENABLE_BAT] and not data[CONF_ENABLE_PV]:
                errors["base"] = "bat_enabled_without_pv"

            if not title.lstrip(" "):
                errors["base"] = "name_invalid"

            if not errors:
                self.title = title
                self.config = data
                return await self.async_step_grid()

        user_input = user_input or {}

        return self.async_show_form(
            step_id="user",
            data_schema=self.get_shema_user_step(user_input),
            description_placeholders=placeholders,
            errors=errors,
        )

    async def async_step_grid(self, user_input=None) -> FlowResult:
        """Handle the user step.

        Allows the user to configure his grid.

        """
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        if user_input is not None:
            data = user_input

            if not errors:
                self.options[CONF_GRID] = data
                return await self.async_step_pv_system()

        user_input = user_input or {}

        return self.async_show_form(
            step_id="grid",
            data_schema=self.get_shema_grid_step(user_input),
            description_placeholders=placeholders,
            errors=errors,
        )

    async def async_step_pv_system(self, user_input=None) -> FlowResult:
        """Handle the user step.

        Allows the user to configure his pv-system.

        """
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        # skip step if the pv system is not enabled.
        if not self.config[CONF_ENABLE_PV]:
            self.options[CONF_PV] = None
            return await self.async_step_battery()

        if user_input is not None:
            options = user_input

            prod = options[CONF_PROD_OL]
            lcoe = options[CONF_COSTS_OL] / prod
            co2_intensity = (options[CONF_CO2_FOOTPRINT] / prod) * 1000

            options.update(
                {
                    CONF_LCOE_CF: 1.0,
                    CONF_CO2_INTENSITY_CF: 1.0
                }
            )

            data = {
                CONF_LCOE: lcoe,
                CONF_CO2_INTENSITY: co2_intensity,
            }

            if not errors:
                self.data[CONF_PV] = data
                self.options[CONF_PV] = options
                return await self.async_step_battery()

        user_input = user_input or {}

        return self.async_show_form(
            step_id="pv_system",
            data_schema=self.get_shema_pv_system_step(user_input),
            description_placeholders=placeholders,
            errors=errors,
        )

    async def async_step_battery(self, user_input=None) -> FlowResult:
        """Handle the user step.

        Allows the user to configure his battery.

        """
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        # skip step if the battery is not enabled.
        if not self.config[CONF_ENABLE_BAT]:
            self.options[CONF_BAT] = None
            return await self.async_step_finish()

        if user_input is not None:
            options = user_input

            prod = options[CONF_PROD_OL]
            pv_lcoe = self.data[CONF_PV][CONF_LCOE]
            price = pv_lcoe * (1 / (options.get(CONF_BAT_EFFICIENCY) / 100))
            lcos = (options[CONF_COSTS_OL] / prod) + price
            co2_intensity = (options[CONF_CO2_FOOTPRINT] / prod) * 100

            options.update(
                {
                    CONF_LCOS_CF: 1.0,
                    CONF_CO2_INTENSITY_CF: 1.0
                }
            )

            data = {
                CONF_LCOS: lcos,
                CONF_CO2_INTENSITY: co2_intensity,
            }

            if not errors:
                self.data[CONF_BAT] = data
                self.options[CONF_BAT] = options
                return await self.async_step_finish()

        user_input = user_input or {}

        return self.async_show_form(
            step_id="battery",
            data_schema=self.get_shema_battery_step(user_input),
            description_placeholders=placeholders,
            errors=errors,
        )

    async def async_step_finish(self) -> FlowResult:
        """Create the config entry."""
        return self.async_create_entry(
            title=self.title,
            data=self.data,
            options=self.options,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)

    @callback
    def get_shema_user_step(self, defaults: dict) -> vol.Schema:
        """Return the schema for the user step."""
        schema = {
            vol.Required(
                CONF_NAME, default=defaults.get(CONF_NAME, "")
            ): str,
            vol.Required(CONF_ENABLE_PV): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),
            vol.Required(CONF_ENABLE_BAT): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),
            vol.Optional(CONF_NUM_LOADS, default=0): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=10, mode="box"),
            ),
        }
        return vol.Schema(schema)

    @callback
    def get_shema_grid_step(self, defaults: dict) -> vol.Schema:
        """Return the shema for the grid config step."""
        schema = {
            vol.Optional(CONF_GRID_POWER): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(CONF_GRID_INVERTED): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),
            vol.Required(CONF_GRID_IMPORT_PRICE): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(CONF_GRID_EXPORT_PRICE): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(CONF_GRID_CO2_INTENSITY): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
        }
        return vol.Schema(schema)

    @callback
    def get_shema_pv_system_step(self, defaults: dict) -> vol.Schema:
        """Return the shema for the pv-system config step."""
        schema = {
            vol.Required(CONF_PV_POWER): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(CONF_PROD_OL): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=10**8,
                    unit_of_measurement="kW/h",
                    mode="box",
                ),
            ),
            vol.Required(CONF_COSTS_OL): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=10**8,
                    unit_of_measurement="Euro",
                    mode="box",
                ),
            ),
            vol.Required(CONF_CO2_FOOTPRINT): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=10**8,
                    unit_of_measurement="Kg",
                    mode="box",
                ),
            ),
        }
        return vol.Schema(schema)

    @callback
    def get_shema_battery_step(self, defaults: dict) -> vol.Schema:
        """Return the shema for the battery config step."""
        schema = {
            vol.Required(CONF_BAT_SOC): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(CONF_BAT_POWER): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Optional(CONF_BAT_INVERTED): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),
            vol.Optional(
                CONF_BAT_EFFICIENCY,
                default=95,
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=100, unit_of_measurement="%", mode="slider",
                ),
            ),
            vol.Optional(
                CONF_PROD_OL
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=10**8,
                    unit_of_measurement="kW/h",
                    mode="box",
                ),
            ),
            vol.Optional(
                CONF_COSTS_OL
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=10**8,
                    unit_of_measurement="Euro",
                    mode="box",
                ),
            ),
            vol.Optional(CONF_CO2_FOOTPRINT): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=10**8,
                    unit_of_measurement="Kg",
                    mode="box",
                ),
            ),
        }
        return vol.Schema(schema)

    @callback
    def get_shema_load_step(self, defaults: dict = {}) -> vol.Schema:
        """Return the shema for the load config step."""
        schema = {
            vol.Optional(CONF_LOAD_CONSUMPTION): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Optional(
                CONF_LOAD_CONSUMPTION_INVERTED
            ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
            vol.Required(
                CONF_LOAD_STATIC_THRESHOLD,
                default=defaults.get("CONF_STATIC_THRESHOLD"),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=2**32,
                    unit_of_measurement="Watt",
                    mode="box",
                ),
            ),
            vol.Required(
                CONF_LOAD_DELAY,
                default=defaults.get(
                    CONF_LOAD_DELAY,
                    {"hours": 0, "minutes": 0, "seconds": 0},
                ),
            ): selector.DurationSelector(
                selector.DurationSelectorConfig(enable_day=False)
            ),
        }
        return vol.Schema(schema)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle the options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self.config_entry = config_entry
        self.config = {}
        self.options = {}

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Handle the user step.

        Allows the user to specify a name and enable the desired signals.

        """
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        if user_input is not None:
            data = user_input
            title = data.pop(CONF_NAME)

            if data[CONF_ENABLE_BAT] and not data[CONF_ENABLE_PV]:
                errors["base"] = "bat_enabled_without_pv"

            if not errors:
                self.title = title
                self.config = data
                return await self.async_step_grid()

        user_input = user_input or {}

        return self.async_show_form(
            step_id="user",
            data_schema=self.get_shema_user_step(user_input),
            description_placeholders=placeholders,
            errors=errors,
        )

    async def async_step_grid(self, user_input=None) -> FlowResult:
        """Handle the user step.

        Allows the user to configure his grid.

        """
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        if user_input is not None:
            data = user_input

            if not errors:
                self.options[CONF_GRID] = data
                return await self.async_step_pv_system()

        user_input = user_input or self.config_entry.options[CONF_GRID]

        return self.async_show_form(
            step_id="grid",
            data_schema=self.get_shema_grid_step(user_input),
            description_placeholders=placeholders,
            errors=errors,
        )

    async def async_step_pv_system(self, user_input=None) -> FlowResult:
        """Handle the user step.

        Allows the user to configure his pv-system.

        """
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        # skip step if the pv system is not enabled.
        if not self.config[CONF_ENABLE_PV]:
            self.options[CONF_PV] = None
            return await self.async_step_finish()

        if user_input is not None:
            options = user_input
            data = self.config_entry.data[CONF_PV]

            prod = options[CONF_PROD_OL]
            lcoe = options[CONF_COSTS_OL] / prod
            co2_intensity = (options[CONF_CO2_FOOTPRINT] / prod) * 1000

            options.update(
                {
                    CONF_LCOE_CF: lcoe / data[CONF_LCOE],
                    CONF_CO2_INTENSITY_CF: (
                        co2_intensity / data[CONF_CO2_INTENSITY]
                    )
                }
            )

            if not errors:
                self.options[CONF_PV] = options
                return await self.async_step_finish()

        user_input = user_input or self.config_entry.options[CONF_PV]

        return self.async_show_form(
            step_id="pv_system",
            data_schema=self.get_shema_pv_system_step(user_input),
            description_placeholders=placeholders,
            errors=errors,
        )

    async def async_step_battery(self, user_input=None) -> FlowResult:
        """Handle the user step.

        Allows the user to configure his battery.

        """
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        # skip step if the battery is not enabled.
        if not self.config[CONF_ENABLE_BAT]:
            self.options[CONF_BAT] = None
            return await self.async_step_finish()

        if user_input is not None:
            options = user_input
            data = self.config_entry.data[CONF_PV]

            prod = options[CONF_PROD_OL]
            pv_lcoe = data[CONF_LCOE]
            price = pv_lcoe * (1 / (options.get(CONF_BAT_EFFICIENCY) / 100))
            lcos = (options[CONF_COSTS_OL] / prod) + price
            co2_intensity = (options[CONF_CO2_FOOTPRINT] / prod) * 100

            options.update(
                {
                    CONF_LCOE_CF: lcos / data[CONF_LCOS],
                    CONF_CO2_INTENSITY_CF: (
                        co2_intensity / data[CONF_CO2_INTENSITY]
                    )
                }
            )

            if not errors:
                self.options[CONF_BAT] = options
                return await self.async_step_finish()

        user_input = user_input or self.config_entry.options[CONF_BAT]

        return self.async_show_form(
            step_id="battery",
            data_schema=self.get_shema_battery_step(user_input),
            description_placeholders=placeholders,
            errors=errors,
        )

    async def async_step_finish(self) -> FlowResult:
        """Create the config entry."""
        return self.async_create_entry(
            title=self.title,
            data=self.options,
        )

    @callback
    def get_shema_grid_step(self, defaults: dict) -> vol.Schema:
        """Return the shema for the grid config step."""
        schema = {
            vol.Optional(
                CONF_GRID_POWER,
                default=defaults[CONF_GRID_POWER],
            ): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(
                CONF_GRID_INVERTED,
                default=defaults[CONF_GRID_INVERTED],
            ): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),
            vol.Required(
                CONF_GRID_PRICE,
                default=defaults[CONF_GRID_PRICE],
            ): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(
                CONF_GRID_CO2_INTENSITY,
                default=defaults[CONF_GRID_CO2_INTENSITY],
            ): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
        }
        return vol.Schema(schema)

    @callback
    def get_shema_pv_system_step(self, defaults: dict) -> vol.Schema:
        """Return the shema for the pv-system config step."""
        schema = {
            vol.Required(
                CONF_PV_POWER,
                default=defaults[CONF_PV_POWER],
            ): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(
                CONF_PROD_OL,
                default=defaults[CONF_PROD_OL],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=10**8,
                    unit_of_measurement="kW/h",
                    mode="box",
                ),
            ),
            vol.Required(
                CONF_COSTS_OL,
                default=defaults[CONF_COSTS_OL],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=10**8,
                    unit_of_measurement="Euro",
                    mode="box",
                ),
            ),
            vol.Required(
                CONF_CO2_FOOTPRINT,
                default=defaults[CONF_CO2_FOOTPRINT],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=10**8,
                    unit_of_measurement="Kg",
                    mode="box",
                ),
            ),
        }
        return vol.Schema(schema)

    @callback
    def get_shema_battery_step(self, defaults: dict) -> vol.Schema:
        """Return the shema for the battery config step."""
        schema = {
            vol.Required(
                CONF_BAT_SOC,
                default=defaults[CONF_BAT_SOC],
            ): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(
                CONF_BAT_POWER,
                default=defaults[CONF_BAT_POWER],
            ): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Optional(
                CONF_BAT_INVERTED,
                default=defaults[CONF_BAT_INVERTED],
            ): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),
            vol.Optional(
                CONF_BAT_EFFICIENCY,
                default=defaults[CONF_BAT_EFFICIENCY],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=100, unit_of_measurement="%", mode="slider",
                ),
            ),
            vol.Optional(
                CONF_PROD_OL,
                default=defaults[CONF_PROD_OL],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=10**8,
                    unit_of_measurement="kW/h",
                    mode="box",
                ),
            ),
            vol.Optional(
                CONF_COSTS_OL,
                default=defaults[CONF_COSTS_OL],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=10**8,
                    unit_of_measurement="Euro",
                    mode="box",
                ),
            ),
            vol.Optional(
                CONF_CO2_FOOTPRINT,
                default=defaults[CONF_CO2_FOOTPRINT],
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=10**8,
                    unit_of_measurement="Kg",
                    mode="box",
                ),
            ),
        }
        return vol.Schema(schema)
