# Getting started

Setting up Power Insight has three parts: create the hub, add your devices, and
choose which sensors to create. This page walks through all three.

:::tip[Terminology]

Power Insight is a **hub** integration. One config entry represents one
**energy mix** (one home / one grid connection). Inside it you add one
**device** per grid connection, PV system, battery, and consumer.

:::

## 1. Create the hub

When you add the integration you are asked for two things:

### Name

> For example "Home". Used as the prefix of every device and sensor name.

### Sensor set

Pick a starting set of sensors. Each set builds on the previous one — you can
change it at any time in the integration's **Options**.

| Sensor set | What it adds |
|---|---|
| **Minimal** | Power split (%), where each consumer's power comes from, and financial return. |
| **Recommended** | Adds the power split in W, battery charging sources, and running totals for costs, savings and export compensation. |
| **Extended** | Adds live cost, savings and export compensation rates (per hour) and each device's share of the home totals. |

Cost, savings and financial return sensors need an electricity price sensor on
your grid connection; levelized ones also need lifetime values per device.

:::note

Not sure which to pick? **Recommended** is a great starting point for most
homes: it covers the sensors people use most without adding complexity you
may not need yet.

:::

## 2. Add your devices

After the hub is created, open the integration and use the **Add device** button
to add each part of your energy mix. Four device types are available:

- **Grid connection** — your import/export meter. **Exactly one grid connection
  is required** per energy mix; costs, savings, and distribution are all measured
  against the grid.
- **PV system** — a solar inverter / array.
- **Battery** — a home battery / storage system.
- **Consumer** — an appliance, EV charger, heat pump, etc.

:::warning[Add the grid first]

Without a grid connection Power Insight cannot calculate anything, and it
will raise a repair issue asking you to add one. Add your **grid connection**
before (or right after) your other devices.

:::

Each device asks for a **power entity** and a few type-specific fields. Which
fields are *required* depends on the sensors you enabled — for example, cost
sensors need a price entity and levelized sensors need lifetime values. See the
per-device pages:

- [Grid connection](configuration/grid.md)
- [PV system](configuration/pv.md)
- [Battery](configuration/battery.md)
- [Consumer](configuration/consumer.md)

:::warning[Mind the sign convention]

Power Insight expects: **Grid** — positive = import, negative = export;
**PV / battery** — positive = producing/discharging, negative =
consuming/charging. If your sensor uses the opposite sign, turn on **Invert
power direction**. See [Sign conventions](concepts.md#sign-conventions).

:::

## 3. Fine-tune the sensors (options)

Open the integration's **Configure / Options** at any time to change which
sensors exist. You can:

- Apply a **preset** to every device at once, or
- Choose **Custom** to configure each device type individually (combined, grid,
  PV, battery, consumers).

Turning a sensor off **disables** it in Home Assistant but does not delete it, so
its history is preserved and it comes back the moment you re-enable the option.

See **[Sensors, presets & options](configuration/options-and-presets.md)** for
the full reference, and the **[Entity reference](entities.md)** for every sensor
Power Insight can create.

## 4. (Optional) Seed accumulated totals

Accumulated **total** sensors (e.g. *Total cost savings*) start counting from
zero. If you are adopting Power Insight partway through the year and want to
carry over a historical total, use the
[`power_insight.set_value` service](services.md).
