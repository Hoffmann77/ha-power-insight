# Core concepts

A short tour of the ideas Power Insight is built on. Understanding these makes
the sensors and options much easier to reason about.

## Sign conventions

Power Insight expects instantaneous power sensors with these signs:

| Device | Positive value means | Negative value means |
|---|---|---|
| **Grid** | Importing from the grid | Exporting to the grid |
| **PV** | Producing | Consuming (standby) |
| **Battery** | Discharging | Charging |

If a sensor uses the opposite sign, turn on **Invert power direction** on that
device. Power Insight normalises W / kW / MW automatically, so the unit itself
doesn't matter — only the sign.

## Gross power and the power split

The central quantity is **gross power**:

```
gross_power = grid_import + PV_production + battery_discharge
```

This is all the power entering your home right now. Power Insight splits it into
where it goes — **self-consumption**, **export** to the grid, battery
**charging**, and device **standby** — and exposes each slice in Watts, as a
**ratio** (% of gross power), and as a **share** (% of a device's own
throughput).

Every derived quantity is computed lazily from live values, and any sensor
whose inputs are unavailable simply reports *unavailable* rather than a wrong
number.

### The four channels

Gross power leaves the system through exactly four **channels**. Each channel
has a natural **sink** — the device type that receives that power:

| Abbrev | Channel | Sink device |
|---|---|---|
| **EXP** | Export | Grid |
| **CON** | Self-consumption | Consumers (loads) |
| **CHG** | Charging | Batteries |
| **STB** | Standby | PV systems (their own night draw) |

Every **provider** — the devices that *feed* gross power (grid import, PV
production, battery discharge) — expresses its relationship to a channel two
ways:

- **ratio** — of *this provider's own* output, the fraction going to the
  channel (`channel_power ÷ provider_output`).
- **share** — of *the whole channel's* power, the fraction *this provider*
  supplied (`provider_contribution ÷ channel_total`).

Not every provider feeds every channel. The grid cannot export to itself, so it
has no EXP sensors; otherwise each provider carries a `_ratio` and a `_share`
for each channel it can feed:

| Provider | EXP | CON | CHG | STB |
|---|:--:|:--:|:--:|:--:|
| **Grid** | — | ✓ | ✓ | ✓ |
| **PV** | ✓ | ✓ | ✓ | ✓ |
| **Battery** | ✓ | ✓ | ✓ | ✓ |

CHG is the only channel with explicit routing (a battery's **Charges from**
list), so it has **two complementary sensor families** — don't confuse them:

- the provider-side aggregate **Charging share** ("X % of *all* charging in the
  home is supplied by the grid"), on the grid/PV/battery device; and
- the sink-side per-source breakdown **Charging share from &lt;source&gt;**
  ("X % of *this battery's* charging comes from the grid"), on the battery — see
  [Charging-source attribution](#charging-source-attribution).

CHG sensors on a provider only appear when that provider is actually a
configured charge source for some battery; STB, having no routing, is
attributed to providers in proportion to their share of gross power.

## Cost of electricity (COE)

The **cost of electricity** is a blended per-kWh price across your whole energy
mix — what one kWh actually costs you right now, given how much is coming from
the grid vs. your own devices. Multiply it by power and you get a **cost rate**
(currency per hour); integrate that over time and you get a **total cost**.

There are two ways to price your *own* devices:

- **Standard** uses the live grid import price for everything — it answers "what
  would this power have cost if I'd bought it from the grid?"
- **Levelized** prices each device by its own lifetime cost per kWh (see below).

## LCOE (Levelized Cost of Electricity)

**LCOE** spreads a PV system's *total lifetime cost* across *all the energy it
produces over its life*:

```
LCOE = lifetime_cost / lifetime_production      (currency per kWh)
```

It answers "what does a kWh of my own solar really cost, once I account for what
the system cost me?" You provide `lifetime_cost` and `lifetime_production` per
device; Power Insight derives the LCOE. Levelized sensors only exist for devices
that have these values.

## LCOS (Levelized Cost of Storage)

**LCOS** is the battery equivalent of LCOE — the lifetime cost of the battery
spread across the energy it stores/delivers over its life. A battery's levelized
sensors use its LCOS in place of an LCOE.

!!! note
    Today LCOS is computed with the same `cost / throughput` formula as LCOE. A
    round-trip-efficiency-aware refinement is planned; the **Round-trip
    efficiency** field is already collected and used for charging-source
    attribution.

## The correction factor

Levelized values are recorded over time (in the accumulated totals). If you later
change a device's lifetime cost or production, its LCOE/LCOS changes — but you
don't want history to become inconsistent.

Power Insight solves this with a **correction factor**:

```
correction_factor = current_lcoe / default_lcoe
```

Because the factor is constant, multiplying a device's recorded base total by it
**retroactively and exactly rescales** all its displayed levelized values to the
new cost basis. When a device is removed, its final corrected contribution is
frozen into a ledger so the combined totals never drop.

This is why the reconfigure page warns:

> If you change the lifetime cost or lifetime production values, Power Insight
> applies a correction factor that retroactively rescales this device's
> already-recorded levelized values to stay consistent.

## Export compensation

**Export compensation** is what you are paid per kWh exported to the grid (your
feed-in tariff). It drives:

- **Export compensation rate** (currency/h) = current export power × the rate.
- **Accumulated export compensation** = that rate integrated over time.

## How savings are calculated

Power Insight recognises **two ways** your devices save you money:

1. **Export compensation** — selling surplus energy back to the grid.
2. **Self-consumption savings** — replacing energy you would otherwise have
   imported with energy from your own devices (valued at the grid price you
   avoided paying).

Total savings combine both and then **subtract the device's operating costs**:

```
savings = export_compensation + self_consumption_savings − operating_costs
```

For PV systems the main operating cost is standby consumption at night. For
batteries it's the cost of the energy used to charge them.

### Why does my battery have negative savings?

Any device can show negative savings if it doesn't earn enough to cover its
costs. Batteries specifically **always** show negative savings *while charging*,
because Power Insight tracks the cost of the energy going into the battery. That
cost is "paid back" as positive savings when the battery later discharges and
offsets a grid import. Over a full charge/discharge cycle the battery's net
contribution is what matters.

## Charging-source attribution

When a battery charges, its stored energy comes from some mix of the grid and
your PV systems — configured in the battery's **Charges from** list. Power
Insight traces that mix in real time to:

- attribute the battery's charging cost to the right source, and
- power the **charging source share** sensors ("70 % solar, 30 % grid").

The **round-trip efficiency** is used to account for the energy lost in a
charge/discharge cycle when attributing these costs.

## Scopes

Sensor selection is organised into **scopes**: the whole-home aggregate
(**combined**) plus one scope per device type (**grid**, **pv_system**,
**battery**, **consumer**). Each scope only offers the options its sensors
support, and a choice applies to *all* devices of that type. See
[Sensors, presets & options](configuration/options-and-presets.md).

## Accumulation

**Total** sensors integrate a rate (currency/h) over time using a left-Riemann
method, and persist their running total in Home Assistant's recorder so it
survives restarts. You can seed a starting value — for example to carry over
historical totals — with the [`power_insight.set_value` service](services.md).
