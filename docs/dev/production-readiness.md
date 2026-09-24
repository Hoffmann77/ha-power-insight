# Production readiness decisions

This page records the decisions taken to get Power Insight production ready,
what is deliberately parked for later, and the order they are implemented in.
Engine decisions graduate from here into
[Engine calculation decisions](engine-calculations.md) as they are
implemented — each with its note and its `tests/engine/manual/` class — so this
page is the plan, and that one is the record the tests enforce.

Status per decision: **settled** (decided, not yet implemented), **done**
(implemented), **parked** (explicitly deferred to a later session).

## Engine

### 1. What a published map contains — done

Six properties used to publish a value while a meter was unavailable, and the
per-device maps dropped a device whenever it went idle. The contract:

| Situation | Published |
| --- | --- |
| A meter is unavailable (gross power unknowable) | the whole map is `None` |
| Every per-device map | carries a key for every device of its family |
| Amount (W, EUR/h), device not involved | `0.0` — the true value |
| Fraction (share, ratio), denominator zero | `0.0` — a documented convention: a share of nothing is nothing |
| Price (EUR/kWh), nothing delivered | `None` — a price with no energy behind it is unknown, not free |

This also settles the `grid-only / GridIdle` open question: a grid reading
exactly 0 W keeps its keys, reads `0.0` amounts and ratios, and a `None` price.
`PUBLISH_WHILE_UNAVAILABLE` goes away.

Rejected: blanking fractions while idle (sensors would read *unknown* every
night), and reporting an idle device's own configured price (it describes a
kWh that was not delivered).

### B. A missing grid price — done

A missing *meter* blanks the whole map. A missing *price* blanks only the
values that need it, per key: a battery charging from PV alone still has a
known levelized cost. Watts, shares and ratios never move. Holding the last
known price through a short dropout is a sensor-layer question, not the
engine's.

### A. A sink whose allowed sources are all idle — done

It used to collapse to an all-zeros row, which moved its draw into the home
base load (a "PV only" battery topping up from the grid overnight was booked as
household consumption, at zero operating cost) and, for an export with no
exporter running, booked exported watts as consumption. It is now relaxed like
any other broken restriction: its row sums to 1, it is priced at what it
actually drew, and its whole draw is its `restriction_deficit`. This is
continuous as the allowed source fades to 0 W.

A deficit is normal operation for a battery that prefers PV but tops up from
the grid, so it stays an attribute on the device's cost sensors — no repair
issue. The balance law gains channel-total checks (the charging channel equals
what the batteries drew, the export channel equals the grid export), which is
what would have caught this.

### 2. Readings that overdraw — done in the engine (sensor and repair issue: Home Assistant layer)

Meters are sampled at different times (a grid meter every 60 s, smart plugs
every 30 s) and are individually inaccurate, so the metered sinks sometimes
draw more than the sources supply. The engine then routed more watts out of a
source than it read.

**Meet in the middle.** No meter is trusted over another: every reading moves
in proportion to its size, by the least that balances the books — sources up by
`1 + λ`, sinks down by `1 − λ`, with `λ = (sinks − sources) / (sinks + sources)`.

- Neutral: when it is unknown which meter is stale, meeting in the middle is
  never fully wrong, where holding the grid or the sources fixed is either
  exactly right or fully wrong.
- Proportional weighting is the only one that keeps the PV-splitting law.
- Continuous (`λ = 0` at balance), and restrictions only get easier to honour.
- Unbiased, so timing errors average out in the running totals.

The raw-reading properties (`combined_production`, `combined_grid_import` /
`_export`, each device's own power) keep what the meters say. `gross_power`,
the channels, the ratios and every cost and avoided cost use the balanced
figures, so every ledger balances in every snapshot. The gap is published as
`metering_imbalance` (W): a diagnostic sensor, disabled by default, plus a
repair issue when it persists (on the order of >10 % of gross power over
15 minutes — a sustained imbalance means an inverted sign or a meter nested
inside another metered circuit). Only overdraw is corrected; an underdraw is
indistinguishable from real unmetered consumption and stays in the base load.

*Possible later refinement:* weight each reading by its age (`last_reported`),
which would put most of the correction on the stale meter. Deferred: it makes
the engine depend on timestamps, and sensors that only report on change look
stale while being accurate. Revisit once `metering_imbalance` shows how large
real imbalances are.

### C. Savings are measured against a home without the device — settled

Self-consumption is valued at the import price even while the house exports.
That is not a simplification: a saving answers "what would this have cost in a
home without this device?", and without the PV system that kWh would have been
imported. The feed-in rate answers a different question, and exported kWh are
already credited through the export compensation. The "known simplification"
wording in the decision log becomes a decision.

### D. The cost of stored battery energy — parked

Booking at charge time already makes savings exact over a full cycle; only a
"what did my stored energy cost" sensor is missing. Deferred past 1.0.

### E. CO₂ — kept as is

The config flow keeps collecting the CO₂ entities and footprints; the engine
still computes no CO₂ result.

### Already settled elsewhere

The open questions in
[the allocation write-up](source-share-allocation-problem.md) are historical:
1–5 were answered by the max-flow solver, 6 (hard restrictions) and 7 (grid
first) are decisions in the log.

### 3. Correction factors — parked

For a separate session. Findings so far: over the random homes with factors on
both PV systems and batteries, every `*_corrected` property equals the same
snapshot recomputed with each device's LCOE / LCOS times its factor, the
components times their factors sum to the corrected value, and no uncorrected
property moves when factors change — so the engine is consistent. Missing is
the promise and its tests: the `*_corrected` and `*_components` families are
not catalogued, the harness's `Adapter.battery` ignores `correction_factor`,
and no manual class pins a battery's factor. Open questions: whether a
correction reaches the whole history (and replaced hardware is a new device),
and whether clearing the lifetime fields can silently re-base the correction
(`config_flow.py`, the `depends_on` branch of the calculated fields).

## Home Assistant layer

| # | Decision | Status |
| --- | --- | --- |
| H1 | Running totals integrate up to the moment a reading becomes unavailable, then pause until it returns. No staleness timeout — HA's availability is trusted, and sensors that only report on change are legitimately silent. At startup a total starts as soon as the engine has all its readings, not at the first source event. Idle devices no longer pause a total (item 1). | settled |
| H2 | Left-Riemann integration: every engine input is a held value between events, so every rate is a step function and left-Riemann is exact; trapezoidal smears each step backwards. | settled |
| H3 | Price units: normalise EUR/kWh, ct/kWh, EUR/MWh and EUR/Wh; reject any other unit in the config flow; at runtime an unknown unit makes the price `None` (decision B). A price in another currency than Home Assistant's raises a repair issue instead of being converted. | settled |
| H4 | A power entity may belong to one device only: the config flow rejects a duplicate, and existing entries that have one get a repair issue. | settled |
| H5 | The combined levelized totals keep summing the per-device totals plus the retired-adapter ledger, but read `unavailable` while any *enabled* per-device total is unknown or unavailable (no more false drops in the statistics). A *disabled* per-device total is skipped, and that is documented on the sensor. | settled |
| H6 | Replace the custom bus events with a dispatcher signal (the recorder stores every custom bus event, including one per `state_reported`) and delete the `event.py` fork. No throttle is needed. | parked |
| H7 | Share sensors key their unique id on the source device's subentry id, not its display name. Must land before 1.0. | settled |
| H8 | Migration refuses a config entry newer than the code (downgrade). Version 1.3 is the 1.0 baseline; every storage change after it needs a migration. | settled |
| H9 | Repair issues: `no_grid_configured` gets a per-entry id; a consumer's `power_from` is checked like a battery's `charge_from`; an issue is deleted once it no longer applies. | settled |
| H10 | `exports_power` and `export_compensation` become reconfigurable and apply from then on (a feed-in rate is a time-varying price, not a lifetime average, so it never rewrites history). The currency-blind 0.08 default is dropped: a value is required when exporting. A feed-in *entity* is post-1.0. | settled |
| H11 | `iot_class: calculated`; `integration_type` stays `hub`; version by month (`2026.x.x`); entity names by `translation_key`; the diagnostic sensors (`metering_imbalance`, available power) get `entity_category: diagnostic` and are disabled by default; diagnostics hold only entity ids and titles, so nothing is redacted. | settled |
| H12 | Stale docs: the efficiency note in `concepts.md`, CLAUDE.md's description of uids (they are subentry ids) and of the integration method, the tests README's known gaps, and the allocation write-up's open questions. | settled |

## Implementation order

1. Engine item 1 (the map contract), then decision B — item 2 builds on both.
2. Engine decision A.
3. Engine item 2 (meet in the middle) and `metering_imbalance`.
4. Decision C and the documentation tidy-up.
5. The Home Assistant layer: H7 and H8 first (they break history if they land
   after a release), then H1/H2, H3, H4, H5, H9, H10, H11, H12, and the
   `metering_imbalance` sensor and repair issue.

Parked for later sessions: item 3 (correction factors), H6 (dispatcher
signal), decision D, and the age-weighted refinement of item 2.
