# Sensors, presets & options

Power Insight can create a lot of sensors. The **Options** flow lets you choose
exactly which ones exist — for the whole home and per device type.

Open it from **Settings → Devices & services → Power Insight → Configure**.

!!! tip "Turning a sensor off never loses data"
    Any sensors you turn off are **disabled** in Home Assistant, not deleted, so
    historical data is preserved. You can re-enable them at any time.

## Presets

The quickest way to configure sensors is a preset, which applies the same
selection to all your devices instantly:

| Preset | What it adds |
|---|---|
| **Minimal** | Power distribution and cost-savings sensors only. |
| **Recommended** | Adds ratios, export compensation, and source-attribution sensors. |
| **Extended** | Also adds real-time electricity cost-rate sensors. |
| **All** | Also adds levelized cost sensors (requires lifetime values per device). |
| **Custom** | Configure each device type individually on the following pages. |

Each preset builds on the previous one. **Recommended** is the sweet spot for
most installations.

## Custom mode: per-scope configuration

Choosing **Custom** walks you through one page per **scope** — a device class the
selection applies to. Only scopes that apply to you are shown.

| Scope | Applies to |
|---|---|
| **Combined** | Whole-home aggregate sensors (the hub). |
| **Grid** | Your single grid connection (import + export). |
| **PV system** | All PV system devices. |
| **Battery** | All battery devices. |
| **Consumer** | All consumer devices. |

Each page groups its options into friendly **categories**. Which categories a
scope shows depends on what its sensors support.

### Power sensors

- **Power distribution (W)** — one sensor per power-flow type (self-consumption,
  import, export, charging, standby, …) in Watts. These are the fundamental
  building blocks other sensors are derived from.
- **Power distribution ratios (%)** — each power flow as a share of total home
  power (e.g. "65 % of my home load comes from solar").
- **Power distribution shares (%)** — how a device's own throughput splits (e.g.
  "60 % of my solar output is self-consumed, 40 % exported"). *(grid / PV /
  battery)*
- **Charging source shares (%)** — how much of a battery's current charging power
  comes from each configured source. *(battery only)*
- **Power source shares (%)** — what fraction of a consumer's power currently
  comes from each source. *(consumer only)*

### Export compensation

- **Export compensation rate (per hour)** — a real-time sensor (currency/h)
  showing how fast you are earning from exported power (current export power × the
  device's export compensation rate).
- **Accumulated export compensation** — a running total of all export
  compensation earned.

### Electricity costs

The **Cost calculation method** select controls whether and how cost sensors are
created:

| Method | Meaning |
|---|---|
| **None** | No cost sensors created. |
| **Standard** | Cost using the live grid import price per kWh. Requires a price entity on the grid adapter. |
| **Levelized** | Cost using each device's lifetime cost per kWh ([LCOE](../concepts.md#lcoe-levelized-cost-of-electricity) / [LCOS](../concepts.md#lcos-levelized-cost-of-storage)). Requires lifetime values per device. |
| **Both** | Creates a pair of sensors, one per method. |

- **Accumulate costs** — adds sensors that sum cost over time (running total,
  stored in the recorder, survives restarts).

!!! info
    Grid electricity has no levelized cost — the **Grid** scope only offers the
    **Standard** method.

### Cost savings

Savings measure the money you avoid spending on grid electricity by
self-consuming your own generation (or discharging your battery) instead of
importing.

The **Savings calculation method** select works the same way (None / Standard /
Levelized / Both), and **Accumulate savings** adds running-total sensors. Savings
is not offered on the grid scope. See
[How savings are calculated](../concepts.md#how-savings-are-calculated).

## Which scope offers which categories

| Category | Combined | Grid | PV | Battery | Consumer |
|---|:---:|:---:|:---:|:---:|:---:|
| Power distribution (W) | ✅ | ✅ | ✅ | ✅ | — |
| Power distribution ratios (%) | ✅ | ✅ | ✅ | ✅ | — |
| Power distribution shares (%) | — | ✅ | ✅ | ✅ | — |
| Charging source shares (%) | — | — | — | ✅ | — |
| Power source shares (%) | — | — | — | — | ✅ |
| Export compensation rate | — | ✅ | ✅ | ✅ | — |
| Accumulated export compensation | — | ✅ | ✅ | ✅ | — |
| Cost method — Standard | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cost method — Levelized | ✅ | — | ✅ | ✅ | ✅ |
| Accumulate costs | ✅ | ✅ | ✅ | ✅ | — |
| Savings method — Standard | ✅ | — | ✅ | ✅ | — |
| Savings method — Levelized | ✅ | — | ✅ | ✅ | — |
| Accumulate savings | ✅ | — | ✅ | ✅ | — |

*(Derived from `SCOPE_SUPPORTED_OPTIONS` in the integration; a ✅ means the
category is offered on that scope.)*

## Diagnostics

The Options **init** page also has a global toggle:

- **Enable debug power entities** — exposes the raw internal power values used
  for calculations as additional sensors. Useful for diagnosing unexpected
  readings; leave off unless troubleshooting.

## Missing-data guard

If you enable an option that a device doesn't have the data for, the options flow
stops and tells you which devices need attention:

> These devices are missing data required by your selection: … Open each device's
> **Reconfigure** page to supply the missing values (for example, an electricity
> price entity for cost sensors, or lifetime production and cost for levelized
> sensors), then save the options again.

Fix the devices (see [Configuration](index.md)) and save the options again.
