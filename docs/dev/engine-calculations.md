# Engine calculation decisions

This page records the non-obvious modelling decisions baked into the
`PowerInsight` calculation engine (`custom_components/power_insight/power_insight.py`).
These are choices where more than one answer is defensible; writing them down
keeps the engine, the tests, and future changes honest about *why* a number
comes out the way it does.

Each decision below is stated as **what** the engine does and **why**, with a
worked example where the arithmetic is not obvious.

## Conventions this builds on

- **Sign convention** (see [Core concepts](../concepts.md)): grid `+` import /
  `-` export; PV/battery `+` produce/discharge / `-` standby/charge; consumer
  `-` = load.
- **Flow roles.** Each snapshot every adapter is classified from its signed
  power into a `FlowRole` (`SOURCE`, `SINK`, `IDLE`, `UNKNOWN`). A battery is a
  source while discharging and a sink while charging; PV is a source while
  producing and a sink while drawing standby; a consumer is always a sink (a
  positive reading is reported `IDLE`, never `SOURCE`). A reading of exactly
  0 W is `IDLE`, in neither group. Pinned by
  `TestIdleAdapterIsInNoFlowGroup` and `TestPvStandbyIsAnUnrestrictedSink` in
  `tests/engine/manual/test_flow_roles.py`.
- **Grid as the balancing node.** The grid keeps its own group (`grid_adapters`)
  and is folded into `source_adapters` / `sink_adapters` direction-aware — it
  joins the sources only while importing and the sinks only while exporting — so
  the two groups stay disjoint and the grid is never counted twice. The
  behind-the-meter subsets are `local_source_adapters` / `local_sink_adapters`.

## Gross power and its shares

`gross_power = grid_import + PV_production + battery_discharge` — the sum of the
source-adapter readings, balanced (below).

:::note[Decision: gross power is `None` if any inflow sensor is unavailable]

`gross_power` returns `None` when *any* grid / PV / battery power sensor is
unavailable, because the total would otherwise silently under-count. A
consumer sensor dropping out does **not** invalidate it (consumers are not
sources). Everything gated on `gross_power` (the share vectors, the source
provenance) then propagates `None` rather than a wrong number.

Pinned by `TestUnavailableMeterPublishesNothing` and
`TestUnavailableConsumerKeepsGrossPower` in
`tests/engine/manual/test_edge_readings.py`.

:::

:::note[Decision: readings that overdraw meet in the middle]

Meters are sampled at different moments — a grid meter every 60 s, smart
plugs every 30 s — and each is individually inaccurate, so the metered sinks
sometimes read more than the sources supply. That cannot physically happen,
and the engine used to route more watts out of a source than it read.

No meter is trusted over another. Every reading moves in proportion to its
size, by the least that balances the books: sources up by `1 + λ`, sinks
down by `1 − λ`, with `λ = (drawn − supplied) / (drawn + supplied)`, which
leaves the base load at exactly 0. With PV reading 1000 W against an export
of 200 W, a battery charging 500 W and a plug drawing 600 W, `λ = 3/23`: PV
becomes 1130 W and the sinks 174 + 435 + 522 W.

Holding the sources — or the grid — fixed looks tempting, since they are the
meters money depends on. But when a heat pump switches on, the plug reports
it within 30 s while the grid meter still shows the old import; holding the
grid fixed then shrinks a load that really ran. Holding it fixed is exactly
right when the grid is fresh and fully wrong when it is stale, and with
these intervals it is often stale. Meeting in the middle is never fully
wrong. It is also the only weighting that keeps the PV-splitting law (equal
adjustments per meter would not), it is continuous (`λ = 0` at balance), it
only ever makes restrictions easier to honour, and because it is unbiased
the timing errors average out in the running totals.

The raw-reading totals — `combined_grid_import` / `_export`,
`combined_production`, `combined_discharging_power`, and each device's own
power — keep what the meters say. `gross_power`, the four channels, the
ratios and every cost and avoided cost use the balanced readings, so every
ledger balances in every snapshot. The gap is published as
`metering_imbalance`. Only overdraw is corrected: an underdraw cannot be told
apart from real unmetered consumption, so it stays in the base load.

A possible later refinement is to weight each reading by its age
(`last_reported`), which would put most of the correction on the stale
meter. It is deferred: it makes the engine depend on timestamps, and sensors
that only report on change look stale while being accurate.

Pinned by `TestOverdrawMeetsInTheMiddle` in
`tests/engine/manual/test_edge_readings.py`; held in general by the balance
law in `tests/engine/automatic/test_laws.py`, which now runs on every home.

:::

:::note[Decision: a map keys every device of its family, and says what an idle one reads]

Every per-device map is keyed by a whole *family* of adapters — every
adapter that can supply power (grid, PV, batteries), every adapter that can
draw it (all of them), every consumer, or every PV system and battery — not
by the ones active this snapshot. The catalog's `keys` names the family. A
device never drops out of a map because it went quiet, so a sensor reading
it never mistakes "idle" for "gone", and a running total never stops.

What a device reads when it is not involved depends on what is measured:

| Situation | Published |
| --- | --- |
| A meter is unavailable (gross power unknowable) | the whole map is `None`, never `{}` |
| The device's own meter is unavailable | its entry is `None` |
| An amount (W, EUR/h), device not involved | `0.0` — the true value |
| A fraction (share, ratio) over nothing | `0.0` — by convention: a share of nothing is nothing |
| A price (EUR/kWh), nothing delivered | `None` — a price with no energy behind it is unknown, not free |

The fraction convention is deliberate: the alternative, `None`, would blank
every PV ratio sensor every night. The price rule is the opposite on
purpose: 0 EUR/kWh claims the energy was free. It covers the blended
`combined_coe` / `combined_lcoe` too, which have no price when gross power
is 0.

Pinned by `TestAnIdleDeviceKeepsItsKeys` in
`tests/engine/manual/test_edge_readings.py`; held in general by the
key-family and unavailability laws in `tests/engine/automatic/test_laws.py`.

:::

:::note[Decision: a missing price blanks only what needs it]

A missing *meter* makes gross power unknowable, so everything built on it is
`None` as a whole. A missing grid *tariff* is narrower: routing never depends
on a price, so every watt, share and ratio stands, and a monetary value is
blank only if it actually needs the tariff. A battery charging from PV alone
still has a known levelized cost; the load drawing grid power next to it does
not. Blanking every money value instead would throw away numbers that are
still right.

Watts a source did not deliver cost nothing at any price, so a zero never
needs one: an exporting grid does not blank a cost because the tariff is
unknown, and a device that served nothing saved nothing. Holding the last
known tariff through a short dropout is a question for the sensor layer; the
engine prices only what it is given.

Pinned by `TestAMissingPriceBlanksOnlyWhatNeedsIt` in
`tests/engine/manual/test_edge_readings.py`; held in general by the
missing-price law in `tests/engine/automatic/test_laws.py`.

:::

`source_adapters_gross_power_shares` sums to 1. `sink_adapters_gross_power_shares`
need **not** sum to 1 — the remainder up to 1 is the **unmetered home base
load** (everything the metered sinks don't account for). Both guard the
zero-gross case (a pure-export snapshot where `gross_power == 0`) by returning
zeros instead of dividing by zero. Pinned by
`TestZeroGrossPowerGuardsEveryRatio` in
`tests/engine/manual/test_edge_readings.py`.

## Source provenance: `sink_adapters_source_shares`

For every drawing adapter, the fraction of its power supplied by each source
(`{sink_uid: {source_uid: share}}`), each row summing to 1 — or to 0 when every
source the sink is allowed happens to be idle. This honours the per-device
source restrictions (`power_source_uids`: a battery's `charge_from_adapters`, a
consumer's `power_from_adapters`).

### It is a transportation problem

Sources have a fixed output, sinks have a fixed draw, some pairings are
forbidden, and the totals must match on both sides. Two extra facts shape the
solve:

- **The home base load takes part.** Everything consumed without a sensor on it
  is `gross − Σ metered draws`. It is unrestricted, competes for power like any
  other sink, and has no adapter — so it shapes every result but never appears
  in one.
- **The answer is not unique.** Many allocations satisfy the totals, so the
  engine has two jobs: find allocations that are valid at all, and pick one.

:::note[Decision: feasibility is decided for *groups*, with max flow]

A set of sinks can collectively exhaust the sources it is allowed while no
single member is individually stuck. Two batteries each restricted to
(east, west) and each drawing 100 W are individually fine — either PV system
could cover either battery — but together they need every watt the two
PV systems make, so a third sink allowed to use east must not touch it.

Asking "what must *this* sink take from this source?" one sink at a time
cannot see that, and no local patch fixes it: it is Hall's condition, which
quantifies over every subset. The engine therefore decides feasibility with
max flow, where a minimum cut names the bottleneck group directly.

Two consequences are visible in the code. `_tight_set` finds a group whose
draw exactly exhausts every source it may use — such a group has no freedom,
so it is split off and solved on its own before anything flexible can take
supply it needed. `_exact_reserves` asks the group question per pairing, by
deleting one pairing and re-running the flow.

Pinned by `TestFeasibilityIsDecidedForGroups` in
`tests/engine/manual/test_feasibility.py`.

:::

### Choosing among valid allocations

Feasibility usually leaves freedom. Three rules spend it, in this order:

1. **The grid goes first.** A restricted sink that is allowed the grid draws it
   before competing for local generation. The grid is the balancing node, not a
   generator; local generation is the scarce thing worth attributing carefully.
2. **Scarce sources are split in proportion to draw.** Two sinks with the same
   restriction therefore come out with the same row whatever their draws. The
   split is proportional, never sink-by-sink, but a reserve held by only one of
   them can still tilt it; `_allocate` then pools the group's watts and deals
   them out again by draw, which keeps every source's total and every reserve.
3. **Unrestricted sinks take what is left.** Including the home base load. They
   can always be served, so they are served last.

All three are pinned in `tests/engine/manual/test_allocation_rules.py`:
rules 1 and 2 by `TestTheGridGoesFirst`, rule 3 by
`TestRestrictedSinksAreServedFirst` (and, in `test_flow_roles.py`, by
`TestPvStandbyIsAnUnrestrictedSink`), and rule 2's "same row" guarantee by
`TestSameRestrictionGetsTheSameRow`: a 100 W and a 300 W load on the same two
PV systems, where only the larger one holds a reserve, both read 3/4 on pv1.

:::note[Decision: a sink splits over what is *left*, not over total output]

When a restricted sink spreads its draw across the several sources it is
allowed, the weights are those sources' **remaining** power — what tighter
restrictions have not already claimed — not their full readings.

It matters whenever restrictions nest. With `pv_1 3000` and `bat_1 400`
available, a consumer captive to `pv_1` drawing 250 W, and an export of
1200 W allowed both sources: the consumer is served first, so the export
splits `2750 : 400` and reads `pv_1 55/63`, not the `15/17` that total
output would give. Weighting by total output would let a flexible sink
take supply a captive one still needed, which is the same starvation
`_tight_set` exists to prevent.

Pinned by `TestASinkSplitsOverWhatIsLeft` in
`tests/engine/manual/test_allocation_rules.py`.

:::

:::note[Decision: feasibility outranks all three]

They genuinely conflict. In one snapshot the only valid allocation required
a battery to take *more* grid than the proportional split would have given
it. When that happens the rules give way — they only ever choose among
allocations that already work. Taken to the extreme, a sink allowed only
the grid takes the whole import, and the other sinks allowed the grid get
none of it.

Pinned by `TestFeasibilityOutranksTheRules` and
`TestACaptiveSinkTakesTheWholeImport` in
`tests/engine/manual/test_feasibility.py`.

:::

:::note[Decision: a broken restriction is reported, not hidden]

A sink's allowed sources are a statement about how the user believes their
energy manager behaves, not a fact about wiring. When the meter disagrees —
a "PV only" battery drawing more than PV produced — the restriction is
relaxed as a last resort, because the watts came from *somewhere* and
leaving them unattributed would break the source totals.

How much that was is published as `sink_adapters_restriction_deficit`, and
surfaced as a `restriction_deficit` attribute on the device's operating-cost
sensors. It is the most useful thing an attributional engine can say: *your
energy manager is not doing what you configured*.

A sink whose allowed sources are **all idle** is no exception: it is relaxed
the same way, and its whole draw is the deficit. It used to collapse to an
all-zeros row instead, which moved its draw into the home base load — a
"PV only" battery topping up from the grid overnight was booked as household
consumption at no operating cost, and the charging channel no longer matched
the battery meter. Relaxing it is also continuous: as the allowed source
fades to 0 W the deficit grows smoothly to the whole draw, with no jump.

A deficit is not always a misconfiguration. A battery that prefers PV but
tops up from the grid at low charge is best configured "PV only" — "PV and
grid" would book it grid first whenever the house imports — and then shows a
deficit in normal operation. So it stays an attribute, not a warning.

Pinned by `TestBrokenRestrictionIsReported` and
`TestASinkWithOnlyIdleSourcesIsRelaxed` in
`tests/engine/manual/test_restrictions.py`; the balance law in
`tests/engine/automatic/test_laws.py` checks that every channel carries what
its meters read.

:::

:::note[Decision: the sink with somewhere else to go is the one that yields]

Restrictions can conflict badly enough that *no* allocation honours them all,
and then more than one way of breaking them costs the same. Two PV systems of
100 W each, east and west; `bat_a` and `bat_b` allowed both and drawing 100 W
each; `bat_c` allowed only east and drawing 100 W. Captive demand is 300 W
against 200 W of local supply, so 100 W of restriction must break — but it
could break on `bat_c` alone, or 50 W each on `bat_a` and `bat_b`, and both
come to the same total.

The engine serves the **most constrained sink first**: `bat_c` takes east
outright and the deficit falls on `bat_a` and `bat_b`, evenly.

Two reasons. It tells the more plausible story — a device with exactly one
permitted source, and that source producing, is almost certainly using it,
while a device with two permitted sources that are jointly exhausted is the
one that must have gone elsewhere. And it is continuous: as `bat_c`'s draw
rises from 0 to 100 W the deficit grows smoothly from nothing to 50 W a side,
with no jump. These numbers drive live sensors, and a share that snaps between
0 and 1 as a battery ramps would be worse than one that slides.

Note this is a *different* question from the one above. There, a tight group
holds off a **flexible** sink that could have taken local power. Here every
contender is captive and the configuration is simply unsatisfiable, so the
question is not who is served but who is blamed.

Sinks with the *same* restriction are equally constrained, so neither has
more somewhere else to go: they share the deficit in proportion to draw and
read the same row. A larger draw is not a tighter restriction — a 100 W and a
200 W load on the same two 100 W PV systems break theirs by 100/3 and 200/3 W,
not 100 W and nothing.

Pinned by `TestTheSinkWithSomewhereElseToGoYields` and
`TestSameRestrictionSharesTheDeficit` in
`tests/engine/manual/test_restrictions.py`. Shown in
[`group-captivity / unsatisfiable_overlap`](../spec/group-captivity.mdx).

:::

:::note[Decision: what every valid allocation carries is never scaled away]

A sink allowed several sources is offered a share of each, and the offers can
add up to more than it draws; they are then scaled down together, which keeps
its split in proportion to what each source has left. But some of an offer may
be a *reserve* — watts that source must carry to this sink in every valid
allocation, because no other sink may take them. Scaling stops at the reserve.

Scaling it away strands the difference on a source only this sink could use,
and some *other* sink then has its restriction relaxed for a configuration
with nothing wrong in it. It takes a sink allowed several PV systems, none of
which it needs in particular: a plug allowed east or west has no reserve on
either, so it was the export's reserve on a third system that got cut — and
the plug was then shown drawing from that third system, with a deficit. Merge
east and west into one system and it did not happen, because the plug's need
then lands on that one system as a reserve.

Pinned by `TestReservesAreNeverScaledAway` in
`tests/engine/manual/test_feasibility.py`; shown in
[`two-pv-systems / every_watt_spoken_for`](../spec/two-pv-systems.mdx).

:::

:::note[Decision: sources the same sinks may use are drawn in proportion to their output]

Two sources that exactly the same sinks may draw are interchangeable: no
restriction tells them apart. The engine solves them as one source and deals
each sink's watts back to them in proportion to what they produce. The grid
is never merged, because it goes first rather than in proportion.

Without this, metering one installation as one PV system or as two (an
inverter reporting each MPP tracker, say) changed the answer. Reserves are
found per source, and a sink that must take 400 W from one system has no
reserve on either half once it can swap between them. A plug allowed east or
west (1000 W each) was then offered 450 W for its 400 W draw, and the export,
which may also use a 200 W carport, read 0.886 from east and west together
instead of the 1600/1800 that one 2000 W system gets.

Pinned by `TestInterchangeableSourcesAreDrawnAlike` in
`tests/engine/manual/test_allocation_rules.py`; held in general by the
split law in `tests/engine/automatic/test_laws.py`.

:::

**Worked example** — grid `+400`, `pv_1 1000`, `pv_2 600` (gross 2000);
`bat_1` on grid+`pv_1` and `bat_2` on grid+`pv_2` drawing 400 W each; `bat_3`
and `cons_1` on PV only, 500 W each; home base load 200 W.

- Neither `bat_1` nor `bat_2` is forced onto the grid — either PV system could
  cover its own battery on its own — so neither reserves any of it, and the
  400 W import splits in proportion to their (equal) draws: 200 W each.
- Each covers its remaining 200 W from its own PV system, so both read
  `grid 0.5` / own PV system `0.5`.
- That leaves `pv_1 800` + `pv_2 400` for `bat_3` 500 + `cons_1` 500 + home 200,
  which is exactly 1200 W, so those three read `pv_1 2/3`, `pv_2 1/3`.
- Columns balance to the watt: grid 400, `pv_1` 1000, `pv_2` 600.

The asymmetry between an abundant and a scarce PV system is real, but it lands
on *which* PV system each battery keeps — not on how they divide a shared import.

## The monetary model

Every monetary result in the engine is one of three things, and keeping them
apart is what makes the numbers add up:

| Ledger | Question it answers | Sign |
| --- | --- | --- |
| **Cost** | What did this energy cost me? | always ≥ 0 |
| **Avoided cost** | What would this energy have cost from the grid? | always ≥ 0 |
| **Saving** | Cost avoided *minus* cost incurred | either sign |

The first two are gross quantities; only the third is a P&L. They are published
side by side, and two of them measure the *same* watts from opposite ends — see
the duality warning below.

### Cost follows the channels

Gross power is partitioned into four channels (EXP / CON / CHG / STB), so the
cost of gross power partitions the same way. Each channel's cost is the watts
routed into it, priced at the cost of whichever source supplied them — the
routing is the provenance allocation, not a proportional guess.

:::note[Decision: the channel cost buckets are the cost ledger]

`combined_consumption_cost_rate`, `combined_charging_cost_rate`,
`combined_standby_cost_rate` and `combined_export_cost_rate` (each with a
levelized twin) replace the single "total operating cost". They exist
because the four channels are the only cost split that conserves:

**Invariant — cost conservation.** `CON + CHG + STB + EXP == combined_lcoe_rate`,
and likewise for the marginal (`coe`) variants. Every watt of gross power
is bought once and lands in exactly one channel.

Pinned by `TestChannelCostsAreTheLedger` in `tests/engine/manual/test_costs.py`.

:::

:::note[Decision: operating cost has a channel view and a device view]

They are different questions and both are worth answering, so both exist
under names that say which is which:

* **Channel** — `combined_charging_cost_rate` is the CHG channel alone:
  what went *into the batteries*. It is one of the four buckets above, so
  it takes part in cost conservation.
* **Device** — `combined_device_operating_cost_rate` is every PV's and
  battery's own draw, so battery charging **plus PV standby** (CHG + STB).
  It answers "what does running my hardware cost", and it is what the
  per-device operating-cost sensors sum to.

They agree exactly whenever nothing is in standby, which is most of the
daylight hours anyone watches a dashboard — which is why a single name
covering both went unnoticed. Overnight it inverts: charging is zero while
standby is not, so the channel figure reads `0.00` while the device total
keeps climbing.

The accumulating `combined_total_levelized_device_operating_cost` belongs
to the device view. It is deliberately *not* an integrated combined rate:
it is derived from the per-device totals plus the retired-adapter ledger,
which is what makes lifetime-cost corrections retroactive and stops a
removed device dropping its history.

The pre-existing `combined_total_operating_cost` measured the CHG channel
alone while being named as if it covered everything, which is why per-device
operating costs never summed to it. It is replaced outright by
`combined_total_charging_cost` — a clean break rather than a rename, so the
accumulated history does not carry over. The integration is still in
development, so no repair issue is raised for it. CON, STB and EXP are new
quantities and start from zero.

Pinned by `TestOperatingCostHasTwoViews` in `tests/engine/manual/test_costs.py`.

:::

### Savings are booked per device, at the moment they are realized

:::note[Decision: a battery's energy cost is booked when it charges]

A battery charging is spending money now for a benefit later. The engine
books the spend at charge time — the CHG bucket — and then values the
discharge at the full grid price it displaces, carrying only the battery's
own `LCOS` as the cost of that discharge.

The alternative (defer the charging cost and net it against the discharge)
needs the engine to remember what the stored energy cost, which a snapshot
model cannot do. Booking at charge time is exact per snapshot and correct
over a full cycle: charge `−(kWh × mix price)`, discharge
`+(kWh × (grid − LCOS))`, and round-trip losses show up honestly as the
difference between the two energies.

Pinned by `TestBatteryPaysWhenItCharges` and
`TestBatteryDischargeSavesTheFullTariff` in
`tests/engine/manual/test_battery_pricing.py`.

:::

`adapters_saving_rates` is keyed by every PV and battery, in every flow role,
and a device with nothing to contribute reads `0.0` rather than being absent —
so a sensor never flips unavailable just because its device went idle:

- **producing / discharging into CON** → `+ delivered × (grid price − own cost)`
- **charging / drawing standby** → `− drawn × (cost of its source mix)`
- **exporting** → `+ export compensation`, and levelized, `− exported × own LCOE`

:::note[Decision: consumers do not get a saving, they get an avoided cost]

A consumer running on PV is the *same saved euro* as the PV supplying it. It
is published on both sides because both are useful — "which device earned
it" and "which device benefited" — but they are two views of one quantity.

**Invariant — savings additivity.** `Σ adapters_saving_rates == combined_saving_rate`
(and the levelized twin). Only the source side is summed; consumers
contribute `0.0`.

**Invariant — avoided-cost duality.** The source side and the sink side of
the CON channel come to the same number:
`Σ source_adapters_avoided_cost_rates == Σ sink_adapters_avoided_cost_rates + home_base_load_avoided_cost_rate`.
**Never add the two sides together** — that double counts every saved euro.

Pinned by `TestConsumersGetAnAvoidedCost` in
`tests/engine/manual/test_savings.py`.

:::

### Corrections apply to prices, not to results

A device's correction factor is `current_lcoe / default_lcoe` — it restates
what that device's energy costs after its lifetime figures are edited.

:::note[Decision: the factor multiplies the lcoe, never the finished number]

A saving is `served × (tariff − lcoe)`. Scaling that *product* by the
factor moves it the wrong way: doubling a PV's lifetime cost would double
its reported saving, when dearer energy can only save less. The factor
belongs on the `lcoe` inside the bracket, which is where the engine's
`*_corrected` families put it.

The same applies to an operating cost, and worse: a battery's charging
cost is a blend of the *source* devices' prices, so the battery's own
factor is not merely misplaced there, it is unrelated.

Pinned by `TestCorrectionFactorScalesTheLcoe` in
`tests/engine/manual/test_savings.py`.

:::

:::note[Decision: accumulated totals persist their price breakdown]

A running total mixes prices from several devices, so it cannot be
re-corrected from a single scalar. The `*_rate_components` families split
each rate by *which adapter's factor scales that part*, and the sensor
layer accumulates the parts alongside the total. Editing one device's
lifetime cost then rescales exactly the share of history that came from
it, however long afterwards.

Terms that must never scale — the import tariff, an export compensation —
are keyed to the grid, whose correction factor is always `1.0`. That keeps
every component keyed by a real adapter instead of needing a sentinel.

Totals accumulated before the breakdown existed restore without one. They
are carried through unscaled: there is no attribution left to correct them
by, and inventing one would be worse than leaving them at face value.

Not pinned in the engine tier: the accumulation happens in the sensor layer.
Covered by `tests/integration/test_correction_flow.py`
(`test_stored_data_round_trips_the_component_breakdown` and its neighbour).

:::

### The home base load is a device

Everything consumed without a sensor on it already takes part in the provenance
solve. It is also the largest single consumer in most homes, so dropping it from
the results makes the totals look wrong.

:::note[Decision: the home base load gets its own properties, not a uid]

It is surfaced through dedicated `home_base_load_*` properties rather than
as an entry in the `sink_adapters_*` dicts. A dict key would need a uid, and
any readable uid (`home`, `base_load`) can collide with a user's slugified
device name — which is exactly why the solver's internal sentinel is
`"\x00home"`. Dedicated properties are collision-proof and make the
duality invariant above explicit rather than hidden in a magic key.

Pinned by `TestBaseLoadHasItsOwnProperties` in
`tests/engine/manual/test_savings.py`.

:::

### Prices for a discharging battery

A battery discharges energy it charged on some *earlier* mix. The engine is
stateless per snapshot, so it cannot know that mix.

:::note[Decision: the dynamic price falls back to the flat LCOS on discharge]

`source_adapters_dynamic_coe` / `_dynamic_lcoe` report the live blended mix
while a battery is **charging**, and the battery's flat `LCOS` while it is
**discharging**. The marginal (`coe`) side reads `0.0` on discharge, because
the energy cost was already booked at charge time — charging it again here
would double count.

The legacy implementation looked no better but was worse: it reported the
mix the battery *would* charge on right now even while discharging, and left
an unrestricted battery undefined entirely. Tracking a true running average
cost of stored energy is a stateful feature, deliberately deferred; nothing
in the savings ledger depends on it, because discharge is valued at `LCOS`.

Pinned by `TestDischargePriceIsTheFlatLcos` in
`tests/engine/manual/test_battery_pricing.py`.

:::

### Two conventions worth stating

:::note[Decision: `exports_power=False` is a hard routing restriction]

It is not a preference about compensation — it is a property of the device
or its control software. In Germany a home battery generally may not feed
the public grid at all, so a battery configured this way physically cannot
supply the EXP channel, and attributing exported watts to it would be
wrong rather than merely unpaid.

The exporting grid is therefore a *restricted sink*: its allowed sources
are exactly the sources with `exports_power=True`. This reuses the existing
restriction machinery rather than adding a parallel one, with one
implementation caveat — an empty allowed set normally means "unrestricted",
but for the export sink it means "nothing may export", and must not
silently reopen the whole mix.

Like every restriction, it gives way if no allocation can honour it: a
house exporting while only non-exporting sources are running relaxes the
restriction and reports the amount through
`sink_adapters_restriction_deficit`, exactly as a "PV only" battery caught
charging off the grid does.

Pinned by `TestExportIsRestrictedToExporters` and
`TestAnExportNoDeviceMayFeedIsRelaxed` in
`tests/engine/manual/test_restrictions.py` (an export that exporters can cover
takes only exporters; one they cannot is relaxed, and its watts stay export,
not household consumption).

:::

:::note[Decision: efficiency is measured at the AC port, and nothing needs it]

A battery's efficiency describes its AC-side round trip, so conversion
losses and parasitics are already inside the metered charge and discharge
readings. A DC-coupled meter would need its losses modelled separately;
that configuration is not supported.

Efficiency therefore never enters the savings arithmetic. It does not
enter `LCOS` either: a battery's lifetime throughput is the energy it
**discharges**, so the losses are already netted out of it and dividing by
efficiency would count them twice. And the dynamic price falls back to the
flat `LCOS` while discharging (above), so it does not need efficiency
either.

That left the configured value with no consumer at all, so the field is
gone: asking for a number nothing reads is worse than not asking. Existing
entries have the stored key dropped by a migration.

Not pinned in the engine tier: there is nothing to pin — the engine has no
efficiency input.

:::

:::note[Decision: a saving is measured against a home without the device]

Self-consumption is valued at the import price even in a snapshot where the
house is exporting. That can look like it overstates the saving — the watts
could have been exported instead, for the feed-in rate — but it answers the
question a saving asks: what would this have cost in a home without this
device? Without the PV system, the watts the house consumed would have been
imported, at the tariff. The feed-in rate answers a different question
("should I use it now or export it?"), and the watts that were exported are
already credited separately, through the export compensation, in the
financial return. Valuing self-consumption at the feed-in rate would count
the export decision twice.

Pinned by `TestSavingsAreMeasuredWithoutTheDevice` in
`tests/engine/manual/test_savings.py`.

:::

## How the tests pin this down

The decisions are pinned by hand-written harnesses (see
[the tests README](https://github.com/Hoffmann77/ha-power-insight/blob/main/tests/README.md)).
Expected values are **hand-derived from first principles**, not read back from
the engine, so a regression in the model flips a test red rather than silently
rewriting the "expected" answer.

Every decision on this page gets an explicit harness in `tests/engine/manual/`:
one class per decision, declaring the smallest home that tells it apart from
its alternatives, with values derived by hand from the decision. Each note
ends with where it is pinned — `Pinned by `TestX` in …` — or, after `Not
pinned in the engine tier:`, why it cannot be and what covers it instead.
`tests/engine/manual/test_decisions.py` fails when a note has neither, when it
names a class that does not exist, when a class is named nowhere on this page,
or when a class's docstring does not open with the decision it pins. So adding
a decision here means adding its class there.

**Approximation policy.** Write a hand-derived value as an exact fraction
(`F(8, 13)`, not `0.615`); it is compared at `pytest.approx`'s default relative
tolerance of `1e-6`, so it pins the engine to the value rather than to a
rounding of it. Pass `abs_tol` to `@expect` only when a value really must be
written rounded.

The reference cases in the docs are not tests of this kind: they show what the
engine computes for fixed readings, and are recomputed whenever it changes.
