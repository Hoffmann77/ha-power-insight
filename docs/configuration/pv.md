# PV system

A PV system represents a solar array / inverter. Power Insight tracks how much
it produces, how much of that you self-consume vs. export, and the financial
impact. If you have multiple PV systems, add one device each — the sensor
*selection* applies to all of them, but each system gets its own set of sensors.

Add it with **Add device → PV system**.

## Fields

### Name

> A unique name for this device, for example "Rooftop Solar". Used as the device
> name in Home Assistant.

### Power entity

> Sensor that reports this device's power in W, kW or MW.
>
> **Sign convention:** PV — positive = producing, negative = consuming
> (standby). Use **Invert power direction** if your sensor uses the opposite
> sign.

### Invert power direction

> Turn on if your sensor reports power with the opposite sign to the expected
> convention.

### Exports power to grid

> Turn on if this device can feed surplus power back to the grid. Enables
> export-compensation tracking when the corresponding option is active.

Default: **on** for PV systems. When off, the export power / ratio / share /
compensation sensors are not created.

### Export compensation rate

> The amount you are paid per kWh of power exported to the grid, in your
> currency. **Required when export-compensation or savings sensors are enabled.**

Default: `0.08`. This is your feed-in tariff.

### Lifetime production

> Total energy in kWh you expect this device to produce over its entire
> lifetime. Combined with the total lifetime cost to derive the levelized
> (per-kWh) cost. **Required when any levelized sensor is enabled.**

### Total lifetime cost

> Total purchase, installation, and expected maintenance cost of this device over
> its lifetime, in your currency. Combined with lifetime production to derive the
> levelized cost per kWh. **Required when any levelized cost sensor is enabled.**

Together, *lifetime cost ÷ lifetime production* gives this system's
[**LCOE**](../concepts.md#lcoe-levelized-cost-of-electricity).

### CO₂ footprint

> Total CO₂ emitted to manufacture and install this device (in kg). Used to
> derive a levelized CO₂ intensity per kWh produced. Required when any levelized
> CO₂ sensor is enabled.

!!! note
    CO₂ sensors are **not implemented yet**; this field currently has no effect.

## Changing lifetime values later

If you reconfigure the lifetime cost or production, Power Insight applies a
[**correction factor**](../concepts.md#the-correction-factor) that retroactively
rescales this device's already-recorded levelized values so history stays
consistent.

## Sensors this device can create

| Sensor | Unit | Enabled by |
|---|---|---|
| Export power / ratio / share | W / % / % | *Power distribution* options (needs *Exports power*) |
| Self-consumption power / ratio / share | W / % / % | *Power distribution* options |
| Export compensation rate | currency/h | *Export compensation rate* |
| Total export compensation | currency | *Accumulated export compensation* |
| Operating cost rate (+ Total) | currency/h, currency | *Cost method = Standard* (+ *Accumulate*) |
| Levelized operating cost rate (+ Total) | currency/h, currency | *Cost method = Levelized* (+ *Accumulate*) |
| Self-consumption cost savings rate | currency/h | *Savings method = Standard* |
| Cost savings rate (+ Total) | currency/h, currency | *Savings method = Standard* (+ *Accumulate*) |
| Levelized cost savings rate (+ Total) | currency/h, currency | *Savings method = Levelized* (+ *Accumulate*) |

See the [Entity reference](../entities.md#pv-system) for the exact meaning of
each sensor.
