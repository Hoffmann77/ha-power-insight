"""The enphase_envoy component."""

from homeassistant.const import Platform


DOMAIN = "heat_pump_signal"

PLATFORMS = [Platform.SENSOR]#, Platform.BINARY_SENSOR]


CONF_COSTS_OL = "costs_over_lifetime"
CONF_PROD_OL = "energy_over_lifetime"
CONF_CO2_FOOTPRINT = "co2_footprint"#

CONF_LCOE = "levelized_cost_of_electricity"
CONF_LCOE_CF = "levelized_cost_of_electricity_cf"
CONF_LCOS = "levelized_cost_of_storage"
CONF_LCOS_CF = "levelized_cost_of_storage_cf"
CONF_CO2_INTENSITY = "co2_intensity"
CONF_CO2_INTENSITY_CF = "co2_intensity_cf"

# CONFIG

CONF_ENABLE_PV = "enable_pv"
CONF_ENABLE_BAT = "enable_bat"

CONF_NUM_PV = "num_of_pv_systems"
CONF_NUM_BAT = "num_of_batteries"
CONF_NUM_LOADS = "num_of_loads"
CONF_NUM_SURPLUS_LOADS = "num_of_surplus_loads"

# GRID

CONF_GRID = "grid_config"
CONF_GRID_POWER = "grid_power_entity"
CONF_GRID_INVERTED = "grid_power_entity_inverted"
CONF_GRID_PRICE = "grid_electricity_price_entity"
# CONF_GRID_ELECTRICITY_RATE = "grid_import_price_entity"
# CONF_GRID_EXPORT_COMPENSATION = "grid_export_price_entity"
CONF_GRID_CO2_INTENSITY = "grid_co2_intensity_entity"

# PV-SYSTEM

CONF_PV = "pv_config"
CONF_PV_NAME = "pv_name"
CONF_PV_POWER = "pv_power_entity"
CONF_PV_PROD_OL = "pv_production_over_lifetime"
CONF_PV_COSTS_OL = "pv_costs_over_lifetime"
CONF_PV_CO2_FOOTPRINT = "pv_co2_footprint"
CONF_PV_LCOE = "pv_levelized_cost_of_electricity"
CONF_PV_LCOE_CF = "pv_levelized_cost_of_electricity_correction_factor"
CONF_PV_CO2_INTENSITY = "pv_levelized_co2_intensity"
CONF_PV_CO2_INTENSITY_CF = "pv_levelized_co2_intensity_correction_factor"

CONF_PV_ADDITIONAL_COSTS = "pv_additional_costs"
CONF_PV_ADDITIONAL_PRODUCTION = "pv_additional_production"
CONF_PV_ADDITIONAL_CO2_FOOTPRINT = "pv_additional_co2_footprint"

# Battery energy storage system

CONF_BAT = "bat_config"
CONF_BAT_NAME = "bat_name"
CONF_BAT_SOC = "bat_soc_entity"
CONF_BAT_POWER = "bat_power_entity"
CONF_BAT_INVERTED = "bat_power_entity_inverted"
CONF_BAT_EFFICIENCY = "bat_round_trip_efficiency"
CONF_BAT_DISCHARGE_OL = "bat_energy_discharged_over_lifetime"
CONF_BAT_ENERGY_DISCHARGED_OL = "bat_energy_discharged_over_lifetime"
CONF_BAT_COSTS_OL = "bat_costs_over_lifetime"
CONF_BAT_CO2_FOOTPRINT = "bat_co2_footprint"
CONF_BAT_CO2_INTENSITY = "bat_levelized_co2_intensity"
CONF_BAT_LCOS = "bat_levelized_cost_of_storage"
CONF_BAT_LCOS_CF = "bat_levelized_cost_of_storage_cf"

CONF_BAT_ADDITIONAL_COSTS = "bat_additional_costs"
CONF_BAT_ADDITIONAL_PRODUCTION = "bat_additional_discharge"
CONF_BAT_ADDITIONAL_CO2_FOOTPRINT = "bat_additional_co2_footprint"

# Electrical load

CONF_LOAD_TOGGLE = "load_toggle_entity"
CONF_LOAD_CONSUMPTION = "load_cons_entity"
CONF_LOAD_CONSUMPTION_INVERTED = "load_cons_entity_inverted"
CONF_LOAD_STATIC_THRESHOLD = "load_static_threshold"
CONF_LOAD_DELAY = "load_delay"

















# general

CONF_STATIC_THRESHOLD = "static_threshold"
CONF_DYNAMIC_THRESHOLD = "dynamic_threshold"
CONF_OPTIONAL_THRESHOLDS = "optional_thresholds"

# pv_signal step new


# shemas

CONF_BAT_SOC_THRD_1 = "battery_soc_threshold_1"
CONF_BAT_SOC_THRD_2 = "battery_soc_threshold_2"
CONF_BAT_MIN_PWR_1 = "battery_min_power_1"
CONF_BAT_MIN_PWR_2 = "battery_min_power_2"
CONF_BAT_MIN_PWR_3 = "battery_min_power_3"




# user step old

CONF_HYSTERESIS = "hysteresis"
CONF_LOCK_INTERVAL = "lock_interval"
CONF_REBOUND_INTERVAL = "rebound_interval"

