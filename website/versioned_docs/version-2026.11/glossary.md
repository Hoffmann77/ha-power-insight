# Glossary

The terms you will meet in Power Insight's sensors, options and docs, in
alphabetical order.

### Avoided cost

What your own power (solar or battery) kept off your grid bill: the power it
supplied to your home, valued at the grid price. Before the device's own
running cost is taken off; compare [cost savings](#cost-savings).

### Base load

See [home base load](#home-base-load).

### Blended price of electricity

What one kWh costs you right now, averaged over everything powering your home.
Grid power counts at the grid price, your own power as free (or at its
[LCOE](#lcoe)/[LCOS](#lcos) in the levelized version). It falls as your solar
and battery cover more of the load.

### Combined

The device Power Insight creates for your **whole home**. Its sensors add up
all your devices. See [Whole home](devices/home.mdx).

### Consumer

A device that only uses power: an appliance, heat pump, EV charger or smart
plug with its own power sensor. See [Consumer](devices/consumer.mdx).

### Correction factor

What Power Insight applies when you change a device's lifetime cost or
production later, so the levelized totals already recorded match the new
figures. See [the correction factor](advanced/costs-and-savings.md#the-correction-factor).

### Cost savings

[Avoided cost](#avoided-cost) minus what the device costs to run. Does not
include export earnings; see [financial return](#financial-return).

### Export compensation

What you are paid for each kWh you export to the grid (also called a feed-in
tariff). You enter it per PV system or battery.

### Financial return

[Cost savings](#cost-savings) plus [export compensation](#export-compensation):
everything a device brings in.

### Gross power

All power entering your home right now: grid import + solar production +
battery discharge.

### Home base load

Everything your home uses that has no power sensor of its own: your total
home consumption minus the consumers you have added. Available as an optional
device; see [Whole home](devices/home.mdx#home-base-load).

### Home consumption

Power used by your household appliances, with or without their own sensor.
Battery charging and [system standby](#system-standby) are counted separately.

### Hub

The Power Insight entry in Home Assistant that holds your devices. One hub
models one grid connection.

### LCOE

*Levelized cost of electricity.* What a kWh from your solar system really
costs once you count what the system cost: lifetime cost ÷ lifetime
production. A system that cost 12,000 and produces 120,000 kWh has an LCOE of
0.10 per kWh.

### LCOS

*Levelized cost of storage.* The battery version of [LCOE](#lcoe): the
battery's lifetime cost ÷ the energy it will discharge over its lifetime.

### Levelized

The money sensors that also count what your hardware cost, using each device's
[LCOE](#lcoe) or [LCOS](#lcos). They show whether your investment pays off.
Compare [standard](#standard).

### Metering imbalance

How much more your metered devices drew than your sources supplied. A little,
briefly, is normal; a lot, for a long time, means a meter is set up wrong. See
[Troubleshooting](troubleshooting.md#metering-imbalance-warning).

### Operating cost

What running a device costs: a PV system's standby draw, a battery's
charging, or a consumer's consumption.

### PV system

A solar installation: panels plus inverter. *PV* stands for photovoltaic.

### Rate

A money sensor measured **per hour, right now** (`EUR/h`). Compare
[total](#total).

### Ratio

A percentage of **the device's own** power. *Production to grid ratio* = the
share of this PV system's production that is exported. Compare
[share](#share).

### Restriction deficit

The watts a battery or consumer set to **Specific devices** is drawing from
*outside* the sources you selected. Shown as the `restriction_deficit`
attribute. See
[When a device draws from outside its sources](advanced/power-attribution.md#when-a-device-draws-from-outside-its-sources).

### Self-consumption

Using your own solar or battery power in your home instead of exporting it.

### Share

A percentage of **a whole-home total**. *Share of grid export* = this PV
system's part of everything your home exports. Compare [ratio](#ratio).

### Standard

The money sensors that value all electricity at your live grid price and
treat your own power as free. Compare [levelized](#levelized).

### System standby

The idle draw of your energy equipment itself, such as a PV inverter at
night. Not household appliances on standby, which count as
[home consumption](#home-consumption).

### Total

A sensor that adds a [rate](#rate) up over time and keeps counting across
restarts (`EUR` or `kWh`).
