---
title: Power Insight for Home Assistant
---

# Power Insight

<p align="center">
  <img src="assets/logo.png" alt="Power Insight" width="320">
</p>

**Real-time insight into the cost, savings, and distribution of the electrical
power in your home.**

Power Insight tracks the real-time power flow, electricity costs, savings, and
CO₂ impact of your home's energy mix — grid, solar, batteries, and individual
consumers in one place.

Add your PV systems and batteries to see how much they impact the power in your
home, and add electrical consumers to get detailed insight into current and
total costs and the distribution of the energy sources they use.

Because every calculation is driven by **instantaneous power values**, Power
Insight works great with **dynamic electricity prices** — the numbers you see
always reflect the price you are paying right now.

!!! note "CO₂ tracking is not available yet"
    Carbon-intensity / CO₂ tracking is planned but not yet implemented in this
    release. The configuration flow may ask for a CO₂ intensity entity or a CO₂
    footprint, but **no CO₂ sensors are created yet**.

!!! warning "Beta software"
    Power Insight is in beta (`0.1.0b1`). Entity names and options may change
    until the 1.0 release.

## What you get

- **Power distribution** — how the power entering your home splits between grid
  import/export, self-consumption, battery charging, and PV standby, in Watts,
  ratios (%), and shares (%).
- **Cost of electricity** — a blended per-kWh price across your whole energy
  mix, plus real-time cost-rate sensors (€/h) and running totals.
- **Savings** — money earned by exporting surplus power to the grid, plus money
  avoided by self-consuming your own generation instead of importing.
- **Levelized costs (LCOE / LCOS)** — spread each device's total lifetime cost
  across every kWh it produces, so you can see the true cost of your own power.
- **Per-device attribution** — which source charged your battery, and which mix
  of grid/solar/battery is currently powering each consumer.

## How to read these docs

<div class="grid cards" markdown>

- :material-download: **[Installation](installation.md)**
  Install via HACS (recommended) or manually.

- :material-rocket-launch: **[Getting started](getting-started.md)**
  Name the hub, pick a preset, add your devices.

- :material-cog: **[Configuration](configuration/index.md)**
  Every setting for the grid, PV, battery, and consumer devices.

- :material-tune-variant: **[Sensors, presets & options](configuration/options-and-presets.md)**
  Choose exactly which sensors get created.

- :material-format-list-bulleted: **[Entity reference](entities.md)**
  The full, accurate list of every sensor Power Insight can create.

- :material-lightbulb-on: **[Core concepts](concepts.md)**
  LCOE/LCOS, sign conventions, how savings are calculated.

</div>

## Limitations

- **Instantaneous power sensors required.** Calculations are driven by live
  power (W/kW/MW) readings, not energy meters. Each PV system, battery, consumer
  and the grid connection must expose a power sensor.
- **One grid connection per entry.** A config entry models a single grid
  connection / energy mix. Two grid connections are modelled as two config
  entries.
- **CO₂ / carbon intensity is not yet implemented.** See the note above.
- **Consumer entities are still under development.**
- **Entity names may change** until the 1.0 release.
