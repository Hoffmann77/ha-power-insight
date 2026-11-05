# How it works

Power Insight needs no extra hardware and no energy meters. It watches the
**power sensors** you already have, recalculates whenever one of them
changes, and turns the result into sensors. This page explains the ideas behind those
sensors without the formulas; the [Advanced](#going-deeper) pages have the
full details.

## What goes in

For every device you add, Power Insight reads **one power sensor** (in W, kW
or MW) that tells it how much power flows right now. For anything to do with
money it also reads your **electricity price** (a sensor or an
`input_number`), plus a few numbers you type in once, such as what you are
paid for exports or what your solar system cost.

Because it only ever uses the **current** power and the **current** price,
dynamic tariffs work out of the box: every second is priced at the price that
held during that second.

## Sign conventions

Every power sensor needs to say which way the power flows. Power Insight
expects these signs:

| Device | Positive means | Negative means |
|---|---|---|
| **Grid** | buying from the grid | selling to the grid |
| **PV system** | producing | drawing power (inverter standby) |
| **Battery** | discharging | charging |
| **Consumer** | — | drawing power |

Most smart plugs report their draw as a positive number. If one of your
sensors uses the opposite sign, turn on **Invert power sign** for that
device. The unit doesn't matter: W, kW and MW are all converted.

## Following the power

At any moment, power **comes in** from three kinds of source:

- the **grid** (what you buy),
- your **PV systems** (what they produce),
- your **batteries** (what they discharge).

It **goes out** to four places:

- **home consumption**: your appliances,
- **batteries**: charging,
- **system standby**: the idle draw of your energy equipment, such as an
  inverter at night,
- the **grid**: export.

What comes in always equals what goes out. Power Insight works out, for every
source, how much of its power ends up in each destination. That is what the
*… to home consumption*, *… to grid* and similar sensors show. The
[sensor reference](sensors.mdx#reading-the-sensor-names) explains how to read
their names.

**Example.** The sun produces 3,000 W, the house uses 1,000 W and the battery
charges at 1,500 W. The remaining 500 W go to the grid. The PV system's
*Production to home consumption* reads 1,000 W, *Production to batteries*
1,500 W and *Production to grid* 500 W.

When a battery or consumer may only use **specific sources**, for example a
battery that charges from solar only, Power Insight respects that when
splitting the power. [Where the power comes from](advanced/power-attribution.md)
explains the rules.

## Putting a price on it

Once Power Insight knows where every watt comes from, it can price it. There
are two ways to do that, and you choose which one you want in the options.

**Standard** uses your **grid price**. Power from the grid costs what you
pay for it; power from your own solar and batteries counts as **free**. This
answers the everyday question: *how much is my solar saving me on my
electricity bill?*

**Levelized** also counts what your **hardware** cost. You enter what a
device cost over its lifetime (purchase, installation, maintenance) and how
much energy it will deliver over that lifetime. Dividing one by the other
gives a price per kWh for your own power, the
[LCOE](glossary.md#lcoe) for solar or [LCOS](glossary.md#lcos) for a
battery. This answers the investor's question: *is my solar system actually
paying off?*

**Example.** Grid power costs 0.30 per kWh. Your solar system cost 12,000 and
will produce 120,000 kWh over 25 years, so its LCOE is 0.10 per kWh. Every
kWh of solar you use yourself saves **0.30** (Standard), or **0.20** once the
hardware is paid for (Levelized).

## Costs, savings and earnings

From those prices Power Insight builds a few kinds of money sensor:

| | What it means |
|---|---|
| **Cost** | What running something costs, such as your home, a consumer, or a battery's charging. |
| **Avoided cost** | What your own power kept off your grid bill. |
| **Cost savings** | Avoided cost minus what the device costs to run. |
| **Export compensation** | What you are paid for power you export. |
| **Financial return** | Cost savings **plus** export compensation: everything a device brings in. |

A battery's savings go **negative while it charges** from the grid: that
energy costs money. They turn positive when it discharges and replaces grid
power. Over a full cycle, the total is what counts.

## Rates and totals

Money sensors come in pairs:

- A **rate** is money **per hour, right now** (`EUR/h`), like a speedometer.
- A **total** adds the rate up over time (`EUR`), like an odometer. Totals
  survive restarts and work with Home Assistant's long-term statistics and
  utility meters.

If a power or price sensor becomes unavailable, the rates show
*unavailable* rather than a wrong number, and the totals pause until it
comes back. Power Insight never guesses.

Already have years of history in your inverter's app? You can
[carry it over](advanced/history.md) so your totals start where your system
really is.

## Going deeper

- [Costs, savings and the maths](advanced/costs-and-savings.md): the
  formulas behind the cost and savings sensors, LCOE and LCOS, and what
  happens when you change a device's lifetime values.
- [Where the power comes from](advanced/power-attribution.md): the four flow
  channels, *ratio* vs. *share*, and how a battery's or consumer's source mix
  is decided.
- [Carried-over history](advanced/history.md): bringing your existing totals
  into Power Insight.
- [Glossary](glossary.md): every term on one page.
- [Reference cases](spec/index.mdx): worked example homes with flow diagrams.
