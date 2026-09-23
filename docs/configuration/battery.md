# Battery

A battery represents a home storage system. Power Insight tracks charge and
discharge power, **which sources charged the battery** (grid vs. solar), and the
levelized cost of storage. If you have multiple batteries, add one device each.

Add it with **Add device → Battery**.

## Fields

### Name

> For example "Rooftop" or "Heat pump". Used in the device and sensor names.

### Power sensor

> Sensor with this device's power in W, kW or MW. Positive = discharging,
> negative = charging.

### Invert power sign

> Turn on if your sensor uses the opposite sign.

### Feeds into the grid

> Turn on if this device can feed power into the grid.

Default: **off** for batteries.

### Export compensation per kWh

> What you are paid per kWh fed into the grid. Required for savings, financial return and export compensation sensors.

Default: `0.0`.

### Power sources / Charges from

> **Whole mix** — the power comes from all sources in proportion to what they supply.
>
> **Specific devices** — only from the sources you select below, e.g. a battery that charges from solar only.

> The sources this battery charges from. Only used with **Specific devices**.

This drives the battery's blended charging cost and its **charging-source-share**
sensors. Batteries are never selectable as a charge source for another battery.

:::note[Reconfigure prompt]

When you add or remove a grid or PV device, Power Insight raises a repair
issue asking you to **reconfigure** each battery so its charge-source list
stays correct.

:::

### Lifetime production / Lifetime cost / CO₂ footprint

These behave exactly as for a [PV system](pv.md#lifetime-production). Together,
*lifetime cost ÷ lifetime throughput* gives this battery's
[**LCOS**](../concepts.md#lcos-levelized-cost-of-storage). Changing them later
applies a [correction factor](../concepts.md#the-correction-factor).

:::note

CO₂ footprint has no effect yet — CO₂ sensors are not implemented.

:::

## Sensors this device can create

The battery has the same sensor set as a [PV system](pv.md#sensors-this-device-can-create),
plus:

| Sensor | Unit | Enabled by |
|---|---|---|
| Charging source shares (one per configured source) | % | *Charging sources (%)* |

These show how much of the battery's current charging power comes from each
source — for example "currently 70 % from solar, 30 % from the grid". Only
sources you selected in **Charges from** appear.

See the [Entity reference](../entities.md#battery) for the full list.

:::info[Why is my battery's savings negative while charging?]

Batteries always cost money to charge, so their savings go negative while
charging and positive while discharging. This is expected — see the
[FAQ](../faq.md#why-does-my-battery-have-negative-cost-savings).

:::