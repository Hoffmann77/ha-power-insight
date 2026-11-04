# Installation

Power Insight is a [Home Assistant](https://www.home-assistant.io/) custom
integration. It ships as the `power_insight` custom component and is installed
through the **Marketplace**, built into Home Assistant since 2026.11 under
**Settings → Marketplace**.

:::info[Home Assistant 2026.11 or newer]
This release needs Home Assistant 2026.11.0 or newer. On an older Home
Assistant the Marketplace offers you the last release that still works with
it.
:::

## Install from the Marketplace (recommended)

Power Insight is not in the Marketplace catalog yet, so add it from its link.
The link opens the repository in the Marketplace of your own Home Assistant,
and offers to add it as a custom repository first. Adding a custom repository
needs a GitHub connection.

[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=Hoffmann77&repository=ha-power-insight&category=integration)

1. Click the button above, and confirm your Home Assistant instance if asked.
2. Add **Power Insight** as a custom repository when the Marketplace offers to.
3. Install it.

Power Insight has a config flow, so a first install loads right away: no
restart needed, continue with [Add the integration](#add-the-integration).

### Updates

New releases show up under **Settings → Updates**, next to the updates of Home
Assistant itself, with the release notes. Anything you have to do before
updating is at the top of those notes. After an update, the Marketplace raises a
repair with a button to restart Home Assistant, which loads the new version.

### Coming from HACS

If you installed Power Insight through HACS, there is nothing to do. On the
first start after updating to Home Assistant 2026.11 the Marketplace takes over
your HACS installation, including Power Insight and its update entity.

## Manual installation

1. Download the latest release from
   [GitHub](https://github.com/Hoffmann77/ha-power-insight/releases).
2. Copy the `custom_components/power_insight/` folder into the
   `custom_components/` directory of your Home Assistant configuration —
   typically `/config/custom_components/power_insight/`.
3. **Restart Home Assistant.**

A manual install gets no update notifications: repeat these steps for each new
release.

## Add the integration

1. Go to **Settings → Devices & services**.
2. Click **Add integration** and search for **Power Insight**.
3. Select it to start the setup flow.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=power_insight)

Continue with **[Getting started](getting-started.md)** to configure your energy
mix.

## Requirements

- Home Assistant **2026.11** or newer.
- The [Recorder](https://www.home-assistant.io/integrations/recorder/)
  enabled (default) — accumulated total sensors store their running total in the
  recorder and restore it across restarts.
- An **instantaneous power sensor** (W, kW or MW) for your grid connection and
  for each PV system, battery, and consumer you want to track.
- For cost and savings sensors: a **grid electricity price** entity (a `sensor`
  or `input_number`) reporting the current import price per kWh.
