"""Constants."""

from homeassistant.const import Platform


PLATFORMS = [Platform.SENSOR]

DOMAIN = "power_insight"

CONF_KEY = "key"

CONF_PV = "pv_systems"
CONF_BAT = "batteries"
CONF_GRID = "grid"

CONF_COSTS_OL = "costs_over_lifetime"
CONF_PROD_OL = "energy_over_lifetime"
CONF_CO2_FOOTPRINT = "co2_footprint"

CONF_LCOE = "levelized_cost_of_electricity"
CONF_LCOE_CF = "levelized_cost_of_electricity_cf"
CONF_LCOS = "levelized_cost_of_storage"
CONF_LCOS_CF = "levelized_cost_of_storage_cf"
CONF_CO2_INTENSITY = "co2_intensity"
CONF_CO2_INTENSITY_CF = "co2_intensity_cf"

CONF_CO2_INTENSITY_ENTITY = "co2_intensity_entity"
CONF_POWER_ENTITY = "power_entity"
CONF_POWER_INVERTED = "power_entity_inverted"

CONF_ADD_PV = "enable_pv"
CONF_ADD_BAT = "enable_bat"

CONF_ELECTRICITY_PRICE = "grid_electricity_price_entity"

CONF_EXPORTS_POWER = "exports_power"
CONF_EXPORT_COMPENSATION = "export_compensation"  # used

CONF_BAT_EFFICIENCY = "bat_round_trip_efficiency"
