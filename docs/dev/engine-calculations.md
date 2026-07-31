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
  positive reading is reported `IDLE`, never `SOURCE`).
- **Grid as the balancing node.** The grid keeps its own group (`grid_adapters`)
  and is folded into `source_adapters` / `sink_adapters` direction-aware — it
  joins the sources only while importing and the sinks only while exporting — so
  the two groups stay disjoint and the grid is never counted twice. The
  behind-the-meter subsets are `local_source_adapters` / `local_sink_adapters`.

## Gross power and its shares

`gross_power = grid_import + PV_production + battery_discharge` — the sum of the
source-adapter readings.

!!! note "Decision: gross power is `None` if any inflow sensor is unavailable"
    `gross_power` returns `None` when *any* grid / PV / battery power sensor is
    unavailable, because the total would otherwise silently under-count. A
    consumer sensor dropping out does **not** invalidate it (consumers are not
    sources). Everything gated on `gross_power` (the share vectors, the source
    provenance) then propagates `None` / `{}` rather than a wrong number.

`source_adapters_gross_power_shares` sums to 1. `sink_adapters_gross_power_shares`
need **not** sum to 1 — the remainder up to 1 is the **unmetered home base
load** (everything the metered sinks don't account for). Both guard the
zero-gross case (a pure-export snapshot where `gross_power == 0`) by returning
zeros instead of dividing by zero.

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

!!! note "Decision: feasibility is decided for *groups*, with max flow"
    A set of sinks can collectively exhaust the sources it is allowed while no
    single member is individually stuck. Two batteries each restricted to
    (east, west) and each drawing 100 W are individually fine — either string
    could cover either battery — but together they need every watt the two
    strings make, so a third sink allowed to use east must not touch it.

    Asking "what must *this* sink take from this source?" one sink at a time
    cannot see that, and no local patch fixes it: it is Hall's condition, which
    quantifies over every subset. The engine therefore decides feasibility with
    max flow, where a minimum cut names the bottleneck group directly.

    Two consequences are visible in the code. `_tight_set` finds a group whose
    draw exactly exhausts every source it may use — such a group has no freedom,
    so it is split off and solved on its own before anything flexible can take
    supply it needed. `_exact_reserves` asks the group question per pairing, by
    deleting one pairing and re-running the flow.

### Choosing among valid allocations

Feasibility usually leaves freedom. Three rules spend it, in this order:

1. **The grid goes first.** A restricted sink that is allowed the grid draws it
   before competing for local generation. The grid is the balancing node, not a
   generator; local generation is the scarce thing worth attributing carefully.
2. **Scarce sources are split in proportion to draw.** Which is also what makes
   two sinks with the same restriction come out with the same row whatever their
   draws — the split is proportional, never sink-by-sink, so there is no
   ordering for them to diverge on.
3. **Unrestricted sinks take what is left.** Including the home base load. They
   can always be served, so they are served last.

!!! note "Decision: a sink splits over what is *left*, not over total output"
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

!!! note "Decision: feasibility outranks all three"
    They genuinely conflict. In one snapshot the only valid allocation required
    a battery to take *more* grid than the proportional split would have given
    it. When that happens the rules give way — they only ever choose among
    allocations that already work.

!!! note "Decision: a broken restriction is reported, not hidden"
    A sink's allowed sources are a statement about how the user believes their
    energy manager behaves, not a fact about wiring. When the meter disagrees —
    a "PV only" battery drawing more than PV produced — the restriction is
    relaxed as a last resort, because the watts came from *somewhere* and
    leaving them unattributed would break the source totals.

    How much that was is published as `sink_adapters_restriction_deficit`, and
    surfaced as a `restriction_deficit` attribute on the device's operating-cost
    sensors. It is the most useful thing an attributional engine can say: *your
    energy manager is not doing what you configured*. A sink whose allowed
    sources are **all idle** is the one exception — it collapses to an all-zeros
    row rather than being forced onto sources the user excluded, and its whole
    draw is reported as the deficit.

**Worked example** — grid `+400`, `pv_1 1000`, `pv_2 600` (gross 2000);
`bat_1` on grid+`pv_1` and `bat_2` on grid+`pv_2` drawing 400 W each; `bat_3`
and `cons_1` on PV only, 500 W each; home base load 200 W.

- Neither `bat_1` nor `bat_2` is forced onto the grid — either string could
  cover its own battery on its own — so neither reserves any of it, and the
  400 W import splits in proportion to their (equal) draws: 200 W each.
- Each covers its remaining 200 W from its own string, so both read
  `grid 0.5` / own string `0.5`.
- That leaves `pv_1 800` + `pv_2 400` for `bat_3` 500 + `cons_1` 500 + home 200,
  which is exactly 1200 W, so those three read `pv_1 2/3`, `pv_2 1/3`.
- Columns balance to the watt: grid 400, `pv_1` 1000, `pv_2` 600.

The asymmetry between an abundant and a scarce string is real, but it lands on
*which* string each battery keeps — not on how they divide a shared import.

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

!!! note "Decision: the channel cost buckets are the cost ledger"
    `combined_consumption_cost_rate`, `combined_charging_cost_rate`,
    `combined_standby_cost_rate` and `combined_export_cost_rate` (each with a
    levelized twin) replace the single "total operating cost". They exist
    because the four channels are the only cost split that conserves:

    **Invariant — cost conservation.** `CON + CHG + STB + EXP == combined_lcoe_rate`,
    and likewise for the marginal (`coe`) variants. Every watt of gross power
    is bought once and lands in exactly one channel.

    The pre-existing `combined_total_operating_cost` measured the CHG channel
    alone while being named as if it covered everything, which is why per-device
    operating costs never summed to it. It is replaced outright by
    `combined_total_charging_cost` — a clean break rather than a rename, so the
    accumulated history does not carry over. The integration is still in
    development, so no repair issue is raised for it. CON, STB and EXP are new
    quantities and start from zero.

### Savings are booked per device, at the moment they are realized

!!! note "Decision: a battery's energy cost is booked when it charges"
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

`adapters_saving_rates` is keyed by every PV and battery, in every flow role,
and a device with nothing to contribute reads `0.0` rather than being absent —
so a sensor never flips unavailable just because its device went idle:

- **producing / discharging into CON** → `+ delivered × (grid price − own cost)`
- **charging / drawing standby** → `− drawn × (cost of its source mix)`
- **exporting** → `+ export compensation`, and levelized, `− exported × own LCOE`

!!! note "Decision: consumers do not get a saving, they get an avoided cost"
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

### The home base load is a device

Everything consumed without a sensor on it already takes part in the provenance
solve. It is also the largest single consumer in most homes, so dropping it from
the results makes the totals look wrong.

!!! note "Decision: the home base load gets its own properties, not a uid"
    It is surfaced through dedicated `home_base_load_*` properties rather than
    as an entry in the `sink_adapters_*` dicts. A dict key would need a uid, and
    any readable uid (`home`, `base_load`) can collide with a user's slugified
    device name — which is exactly why the solver's internal sentinel is
    `"\x00home"`. Dedicated properties are collision-proof and make the
    duality invariant above explicit rather than hidden in a magic key.

### Prices for a discharging battery

A battery discharges energy it charged on some *earlier* mix. The engine is
stateless per snapshot, so it cannot know that mix.

!!! note "Decision: the dynamic price falls back to the flat LCOS on discharge"
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

### Two conventions worth stating

!!! note "Decision: `exports_power=False` is a hard routing restriction"
    It is not a preference about compensation — it is a property of the device
    or its control software. In Germany a home battery generally may not feed
    the public grid at all, so a battery configured this way physically cannot
    supply the EXP channel, and attributing exported watts to it would be
    wrong rather than merely unpaid.

    The exporting grid is therefore a *restricted sink*: its allowed sources
    are exactly the sources with `exports_power=True`. This reuses the existing
    restriction machinery rather than adding a parallel one, with one
    implementation caveat — an empty allowed set normally means "unrestricted",
    but for the export sink it means "nothing may export". That case has to
    collapse to a stranded, all-zeros row (whole draw reported as a deficit),
    not silently reopen the whole mix.

    Like every restriction, it gives way if no allocation can honour it: a
    house exporting while only non-exporting sources are running relaxes the
    restriction and reports the amount through
    `sink_adapters_restriction_deficit`, exactly as a "PV only" battery caught
    charging off the grid does.

!!! note "Decision: efficiency is measured at the AC port"
    A battery's configured efficiency describes its AC-side round trip, so
    conversion losses and parasitics are already inside the metered charge and
    discharge readings. Efficiency therefore never enters the savings
    arithmetic — it is used only for the dynamic price and the `LCOS`
    refinement. A DC-coupled meter would need its losses modelled separately;
    that configuration is not supported.

**Known simplification.** Self-consumption is valued at the import price even in
a snapshot where the house is exporting, where the true marginal alternative is
the feed-in tariff. This is the conventional treatment and matches how the docs
describe self-consumption, but it slightly overstates savings during an export
surplus.

## How the tests pin this down

The engine tests use the source-order scenario framework (see
[the tests README](https://github.com/Hoffmann77/ha-power-insight/blob/main/tests/README.md)).
Expected values are **hand-derived from first principles**, not read back from
the engine, so a regression in the model flips a test red rather than silently
rewriting the "expected" answer.

**Approximation policy.** Share and ratio expectations are compared with
`pytest.approx(..., abs=1e-3)` — they must agree to **three decimal places**
(0.1 percentage point). That lets an author write a readable rounded literal
like `0.615` for `8/13`, while still catching any real regression (which shifts
a share by far more than `1e-3` — the home-load bug above moved a share from
`0.615` to `0.951`). Values that *are* exact — `0.5`, `2/3`, `0.625`, `0.0`,
`1.0` — can be written exactly and compared at the default `pytest.approx`
tolerance (relative `1e-6`). When you want a share pinned tighter than three
decimals, write it as an exact fraction instead of rounding.
