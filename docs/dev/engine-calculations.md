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
