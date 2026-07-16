# Grid connection

The grid connection is the **import/export meter** of your home and the price
baseline for every cost and savings calculation. **Exactly one grid connection
is required** per energy mix — if you have two grid connections, model them as
two separate config entries.

Add it with **Add device → Grid connection**.

## Fields

### Power entity

> Sensor that reports this device's power in W, kW or MW.
>
> **Sign convention:** Grid — positive = import, negative = export. Use **Invert
> power direction** if your sensor uses the opposite sign.

This is the only always-required field. It must report instantaneous power (not
energy). Power Insight normalises W / kW / MW automatically.

### Invert power direction

> Turn on if your sensor reports power with the opposite sign to the convention
> described above.

Use this when your meter reports **import as negative** (or export as positive).

### Electricity price entity

> Sensor or input number with the current grid import price per kWh, in your Home
> Assistant currency. **Required when any cost or savings sensors are enabled.**

This can be a live/dynamic price sensor (for example from a dynamic-tariff
integration) or a static `input_number`. Because Power Insight uses the *current*
value at every calculation, dynamic tariffs are fully supported.

### CO₂ intensity entity

> Sensor reporting the current grid CO₂ intensity in g/kWh (for example from the
> [Electricity Maps](https://www.home-assistant.io/integrations/co2signal/)
> integration). Required when CO₂ sensors are enabled.

!!! note
    CO₂ sensors are **not implemented yet**, so this field currently has no
    effect. It is safe to leave empty.

## Sensors this device can create

Import and export both physically happen at the single grid connection, so the
grid device owns **both sides of the meter**.

| Sensor | Unit | Enabled by |
|---|---|---|
| Import power | W | *Power distribution (W)* |
| Export power | W | *Power distribution (W)* |
| Consumption ratio | % | *Power distribution ratios (%)* |
| Consumption share | % | *Power distribution shares (%)* |
| Import cost rate | currency/h | *Cost method = Standard* |
| Total import cost | currency | *Accumulate costs* |
| Export compensation rate | currency/h | *Export compensation rate* |
| Total export compensation | currency | *Accumulated export compensation* |

See the [Entity reference](../entities.md#grid-connection) for exactly what each
sensor means, and [Sensors, presets & options](options-and-presets.md) for how to
enable them.

!!! info "Grid electricity has no levelized cost"
    The levelized (LCOE/LCOS) concept applies only to devices you own, like solar
    panels and batteries — so the grid scope only offers the **Standard** cost
    method.
