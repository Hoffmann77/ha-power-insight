# Troubleshooting & FAQ

## Troubleshooting

### A sensor I turned on doesn't appear

Most sensors need some extra information before they can be created:

| Sensor | Needs |
|---|---|
| Any cost, savings or financial return sensor | an **Electricity price** on the [grid connection](devices/grid.mdx#electricity-price) |
| Any **levelized** sensor | **Lifetime production** and **Lifetime cost** on the PV system or battery |
| Export sensors on a PV system or battery | **Exports to the grid** turned on for that device |
| *… to batteries* sensors | a battery that is allowed to charge from that source |

When you save the options, Power Insight names any device that is missing
something. Open it, choose **Reconfigure**, fill in the missing value and
save the options again. See
[Sensor options & presets](sensor-options.md#missing-data-guard).

### Values look backwards: export shows as import, charging as discharging

The power sensor uses the opposite sign from what Power Insight expects (see
[sign conventions](how-it-works.md#sign-conventions)). Open the device,
choose **Reconfigure** and turn on **Invert power sign**. Smart plugs in
particular usually need this.

### Sensors show *unavailable*

A sensor is unavailable while any reading it depends on is unavailable: a
power sensor that dropped out, or the price sensor. Check the source entities
in Home Assistant. Power Insight shows *unavailable* on purpose rather than a
wrong number, and totals simply pause until the reading comes back.

### Repair issues

Power Insight raises a repair issue under **Settings → System → Repairs**
when something needs your attention:

| Issue | What to do |
|---|---|
| **… needs a grid connection** | Add a grid connection: **Add device → Grid connection**. Nothing can be calculated without one. |
| **Check the charging sources of …** | A possible charging source was added or removed. **Reconfigure** the battery and check *Charges from*. |
| **Check the power sources of …** | A consumer is restricted to a source you removed. **Reconfigure** it and pick its sources again. |
| **The electricity price … has an unknown unit** | The price sensor's unit isn't a price per energy. Use one in `EUR/kWh`, `ct/kWh`, `EUR/MWh` or similar. |
| **The electricity price … is in another currency** | Power Insight doesn't convert currencies. Use a price sensor in your Home Assistant currency, or change the currency in **Settings → System → General**. |
| **Two devices … share a power sensor** | Each device needs its own power sensor; otherwise its watts are counted twice. |
| **The meters … disagree** | See [Metering imbalance warning](#metering-imbalance-warning) below. |
| **Carried-over savings … need an average grid tariff** | Enter an **Average grid tariff** on the grid connection's *Already accumulated* section. See [Carried-over history](advanced/history.md). |

### Metering imbalance warning

Your consumers drew more power than your grid, solar and batteries supplied,
for at least 15 minutes. Meters that update at slightly different moments
cause short gaps, which Power Insight evens out by itself; a long-lasting gap
usually means:

- a power sensor with the **wrong sign**: turn on **Invert power sign**;
- a consumer whose meter sits **inside another metered circuit**, so its
  power is counted twice.

Turn on **Debug sensors** in the options to watch the *Metering imbalance*
sensor on the [Combined device](devices/home.mdx) while you fix it.

### My battery charges from the grid even though I set it to solar only

The selection under **Specific devices** describes what you *expect*, not a
hard limit: Power Insight counts every watt your meters report. If the
battery charges at night with no solar available, that power can only have
come from the grid, and it is counted and priced that way. The
`restriction_deficit` attribute on its *Operating cost rate* shows how many
watts came from outside its selection. See
[When a device draws from outside its sources](advanced/power-attribution.md#when-a-device-draws-from-outside-its-sources).

## FAQ

### Do I need energy (kWh) meters?

No. Power Insight works from **power** sensors (W, kW or MW) only. Every
device you add, and the grid connection, needs one.

### Does it work with dynamic electricity prices?

Yes, that is a core design goal. Every calculation uses the **current** value
of your price sensor, so each moment is priced at the price that held then.

### How are savings calculated?

In short: **cost savings** is what your own power kept off your grid bill,
minus what the device costs to run. **Financial return** adds what exporting
earned. See [How it works](how-it-works.md#costs-savings-and-earnings) and,
for the formulas,
[Costs, savings and the maths](advanced/costs-and-savings.md#how-savings-and-financial-return-are-calculated).

### Why does my battery have negative cost savings?

While a battery charges from the grid, that energy costs money, so its
savings go down. They go up again when it discharges and replaces grid power.
Over a full charge and discharge cycle, the net result is what matters. See
[Why does my battery have negative cost savings?](advanced/costs-and-savings.md#why-does-my-battery-have-negative-cost-savings)

### Why is my levelized financial return lower than my levelized savings?

Because exported energy also carries the hardware's cost. If you are paid
less per exported kWh than its LCOE, exporting loses a little money. See
[the explanation](advanced/costs-and-savings.md#why-is-my-levelized-financial-return-lower-than-my-levelized-savings).

### Can I track two grid connections?

Not in one hub: a hub models one grid connection. Add Power Insight a
**second time** for a second grid connection.

### Are there CO₂ sensors?

Not yet. The setup may ask for a CO₂ intensity or footprint, but **no CO₂
sensors are created in this release**. You can leave those fields empty.

### If I turn a sensor off, do I lose its history?

No. Turned-off sensors are hidden and stop updating, but their history is
kept, and they come back when you turn the option on again.

### How do I carry over my existing totals?

Enter the figures from your PV system's or battery's app in the device's
**Already accumulated** section, when you add it or later under
**Reconfigure**. See [Carried-over history](advanced/history.md).

### Why did my PV system's savings drop when I added my battery's history?

Because the solar energy that went into the battery is now credited to the
battery, when it discharges into your home. The combined savings drop a
little too: a battery gives back less than it takes in (typically 85–92 %),
and only energy that reaches your home saves the grid price. See
[Adding a battery's history](advanced/history.md#adding-a-batterys-history-lowers-the-pv-systems-savings).
