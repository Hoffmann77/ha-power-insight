# Getting started

Setting up Power Insight has three parts: create the hub, add your devices, and
choose which sensors to create. This page walks through all three.

!!! tip "Terminology"
    Power Insight is a **hub** integration. One config entry represents one
    **energy mix** (one home / one grid connection). Inside it you add one
    **device** per grid connection, PV system, battery, and consumer.

## 1. Create the hub

When you add the integration you are asked for two things:

### Name

> A short name for this energy-mix configuration, for example "Home" or
> "Office". Used as the device name in Home Assistant.

### Sensor preset

Pick a starting point for which sensors Power Insight creates. Each preset builds
on the previous one — you can always change this later in the integration's
**Options**.

| Preset | What it adds |
|---|---|
| **Minimal** | Distribution ratios (%), power-source attribution, and financial-return sensors. A lightweight overview of your energy mix. |
| **Recommended** | Adds distribution power (W), charging-source attribution, and running totals for export compensation, costs and savings. The sweet spot for most installations. |
| **Extended** | Also adds real-time cost, savings and export-compensation rate sensors (€/h or $/h) plus levelized cost sensors. Cost sensors need a live price entity on your grid adapter; levelized sensors need lifetime production and cost values per device. |

!!! note
    Not sure which to pick? **Recommended** is a great starting point for most
    homes: it covers the sensors people use most without adding complexity you
    may not need yet.

## 2. Add your devices

After the hub is created, open the integration and use the **Add device** button
to add each part of your energy mix. Four device types are available:

- **Grid connection** — your import/export meter. **Exactly one grid connection
  is required** per energy mix; costs, savings, and distribution are all measured
  against the grid.
- **PV system** — a solar inverter / array.
- **Battery** — a home battery / storage system.
- **Electrical consumer** — an appliance, EV charger, heat pump, etc.

!!! important "Add the grid first"
    Without a grid connection Power Insight cannot calculate anything, and it
    will raise a repair issue asking you to add one. Add your **grid connection**
    before (or right after) your other devices.

Each device asks for a **power entity** and a few type-specific fields. Which
fields are *required* depends on the sensors you enabled — for example, cost
sensors need a price entity and levelized sensors need lifetime values. See the
per-device pages:

- [Grid connection](configuration/grid.md)
- [PV system](configuration/pv.md)
- [Battery](configuration/battery.md)
- [Consumer](configuration/consumer.md)

!!! warning "Mind the sign convention"
    Power Insight expects: **Grid** — positive = import, negative = export;
    **PV / battery** — positive = producing/discharging, negative =
    consuming/charging. If your sensor uses the opposite sign, turn on **Invert
    power direction**. See [Sign conventions](concepts.md#sign-conventions).

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
zero. If you are adopting Power Insight partway through the year, you can carry
over the totals your system had already reached before you added the integration.

### Starting totals (recommended)

The easiest way is the **Starting totals** section built into the flows:

- **Whole-home totals** — open the integration's **Configure / Options**, choose
  **Custom**, and expand *Starting totals (carry over history)* on the **Combined
  sensors** page. Enter your historical *Total cost savings*, *Total financial
  return* and/or *Total operating cost*.
- **Per-device totals** — open a device and use **Reconfigure**; the same
  *Starting totals* section lets you seed that device's totals (import cost,
  export compensation, operating cost, cost savings, financial return).

Each value is added as a **fixed baseline on top of** whatever the sensor
accumulates from then on — it never disturbs the live accumulation. Leave a field
empty for no baseline; clearing a value later simply drops that baseline back to
zero.

!!! note
    Levelized totals (the *…levelized…* sensors) don't offer a starting-total
    field — their values are rescaled retroactively by each device's lifetime
    figures, so a fixed baseline wouldn't stay consistent.

### `set_value` service (scripting / one-offs)

The [`power_insight.set_value` service](services.md) is the scripting-friendly
alternative: it seeds a sensor's running accumulator directly. It **composes**
with the starting-total baseline above — the displayed total is always
`baseline + accumulator` — so use one or the other for a given figure, not both.
