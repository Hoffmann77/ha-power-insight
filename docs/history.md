# Carried-over history

Power Insight starts counting when you add a device, but your PV system or
battery has probably been running for years. Its app or web portal knows what
happened since: how much was produced, fed in, charged and discharged, and
often how much you saved. Enter those figures and your running totals start
where your system really is, not at zero.

## Where to enter it

Every grid, PV system and battery form ends in an optional **Already
accumulated** section:

- **When you add a device.** Power Insight starts counting when you finish
  the form, so enter your app's totals up to now.
- **Later, under the device's Reconfigure page.** The form shows since when
  the device has been counted: *"Power Insight has counted this device since
  2026-08-14 10:32."* Enter your app's totals up to that moment, so nothing
  is counted twice.

Every field is optional. Leave the section empty and nothing changes.

## What to enter

Enter what your app shows, in kWh. Power Insight works out the money from it.

| Device | Figures |
| --- | --- |
| **Grid** (the whole home) | *Fed into the grid* — your grid meter's total feed-in. *Average grid tariff* — what a kWh from the grid cost on average over that period. |
| **PV system** | *Produced* — everything it produced, including what went into a battery or the grid. |
| **Battery** | *Charged*, *Discharged*, and *Of which from the grid* (leave empty unless your battery charges from the grid). |

:::tip[Why "Produced" and not "self-consumption"?]

Apps disagree on what self-consumption means: some include the energy that
went into a battery, some the energy that came back out of it. Power Insight
credits PV energy that charges a battery to the **battery**, when it
discharges into your home. Counting it for the PV system as well would count
it twice. *Produced* and *fed in* mean the same in every app, so Power
Insight works out the rest itself.

:::

### Optional figures

- **Own feed-in** (PV system, battery) — this device's own feed-in, if you
  know it, for example from the grid operator's annual statement for one
  installation. It is used as entered, and only the rest of the home's
  feed-in is split between the other devices.
- **Average feed-in tariff** — leave it empty to use the device's configured
  export compensation.
- **Savings**, **Export compensation** — amounts from your app. They are
  taken as they are, instead of being calculated from the kWh.
- **Levelized savings** — only needed when you enter amounts and no kWh.
- **Total savings**, **Total export compensation** (grid) — your app's
  figures for the whole home. They are split between the devices: savings in
  proportion to each device's calculated savings, export compensation in
  proportion to what each fed in.

## How the kWh become money

The history follows the same rules as everything Power Insight counts:

| Energy | Credited to | Saves |
| --- | --- | --- |
| PV → home | the PV system | the grid tariff |
| PV → grid | the PV system | the feed-in tariff (export compensation) |
| PV → battery | the battery, when it discharges | — |
| Battery → home | the battery | the grid tariff |
| Grid → battery | the battery | costs the grid tariff |

**Example.** Your PV system produced 10,000 kWh; 4,000 kWh were fed in; your
battery charged 2,500 kWh from the PV system and discharged 2,200 kWh; a kWh
from the grid cost 0.34 on average and feed-in paid 0.08.

| | PV system | Battery |
| --- | --- | --- |
| Energy into the home | 10,000 − 4,000 − 2,500 = 3,500 kWh | 2,200 kWh |
| Total cost savings | 3,500 × 0.34 = **1,190.00** | 2,200 × 0.34 = **748.00** |
| Total export compensation | 4,000 × 0.08 = **320.00** | — |

The levelized totals also subtract what the energy cost to produce, at the
device's *current* LCOE or LCOS. So if you later change a device's lifetime
cost, its carried-over history is restated along with everything else.

## Several PV systems or batteries

Your grid meter only knows what the **whole home** fed in, so Power Insight
splits it between the devices that feed in. It uses the same rules it uses for
live readings: two PV systems that are interchangeable split in proportion to
what they produced, and a battery charges only from the PV systems it is
allowed to charge from.

- **Enter history for every device that feeds in.** While one of them has
  none, the home's feed-in cannot be split honestly, so the history waits.
  Enter 0 for a device that really has none.
- **A device you add later** stands on its own: the home's figures cover a
  period it was not part of. Its form also asks for its own average tariff
  (and, for a PV system, what it charged batteries with), and needs its own
  feed-in if it feeds into the grid.

The split only decides which device earned what. Your combined savings are
the same however it falls.

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
*Total export compensation* carries everything the home fed in.

A total carries its history only when every part of it is known. Otherwise it
carries nothing, and `carried_over_missing` says why:

| Reason | What is missing |
| --- | --- |
| `waiting` | another device's history; `carried_over_waiting_for` names it |
| `no_energy` | the kWh to calculate it from (for example an amounts-only history) |
| `no_tariff` | the average grid tariff |
| `no_feed_in_tariff` | the feed-in tariff |
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

- a device fed in more than it produced or discharged;
- the devices' own feed-ins add up to more than the whole home fed in;
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
