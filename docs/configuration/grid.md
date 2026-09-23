# Grid connection

The grid connection is the **import/export meter** of your home and the price
baseline for every cost and savings calculation. **Exactly one grid connection
is required** per energy mix — if you have two grid connections, model them as
two separate config entries.

Add it with **Add device → Grid connection**.

## Fields

### Power sensor

> Sensor with the grid power in W, kW or MW. Positive = import, negative =
> export.

This is the only always-required field. It must report instantaneous power (not
energy). Power Insight normalises W / kW / MW automatically.

### Invert power sign

> Turn on if your sensor uses the opposite sign.

Use this when your meter reports **import as negative** (or export as positive).

### Electricity price

> Sensor or number with the current price per kWh you pay for grid power. Required for cost, savings and financial return sensors.

This can be a live/dynamic price sensor (for example from a dynamic-tariff
integration) or a static `input_number`. Because Power Insight uses the *current*
value at every calculation, dynamic tariffs are fully supported.

### Grid CO₂ intensity

> Sensor with the grid's current CO₂ intensity in g/kWh (e.g. from
> [Electricity Maps](https://www.home-assistant.io/integrations/co2signal/)).
> Optional; reserved for CO₂ sensors.

:::note

CO₂ sensors are **not implemented yet**, so this field currently has no
effect. It is safe to leave empty.

:::

## Sensors this device can create

Import and export both physically happen at the single grid connection, so the
grid device owns **both sides of the meter**.

| Sensor | Unit | Enabled by |
|---|---|---|
| Import power | W | *Power split (W)* |
| Export power | W | *Power split (W)* |
| Import to home consumption / batteries / system standby | W | *Power split (W)* |
| Import to home consumption / batteries / system standby ratio | % | *Power split (%)* |
| Share of home consumption / battery charging / system standby | % | *Share of home totals (%)* |
| Import cost rate | currency/h | *Cost method = Standard* |
| Total import cost | currency | *Accumulate costs* |
| Export compensation rate | currency/h | *Export compensation rate* |
| Total export compensation | currency | *Total export compensation* |

See the [Entity reference](../entities.md#grid-connection) for exactly what each
sensor means, and [Sensors, presets & options](options-and-presets.md) for how to
enable them.

:::info[Grid electricity has no levelized cost]

The levelized (LCOE/LCOS) concept applies only to devices you own, like solar
panels and batteries — so the grid scope only offers the **Standard** cost
method.

:::