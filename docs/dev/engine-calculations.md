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
(`{sink_uid: {source_uid: share}}`, each row summing to 1, or all-zeros when the
sink's allowed sources are all idle). This honours per-device source
restrictions (`power_source_uids`: a battery's `charge_from_adapters`, a
consumer's `power_from_adapters`).

Attribution runs in **three tiers**, and the tiers exist only while the grid is
importing — with no import there is nothing to "fall back" to, so every sink
shares the sources in a single equal-footing pass.

1. **Priority tier** — sinks restricted to non-grid sources (a PV-only battery,
   a smart-plug on excess solar). They get first pick of their allowed sources,
   weighted by each source's share of gross power, and *consume* what they take
   from the availability pool.
2. **Home base-load tier** — the unmetered home load
   (`home_share = 1 − Σ sink_shares`). It consumes the remaining **local**
   generation next, with the grid as its fallback.
3. **Leftover tier** — every flexible sink (unrestricted, or allowed to draw the
   grid). They split whatever the first two tiers left behind.

!!! note "Decision: the home base load consumes local-first, before flexible grid-capable sinks"
    A grid-capable sink (a battery that *can* charge from the grid) is flexible;
    the always-on home base load is not. So the base load has the stronger claim
    on scarce local generation, and the flexible sinks are the ones pushed onto
    the grid when local runs out.

    Concretely, between the priority and leftover tiers the home load consumes
    the residual local generation first (grid covers its deficit), depleting
    **both** the local and grid slices of the availability pool by its actual
    draw. Only then do the grid-capable leftover sinks share what remains.

    Without this tier the flexible sinks over-claimed local generation the base
    load had really eaten — e.g. a PV-only battery would correctly take the solar
    while a grid-capable battery still showed a sliver of that same solar.

!!! note "Decision: the split across grid-capable sinks is asymmetric, not equal"
    When two grid-capable batteries draw from two different PV strings, their
    grid shares are **not** equal unless the strings are equal — each keeps the
    local generation of *its* string, and a bigger string leaves more local
    behind.

    **Worked example** — grid `+400`, `pv_1 1000`, `pv_2 600` (gross 2000);
    `bat_3`/`cons_1` charge from PV only (500 W each), `bat_1` from grid+`pv_1`
    (400 W), `bat_2` from grid+`pv_2` (400 W); home base load 200 W.

    - Priority: `bat_3` and `cons_1` each take `pv_1 0.625 / pv_2 0.375`
      (proportional to the 1000 : 600 split).
    - Home (`home_share = 0.10`) eats the residual local proportionally.
    - Leftover: because `pv_1` (1000 W) is more abundant than `pv_2` (600 W),
      more `pv_1` survives, so `bat_1` keeps more local than `bat_2`:
      `bat_1 → grid 0.615, pv_1 0.385`; `bat_2 → grid 0.727, pv_2 0.273`.

    An equal `0.5 / 0.5` split would only be correct if the two strings were
    equal, or if the home load ate the abundant string preferentially to level
    them (which local-first proportional does not do).

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
