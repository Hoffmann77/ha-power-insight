# Entity reference

This is the full list of sensors Power Insight can create, grouped by scope.
Which sensors actually appear depends on the options you enable — see
[Sensors, presets & options](configuration/options-and-presets.md).

:::info[Currency units]

Sensors are documented in `EUR` for brevity. At runtime the `EUR` unit is
replaced with **your Home Assistant currency** (e.g. `$/h`, `£/kWh`).

:::

:::warning[Entity names may change]

Power Insight is in beta; entity names may change until 1.0.

:::

:::info[`ratio` vs. `share` — they are not the same]

Every percentage sensor is one or the other, and the denominator differs:

- **`… ratio`** — a fraction of the **scope's own power**: for a device, its
  own production/throughput (e.g. *Production to grid ratio* = the fraction of
  *this PV system's production* that is exported); for the whole home, gross
  power.
- **`Share of …`** — this device's slice of a **home-wide total** (e.g. *Share
  of grid export* = this system's exports ÷ *all power exported by the home*).

See [Power distribution → ratio vs. share](concepts.md#the-four-channels)
for the full definition.

:::

:::info[Where a device's power goes]

On the grid, PV and battery devices, the distribution sensors describe **where
that device's output goes** — never what the device itself consumes. They read
`{Import|Production|Discharge} to {destination}`:

- **home consumption** — your household appliances;
- **batteries** — battery charging;
- **system standby** — the idle draw of your energy system's own equipment
  (e.g. PV inverters at night), *not* appliances on standby;
- **grid** — export.

So a battery's *Discharge to system standby* is battery power feeding a PV
inverter's night draw, not the battery's own standby.

:::

Legend for the **Enabled by** column — the option/category (and where relevant
the device capability) that must be on for the sensor to exist:

- *Power split (W)*, *Power split (%)*, *Share of home totals* → the matching
  toggle in the **Power** section.
- *Cost — Standard / Levelized* → the **Cost method**.
- *Savings — Standard / Levelized* → the **Savings method**.
- *Financial return — Standard / Levelized* → the **Financial return method**.
- *Total costs / savings / financial return* → the matching **Total …** toggle,
  for the method(s) selected above it (*levelized* = the Levelized method).

---

## Combined (whole home)

These aggregate power and cost **across your whole home** — they sum all your
devices into a single number per metric. They live on the **Combined**
device, so the device name already says "combined" and the sensor names don't
repeat it.

### Real-time sensors

| Sensor | Unit | Meaning | Enabled by |
|---|---|---|---|
| Available power | W | Gross power entering the home (grid import + PV production + battery discharge). Diagnostic. | *Debug sensors* |
| Metering imbalance | W | How much more the metered devices drew than the sources supplied. Meters sampled at different moments make this briefly non-zero; Power Insight then balances the readings by moving every one of them in proportion to its size. Persistently large, it points at a misconfigured meter — an inverted sign, or a meter inside another metered circuit — and a repair issue says so. Diagnostic. | *Debug sensors* |
| Home consumption power | W | Everything your home's appliances draw right now — metered consumers plus the unmetered base load — from any source (grid, solar or battery). | Power split (W) |
| Battery charging power | W | Power currently going into battery charging. | Power split (W) |
| System standby power | W | Power currently drawn by your energy system's own equipment while idle (e.g. PV inverters at night) — not household appliances on standby. | Power split (W) |
| Export ratio | % | Share of gross power currently exported to the grid. | Power split (%) |
| Home consumption ratio | % | Share of gross power currently going to home consumption. | Power split (%) |
| Battery charging ratio | % | Share of gross power currently going to battery charging. | Power split (%) |
| System standby ratio | % | Share of gross power currently lost to system standby. | Power split (%) |
| Price of electricity | EUR/kWh | Current blended price of one kWh across your whole mix (grid + your devices). | Cost — Standard |
| Levelized price of electricity | EUR/kWh | As above, but each device's cost is its levelized lifetime cost. | Cost — Levelized |
| Cost rate | EUR/h | What all the power entering your home costs per hour right now (gross power × price of electricity). | Cost — Standard |
| Levelized cost rate | EUR/h | Cost rate computed with levelized device costs. | Cost — Levelized |
| Consumption cost rate | EUR/h | The part of the cost rate that goes to **home consumption**. | Cost — Standard |
| Levelized consumption cost rate | EUR/h | Consumption cost rate computed with levelized device costs. | Cost — Levelized |
| Charging cost rate | EUR/h | The part of the cost rate that goes into **battery charging**. | Cost — Standard |
| Levelized charging cost rate | EUR/h | Charging cost rate computed with levelized device costs. | Cost — Levelized |
| Levelized system standby cost rate | EUR/h | The part of the levelized cost rate lost to **system standby**. | Cost — Levelized |
| Levelized export cost rate | EUR/h | What producing the **exported** power cost, at levelized device costs. | Cost — Levelized |
| Device operating cost rate | EUR/h | What running your PV and battery hardware costs per hour — their own draw (charging plus standby). The sum of the per-device *Operating cost rate* sensors. | Cost — Standard |
| Levelized device operating cost rate | EUR/h | Device operating cost rate computed with levelized device costs. | Cost — Levelized |
| Cost savings rate | EUR/h | Money saved per hour by self-consuming your own generation — avoided grid import minus operating costs. Does not include export revenue. | Savings — Standard |
| Levelized cost savings rate | EUR/h | Cost savings rate computed with levelized device costs. | Savings — Levelized |
| Financial return rate | EUR/h | Total financial benefit per hour — cost savings plus export compensation. | Financial return — Standard |
| Levelized financial return rate | EUR/h | Financial return computed with levelized device costs. | Financial return — Levelized |

### Accumulated totals

| Sensor | Unit | Meaning | Enabled by |
|---|---|---|---|
| Total consumption cost | EUR | Consumption cost rate integrated over time. | Total costs |
| Total charging cost | EUR | Charging cost rate integrated over time. | Total costs |
| Total levelized device operating cost | EUR | Levelized operating cost totalled across all devices (retro-corrected). | Total costs (levelized) |
| Total cost savings | EUR | Avoided import cost integrated over time (does not include export revenue). | Total savings |
| Total levelized cost savings | EUR | Levelized cost savings totalled across all devices (retro-corrected). | Total savings (levelized) |
| Total financial return | EUR | Financial return rate integrated over time. | Total financial return |
| Total levelized financial return | EUR | Levelized financial return totalled across all devices (retro-corrected). | Total financial return (levelized) |

:::note[Combined levelized totals are derived, not integrated]

The *levelized* totals are computed as the sum of each device's own
levelized total (scaled by its [correction factor](concepts.md#the-correction-factor))
plus a ledger of removed devices — so editing lifetime values is retroactive
and removing a device never drops its historical contribution.

While a device's own total has no value — at startup before it is restored,
say — the combined total is **unavailable** rather than a partial sum, which
would show up in the statistics as a false drop and rise. A device whose own
total is **disabled** is left out of the combined total altogether: it is not
accumulating anything.

:::

---

## Grid connection

Import and export both live on the grid device (the single point where they
physically happen). See [Grid connection configuration](configuration/grid.md).

| Sensor | Unit | Meaning | Enabled by |
|---|---|---|---|
| Import power | W | Power currently bought from the grid. | Power split (W) |
| Export power | W | Surplus power currently sent back to the grid. | Power split (W) |
| Import to home consumption | W | Grid import currently going to home consumption. | Power split (W) |
| Import to home consumption ratio | % | Fraction of **grid import** currently going to home consumption. | Power split (%) |
| Share of home consumption | % | The grid's share of **all home consumption**. | Share of home totals |
| Import to batteries | W | Grid import currently going to battery charging. Only exists when a battery charges from the grid. | Power split (W) · charge source |
| Import to batteries ratio | % | Fraction of grid import currently going to battery charging. Only exists when a battery charges from the grid. | Power split (%) · charge source |
| Share of battery charging | % | The grid's share of all battery-charging power in the home. Only exists when a battery charges from the grid. | Share of home totals · charge source |
| Import to system standby | W | Grid import currently feeding system standby (e.g. PV inverters at night). | Power split (W) |
| Import to system standby ratio | % | Fraction of grid import currently going to system standby. | Power split (%) |
| Share of system standby | % | The grid's share of all system standby power. | Share of home totals |
| Import cost rate | EUR/h | Current cost per hour of grid imports (live price × import power). | Cost — Standard |
| Total import cost | EUR | Import cost integrated over time. | Total costs |
| Export compensation rate | EUR/h | Money earned per hour from exports (export power × compensation rate). | Export compensation rate |
| Total export compensation | EUR | Export compensation integrated over time. | Total export compensation |

---

## PV system

Per PV device. Export sensors require **Feeds into the grid** to be on;
levelized sensors require lifetime values (an LCOE). See
[PV system configuration](configuration/pv.md).

### Real-time sensors

| Sensor | Unit | Meaning | Enabled by |
|---|---|---|---|
| Production to grid | W | Power from this system currently sent to the grid. | Power split (W) · exports |
| Production to grid ratio | % | Fraction of **this system's own production** currently exported to the grid. | Power split (%) · exports |
| Share of grid export | % | This system's share of **all power exported by the home**. | Share of home totals · exports |
| Production to home consumption | W | Power from this system currently consumed in the home. | Power split (W) |
| Production to home consumption ratio | % | Fraction of **this system's own production** consumed directly in the home. | Power split (%) |
| Share of home consumption | % | This system's share of **all home consumption**. | Share of home totals |
| Production to batteries | W | Power from this system currently going to battery charging. Only exists when a battery charges from this system. | Power split (W) · charge source |
| Production to batteries ratio | % | Fraction of this system's production currently going to battery charging. Only exists when a battery charges from this system. | Power split (%) · charge source |
| Share of battery charging | % | This system's share of all battery-charging power in the home. Only exists when a battery charges from this system. | Share of home totals · charge source |
| Production to system standby | W | Power from this system currently feeding another device's standby draw (system standby). | Power split (W) |
| Production to system standby ratio | % | Fraction of this system's production currently going to system standby. | Power split (%) |
| Share of system standby | % | This system's share of all system standby power. | Share of home totals |
| Export compensation rate | EUR/h | Money earned per hour exporting this system's power. | Export compensation rate · exports |
| Operating cost rate | EUR/h | Running operating cost per hour of this system. | Cost — Standard |
| Levelized operating cost rate | EUR/h | Operating cost rate using this system's LCOE. | Cost — Levelized · has lifetime values |
| Cost savings rate | EUR/h | Money saved per hour by self-consuming this system's power — avoided grid import minus operating costs. Does not include export revenue. | Savings — Standard |
| Levelized cost savings rate | EUR/h | Cost savings rate computed with this system's LCOE. | Savings — Levelized · has lifetime values |
| Financial return rate | EUR/h | Cost savings plus export compensation for this system. | Financial return — Standard · exports |
| Levelized financial return rate | EUR/h | Financial return computed with this system's LCOE. | Financial return — Levelized · has lifetime values · exports |

### Accumulated totals

| Sensor | Unit | Meaning | Enabled by |
|---|---|---|---|
| Total export compensation | EUR | Export compensation integrated over time. | Total export compensation · exports |
| Total operating cost | EUR | Operating cost rate integrated over time. | Total costs |
| Total levelized operating cost | EUR | Levelized operating cost integrated (retro-corrected). | Total costs (levelized) · has lifetime values |
| Total cost savings | EUR | Avoided import cost integrated over time (does not include export revenue). | Total savings |
| Total levelized cost savings | EUR | Levelized cost savings integrated (retro-corrected). | Total savings (levelized) · has lifetime values |
| Total financial return | EUR | Financial return rate integrated over time. | Total financial return · exports |
| Total levelized financial return | EUR | Levelized financial return integrated (retro-corrected). | Total financial return (levelized) · has lifetime values · exports |

---

## Battery

Per battery device. The battery has the **same sensor set as a PV system**
(above) — including cost savings, financial return, and their levelized variants
— reading the battery's own values, with **Discharge** in place of
**Production** (*Discharge to home consumption*, *Discharge to grid*, …), **plus**
dynamic charging-source sensors. (Its *Discharge to batteries* sensors only
appear when another battery is configured to charge *from* this one —
battery-to-battery charging — so in most setups they are absent.)

| Sensor | Unit | Meaning | Enabled by |
|---|---|---|---|
| Charging source shares (one per configured source) | % | Share of the battery's current charging power coming from each source (e.g. "70 % solar, 30 % grid"). One sensor per source selected in **Charges from**. | Charging source shares |

For the battery, the levelized quantities use the battery's
[**LCOS**](concepts.md#lcos-levelized-cost-of-storage) instead of an LCOE. See
[Battery configuration](configuration/battery.md).

---

## Consumer

Per consumer device. Consumer support is still under development. See
[Consumer configuration](configuration/consumer.md).

| Sensor | Unit | Meaning | Enabled by |
|---|---|---|---|
| Consumption share | % | This consumer's share of all self-consumption in the home. | Share of home totals |
| Power share from &lt;source&gt; (one per source) | % | Share of this consumer's current power coming from that source (grid / solar / battery). Mirrors the battery's *Charging share from &lt;source&gt;*. | Power source shares |
| Power from &lt;source&gt; (one per source) | W | The watts of this consumer's current power coming from that source. They add up to its draw — slightly less than its own meter while the meters overdraw (see *Metering imbalance*). | Power from each source |
| Operating cost rate | EUR/h | Current cost per hour to run this consumer, using the live grid price weighted by its source mix. | Cost — Standard |
| Levelized operating cost rate | EUR/h | As above, using each source's levelized cost per kWh. | Cost — Levelized |

On a battery or consumer set to **Specific devices**, both operating-cost rate
sensors carry a `restriction_deficit` attribute: the watts the device currently
draws from outside its selected sources. See
[When a device draws from outside its sources](concepts.md#when-a-device-draws-from-outside-its-sources).

### Accumulated totals

| Sensor | Unit | Meaning | Enabled by |
|---|---|---|---|
| Total operating cost | EUR | Operating cost rate integrated over time. | Total costs |
| Total levelized operating cost | EUR | Levelized operating cost integrated over time. Retro-corrected per **supplying** device, since a consumer has no lifetime cost of its own. | Total costs (levelized) |
| Total avoided cost | EUR | Avoided cost rate integrated over time — what this consumer did not pay the grid because local generation served it. | Total savings |
| Energy from &lt;source&gt; (one per source) | kWh | *Power from &lt;source&gt;* integrated over time — how much of this consumer's energy came from that source. | Energy from each source |

The *Energy from &lt;source&gt;* sensors split the energy the consumer's own
meter already counts. Don't add them to the Energy dashboard next to that
meter: the same energy would be counted twice.
