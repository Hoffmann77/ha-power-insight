<div align="center">

<img src="custom_components/power_insight/brand/logo.png" alt="Power Insight" width="360">

# Power Insight for Home Assistant

**Real-time insight into the cost, savings, and distribution of the electrical power in your home.**

[![Marketplace](https://img.shields.io/badge/Marketplace-custom%20repository-41BDF5.svg?style=flat-square)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=Hoffmann77&repository=ha-power-insight&category=integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.11%2B-41BDF5.svg?style=flat-square)](https://www.home-assistant.io/)
[![Release](https://img.shields.io/github/v/release/Hoffmann77/ha-power-insight?include_prereleases&style=flat-square)](https://github.com/Hoffmann77/ha-power-insight/releases)
[![Tests](https://img.shields.io/github/actions/workflow/status/Hoffmann77/ha-power-insight/tests.yaml?branch=main&label=tests&style=flat-square)](https://github.com/Hoffmann77/ha-power-insight/actions/workflows/tests.yaml)
[![License](https://img.shields.io/github/license/Hoffmann77/ha-power-insight?style=flat-square)](LICENSE)

[**📖 Docs**](https://hoffmann77.github.io/ha-power-insight/) ·
[Installation](https://hoffmann77.github.io/ha-power-insight/installation/) ·
[Getting started](https://hoffmann77.github.io/ha-power-insight/getting-started/) ·
[Entities](https://hoffmann77.github.io/ha-power-insight/entities/) ·
[Concepts](https://hoffmann77.github.io/ha-power-insight/concepts/)

</div>

---

Power Insight tracks the real-time power flow, electricity costs, savings, and
CO₂ impact of your home's energy mix — grid, solar, batteries, and individual
consumers in one place.

Add your PV systems and batteries to see how much they impact the power in your
home, and add electrical consumers to get detailed insight into current and total
costs and the distribution of the energy sources they use.

Because every calculation is driven by **instantaneous power values**, Power
Insight works great with **dynamic electricity prices** — the numbers you see
always reflect the price you are paying right now.

> [!NOTE]
> Carbon-intensity / CO₂ tracking is planned but **not yet implemented**. The
> configuration flow may ask for a CO₂ intensity entity, but no CO₂ sensors are
> created yet.

> [!IMPORTANT]
> Power Insight is in an early development phase. Entity names and options may change
> until the 1.0 release. 

## ✨ Features

- **Power distribution** — how the power entering your home splits between grid
  import/export, self-consumption, battery charging, and PV standby — in Watts,
  ratios (%), and shares (%).
- **Cost of electricity** — a blended per-kWh price across your whole mix, plus
  real-time cost-rate sensors (€/h) and running totals.
- **Savings** — money earned by exporting surplus power, plus money avoided by
  self-consuming your own generation instead of importing.
- **Levelized costs (LCOE / LCOS)** — spread each device's total lifetime cost
  across every kWh it produces, to see the true cost of your own power.
- **Per-device attribution** — which source charged your battery, and which mix
  of grid/solar/battery is currently powering each consumer.
- **Presets** — pick Minimal / Recommended / Extended / All, or customize exactly
  which sensors get created per device type.

## 🚀 Quick start

1. **Install** from the Marketplace (Settings → Marketplace, Home Assistant
   2026.11 or newer) or manually —
   [installation guide](https://hoffmann77.github.io/ha-power-insight/installation/).
2. **Add the integration** (Settings → Devices & services → Add integration →
   Power Insight), give it a name, and pick a **sensor preset**.
3. **Add your devices** with the *Add device* button — start with your **grid
   connection**, then add PV systems, batteries, and consumers.
4. **Fine-tune the sensors** in the integration's *Options* at any time —
   [sensors, presets & options](https://hoffmann77.github.io/ha-power-insight/configuration/options-and-presets/).

## 📦 Installation

Power Insight needs **Home Assistant 2026.11** or newer.

### Marketplace (recommended)

Power Insight is installed through the Marketplace built into Home Assistant
(**Settings → Marketplace**). It is not in the catalog yet: this link opens it
in your Marketplace and offers to add it as a custom repository (needs a GitHub
connection):

[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=Hoffmann77&repository=ha-power-insight&category=integration)

Install it, then add the integration — no restart needed on a first install:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=power_insight)

Updates show up under **Settings → Updates**. Installed through HACS before?
The Marketplace takes it over on its own. Full steps (including manual
installation) are in the
[installation guide](https://hoffmann77.github.io/ha-power-insight/installation/).

## 🖼️ Screenshots

<!--
Screenshots go here. Drop images into docs/assets/ and reference them, e.g.:
![Dashboard](docs/assets/screenshot-dashboard.png)
-->

_Screenshots coming soon._

## 📖 Documentation

Full documentation is hosted at
**[hoffmann77.github.io/ha-power-insight](https://hoffmann77.github.io/ha-power-insight/)**:

| Section | What's inside |
|---|---|
| [Installation](https://hoffmann77.github.io/ha-power-insight/installation/) | Marketplace + manual install, updates, requirements |
| [Getting started](https://hoffmann77.github.io/ha-power-insight/getting-started/) | Create the hub, add devices, pick sensors |
| [Configuration](https://hoffmann77.github.io/ha-power-insight/configuration/) | Every setting for grid, PV, battery, consumer |
| [Sensors, presets & options](https://hoffmann77.github.io/ha-power-insight/configuration/options-and-presets/) | Choose exactly which sensors exist |
| [Entity reference](https://hoffmann77.github.io/ha-power-insight/entities/) | Every sensor Power Insight can create |
| [Core concepts](https://hoffmann77.github.io/ha-power-insight/concepts/) | LCOE/LCOS, sign conventions, how savings work |
| [Carried-over history](https://hoffmann77.github.io/ha-power-insight/history/) | Start your totals from what your app already shows |
| [FAQ](https://hoffmann77.github.io/ha-power-insight/faq/) | Common questions |

## ⚠️ Limitations

- **Instantaneous power sensors required.** Calculations use live power (W/kW/MW)
  readings, not energy meters. Each device and the grid must expose a power sensor.
- **One grid connection per entry.** Two grid connections are modelled as two
  config entries.
- **CO₂ / carbon intensity is not yet implemented.**
- **Consumer entities are still under development.**
- **Entity names may change** until the 1.0 release.

## 🤝 Contributing

Issues and pull requests are welcome — please use the
[issue tracker](https://github.com/Hoffmann77/ha-power-insight/issues).

Run the test suite with [uv](https://docs.astral.sh/uv/):

```bash
uv run pytest
```

Preview the documentation locally:

```bash
cd website
npm install
npm start
```

The docs are a [Docusaurus](https://docusaurus.io/) site: the prose lives in
`docs/` and the site machinery in `website/`. Pushes to `main` publish to GitHub
Pages via the Actions Pages source. See
[the docs publishing process](https://hoffmann77.github.io/ha-power-insight/dev/releasing).

## 📄 License

Released under the [Apache License 2.0](LICENSE).
