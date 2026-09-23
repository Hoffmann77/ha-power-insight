# Sensors, presets & options

Power Insight can create a lot of sensors. The **Options** flow lets you choose
exactly which ones exist — for the whole home and per device type.

Open it from **Settings → Devices & services → Power Insight → Configure**.

:::tip[Turning a sensor off never loses data]

Any sensors you turn off are **disabled** in Home Assistant, not deleted, so
historical data is preserved. You can re-enable them at any time.

:::

## Sensor sets

The quickest way to configure sensors is a sensor set, which applies the same
selection to all your devices at once:

| Sensor set | What it adds |
|---|---|
| **Minimal** | Power split (%), where each consumer's power comes from, and financial return (with running totals). |
| **Recommended** | Adds the power split in W, battery charging sources, and running totals for costs, savings and export compensation. |
| **Extended** | Adds live cost, savings and export compensation rates (per hour) and each device's share of the home totals. |
| **Custom** | Choose sensors per device type on the following pages. |

Each set builds on the previous one. **Recommended** suits most homes.
Levelized sensors in a set only appear for devices that have lifetime values.

## Custom: one page per device type

Choosing **Custom** walks you through one page per **scope** — the devices the
selection applies to. Only scopes you have devices for are shown.

| Scope | Applies to |
|---|---|
| **Combined** | Whole-home sensors, on the *Combined* device. |
| **Grid** | Your grid connection. |
| **PV system** | All PV systems. |
| **Battery** | All batteries. |
| **Consumer** | All consumers. |

Each page groups its options into sections. Which ones a page shows depends on
what its sensors support — see [the matrix below](#which-scope-offers-what).

### Power

- **Power split (W)** — where the power goes, in Watts. On a device: *Import /
  Production / Discharge to home consumption*, *to batteries*, *to system
  standby*, *to grid*. On *Combined*: *Home consumption power*, *Battery
  charging power*, *System standby power*. The grid also gets *Import power*
  and *Export power*.
- **Power split (%)** — the same split as a percentage of the device's own
  output (or, on *Combined*, of all power entering the home).
- **Share of home totals (%)** — how much of the home's consumption, battery
  charging, system standby and export this device supplies. On a consumer:
  its share of the home's total consumption.
- **Home base load** — a device for everything your home uses that has no
  sensor of its own. *(Combined only)*
- **Charging sources (%)** — how much of a battery's charging comes from each
  source. *(battery only)*
- **Power sources (%)** — how much of a consumer's power comes from each
  source. *(consumer only)*

See [Where a device's power goes](../entities.md) for how to read these names.

### Export compensation

- **Export compensation rate** — what the device currently earns per hour from
  exports.
- **Total export compensation** — running total of the export compensation
  earned.

### Costs

The **Cost method** controls whether and how cost sensors are created:

| Method | Meaning |
|---|---|
| **None** | No cost sensors. |
| **Standard** | Priced at the live grid price. Needs an electricity price sensor on your grid connection. |
| **Levelized** | Priced at each device's lifetime cost per kWh ([LCOE](../concepts.md#lcoe-levelized-cost-of-electricity) / [LCOS](../concepts.md#lcos-levelized-cost-of-storage)). Needs lifetime values. |
| **Both** | One sensor for each method. |

- **Total costs** — adds running totals that keep counting across restarts.

What "cost" means differs per device: the grid's *Import cost rate*, a PV
system's or battery's *Operating cost* (its own draw — standby, or charging),
and a consumer's *Operating cost* (running it, based on where its power comes
from).

:::info

Grid power has no levelized cost, so the **Grid** page only offers
**Standard**.

:::

### Savings

Savings are the money you did not pay the grid because your own devices
supplied the power. The **Savings method** works like the cost method, and
**Total savings** adds running totals. On a consumer, the same money appears as
its *Avoided cost* — don't add it to the producing devices' savings. See
[How savings are calculated](../concepts.md#how-savings-and-financial-return-are-calculated).

### Financial return

Savings plus export compensation (for a battery, minus what charging cost).
The **Financial return method** works like the cost method, and **Total
financial return** adds running totals.

## Which scope offers what

| Option | Combined | Grid | PV | Battery | Consumer |
|---|:---:|:---:|:---:|:---:|:---:|
| Power split (W) | ✅ | ✅ | ✅ | ✅ | — |
| Power split (%) | ✅ | ✅ | ✅ | ✅ | — |
| Share of home totals (%) | — | ✅ | ✅ | ✅ | ✅ |
| Home base load | ✅ | — | — | — | — |
| Charging sources (%) | — | — | — | ✅ | — |
| Power sources (%) | — | — | — | — | ✅ |
| Export compensation rate | — | ✅ | ✅ | ✅ | — |
| Total export compensation | — | ✅ | ✅ | ✅ | — |
| Cost method — Standard | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cost method — Levelized | ✅ | — | ✅ | ✅ | ✅ |
| Total costs | ✅ | ✅ | ✅ | ✅ | ✅ |
| Savings method — Standard | ✅ | — | ✅ | ✅ | ✅ |
| Savings method — Levelized | ✅ | — | ✅ | ✅ | — |
| Total savings | ✅ | — | ✅ | ✅ | ✅ |
| Financial return method — Standard | ✅ | — | ✅ | ✅ | — |
| Financial return method — Levelized | ✅ | — | ✅ | ✅ | — |
| Total financial return | ✅ | — | ✅ | ✅ | — |

*(Derived from `SCOPE_SUPPORTED_OPTIONS` in the integration; a ✅ means the
option is offered on that scope.)*

## Diagnostics

The first Options page also has a global toggle:

- **Debug sensors** — adds diagnostic sensors with the raw values used in the
  calculations. Leave off unless troubleshooting.

## Missing-data guard

If you enable an option that a device doesn't have the data for, the options
flow stops and tells you which devices need attention:

> These devices are missing values the selected sensors need: … Open
> **Reconfigure** on each device to add them (e.g. a price sensor for costs,
> lifetime values for levelized sensors), then save again.

Fix the devices (see [Configuration](index.md)) and save the options again.
