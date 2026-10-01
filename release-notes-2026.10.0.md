## What's Changed
Release 2026.10.0 is the biggest update since the first release. It adds a full cost and savings model: you can now see what each device costs to run, how much local generation saves you, and running totals for both. The calculation engine was rebuilt, so it now works out more accurately where every watt comes from and goes to. Consumers can now draw from batteries, and they get new per-source power and energy sensors. Price units are handled correctly, and new repair issues catch wiring mistakes. Many sensors have clearer display names, and your existing entities and automations keep working, apart from the few listed below.

## ⚠️ Breaking Changes
**Combined operating cost sensors replaced (#73):**

- Operating cost rate → Device operating cost rate, plus new separate cost rates for consumption, charging, standby and export
- Levelized operating cost rate → Levelized device operating cost rate
- Total operating cost / Total levelized operating cost → Total levelized device operating cost, plus new totals for consumption and charging

> [!WARNING]
> **These are new entities, not renamed ones.** The old Combined operating cost entities stop updating and can be removed. Update any automations or dashboards that use them.

**Feed-in tariff no longer has a default (#108):**

- PV systems used to have a default export compensation of 0.08. Now you must enter a rate yourself for every device that exports to the grid.

**Grid price units are now respected (#108):**

- Before, a price in `ct/kWh` or `EUR/MWh` was read as if it were per kWh, so costs came out 100× or 1000× too high. If you corrected for this yourself, remove that workaround.

**Battery round-trip efficiency removed:** this field had no effect, so it is now dropped from existing batteries automatically.

**Minimum Home Assistant version is now 2026.2.0.**

**Many sensors have clearer names (#97):**

- Provider devices: "{Import | Production | Discharge} to {destination}" and "Share of {channel}", for example *Discharge to home consumption* instead of *Self-consumption power*
- Combined device: Home consumption power, Battery charging power, System standby power, System standby cost rate

> [!NOTE]
> **Existing installations keep their entity IDs and history. Only the default display name changes.**
> Custom entity names you set yourself are kept. New installations get entity IDs that match the new names.

## 🚀 New Features
**Cost and savings model (#67, #73)**

- Cost rates for the consumption, charging, standby and export channels
- Avoided cost for consumers: what local generation saved them
- Running totals for a consumer's operating cost, levelized operating cost and avoided cost
- Home base load as its own device (new *Home base load* option), with its power, power mix and avoided cost

**Consumers (#109, #112, #113)**

- Source selection: choose which devices may power a consumer
- Batteries can now be a consumer's power source
- Power from {source} (W) and Energy from {source} (kWh): per-source sensors, behind two new options that are included in the Extended preset

**PV systems and batteries**

- Standby power: the watts behind the existing standby ratio and share

**Correction factors (#111)**

- If you change a device's lifetime cost or production, totals already recorded are recalculated to match, and only the part that came from that device changes

**Diagnostics and repairs (#108)**

- Metering imbalance (diagnostic sensor): the gap between your meters that the engine has to close
- Repair issue when the imbalance stays above 10 % for 15 minutes, which usually means a sign is inverted or one meter is inside another meter's circuit
- Repair issues for an unusable price unit, a price in a different currency than Home Assistant's, a power sensor used by two devices, and a source restriction that your readings contradict

**New options:**

- Export settings (*Exports to grid*, *Export compensation*) can now be changed when you reconfigure a device, so a new feed-in tariff no longer means deleting it. The new rate applies from then on.

## 🛠️ Improvements & fixes

- More accurate attribution: a new solver works out exactly where each watt comes from, even when several restricted devices compete for the same source. Before, this could be off by several percent in some setups (#66, #102)
- Devices that may not export (such as most German home batteries) are kept out of the export channel entirely, instead of only being paid nothing for it (#73)
- Running totals are more accurate: each value counts for the exact time it held, a total pauses while a rate is unavailable, and counting starts as soon as the integration is set up (#108)
- Idle devices read 0 instead of unavailable; "unavailable" now only means a meter is actually down (#85)
- Readings that don't add up are balanced by meeting in the middle (#108)
- Renaming a device no longer orphans its share sensors; existing history moves over automatically (#108)
- Fixed correction factors moving savings the wrong way, and battery costs being corrected by the wrong device (#73)
- Less database load: sensor updates no longer go through the event bus, so the recorder stops storing every reading twice (#110)
- A config entry from a newer version is refused with a clear error instead of loading incorrectly after a downgrade (#107)
- Setup, options and error texts are shorter, clearer and fully translatable (#97)

## 🏠 Behind the scenes

- New documentation site with interactive reference cases, plus a Developers section (#76, #77, #80, #115)
- Engine test suite rebuilt into manual, automatic and frozen tiers using declarative homes (#100, #101)
- CalVer versioning and a reorganized release drafter (#106)
- Dependency updates, and Dependabot replaced by Renovate (#104 and others)
