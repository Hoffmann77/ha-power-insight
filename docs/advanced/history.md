# Carried-over history

Power Insight starts counting when you add a device, but your PV system or
battery has probably been running for years. Its app or web portal knows what
happened since: how much was produced, exported, charged and discharged, and
often how much you saved. Enter those figures and your running totals start
where your system really is, not at zero.

:::tip[In short]

1. Open your PV system's or battery's app and note its totals: what it
   produced, exported, charged and discharged.
2. Enter them in the device's **Already accumulated: energy (kWh)** section.
3. Enter your **Average grid tariff** once, on the grid connection.

Everything below explains the details; you only need it if the form refuses
your figures or the totals look surprising.

:::

## Where to enter it

Every grid, PV system and battery form ends in two optional **Already
accumulated** sections, one for each route:

- **When you add a device.** Power Insight starts counting when you finish
  the form, so enter your app's totals up to now.
- **Later, under the device's Reconfigure page.** The form shows since when
  the device has been counted: *"Power Insight has counted this device since
  2026-08-14 10:32."* Enter your app's totals up to that moment, so nothing
  is counted twice.

Every field is optional. Leave both sections empty and nothing changes.

## Two routes

| Route | Section | You enter | Power Insight |
| --- | --- | --- | --- |
| **1. Energy** | *Already accumulated: energy (kWh)* | the kWh your app shows, and the average prices | calculates the money, the same way it does for everything it counts |
| **2. Amounts** | *Already accumulated: amounts* | the money your app shows | takes it as it is |

Use either route, or both: an amount from route 2 replaces the one route 1
would calculate. Route 1 is the better one where you can: its levelized
figures follow a later change of a device's lifetime cost, and it gives
amounts route 2 cannot, such as a battery's operating cost.

### Route 1: energy (kWh)

| Device | Figures |
| --- | --- |
| **Grid** (the whole home) | *Exported to the grid* — your grid meter's total export. *Average grid tariff* — what a kWh from the grid cost on average over that period. |
| **PV system** | *Produced* — everything it produced, including what went into a battery or the grid. |
| **Battery** | *Charged*, *Discharged*, and *Of which from the grid* (leave empty unless your battery charges from the grid). |

:::tip[Your savings need an average grid tariff]

A PV system's and a battery's savings are the energy they delivered into your
home, valued at the **Average grid tariff**. You can enter it in two places:

| Where | What it is | When to use it |
| --- | --- | --- |
| **On the grid** | the whole home's average, used for every PV system and battery without a tariff of its own | usually: enter it once, here |
| **On a PV system or battery** | that device's average; it replaces the grid's for that device | only if the device's period had a different average, for example a device added later |

Without either, a device's savings carry nothing and say `no_tariff`; its
export compensation, which only needs the export compensation per kWh, still
carries its part. Home Assistant then also shows a **repair** (Settings →
System → Repairs) naming the devices and pointing to the grid; it goes away
once every device has a tariff.

:::

:::tip[Why "Produced" and not "self-consumption"?]

Apps disagree on what self-consumption means: some include the energy that
went into a battery, some the energy that came back out of it. Power Insight
credits PV energy that charges a battery to the **battery**, when it
discharges into your home; the battery pays the PV system what the energy
would have earned otherwise. Counting the energy for the PV system as well
would count it twice. *Produced* and *exported* mean the same in every app, so Power
Insight works out the rest itself.

:::

Optional in route 1:

- **Own export to the grid** (PV system, battery) — what this device exported
  itself, if you know it, for example from the grid operator's annual
  statement for one installation. It is used as entered, and only the rest of
  the home's export is split between the other devices.
- **Average export compensation per kWh** — leave it empty to use the
  device's configured export compensation.

### Route 2: amounts

- **Savings**, **Export compensation** (PV system, battery) — the amounts your
  app shows, taken as they are.
- **Levelized savings** — only needed when you enter amounts and no kWh.
- **Total savings**, **Total export compensation** (grid) — your app's
  figures for the whole home. They are split between the devices: savings in
  proportion to each device's calculated savings, export compensation in
  proportion to what each exported.

## How the kWh become money

The history follows the same rules as everything Power Insight counts:

| Energy | Credited to | Saves |
| --- | --- | --- |
| PV → home | the PV system | the grid tariff |
| PV → grid | the PV system | the export compensation |
| PV → battery | the battery, when it discharges | the battery pays the PV system its export compensation (nothing if it may not export) |
| Battery → home | the battery | the grid tariff |
| Grid → battery | the battery | costs the grid tariff |

The payment for stored PV energy follows
[the rule for live readings](costs-and-savings.md#what-a-battery-pays-for-the-solar-energy-it-stores)
with one price. Your app's totals cannot tell when the home was buying from
the grid while the battery charged, so the history assumes the most common
case: the energy would have been exported. What the battery pays, the PV
system earns, so the combined savings stay the same.

**Example.** Your PV system produced 10,000 kWh; 4,000 kWh were exported; your
battery charged 2,500 kWh from the PV system and discharged 2,200 kWh; a kWh
from the grid cost 0.34 on average and export paid 0.08.

| | PV system | Battery |
| --- | --- | --- |
| Energy into the home | 10,000 − 4,000 − 2,500 = 3,500 kWh | 2,200 kWh |
| Total avoided cost | 3,500 × 0.34 = **1,190.00** | 2,200 × 0.34 = **748.00** |
| Stored PV energy | earns 2,500 × 0.08 = 200.00 | pays 200.00 |
| Total cost savings | 1,190 + 200 = **1,390.00** | 748 − 200 = **548.00** |
| Total export compensation | 4,000 × 0.08 = **320.00** | — |

*Total avoided cost* is what a device's energy into your home saved at the
grid tariff, before anything it paid. Had the battery charged 500 kWh from
the grid, it would have paid 500 × 0.34 = 170 for those and 2,000 × 0.08 =
160 for its PV energy: savings 748 − 170 − 160 = 418.00, avoided cost still
748.00. A battery entered as amounts only carries no avoided cost
(`no_energy`): its savings already have its grid charging taken off, and
without the kWh there is no telling how much.

If you enter a device's **Savings** amount yourself, it is taken as it is,
and neither that device nor the ones it shares stored energy with books the
payment: Power Insight cannot tell what your app's figure already includes.
A battery you add later does not book it either, since its history covers a
period the PV systems' history does not.

The levelized totals also subtract what the energy cost to produce, at the
device's *current* LCOE or LCOS. The PV system carries its LCOE on the energy
it stored too: the battery paid it the export compensation, not the cost of
making it. So if you later change a device's lifetime
cost, its carried-over history is restated along with everything else.

## Several PV systems or batteries

Your grid meter only knows what the **whole home** exported, so Power Insight
splits it between the devices that export. It uses the same rules it uses for
live readings: two PV systems that are interchangeable split in proportion to
what they produced, and a battery charges only from the PV systems it is
allowed to charge from.

- **Enter history for every device that exports.** While one of them has
  none, the home's export cannot be split honestly, so the history waits.
  Enter 0 for a device that really has none.
- **A device you add later** stands on its own: the home's figures cover a
  period it was not part of. It needs its own average grid tariff and, if it
  exports to the grid, its own export; a PV system's form also asks what it
  charged batteries with.

The split only decides which device earned what. Your combined savings are
the same however it falls.

### Adding a battery's history lowers the PV system's savings

Once a battery has history, the PV energy that went into it is credited to
the **battery**, when it discharges into your home, and no longer to the PV
system. The PV system is paid the export compensation for it instead. So the
PV system's savings drop by the grid price of what it charged the battery
with, less that payment, and the battery's savings carry what it delivered,
less the payment.

The combined savings drop a little too, and that is correct: a battery gives
back less than it takes in, and only energy that reaches your home saves the
grid price. Before the battery had history, its losses were counted as if
they had saved money.

**Example.** At a grid price of 0.30 and an export compensation of 0.08,
the battery charged 7,000 kWh from the PV system. Before the battery had
history, the PV system's savings read 4,200. Afterwards the PV system reads
2,660 and the battery 1,240, so 3,900 combined:

| | Value |
|---|---|
| PV energy into the battery, at the grid price | 7,000 × 0.30 = 2,100 |
| Paid by the battery to the PV system | 7,000 × 0.08 = 560 |
| PV system: 4,200 − 2,100 + 560 | 2,660 |
| Battery energy into the home, at the grid price | 1,800 |
| Battery: 1,800 − 560 | 1,240 |
| Lost in the battery: 2,100 − 1,800 | 300 |

The battery gave back 1,800 ÷ 2,100 ≈ 86 % of what it took in, a typical
round-trip efficiency (85–92 %). To check against your app, divide the
battery's *Discharged* by its *Charged*: the result should be close, allowing
for the app's rounding. If it is noticeably lower, the battery may also have
exported energy (that earns export compensation, in **Total financial
return**) or charged from the grid (that costs the battery the grid price).

## What your sensors show

Each total reads what Power Insight counted plus what it carries over. Its
attributes show both parts:

| Attribute | Meaning |
| --- | --- |
| `carried_over` | the amount carried over from your app |
| `carried_over_until` | the moment it covers up to (when counting started) |
| `tracked` | what Power Insight counted itself |
| `carried_over_missing` | why a total carries nothing (see below) |

The combined totals carry the sum of every device's history, and the grid's
*Total export compensation* carries everything the home exported.

A total carries its history only when every part of it is known. Otherwise it
carries nothing, and `carried_over_missing` says why:

| Reason | What is missing |
| --- | --- |
| `waiting` | another device's history; `carried_over_waiting_for` names it |
| `no_energy` | the kWh to calculate it from (for example an amounts-only history) |
| `no_tariff` | an average grid tariff, on the device or on the grid |
| `no_export_compensation` | the export compensation per kWh |
| `no_price` | a device's lifetime cost, for a levelized total |

:::note

Long-term statistics record the carried-over amount as one step in the hour
you save it. Past statistics are not rewritten.

:::

## When the form refuses the figures

The figures are checked together with every other device's history before
they are saved. Small disagreements are fine: app figures are rounded and
come from different meters, so figures may be up to 1 % (at least 1 kWh)
apart. If they are further apart than that, the form says which device's
figure is off, for example:

- a device exported more than it produced or discharged;
- the devices' own exports add up to more than the whole home exported;
- a battery charged more from local generation than the PV systems it may
  charge from could supply — enter its grid charging, or check what it
  charges from;
- the whole home's savings cannot be split — enter each device's kWh, or its
  own savings.

Your figures stay in the form, so you can correct the one that is off.

## Good to know

- **A total switched on later** (for example *Total financial return*, a month
  after you added the device) starts counting when you switch it on. The time
  in between is not in the carried-over history either.
- **A device you remove** keeps its history in the combined totals.
- **Not carried over:** consumer totals (*avoided cost*, *consumption cost*)
  and a PV system's standby cost. No app reports them.
