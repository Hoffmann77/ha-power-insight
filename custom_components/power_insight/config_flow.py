"""Config flow for Enphase gateway integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.const import CONF_NAME
from homeassistant.util import slugify

from .const import (
    DOMAIN,

    CONF_KEY,

    CONF_COSTS_OL,
    CONF_PROD_OL,
    CONF_CO2_FOOTPRINT,

    CONF_LCOE,
    CONF_LCOE_CF,
    CONF_LCOS,
    CONF_LCOS_CF,
    CONF_CO2_INTENSITY,
    CONF_CO2_INTENSITY_CF,

    CONF_CO2_INTENSITY_ENTITY,


    CONF_EXPORTS_POWER,
    CONF_EXPORT_COMPENSATION,

    CONF_ADD_PV,
    CONF_ADD_BAT,


    CONF_POWER_ENTITY,  # used
    CONF_POWER_INVERTED,  # used

    # Grid
    CONF_GRID,
    CONF_ELECTRICITY_PRICE,

    # PV
    CONF_PV,

    # Battery
    CONF_BAT,
    CONF_BAT_EFFICIENCY,

)

# from .signals import SIGNALS


_LOGGER = logging.getLogger(__name__)


class MyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Heat pump coordinator."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.title = None
        self.config = None
        self.data = {CONF_PV: {}, CONF_BAT: {}}
        self.options = {CONF_PV: {}, CONF_BAT: {}}

        self._used_slugs = ["grid"]

        self._add_pv = False
        self._add_bat = False
        self._add_num_consumers = 0

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the user step.

        Allows the user to specify a name and enable the desired signals.

        """
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        if user_input is not None:
            data = user_input

            # Ensure that the provided name is not an empty string
            title = data[CONF_NAME]
            if not title.strip():
                errors["base"] = "invalid_name"

            self._add_pv = data[CONF_ADD_PV]
            self._add_bat = data[CONF_ADD_BAT]

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
        """Handle the grid step.

        Allows the user to configure the grid adapter.

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

        if not self._add_pv:
            return await self.async_step_battery()

        if user_input is not None:
            data = user_input.copy()

            add_another = data.pop("add_another")

            # Ensure that the adapter name is valid and unique.
            name = data.pop(CONF_NAME).strip()
            slug = slugify(name)
            if not name or slug == "unknown":
                errors["base"] = "invalid_name"
            elif slug in self._used_slugs:
                errors["base"] = "name_not_unique"

            # Calculate lcoe and co2 intensity.
            lcoe = data[CONF_COSTS_OL] / data[CONF_PROD_OL]
            co2_intensity = (
                (data[CONF_CO2_FOOTPRINT] / data[CONF_PROD_OL]) * 1000
            )

            data_dict = {
                CONF_KEY: slug,
                CONF_NAME: name,
                CONF_LCOE: lcoe,
                CONF_LCOE_CF: 1.0,
                CONF_CO2_INTENSITY: co2_intensity,
                CONF_CO2_INTENSITY_CF: 1.0
            }

            options_dict = {**data}

            if not errors:
                self.data[CONF_PV].update({slug: data_dict})
                self.options[CONF_PV].update({slug: options_dict})
                self._used_slugs.append(slug)

                if add_another:
                    return await self.async_step_pv_system()

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

        if not self._add_bat:
            return await self.async_step_finish()

        if user_input is not None:
            data = user_input.copy()

            add_another = data.pop("add_another")

            # Ensure that the adapter name is valid and unique.
            name = data.pop(CONF_NAME).strip()
            slug = slugify(name)
            if not name or slug == "unknown":
                errors["base"] = "invalid_name"
            elif slug in self._used_slugs:
                errors["base"] = "name_not_unique"

            # Calculate lcoe and co2 intensity.
            lcos = data[CONF_COSTS_OL] / data[CONF_PROD_OL]
            co2_intensity = (
                (data[CONF_CO2_FOOTPRINT] / data[CONF_PROD_OL]) * 1000
            )

            data_dict = {
                CONF_KEY: slug,
                CONF_NAME: name,
                CONF_LCOS: lcos,
                CONF_LCOS_CF: 1.0,
                CONF_CO2_INTENSITY: co2_intensity,
                CONF_CO2_INTENSITY_CF: 1.0
            }

            options_dict = {
                **data,
            }

            if not errors:
                self.data[CONF_BAT].update({slug: data_dict})
                self.options[CONF_BAT].update({slug: options_dict})
                self._used_slugs.append(slug)

                if add_another:
                    return await self.async_step_battery()

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

    # @staticmethod
    # @callback
    # def async_get_options_flow(
    #     config_entry: config_entries.ConfigEntry,
    # ) -> config_entries.OptionsFlow:
    #     """Create the options flow."""
    #     return OptionsFlowHandler(config_entry)

    @callback
    def get_shema_user_step(self, defaults: dict) -> vol.Schema:
        """Return the schema for the user step."""
        schema = {
            vol.Required(
                CONF_NAME, default=defaults.get(CONF_NAME, "")
            ): str,
            vol.Required(
                CONF_ADD_PV, default=False
            ): selector.BooleanSelector(
                selector.BooleanSelectorConfig(),
            ),
            vol.Required(
                CONF_ADD_BAT, default=False
            ): selector.BooleanSelector(
                selector.BooleanSelectorConfig(),
            ),
            # vol.Optional(
            #     CONF_NUM_CONSUMERS, default=0
            # ): selector.NumberSelector(
            #     selector.NumberSelectorConfig(min=0, max=10, mode="box"),
            # ),
        }
        return vol.Schema(schema)

    @callback
    def get_shema_grid_step(self, defaults: dict) -> vol.Schema:
        """Return the shema for the grid config step."""
        schema = {
            vol.Optional(CONF_POWER_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(CONF_POWER_INVERTED): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),
            vol.Required(CONF_ELECTRICITY_PRICE): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(CONF_CO2_INTENSITY_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
        }
        return vol.Schema(schema)

    @callback
    def get_shema_pv_system_step(self, defaults: dict) -> vol.Schema:
        """Return the shema for the pv-system config step."""
        schema = {
            vol.Required(
                CONF_NAME, default=defaults.get(CONF_NAME, "Pv-system")
            ): str,
            vol.Required(CONF_POWER_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(CONF_POWER_INVERTED): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),
            vol.Required(
                CONF_PROD_OL, default=defaults.get(CONF_PROD_OL, 0)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=10**8,
                    unit_of_measurement="kW/h",
                    mode="box",
                ),
            ),
            vol.Required(
                CONF_COSTS_OL, default=defaults.get(CONF_COSTS_OL, 0)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1.0,
                    max=10.0**8,
                    unit_of_measurement="Euro",
                    mode="box",
                ),
            ),
            vol.Required(
                CONF_CO2_FOOTPRINT, default=defaults.get(CONF_CO2_FOOTPRINT, 0)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1.0,
                    max=10.0**8,
                    unit_of_measurement="Kg",
                    mode="box",
                ),
            ),
            vol.Required(CONF_EXPORTS_POWER): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),
            vol.Required(CONF_EXPORT_COMPENSATION): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=10.0**8,
                    unit_of_measurement="Euro",
                    mode="box",
                ),
            ),
            vol.Optional("add_another", default=False): bool,
        }
        return vol.Schema(schema)

    @callback
    def get_shema_battery_step(self, defaults: dict) -> vol.Schema:
        """Return the shema for the battery config step."""
        schema = {
            vol.Required(
                CONF_NAME, default=defaults.get(CONF_NAME, "Battery")
            ): str,
            vol.Optional(CONF_POWER_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(CONF_POWER_INVERTED): selector.BooleanSelector(
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
            vol.Required(CONF_EXPORTS_POWER): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),
            vol.Required(CONF_EXPORT_COMPENSATION): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=10**8,
                    unit_of_measurement="Kg",
                    mode="box",
                ),
            ),
            vol.Optional("add_another", default=False): bool,
        }
        return vol.Schema(schema)

    # @callback
    # def get_shema_load_step(self, defaults: dict = {}) -> vol.Schema:
    #     """Return the shema for the load config step."""
    #     schema = {
    #         vol.Optional(CONF_LOAD_CONSUMPTION): selector.EntitySelector(
    #             selector.EntitySelectorConfig()
    #         ),
    #         vol.Optional(
    #             CONF_LOAD_CONSUMPTION_INVERTED
    #         ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
    #         vol.Required(
    #             CONF_LOAD_STATIC_THRESHOLD,
    #             default=defaults.get("CONF_STATIC_THRESHOLD"),
    #         ): selector.NumberSelector(
    #             selector.NumberSelectorConfig(
    #                 min=0,
    #                 max=2**32,
    #                 unit_of_measurement="Watt",
    #                 mode="box",
    #             ),
    #         ),
    #         vol.Required(
    #             CONF_LOAD_DELAY,
    #             default=defaults.get(
    #                 CONF_LOAD_DELAY,
    #                 {"hours": 0, "minutes": 0, "seconds": 0},
    #             ),
    #         ): selector.DurationSelector(
    #             selector.DurationSelectorConfig(enable_day=False)
    #         ),
    #     }
    #     return vol.Schema(schema)


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
                CONF_POWER_ENTITY, default=defaults[CONF_POWER_ENTITY]
            ): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(
                CONF_POWER_INVERTED, default=defaults[CONF_POWER_INVERTED]
            ): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),
            vol.Required(
                CONF_GRID_PRICE, default=defaults[CONF_GRID_PRICE]
            ): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(
                CONF_CO2_INTENSITY, default=defaults[CONF_CO2_INTENSITY]
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
                CONF_POWER_ENTITY, default=defaults[CONF_POWER_ENTITY]
            ): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Required(
                CONF_POWER_INVERTED, default=defaults[CONF_POWER_INVERTED]
            ): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),

            # TODO: the following configuration options require the use
            # of correction factors to work.
            # vol.Required(
            #     CONF_PROD_OL, default=defaults.get(CONF_PROD_OL, 0)
            # ): selector.NumberSelector(
            #     selector.NumberSelectorConfig(
            #         min=1,
            #         max=10**8,
            #         unit_of_measurement="kW/h",
            #         mode="box",
            #     ),
            # ),
            # vol.Required(
            #     CONF_COSTS_OL, default=defaults.get(CONF_COSTS_OL, 0)
            # ): selector.NumberSelector(
            #     selector.NumberSelectorConfig(
            #         min=1,
            #         max=10**8,
            #         unit_of_measurement="Euro",
            #         mode="box",
            #     ),
            # ),
            # vol.Required(
            #     CONF_CO2_FOOTPRINT, default=defaults.get(CONF_CO2_FOOTPRINT, 0)
            # ): selector.NumberSelector(
            #     selector.NumberSelectorConfig(
            #         min=1,
            #         max=10**8,
            #         unit_of_measurement="Kg",
            #         mode="box",
            #     ),
            # ),
            vol.Required(
                CONF_EXPORTS_POWER, default=defaults[CONF_EXPORTS_POWER]
            ): selector.BooleanSelector(
                selector.BooleanSelectorConfig()
            ),
            vol.Required(
                CONF_EXPORT_COMPENSATION,
                default=defaults[CONF_EXPORT_COMPENSATION],
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
