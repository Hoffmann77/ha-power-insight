# PV system

A PV system represents a solar array / inverter. Power Insight tracks how much
it produces, how much of that you self-consume vs. export, and the financial
impact. If you have multiple PV systems, add one device each — the sensor
*selection* applies to all of them, but each system gets its own set of sensors.

Add it with **Add device → PV system**.

## Fields

### Name

> For example "Rooftop" or "Heat pump". Used in the device and sensor names.

### Power sensor

> Sensor with this device's power in W, kW or MW. Positive = producing,
> negative = drawing (standby).

### Invert power sign

> Turn on if your sensor uses the opposite sign.

### Feeds into the grid

> Turn on if this device can feed power into the grid.

Default: **on** for PV systems. When off, the *Production to grid* (+ ratio),
*Share of grid export* and export-compensation sensors are not created.

### Export compensation per kWh

> What you are paid per kWh fed into the grid. Required for savings, financial return and export compensation sensors.

This is your feed-in tariff, in your currency per kWh. There is no default —
a rate that fits one country is wrong in the next — so it is asked for whenever
the device feeds into the grid; enter `0` if you are not paid for it.

Both this and *Feeds into the grid* can be changed later under **Reconfigure**.
A new rate applies from then on: a feed-in tariff is a price that changes over
time, so the totals already accumulated keep the rate that held when they were
earned.

### Lifetime production

> Energy in kWh you expect this device to deliver over its lifetime: generated (PV) or discharged (battery). Used for levelized sensors.

### Lifetime cost

> Total cost over the device's lifetime (purchase, installation, maintenance). Used for levelized sensors.

Together, *lifetime cost ÷ lifetime production* gives this system's
[**LCOE**](../concepts.md#lcoe-levelized-cost-of-electricity).

### CO₂ footprint

> CO₂ emitted to make and install this device, in kg. Optional; reserved for CO₂ sensors.

:::note

CO₂ sensors are **not implemented yet**; this field currently has no effect.

:::

## Changing lifetime values later

If you reconfigure the lifetime cost or production, Power Insight applies a
[**correction factor**](../concepts.md#the-correction-factor) that retroactively
rescales this device's already-recorded levelized values so history stays
consistent.

## Sensors this device can create

| Sensor | Unit | Enabled by |
|---|---|---|
| Production to grid (+ ratio) · Share of grid export | W / % / % | *Power distribution* options (needs *Exports power*) |
| Production to home consumption (+ ratio) · Share of home consumption | W / % / % | *Power distribution* options |
| Production to batteries (+ ratio) · Share of battery charging | W / % / % | *Power distribution* options (only when a battery charges from this system) |
| Production to system standby (+ ratio) · Share of system standby | W / % / % | *Power distribution* options |
| Export compensation rate | currency/h | *Export compensation rate* |
| Total export compensation | currency | *Total export compensation* |
| Operating cost rate (+ Total) | currency/h, currency | *Cost method = Standard* (+ *Accumulate*) |
| Levelized operating cost rate (+ Total) | currency/h, currency | *Cost method = Levelized* (+ *Accumulate*) |
| Self-consumption cost savings rate | currency/h | *Savings method = Standard* |
| Cost savings rate (+ Total) | currency/h, currency | *Savings method = Standard* (+ *Accumulate*) |
| Levelized cost savings rate (+ Total) | currency/h, currency | *Savings method = Levelized* (+ *Accumulate*) |

See the [Entity reference](../entities.md#pv-system) for the exact meaning of
each sensor.
