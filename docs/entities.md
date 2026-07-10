# Entity reference

This is the full list of sensors Power Insight can create, grouped by scope.
Which sensors actually appear depends on the options you enable — see
[Sensors, presets & options](configuration/options-and-presets.md).

!!! info "Currency units"
    Sensors are documented in `EUR` for brevity. At runtime the `EUR` unit is
    replaced with **your Home Assistant currency** (e.g. `$/h`, `£/kWh`).

!!! warning "Entity names may change"
    Power Insight is in beta; entity names may change until 1.0.

Legend for the **Enabled by** column — the option/category (and where relevant
the device capability) that must be on for the sensor to exist:

- *Distribution (W/ratios/shares)* → the matching **Power sensors** category.
- *Cost — Standard / Levelized* → the **Cost calculation method**.
- *Savings — Standard / Levelized* → the **Savings calculation method**.
- *Accumulate …* → the matching accumulate toggle.

---

## Combined (whole home)

These aggregate power and cost **across your whole home** — they sum all your
devices into a single number per metric.

### Real-time sensors

| Sensor | Unit | Meaning | Enabled by |
|---|---|---|---|
| Available power | W | Gross power entering the home (grid import + PV production + battery discharge). Diagnostic, **disabled by default**. | *Debug power entities* |
| Combined self-consumption power | W | Locally produced power (solar + battery discharge) your home is using right now instead of importing. | Distribution (W) |
| Combined charging power | W | Power currently going into battery charging. | Distribution (W) |
| Combined standby power | W | Power currently consumed by device standby (e.g. PV at night). | Distribution (W) |
| Combined export ratio | % | Share of gross power currently exported to the grid. | Distribution ratios |
| Combined self-consumption ratio | % | Share of gross power currently self-consumed. | Distribution ratios |
| Combined charging ratio | % | Share of gross power currently going to charging. | Distribution ratios |
| Combined standby ratio | % | Share of gross power currently lost to standby. | Distribution ratios |
| Combined price of electricity | EUR/kWh | Current blended price of one kWh across your whole mix (grid + your devices). | Cost — Standard |
| Combined levelized price of electricity | EUR/kWh | As above, but each device's cost is its levelized lifetime cost. | Cost — Levelized |
| Combined cost rate | EUR/h | Running cost per hour of your current mix. | Cost — Standard |
| Combined levelized cost rate | EUR/h | Cost rate computed with levelized device costs. | Cost — Levelized |
| Combined operating cost rate | EUR/h | Running operating cost per hour of your mix. | Cost — Standard |
| Combined levelized operating cost rate | EUR/h | Operating cost rate with levelized device costs. | Cost — Levelized |
| Combined cost savings rate | EUR/h | Money saved per hour by self-consuming and exporting your own generation instead of importing. | Savings — Standard |
| Combined levelized cost savings rate | EUR/h | Savings rate computed with levelized device costs. | Savings — Levelized |
| Combined self-consumption cost savings rate | EUR/h | Money saved per hour purely by self-consuming (avoided grid import). | Savings — Standard |

### Accumulated totals

| Sensor | Unit | Meaning | Enabled by |
|---|---|---|---|
| Combined total operating costs | EUR | Operating cost rate integrated over time. | Accumulate costs |
| Combined total levelized operating costs | EUR | Levelized operating cost totalled across all devices (retro-corrected). | Accumulate levelized costs |
| Combined total self-consumption cost savings | EUR | Self-consumption savings integrated over time. | Accumulate savings |
| Combined total cost savings | EUR | Total savings integrated over time. | Accumulate savings |
| Combined total levelized cost savings | EUR | Levelized savings totalled across all devices (retro-corrected). | Accumulate levelized savings |

!!! note "Combined levelized totals are derived, not integrated"
    The two *levelized* totals are computed as the sum of each device's own
    levelized total (scaled by its [correction factor](concepts.md#the-correction-factor))
    plus a ledger of removed devices — so editing lifetime values is retroactive
    and removing a device never drops its historical contribution.

---

## Grid connection

Import and export both live on the grid device (the single point where they
physically happen). See [Grid connection configuration](configuration/grid.md).

| Sensor | Unit | Meaning | Enabled by |
|---|---|---|---|
| Import power | W | Power currently bought from the grid. | Distribution (W) |
| Export power | W | Surplus power currently sent back to the grid. | Distribution (W) |
| Consumption ratio | % | Grid import as a share of total home power flow. | Distribution ratios |
| Consumption share | % | Share of all grid throughput that is import vs. export. | Distribution shares |
| Cost rate | EUR/h | Current cost per hour of grid imports (live price × import power). | Cost — Standard |
| Total cost | EUR | Import cost integrated over time. | Accumulate costs |
| Export compensation rate | EUR/h | Money earned per hour from exports (export power × compensation rate). | Export compensation rate |
| Total export compensation | EUR | Export compensation integrated over time. | Accumulated export compensation |

---

## PV system

Per PV device. Export sensors require **Exports power to grid** to be on;
levelized sensors require lifetime values (an LCOE). See
[PV system configuration](configuration/pv.md).

### Real-time sensors

| Sensor | Unit | Meaning | Enabled by |
|---|---|---|---|
| Export power | W | Power from this system currently sent to the grid. | Distribution (W) · exports |
| Export ratio | % | Share of total home power flow that is this system's export. | Distribution ratios · exports |
| Export share | % | Share of this system's production that is exported. | Distribution shares · exports |
| Self-consumption power | W | Power from this system currently consumed in the home. | Distribution (W) |
| Self-consumption ratio | % | Share of total home power flow supplied by this system. | Distribution ratios |
| Self-consumption share | % | Share of this system's production consumed in the home. | Distribution shares |
| Export compensation rate | EUR/h | Money earned per hour exporting this system's power. | Export compensation rate · exports |
| Self-consumption cost savings rate | EUR/h | Money saved per hour by self-consuming this system's power. | Savings — Standard |
| Operating cost rate | EUR/h | Running operating cost per hour of this system. | Cost — Standard |
| Levelized operating cost rate | EUR/h | Operating cost rate using this system's LCOE. | Cost — Levelized · has lifetime values |
| Cost savings rate | EUR/h | Total money saved per hour by this system (self-consumption + export − costs). | Savings — Standard |
| Levelized cost savings rate | EUR/h | Savings rate computed with this system's LCOE. | Savings — Levelized · has lifetime values |

### Accumulated totals

| Sensor | Unit | Meaning | Enabled by |
|---|---|---|---|
| Total export compensation | EUR | Export compensation integrated over time. | Accumulated export compensation · exports |
| Total operating costs | EUR | Operating cost rate integrated over time. | Accumulate costs |
| Total levelized operating costs | EUR | Levelized operating cost integrated (retro-corrected). | Accumulate levelized costs · has lifetime values |
| Total self-consumption cost savings | EUR | Self-consumption savings integrated over time. | Accumulate savings |
| Total cost savings | EUR | Total savings integrated over time. | Accumulate savings |
| Total levelized cost savings | EUR | Levelized savings integrated (retro-corrected). | Accumulate levelized savings · has lifetime values |

---

## Battery

Per battery device. The battery has the **same sensor set as a PV system**
(above), reading the battery's own values, **plus** dynamic charging-source
sensors.

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
| Power source shares (one per source) | % | Share of this consumer's current power coming from each source (grid / solar / battery). | Power source shares |
| Operating cost rate | EUR/h | Current cost per hour to run this consumer, using the live grid price weighted by its source mix. | Cost — Standard |
| Levelized operating cost rate | EUR/h | As above, using each source's levelized cost per kWh. | Cost — Levelized |
