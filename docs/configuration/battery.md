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

### Exports to the grid

> Turn on if this device can export power to the grid.

Default: **off** for batteries.

### Export compensation per kWh

> What you are paid per kWh exported to the grid. Required for savings, financial return and export compensation sensors.

Asked for whenever the battery exports to the grid; enter `0` if you are not
paid for it. Both this and *Exports to the grid* can be changed later under
**Reconfigure**, and a new rate applies from then on.

### Power sources / Charges from

> **Whole mix** — the power comes from all sources in proportion to what they supply.
>
> **Specific devices** — only from the sources you select below, e.g. a battery that charges from solar only.

> The sources this battery charges from. Only used with **Specific devices**.

This drives the battery's blended charging cost and its **charging-source-share**
sensors. Batteries are never selectable as a charge source for another battery.

The selection describes what you expect your energy manager to do, not a hard
limit. If the battery charges from elsewhere — say it is set to solar only but
tops up from the grid at night — that power is still counted, as coming from
your other sources, and the watts show up in the `restriction_deficit`
attribute of its operating-cost sensors. See
[When a device draws from outside its sources](../concepts.md#when-a-device-draws-from-outside-its-sources).

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

### Already accumulated

> Optional, in two sections, one per route. **Energy (kWh):** *Charged*,
> *Discharged* and any grid charging, and optionally its own export to the
> grid and its own average grid tariff (else the grid's). **Amounts:** the savings and export compensation your app shows,
> taken as they are. See [Carried-over history](../history.md).

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
## Reading the battery's totals

A battery does not produce energy. It buys energy when it charges and replaces
grid energy when it discharges, and its totals split those two sides up:

| Total | What it adds up | Counts up when |
|---|---|---|
| **Total operating cost** | What charging cost: grid energy at the grid price; energy from your PV systems counts as free | charging from the grid |
| **Total levelized operating cost** | The same, with PV energy priced at that PV system's LCOE, its lifetime cost per kWh | charging from anything |
| **Total cost savings** | Grid electricity it replaced (discharge into the home × grid price), minus the operating cost | discharging; it goes **down** while charging from the grid |
| **Total financial return** | Savings plus export compensation, if the battery may export to the grid | discharging, and exporting |

- **The operating cost is already inside the savings.** Do not subtract it
  again: the savings are the battery's net result, what discharging saved
  minus what charging cost.
- **Charging from PV is free in the standard totals and costs the LCOE in the
  levelized ones.** A battery charged only from PV has a *Total operating
  cost* near 0 but a real *Total levelized operating cost*: what the PV
  energy it stored cost to produce.
- **Financial return equals savings for most batteries.** It only adds export
  compensation, and a battery that may not export to the grid earns none.
- **The battery's own lifetime cost (its LCOS) is in neither operating cost.**
  It is charged when energy *leaves* the battery, so it lowers the levelized
  savings and levelized financial return instead.

**Example.** The battery charged 2,500 kWh from PV and discharged 2,200 kWh
into the home; a kWh from the grid costs 0.34, the PV system's LCOE is 0.10
and the battery's LCOS 0.15.

| Total | Calculation | Value |
|---|---|---|
| Total operating cost | 0 kWh from the grid × 0.34 | **0.00** |
| Total levelized operating cost | 2,500 kWh × 0.10 | **250.00** |
| Total cost savings | 2,200 × 0.34 − 0 | **748.00** |
| Total financial return | 748 + 0 export | **748.00** |
| Total levelized cost savings | 748 − 2,200 × 0.15 (LCOS) − 250 (PV energy at its LCOE) | **168.00** |

Had 500 of the 2,500 kWh come from the grid instead, the operating cost would
be 500 × 0.34 = 170.00, and the savings 170.00 lower: 578.00.

:::info[Why does a battery that never charges from the grid have an operating cost?]

Because some of its draw did come from the grid, as far as the meters can
tell. Whenever the battery's power sensor shows it drawing power and the PV
systems it may charge from produce nothing — at night, for example — that
draw can only have come from the grid, and it is booked at the grid price.
Small amounts like this usually come from the battery's own consumption (its
battery management and inverter in standby), or from short top-ups by its
energy manager.

If the battery is set to **Specific devices**, its *Operating cost rate*
shows the watts drawn from outside its sources in the `restriction_deficit`
attribute. The *Total operating cost* attributes show whether any of the
total was carried over from your app (`carried_over`) or counted by Power
Insight (`tracked`): carried-over history only adds operating cost for what
you entered under *Of which from the grid*.

:::
