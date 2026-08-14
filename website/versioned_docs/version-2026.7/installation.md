# Installation

Power Insight is a [Home Assistant](https://www.home-assistant.io/) custom
integration. It ships as the `power_insight` custom component and is distributed
through [HACS](https://hacs.xyz/).

## Install with HACS (recommended)

If you do not have HACS installed yet, follow the
[HACS installation guide](https://hacs.xyz/docs/use/download/download/) first.

Because Power Insight is not (yet) part of the default HACS store, add it as a
**custom repository**:

1. Open **HACS** in Home Assistant.
2. Click the **⋮** (three dots) menu in the top-right corner and choose
   **Custom repositories**.
3. Enter the repository URL `https://github.com/Hoffmann77/ha-power-insight`
   and select the **Integration** category, then click **Add**.
4. Search for **Power Insight** in HACS and download it.
5. **Restart Home Assistant.**

Or use the My Home Assistant link to jump straight to the repository in HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Hoffmann77&repository=ha-power-insight&category=Integration)

## Manual installation

1. Download the latest release (or the ZIP of the repository) from
   [GitHub](https://github.com/Hoffmann77/ha-power-insight).
2. Copy the `custom_components/power_insight/` folder into the
   `custom_components/` directory of your Home Assistant configuration —
   typically `/config/custom_components/power_insight/`.
3. **Restart Home Assistant.**

## Add the integration

After restarting:

1. Go to **Settings → Devices & services**.
2. Click **Add integration** and search for **Power Insight**.
3. Select it to start the setup flow.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=power_insight)

Continue with **[Getting started](getting-started.md)** to configure your energy
mix.

## Requirements

- Home Assistant with the [Recorder](https://www.home-assistant.io/integrations/recorder/)
  enabled (default) — accumulated total sensors store their running total in the
  recorder and restore it across restarts.
- An **instantaneous power sensor** (W, kW or MW) for your grid connection and
  for each PV system, battery, and consumer you want to track.
- For cost and savings sensors: a **grid electricity price** entity (a `sensor`
  or `input_number`) reporting the current import price per kWh.
