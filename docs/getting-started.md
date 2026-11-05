# Getting started

This page takes you from a fresh install to your first sensors in about ten
minutes. You'll need Power Insight [installed](installation.md) and a power
sensor for your grid connection.

:::tip[Two words you'll see]

Power Insight is a **hub**: one entry in Home Assistant for your home. Inside
it you add a **device** for your grid connection and for each PV system,
battery and consumer you want to track.

:::

## Step 1: Create the hub

Go to **Settings → Devices & services → Add integration**, search for
**Power Insight**, and fill in two fields:

- **Name**, for example "Home". It is put in front of every device and
  sensor name: a PV system called "Rooftop" gets sensors like *Home Rooftop
  Production to grid*.
- **Sensor set**, a ready-made selection of sensors. **Recommended** suits
  most homes; you can change it at any time. See
  [Sensor sets](sensor-options.md#sensor-sets) for what each one contains.

## Step 2: Add your grid connection

Open the Power Insight integration and choose **Add device → Grid
connection**. This one comes first: without it nothing can be calculated, and
Power Insight raises a repair issue until you add it.

- **Power sensor**: your grid meter's power. Positive while you buy from the
  grid, negative while you sell.
- **Electricity price**: a sensor or `input_number` with your price per kWh.
  Needed for every cost and savings sensor; leave it empty if you only care
  about power flow.

All settings are explained on [Grid connection](devices/grid.mdx).

## Step 3: Add your other devices

Use **Add device** again for each of these you have:

| Device | Add one for | Power sensor sign |
|---|---|---|
| [PV system](devices/pv.mdx) | each solar inverter | positive while producing |
| [Battery](devices/battery.mdx) | each home battery | positive while discharging, negative while charging |
| [Consumer](devices/consumer.mdx) | each appliance with its own power sensor, such as a heat pump, EV charger or smart plug | negative while drawing |

:::warning[Check the signs]

A sensor with the opposite sign makes the numbers look backwards: export
counted as import, charging as discharging. Turn on **Invert power sign** on
that device to fix it. Most smart plugs need this. See
[Sign conventions](how-it-works.md#sign-conventions).

:::

For levelized sensors, enter **Lifetime production** and **Lifetime cost** on
your PV systems and batteries; you can also add them later with
**Reconfigure**.

## Step 4: Look at your sensors

Each device now has its sensors in Home Assistant. Open a device to see them,
or put them on a dashboard. The [Sensor reference](sensors.mdx) explains
what each name means.

Want different sensors? Open the integration's **Configure** button to pick
another sensor set, or choose **Custom** to pick sensors per device type. See
[Sensor options & presets](sensor-options.md). Turning a sensor off keeps its
history, so you can safely experiment.

## Step 5 (optional): Bring in your history

Total sensors such as *Total cost savings* start at zero. If your PV system
or battery has been running for years, enter the totals from its app in the
device's **Already accumulated** section and your totals start where your
system really is. See [Carried-over history](advanced/history.md).
