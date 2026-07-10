# Power Insight for Home Assistant

**A custom component that provides useful insights about the electrical power in your home.**

Get useful insights about the cost of electricity, savings and power distribution in your home.

Add your PV systems and energy storages to see how much they impact the power in your home. In addition you can add electrical consumers to get detailed insights about the current and total costs and the distribution of used energy sources.

Track the power, price, and cost of your energy mix in real time.

By using instantaneous values for calculation this component works great with dynamic electricity prices.

> [!NOTE]
> Carbon-intensity / CO₂ tracking is planned but not yet available in this
> release. The configuration flow may ask for a CO₂ intensity entity, but no
> CO₂ sensors are created yet.

See below for a full list of entities provided by this component.

## Installation
### Install using HACS (recommended)
If you do not have HACS installed yet visit https://hacs.xyz for installation instructions.

To add the this repository to HACS in your Home Assistant instance, use this Button:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Hoffmann77&repository=ha-power-insight&category=Integration)

After installation, please restart Home Assistant. To add Power Insight to your Home Assistant instance, use this Button:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=power_insight)

<details>
<summary>Manual configuration steps</summary>

### Semi-Manual Installation with HACS
1. Go HACS integrations section.
2. Click on the 3 dots in the top right corner.
3. Select "Custom repositories"
4. Add the URL (https://github.com/hoffmann77/ha-power-insight) to the repository.
5. Select the integration category.
6. Click the "ADD" button.
7. Now you are able to download the integration

## Manual Installation
1. Access the GitHub repository for this integration.
2. Download the ZIP file of the repository and extract its contents.
3. Copy the "power_insight" folder into the custom_components directory located typically at /config/custom_components/ in your Home Assistant directory.

## Restart Home Assistant
1. Restart your Home Assistant.

## Add Integration
1. Navigate to Settings > Devices & Services.
2. Click Add Integration and search for "Power Insight".
3. Select the Power Insight integration to initiate setup.

</details>



## Limitations
- **Instantaneous power sensors required.** Calculations are driven by live power (W/kW) readings, not energy meters. Each PV system, battery, consumer and the grid connection must expose a power sensor.
- **One grid connection per entry.** A config entry models a single grid connection / energy mix. Multiple grid connections are modelled as multiple config entries.
- **CO₂ / carbon intensity is not yet implemented.** See the note at the top of this README.
- **Consumer entities are still under development.** See below.
- **Entity names may change** until the 1.0 release.

## Entities

> [!WARNING]
> Please note that entity names can be subject to changes until the release of version 1.0.

**Power Insight entities:**

| Entitiy | Description |
| ---- | ---- |
| `Available power`| Diagnostic sensor: the amount of generated/imported power not currently consumed in the home (W). Disabled by default. |
| `Cost of electricity`| Current blended cost of one kWh across your whole energy mix — grid plus your own devices (EUR/kWh). |
| `Electricity price`| Current price you pay for one kWh imported from the grid (EUR/kWh). |
| `Export compensation rate`| Money earned per hour from exporting surplus power to the grid (EUR/h). |
| `Export share`| Share of the total power exported to the grid that this energy mix contributes (%). |
| `Levelized cost of electricity`| Like *Cost of electricity*, but each device's cost is its levelized lifetime cost rather than only its running cost (EUR/kWh). |
| `Levelized electricity price`| Price of one kWh of your mix computed with levelized device costs (EUR/kWh). |
| `Savings rate`| Money saved per hour by self-consuming and exporting your own generation instead of importing (EUR/h). |
| `Levelized savings rate`| *Savings rate* computed with levelized device costs (EUR/h). |
| `Operating costs rate`| Running cost per hour of your current energy mix (EUR/h). |
| `Levelized operating costs rate`| *Operating costs rate* computed with levelized device costs (EUR/h). |
| `Self consumption power`| Amount of power generated or imported that is self consumed by the home (W). |
| `Self consumption share`| Share of the power consumed in your home that is supplied by your own generation/storage (%). |
| `Self consumption savings rate`| Money saved per hour by consuming your own generation instead of importing it (EUR/h). |

> [!NOTE]
> Which of these entities are created depends on the options you enable per
> scope (combined / grid / PV / battery / consumer). Accumulated (total) sensors
> integrate the matching rate over time; you can seed their starting value with
> the `power_insight.set_value` service.



**PV-System and Battery entities:**

| Entitiy | Enabled | Description |
| ---- | :----: | ---- |
| `Export power`| Yes | Amount of power generated by this device that is returned to the grid. <br/> *How much power generated by the device is returned to the grid.* |
| `Export rate` | Yes | Fraction of power generated by the device that is returned to the grid. <br/> *How much % of the total power generated by the device is returned to the grid.* |
| `Export share` | Yes | Fraction of total power returned to the grid that is generated by the device. <br/> *How much % of the total power returned to the grid is generated by the device* |
| `Export compensation rate` | Yes | The product of the configured export compensation and `Export power`. <br/> *At which rate is the device earning money by returning power to the grid.* |
| `Total export compensation` | Yes | Value of  `Export compensation rate` integrated over time. <br/> *How much money did the device earn you by returning power to the grid.* |
| `Self-consumption power`| Yes | Amount of power generated by this device that is consumed by the electrical consumers in your home. <br/> *How much power generated by the device is consumed by the electrical consumers in your home.* |
| `Self-consumption rate` | Yes | Fraction of power generated by the device that is consumed by the electrical consumers in your home. <br/> *How much % of the total power generated by the device is consumed by the electrical consumers in your home.* |
| `Self-consumption share` | Yes | Fraction of total power consumed by the electrical consumers in your home that is generated by the device. <br/> *How much % of the total power consumed by the electrical consumers in your home is generated by the device* |

**Consumer entities:**
> [!NOTE]
> Coming soon. These entities are currently under development.

## Frequently asked questions:

How are the savings calculated:
We consider two ways The devices can generate savings. The first way is accomplished by selling surplus energy to the grid.
The second way is accomplished by replacing energy that would need to be imported from the grid with energy generated by your devices.
To get the savings we add the savings generated by selling to the grid (export compensation) and the savings generated by replacing grid energy (self consumption savings) and subtract the costs the devices accumulate. For PV-Systems this is mainly the standby consumption during nights. For Energy storages this is the consumption associated with the charging of the device.

Why does my Battery have negative savings.
First of all all devices can have negative savings if they don't generate enough money to cover the costs. This can also be the case for batteries. Nevertheless energy storages always have negative savings when charging. We track the costs of the energy storage during charging.








