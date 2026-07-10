# Configuration overview

Power Insight configuration has two layers:

1. **Devices** — one per grid connection, PV system, battery, and consumer. Each
   device supplies the raw inputs (power entity, price entity, lifetime values,
   …). Configured with the **Add device** button and each device's **Reconfigure**
   page.
2. **Sensor selection** — which sensors get created for the whole home and for
   each device type. Configured in the integration's **Options**, either by
   preset or per scope.

## Devices

| Device | Purpose | Reference |
|---|---|---|
| **Grid connection** | Your import/export meter and the price baseline for all cost/savings math. Exactly one per energy mix. | [Grid connection](grid.md) |
| **PV system** | A solar array/inverter — production, self-consumption, export. | [PV system](pv.md) |
| **Battery** | A home battery — charge/discharge, charging-source tracing, LCOS. | [Battery](battery.md) |
| **Consumer** | An appliance/EV/heat pump — operating cost and source mix. | [Consumer](consumer.md) |

### How device data is stored

Each device is a Home Assistant **config subentry** of the main hub entry. Its
configuration is split into:

- `adapter.config` — the device's own settings (power entity, price entity,
  export compensation, efficiency, charge sources, and the derived LCOE/LCOS).
- top-level `data` — the raw **lifetime** inputs (`lifetime_production`,
  `lifetime_cost`, `co2_footprint`) used to derive levelized costs.

You do not edit these directly — the config flow does it for you — but it
explains why some fields (lifetime values) behave differently from the rest.

### Required vs. optional fields

A field's *required-ness is dynamic*: it depends on which sensors you have
enabled. For example the grid **electricity price entity** is only required once
you enable any cost or savings sensor, and the **lifetime** values are only
required once you enable any levelized sensor.

If you enable an option that a device is missing data for, the options flow tells
you which devices need attention:

> These devices are missing data required by your selection: … Open each
> device's **Reconfigure** page to supply the missing values (for example, an
> electricity price entity for cost sensors, or lifetime production and cost for
> levelized sensors), then save the options again.

## Sensor selection

See **[Sensors, presets & options](options-and-presets.md)** for presets, the
per-scope Custom flow, and the full mapping of options to sensors.
