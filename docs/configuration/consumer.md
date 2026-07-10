# Consumer

A consumer represents an electrical load — an appliance, EV charger, heat pump,
etc. Power Insight tracks how much power it draws and where that power comes from.

Add it with **Add device → Electrical consumer**.

!!! warning "Under development"
    Consumer support is still being built out. Today a consumer produces
    operating-cost sensors and (with the option enabled) power-source-share
    sensors. More consumer sensors are planned.

## Fields

### Name

> A unique name for this device, for example "Heat Pump". Used as the device name
> in Home Assistant.

### Power entity

> Sensor that reports this device's power in W, kW or MW. Positive = power drawn
> by the consumer.

### Invert power direction

> Turn on if your sensor reports power with the opposite sign to the expected
> convention.

A consumer has no cost, price, or lifetime fields of its own — its cost is
derived from the mix of sources currently supplying it (grid / solar / battery).

## Sensors this device can create

| Sensor | Unit | Enabled by |
|---|---|---|
| Power source shares (one per source) | % | *Power source shares (%)* |
| Operating cost rate | currency/h | *Cost method = Standard* |
| Levelized operating cost rate | currency/h | *Cost method = Levelized* |

**Power source shares** show what fraction of this consumer's power currently
comes from each source in your home — for example "the heat pump is currently
running 55 % on solar power." Power Insight infers the source mix from the
real-time state of all your adapters.

See the [Entity reference](../entities.md#consumer) for details.
