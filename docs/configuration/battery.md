# Battery

A battery represents a home storage system. Power Insight tracks charge and
discharge power, **which sources charged the battery** (grid vs. solar), and the
levelized cost of storage. If you have multiple batteries, add one device each.

Add it with **Add device → Battery**.

## Fields

### Name

> A unique name for this device, for example "Home Battery". Used as the device
> name in Home Assistant.

### Power entity

> Sensor that reports this device's power in W, kW or MW.
>
> **Sign convention:** battery — positive = discharging, negative = charging. Use
> **Invert power direction** if your sensor uses the opposite sign.

### Invert power direction

> Turn on if your sensor reports power with the opposite sign to the expected
> convention.

### Round-trip efficiency

> Round-trip efficiency in percent — the share of energy stored that you actually
> get back when discharging (typical values: 85–95 %). Used to correctly
> attribute charging losses to their source.

Default: `95`.

### Exports power to grid

> Turn on if this device can feed surplus power back to the grid. Enables
> export-compensation tracking when the corresponding option is active.

Default: **off** for batteries.

### Export compensation rate

> The amount you are paid per kWh of power exported to the grid, in your
> currency. Required when export-compensation or savings sensors are enabled.

Default: `0.0`.

### Charges from

> Select which sources this battery can charge from — the grid and/or specific PV
> systems you have configured. Power Insight uses this to trace how much of the
> battery's stored energy came from each source.

This drives the battery's blended charging cost and its **charging-source-share**
sensors. Batteries are never selectable as a charge source for another battery.

!!! note "Reconfigure prompt"
    When you add or remove a grid or PV device, Power Insight raises a repair
    issue asking you to **reconfigure** each battery so its charge-source list
    stays correct.

### Lifetime production / Total lifetime cost / CO₂ footprint

These behave exactly as for a [PV system](pv.md#lifetime-production). Together,
*lifetime cost ÷ lifetime throughput* gives this battery's
[**LCOS**](../concepts.md#lcos-levelized-cost-of-storage). Changing them later
applies a [correction factor](../concepts.md#the-correction-factor).

!!! note
    CO₂ footprint has no effect yet — CO₂ sensors are not implemented.

## Sensors this device can create

The battery has the same sensor set as a [PV system](pv.md#sensors-this-device-can-create),
plus:

| Sensor | Unit | Enabled by |
|---|---|---|
| Charging source shares (one per configured source) | % | *Charging source shares (%)* |

These show how much of the battery's current charging power comes from each
source — for example "currently 70 % from solar, 30 % from the grid". Only
sources you selected in **Charges from** appear.

See the [Entity reference](../entities.md#battery) for the full list.

!!! info "Why is my battery's savings negative while charging?"
    Batteries always cost money to charge, so their savings go negative while
    charging and positive while discharging. This is expected — see the
    [FAQ](../faq.md#why-does-my-battery-have-negative-savings).
