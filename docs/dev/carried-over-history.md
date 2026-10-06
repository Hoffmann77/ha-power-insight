# Carried-over history

Most users adopt Power Insight years after their PV system or battery went in.
Their inverter app or web portal knows what happened in those years: how much
was produced, fed in, charged and discharged. This feature lets them carry that
history into the running totals, so *Total cost savings* starts at what the
system has really saved, not at zero.

This page is the plan. Each decision here graduates into
[Engine calculation decisions](engine-calculations.md) as it is implemented
(as a note marked *Not pinned in the engine tier*, with the integration tests
that cover it), and this page then records only what is still open.

Status: **settled**; steps 1–6 of the [implementation order](#implementation-order) are done.

## What the user can enter

Three ways, freely mixed per device and per figure. An entered figure always
wins over a calculated one.

| What is entered | Standard totals | Levelized totals |
| --- | --- | --- |
| kWh only | calculated | calculated, follow corrections |
| kWh + amounts (€) | **as entered** | entered € − the energy's cost at the current LCOE / LCOS, so they **still follow corrections** |
| amounts only | as entered | only if entered too, then at face value |

The kWh are the figures every app shows the same way: *produced*, *fed into
the grid*, *charged*, *discharged*. "Self-consumption" is deliberately not
asked for, because apps disagree on whether it includes battery charging, and
the engine credits PV energy that goes into a battery to the battery, not to
the PV (see [below](#how-the-kwh-become-money)).

### Fields

All optional, in a collapsed **Already accumulated** section of the device's
subentry flow — both the first setup step and reconfigure. Every device type
shares one form and its labels, so the grid's home-level fields have keys of
their own (`home_fed_in`, `average_tariff`, `home_savings`,
`home_export_compensation`). Stored values are suggested rather than
defaulted, so a cleared field stays cleared; a form that carries no section
leaves the stored history as it is. Amounts and prices are in Home Assistant's
currency, the same one the totals publish.

**Grid** (the home-level figures):

| Field | Unit | Notes |
| --- | --- | --- |
| Fed into the grid | kWh | The grid meter's total. Split over the devices that export. |
| Average grid tariff | currency / kWh | Over the history period. Used for every device in the shared split. |
| Total savings | currency | Optional. The app's "you saved …" figure for the whole home. |
| Total export compensation | currency | Optional. The app's feed-in revenue for the whole home. |

**PV system:**

| Field | Unit | Notes |
| --- | --- | --- |
| Produced | kWh | Required for a kWh history. |
| Own feed-in | kWh | Optional. Used as entered, e.g. from the grid operator's statement for one installation. Only the rest of the home's feed-in is split. |
| Average feed-in tariff | currency / kWh | Defaults to the device's configured export compensation. |
| Savings | currency | Optional amount. |
| Export compensation | currency | Optional amount. |
| Levelized savings | currency | Optional. Only used when there are no kWh to calculate it from. |

**Battery:**

| Field | Unit | Notes |
| --- | --- | --- |
| Charged | kWh | Required for a kWh history. |
| Of which from the grid | kWh | Default 0. Most systems never charge from the grid. |
| Discharged | kWh | Required for a kWh history. |
| Own feed-in | kWh | Optional, only offered when the battery exports. |
| Average feed-in tariff | currency / kWh | Defaults to the device's configured export compensation. |
| Savings, export compensation, levelized savings | currency | Optional amounts, as for a PV system. |

**Financial return is never asked for.** It is always savings + export
compensation (in the engine and here), and a third entered figure could
contradict the other two.

Signs are allowed on amounts: a battery that charged from the grid can have
negative savings.

### Hints in the form

- **First setup:** "Optional. Power Insight starts counting when you finish
  this step, so enter your app's totals up to now. You can add or change this
  later under *Reconfigure*."
- **Reconfigure:** "Power Insight has counted this device since
  {counting_since}. Enter your app's totals up to that moment, so nothing is
  counted twice."
- **PV *Produced*:** "Everything the system produced, including what went
  into a battery or the grid."
- **Battery *Of which from the grid*:** "Leave at 0 unless your battery is
  set to charge from the grid."

## When counting started

Each device subentry stores `counting_since`, a UTC timestamp written when the
subentry is created. It is the cutoff for that device's history: the app
totals must cover everything *before* it, and Power Insight covers everything
after.

**Migration (entry minor version 4 → 5):** set `counting_since` on every
existing subentry to the earliest `created_at` among that device's entity
registry entries (unique ids `{entry_id}_{uid}_…`), and to the migration time
when there are none.

**Accepted gap:** a running total switched on later in the options (say
*Total financial return*, a month after setup) starts counting later than its
device. The month in between cannot be recovered from the stored history, so
it is left out and the user documentation says so. A date per sensor is not
worth its complexity for this.

## How the kWh become money

### The engine's credit rules

What a kWh earns depends on where it went (`power_insight.py`,
`_source_saving_rate` and `_adapter_financial_return_rates`). Local generation
is free at the margin (`coe = 0`). Levelized, it costs its `lcoe × correction_factor`.

| Energy | Credited to | Standard | Levelized adds |
| --- | --- | --- | --- |
| PV → home | PV saving | kWh × tariff | − kWh × PV LCOE |
| PV → grid | PV financial return | kWh × feed-in | − kWh × PV LCOE |
| PV → battery | nothing for the PV | 0 | battery pays kWh × PV LCOE |
| Battery → home | battery saving | kWh × tariff | − kWh × LCOS |
| Grid → battery | battery cost | − kWh × tariff | (same) |

The history must follow the same rules, or the carried-over and the tracked
parts of one total would mean different things.

### Step 1: split the period's energy (solve on save)

A period's totals form the same allocation problem as a live snapshot: sources,
sinks and the batteries' `charge_from` restrictions. The history is split with
the engine's own solver, so the rules match the live ones: restrictions are
honoured, restricted sinks are served first, a share is split over what is left,
and interchangeable sources are drawn in proportion to their output.

`allocate` (`power_insight.py`) is a pure, module-level function over explicit
totals, public for this purpose, and the new `history.py` calls it with:

| | Entries |
| --- | --- |
| **Supply** | each PV's *produced* and each battery's *discharged*, less any own feed-in |
| **Demand** | export (the grid's *fed in* less all own feed-ins), allowed only the exporting devices **without** an own feed-in; each battery's *charged* less *of which from the grid*, allowed its `charge_from` PV systems; the home, unrestricted |

The three ways this differs from a live snapshot are decisions of their own:

1. **Grid import is not a source.** On period totals, "the grid goes first"
   would hand a battery allowed the grid all of its charging, because the home
   imports far more over a year than the battery ever charges. The timing that
   makes this wrong live (the battery charges at noon, the home imports at
   night) is lost in a total. Grid charging is therefore the entered *of which
   from the grid*, never solved.
2. **Batteries do not charge each other.** Over a period a battery both
   charges and discharges, so it appears as a source and as a sink. It is never
   allowed to draw itself or another battery. Battery-to-battery transfer is
   rare, and on totals it would only absorb energy that really came from PV.
3. **Own feed-in is pre-assigned.** A device with an own feed-in exports
   exactly that. It is taken out of supply and demand before the solve, and the
   remaining export may only draw the devices without one.

The result is stored as **flows** per device:

```python
{
    "to_home": 3500.0,                # kWh delivered into the home
    "exported": 4000.0,               # kWh fed in
    "from_grid": 0.0,                 # batteries only: the entered grid charging
    "from_pv": {"<pv uid>": 2500.0},  # batteries only: the solved local charging
}
```

Grid charging is kept apart from the PV charging because it is priced at the
tariff and never has an LCOE.

The split is **solved when history is saved, then frozen.** Removing a device
or editing a `charge_from` restriction later does not move anyone else's past.
Re-saving any history of the group re-solves the whole group with the current
restrictions.

### Step 2: price the flows (at read time)

`history_totals(record, price)` turns one device's flows into its carried-over
totals. `price(uid)` is the current corrected price, `lcoe × correction_factor`
for a live device and the frozen last price for a removed one. `T` is the
period's average tariff and `F` the device's average feed-in tariff.

| Total | Carried-over value |
| --- | --- |
| `total_cost_savings` | entered savings, else `to_home × T − from_grid × T` |
| `total_levelized_cost_savings` | `savings − to_home × price(self) − Σ from_pv × price(pv)`; with no flows, the entered levelized savings |
| `total_export_compensation` | entered export compensation, else `exported × F` |
| `total_financial_return` | `savings + export compensation` |
| `total_levelized_financial_return` | `levelized savings + export compensation − exported × price(self)` |
| `total_operating_cost` (battery) | `from_grid × T` |
| `total_levelized_operating_cost` (battery) | `from_grid × T + Σ from_pv × price(pv)` |

**Inclusion rule:** a total gets history only when every term in it is known.
Otherwise it gets none, and the sensor's attribute says why. An amounts-only
device with export compensation therefore has no levelized financial return
history, because its exported kWh are unknown. It never silently mixes a
known part with a missing one.

**Not carried over in this version:** PV standby operating cost (not in any
app, and negligible), and the consumer totals (*avoided cost*, *consumption
cost*), which need a per-consumer history no app has.

### Home-level amounts

Every combined total is the sum of its devices, so a home-level amount has to
be split between them at save time:

- **Total savings:** home total minus any per-device entered savings, split
  over the remaining devices in proportion to their *calculated* standard
  savings. If any of those is ≤ 0 (a grid-charging battery, say) the split is
  ill-defined, and the form asks for per-device amounts instead.
- **Total export compensation:** the same, in proportion to the exported kWh.
- **Without kWh:** only allowed when the home has a single PV system or
  battery, which then gets the whole amount. With several, the form refuses it.

The split amounts are stored as that device's entered amounts, so from there
on they behave exactly like amounts typed in per device.

### Worked examples

These become the integration tests' expected values.

**One PV system, one battery charging only from it.** 10,000 kWh produced,
4,000 fed in, 2,500 charged (none from the grid), 2,200 discharged; tariff
0.34, feed-in 0.08, LCOE 0.10, LCOS 0.15.

| | PV | Battery |
| --- | --- | --- |
| Flows | to_home 3,500, exported 4,000 | to_home 2,200, from_pv 2,500 |
| Savings | 3,500 × 0.34 = **1,190.00** | 2,200 × 0.34 = **748.00** |
| Levelized savings | 1,190 − 3,500 × 0.10 = **840.00** | 748 − 2,200 × 0.15 − 2,500 × 0.10 = **168.00** |
| Export compensation | 4,000 × 0.08 = **320.00** | 0 |
| Financial return | **1,510.00** | 748.00 |
| Levelized financial return | 840 + 320 − 4,000 × 0.10 = **760.00** | 168.00 |
| Levelized operating cost | — | 2,500 × 0.10 = **250.00** |

Entering self-consumption (10,000 − 4,000 = 6,000 kWh) for the PV would have
read 2,040.00: the battery's 2,500 kWh counted twice.

**Correction:** doubling the PV's lifetime cost (factor 2, LCOE 0.20) restates
both devices' history: PV levelized savings 3,500 × 0.14 = 490.00, battery
748 − 330 − 500 = −82.00. Standard savings do not move.

**Two PV systems.** Roof 8,000 kWh and carport 2,000 kWh, both exporting; the
battery may charge from both; the rest as above. Roof and carport are allowed
by the same sinks, so they are interchangeable and split 8 : 2.

| | Roof | Carport |
| --- | --- | --- |
| Exported | 3,200 | 800 |
| Charged the battery | 2,000 | 500 |
| To home | 2,800 | 700 |

Combined savings are 3,500 × 0.34 + 748 = 1,938.00 whatever the split. The
split only decides which device earned what.

**Own feed-in.** The roof's own feed-in is 3,500 kWh (from the grid operator's
statement). The carport gets the remaining 500 kWh. The two are no longer
interchangeable, so the battery splits over what is left (roof 4,500,
carport 1,500): roof 1,875, carport 625. To home: roof 2,625, carport 875.

**Home-level amount.** Total savings 2,000.00 entered on the grid, single
PV + battery as in the first example: PV 2,000 × 1,190 / 1,938 = 1,228.07,
battery 771.93. Levelized still follows the kWh: PV 878.07, battery 191.93.

## Which devices are split together

The split is only valid between figures for the **same period**. A device is
in the **shared split** when its `counting_since` is within 24 hours of the
grid's, which covers every device set up together. All others are
**standalone**.

| | Shared split | Standalone |
| --- | --- | --- |
| Tariff | the grid's average tariff | its own *average tariff* field (required) |
| Feed-in | split from the grid's total, or own feed-in | own feed-in, required when the device exports |
| PV → battery | solved | PV: optional *of which into batteries* (earns nothing). Battery: split evenly over the PV systems it may charge from |
| Home-level amounts | apply | do not apply |

A standalone device's period overlaps the time the others were already being
counted live, and the grid meter's total mixes both. So there is no shared
total to split. The even split for a standalone battery with several PV
systems is the crudest estimate in the feature. It is only reached for a
battery added later to a home with several PV systems, and it only affects
which PV's LCOE prices the battery's levelized charging.

**A missing device blocks the split.** If an exporting device in the shared
split has no history yet, the grid's *fed in* cannot be split honestly, because
part of it is that device's. The same holds for a PV system without history
that a battery with local charging may charge from: part of that charging may
be its. The split then waits, and the totals that depend on it get no
history, with an attribute naming the device. Entering 0 for it states that
it has none. So does the grid's missing *fed in*, while an exporting device
has no own feed-in to use instead.

**Energy that is not there needs no price.** A term with 0 kWh is a known 0,
whatever its price, as in the engine: a battery that never charged from the
grid has an operating cost of 0 even without a tariff.

## Validation

When a history section is saved, the whole group is solved with the form's
figures in place of the stored ones (`history_store.check_view`), and the
form refuses figures that cannot balance. The refusal is the form's general
error and names the device whose figure is off, because it is often another
device's (the grid's home figures, say) and a field inside a section cannot
reliably carry an error of its own. The figures stay in the form as typed.
Refused:

- more fed in than produced plus discharged
- own feed-ins adding up to more than the home's *fed in*
- a device whose `to_home` would come out negative
- a battery whose charging its allowed PV systems could not cover (the
  solver's restriction deficit), or *of which from the grid* above *charged*
- a home-level amount that cannot be split (see above)
- kWh fields given partly (a battery with *charged* but no *discharged*)

## Storage

| Where | What | Why there |
| --- | --- | --- |
| Device subentry, `history` | the inputs as typed | edited in that device's flow |
| Device subentry, `counting_since` | the cutoff | belongs to the device |
| Main entry `data["history"]` | `records` (per uid: flows, tariffs, resolved amounts, what a split waits for), `last_price`, and the last solve's `entered` figures and `inputs` | must outlive a removed device's subentry |

The sensors only read `data["history"]`. It is re-solved at setup whenever
the entered figures differ from the `entered` the last solve used. Saving a
history section updates the subentry, which reloads the entry, so that is
"on save". Removing a device or editing its configuration changes no entered
figure, so it moves nobody's past. The write happens before the update
listener is registered, so it triggers no reload of its own
(`history_store.py`, `async_sync_history`).

**A removed device still takes part.** Its `inputs` stay stored, because its
kWh are still part of the home's totals: when the others are re-solved later,
the home's feed-in is still split with it, while its own record stays frozen.
A removed device that never had history has no inputs and drops out.

**Figures that do not balance** keep the history solved last and log a
warning. The flows refuse them, so they only arrive when edited outside the
flow.

**`last_price`:** at every setup, each device's current corrected price is
written to its history record. A removed device's last price therefore stays
available to every battery history that references it. That is the same rule as
*a removed device's correction is final*, and it does not depend on which
sensors happened to be enabled. A teardown hook does depend on that, because
HA calls no hook when a subentry is removed.

## Sensors

- **Per-device totals:** `native_value = counted + carried over`.
  `PowerInsightIntegrationSensorDescription.history_key` names the row of the
  table above a total carries. The counted total and its per-device breakdown
  stay exactly what was measured, and the restore data persists the counted
  total, never the displayed one, so a restart cannot add the history twice.
  Nothing about the history is accumulated or stored in the engine.
- **Priced once per setup:** the records only change at setup, and so do the
  prices (a lifetime cost edit is a reconfigure, which reloads), so
  `priced_history` prices every record at setup into the entry's runtime
  data, and the sensors only look their amount up.
- **Whole-home totals** add the sum of every device's carried-over value,
  **removed devices included** (their records stay in `data["history"]`):
  `combined_total_cost_savings`, `combined_total_financial_return`,
  `combined_total_charging_cost` (a battery's grid charging), and the grid's
  `total_export_compensation`, which is everything the home exported.
- **Combined levelized totals** already sum the per-device states plus the
  retired ledger (`sensor.py`, `_ledger_total`). A removed device's frozen
  ledger value includes its history, so these add nothing themselves, which
  avoids counting it twice.
- **Attributes:** `carried_over`, `carried_over_until` (the cutoff, per
  device) and `tracked` (what the sensor counted itself). When a total has
  no history, `carried_over_missing` gives the reason as a code (`waiting`,
  `no_energy`, `no_tariff`, `no_feed_in_tariff`, `no_price`), with
  `carried_over_waiting_for` naming the devices a split waits for. On a
  whole-home total, `carried_over_missing` maps each device left out to its
  reason.
- **Statistics:** saving history is one step in the hour it was saved. The
  past is not rewritten, which is the same consequence corrections already
  accept.
- **Before the first reading** the sensor is unavailable as today. History is
  added once there is a value to add it to.

## Retiring `set_value`

This feature replaces it. Remove:

- the service: `services.yaml`, its registration (`sensor.py`,
  `async_register_entity_service`), `async_set_value` on both sensor
  bases, the `set_value` and `set_value_not_total` strings and translations,
  and the comment in `__init__.py`
- `docs/services.md` and its sidebar entry; replace the mentions in the
  README, FAQ, getting-started and concepts pages with links to the new
  user page
- `test_a_seeded_total_reads_exactly_what_was_set`, and the "seeded with
  `set_value`" sentences in `engine-calculations.md`

A total already seeded with `set_value` restores as it is today: a total
without a breakdown, carried at face value. The release notes tell those users
to set the history up instead, and to subtract their seed first if they want
both.

## Decision notes to add to `engine-calculations.md`

Under *The monetary model*, each *Not pinned in the engine tier*:

1. **History is added when a value is reported, never accumulated.** The
   engine and the restored totals hold only what was measured.
2. **History is split by the engine's allocator, on period totals.** Grid
   import is not a source, batteries do not charge each other, own feed-in is
   pre-assigned, and the split is frozen at save.
3. **Entered amounts are the truth; only their cost-of-energy part follows
   corrections.** A total whose terms are not all known gets no history.
4. **A removed device keeps its history, at its last price.**

## Tests

| Where | What |
| --- | --- |
| `tests/integration/test_history.py` | `history.py` on its own: every worked example above, the inclusion rule, the home-level splits, the blocked split, each validation error |
| `tests/integration/test_history_flow.py` | the section in setup and reconfigure, hints and the `counting_since` placeholder, errors on the right field, a save re-solving the group |
| `tests/integration/test_history_sensors.py` | totals = tracked + carried over; attributes; combined totals including a removed device; a reload adding nothing twice; a correction restating the history |
| `tests/integration/test_migration.py` (or existing) | 1.4 → 1.5 sets `counting_since` from the registry |
| engine tier | unchanged. The `allocate` rename moves no frozen output |

## Implementation order

Each step is one commit and leaves the integration working.

1. **`counting_since`:** write it on subentry creation, add the 1.5
   migration, and show it in reconfigure. This is useful on its own. — **done**
2. **`allocate`:** make the solver public. Engine tests pass, and nothing
   frozen moves. — **done**
3. **`history.py`:** inputs, the solve (with the three differences),
   pricing, the inclusion rule and home-level splits, with
   `test_history.py`. — **done**
4. **Storage:** solve on save, `data["history"]`, `last_price` refresh at
   setup. — **done**
5. **Sensors:** carried-over values, combined totals, attributes. — **done**
6. **Flow:** sections, strings and translations, hints, validation. — **done**
7. **Retire `set_value`.**
8. **Docs:** user page `docs/history.md` (in the sidebar where *Services* was),
   the four decision notes, the FAQ and getting-started updates, and this
   page reduced to what is still open.
