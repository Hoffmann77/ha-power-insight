<div align="center">

<img src="brand/logo.png" alt="Power Insight" width="360">

# Power Insight for Home Assistant

**Real-time insight into the cost, savings, and distribution of the electrical power in your home.**

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=flat-square)](https://hacs.xyz/)
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

1. **Install** via HACS (custom repository) or manually, then restart Home
   Assistant — [installation guide](https://hoffmann77.github.io/ha-power-insight/installation/).
2. **Add the integration** (Settings → Devices & services → Add integration →
   Power Insight), give it a name, and pick a **sensor preset**.
3. **Add your devices** with the *Add device* button — start with your **grid
   connection**, then add PV systems, batteries, and consumers.
4. **Fine-tune the sensors** in the integration's *Options* at any time —
   [sensors, presets & options](https://hoffmann77.github.io/ha-power-insight/configuration/options-and-presets/).

## 📦 Installation

### HACS (recommended)

If you don't have HACS yet, see the [HACS docs](https://hacs.xyz). Power Insight
is not in the default store yet, so add it as a **custom repository**:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Hoffmann77&repository=ha-power-insight&category=Integration)

Then restart Home Assistant and add the integration:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=power_insight)

Full steps (including manual installation) are in the
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
| [Installation](https://hoffmann77.github.io/ha-power-insight/installation/) | HACS + manual install, requirements |
| [Getting started](https://hoffmann77.github.io/ha-power-insight/getting-started/) | Create the hub, add devices, pick sensors |
| [Configuration](https://hoffmann77.github.io/ha-power-insight/configuration/) | Every setting for grid, PV, battery, consumer |
| [Sensors, presets & options](https://hoffmann77.github.io/ha-power-insight/configuration/options-and-presets/) | Choose exactly which sensors exist |
| [Entity reference](https://hoffmann77.github.io/ha-power-insight/entities/) | Every sensor Power Insight can create |
| [Core concepts](https://hoffmann77.github.io/ha-power-insight/concepts/) | LCOE/LCOS, sign conventions, how savings work |
| [Services](https://hoffmann77.github.io/ha-power-insight/services/) | `power_insight.set_value` |
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
pip install -r docs/requirements.txt
mkdocs serve
```

## 📄 License

Released under the [MIT License](LICENSE).
