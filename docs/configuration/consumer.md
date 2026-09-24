# Consumer

A consumer represents an electrical load — an appliance, EV charger, heat pump,
etc. Power Insight tracks how much power it draws and where that power comes from.

Add it with **Add device → Consumer**.

:::warning[Under development]

Consumer support is still being built out. Today a consumer produces
operating-cost sensors and (with the option enabled) power-source-share
sensors. More consumer sensors are planned.

:::

## Fields

### Name

> For example "Rooftop" or "Heat pump". Used in the device and sensor names.

### Power sensor

> Sensor that reports this device's power in W, kW or MW. Negative = power drawn
> by the consumer. Most smart plugs report their draw as a positive value — turn
> on **Invert power sign** for those.

### Invert power sign

> Turn on if your sensor uses the opposite sign.

### Power sources / Powered by

> **Whole mix** — the power comes from all sources in proportion to what they supply.
>
> **Specific devices** — only from the sources you select below, e.g. a battery that charges from solar only.

> The sources that power this consumer. Only used with **Specific devices**.

Default: **Whole mix**. Choose **Specific devices** for a load your energy
manager runs on particular sources — for example a smart plug that only switches
on with excess solar. The grid and your PV systems are selectable.

The selection describes what you expect your energy manager to do, not a hard
limit. If the consumer draws more than its selected sources supply — say it is
set to solar only but keeps running after the sun goes down — that power is
still counted, as coming from your other sources, and the watts show up in
the `restriction_deficit` attribute of its operating-cost sensors. See
[When a device draws from outside its sources](../concepts.md#when-a-device-draws-from-outside-its-sources).

:::note[Reconfigure prompt]

When you remove a grid or PV device this consumer is restricted to, Power
Insight raises a repair issue asking you to **reconfigure** the consumer.

:::

A consumer has no cost, price, or lifetime fields of its own — its cost is
derived from the mix of sources currently supplying it (grid / solar / battery).

## Sensors this device can create

| Sensor | Unit | Enabled by |
|---|---|---|
| Power source shares (one per source) | % | *Power sources (%)* |
| Operating cost rate | currency/h | *Cost method = Standard* |
| Levelized operating cost rate | currency/h | *Cost method = Levelized* |

**Power source shares** show what fraction of this consumer's power currently
comes from each source in your home — for example "the heat pump is currently
running 55 % on solar power." Power Insight infers the source mix from the
real-time state of all your adapters.

See the [Entity reference](../entities.md#consumer) for details.
