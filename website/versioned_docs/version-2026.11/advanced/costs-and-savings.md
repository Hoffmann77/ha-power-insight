# Costs, savings and the maths

This page explains how Power Insight puts a price on power, for readers who
want the formulas behind the [cost and savings sensors](../sensors.mdx). For
the short version, see [How it works](../how-it-works.md).

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

:::note

LCOS is computed with the same `cost / throughput` formula as LCOE, where the
throughput is the energy the battery **discharges** over its life. That energy
is metered at the battery's AC port, so round-trip losses are already netted
out of it — which is why Power Insight asks for no efficiency figure.

:::

## The correction factor

Levelized values are recorded over time (in the accumulated totals). If you later
change a device's lifetime cost or production, its LCOE/LCOS changes — but you
don't want history to become inconsistent.

Power Insight solves this with a **correction factor**:

```
correction_factor = current_lcoe / default_lcoe
```

Because the factor is constant, multiplying the recorded base totals by it
**retroactively and exactly rescales** all the displayed levelized values to the
new cost basis. A total that mixes energy from several devices — a battery
charged from two PV systems, say — keeps a share per device, so each share is
rescaled by its own device's factor.

The correction reaches the device's **whole history** on purpose. LCOE and
LCOS are lifetime averages, so a revised lifetime cost or production is the
right price for energy already recorded too — whether the first estimate was
off, a repair added to the cost, or the device produces less than expected.
Two things follow:

- **The long-term statistics show the correction as one step** in the hour you
  made the edit; earlier statistics are not rewritten.
- **Replaced hardware is a new device.** New panels or a new battery have a
  lifetime of their own: add them as a new device and remove the old one
  rather than editing its lifetime values.

When a device is removed, its final corrected contribution is frozen into a
ledger so the combined totals never drop, and its share in other devices'
totals keeps its last factor.

This is why the reconfigure page warns:

> If you change the lifetime cost or lifetime production values, Power Insight
> applies a correction factor that retroactively rescales this device's
> already-recorded levelized values to stay consistent.

## Export compensation

**Export compensation** is what you are paid per kWh exported to the grid. It
drives:

- **Export compensation rate** (currency/h) = current export power × the rate.
- **Total export compensation** = that rate integrated over time.

## How savings and financial return are calculated

Power Insight tracks three related but distinct financial quantities:

**Cost savings** — the money you save by *not importing* power you would
otherwise have bought. Your own generation (PV, battery discharge) covers some
of your load; the savings are the grid price of that avoided import, minus the
operating cost of the device that provided it:

```
cost_savings = avoided_import_cost − operating_costs
```

For PV the main operating cost is standby consumption at night. For batteries it
is the cost of the energy used to charge them, adjusted for round-trip losses.

**Export compensation** — the revenue you earn from power exported to the
grid. This has its own dedicated sensors (see [Export compensation](#export-compensation)).

**Financial return** — the combined picture: savings plus export compensation.

```
financial_return = cost_savings + export_compensation
```

Use **cost savings** when you want to know how much you avoided spending. Use
**financial return** when you want one number that includes everything your
devices are earning for you.

### Why is my levelized financial return lower than my levelized savings?

In the levelized version, every kWh a device produces carries its lifetime
cost (LCOE for PV, LCOS for a battery) — the kWh it exports included. So the
levelized financial return also subtracts what the exported energy cost to
produce:

```
levelized_financial_return = levelized_cost_savings
                           + exported_kWh × (export_compensation − LCOE)
```

When your feed-in tariff is below the device's LCOE/LCOS, each exported kWh
loses money and the financial return ends up **below** the savings. That is
not an error: it tells you self-consumption pays for the device while
exporting does not. If you never export, the two are equal.

**Example.** A PV system with an LCOE of 0.10 sends 1 kWh into the home and
exports 1 kWh; the grid price is 0.30 and the feed-in tariff 0.08.

| Total | Calculation | Value |
|---|---|---|
| Levelized cost savings | 1 × (0.30 − 0.10) | **0.20** |
| Levelized financial return | 0.20 + 1 × (0.08 − 0.10) | **0.18** |

The standard (non-levelized) values treat your own generation as free, so
there the financial return is never below the savings.

### Why does my battery have negative cost savings?

Any device can show negative cost savings if it doesn't earn enough to cover its
costs. Batteries specifically **always** show negative cost savings *while
charging*, because Power Insight tracks the cost of the energy going into the
battery. That cost is "paid back" as positive savings when the battery later
discharges and offsets a grid import. Over a full charge/discharge cycle the
battery's net contribution is what matters.

## How totals are counted

**Total** sensors integrate a rate (currency/h) over time using a left-Riemann
method — each stretch of time is counted at the rate that held through it —
and persist their running total in Home Assistant's recorder so it survives
restarts. While a rate is unavailable (a meter has dropped out) the total
pauses, and it resumes when the meter reports again; the time in between is
not counted. There is no staleness timeout: a sensor that is still available
is trusted, even if it has not reported for a while. What a device earned before
Power Insight counted it can be carried over from its app, in the device's
**Already accumulated** section (see [Carried-over history](history.md)).
