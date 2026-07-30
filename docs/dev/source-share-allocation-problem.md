# Power provenance as a constrained assignment

**Resolved.** This began as a hand-off document for an unsolved problem and is
kept as the record of how it was settled — the approaches that failed are as
useful as the one that worked.

`sink_adapters_source_shares` now decides feasibility with max flow: `_tight_set`
splits off any group of sinks whose draw exactly exhausts the sources it may use,
and `_exact_reserves` asks the group question per pairing by deleting the pairing
and re-running the flow. The selection preferences (grid first, proportional
split, unrestricted last) are unchanged; they now only ever choose among
allocations that already work. The watts a restriction could not cover are
published as `sink_adapters_restriction_deficit`.

Over the 250-topology corpus: **0 group-captivity failures** (was 1 in 217),
source columns balance to the watt, and all six hand-derived scenarios reproduce
exactly. The unlock was moving the home load and every other unrestricted sink
to the slack side, which removes the `Σs = Σd` identity that had made every
minimum cut degenerate.

## Context

Home energy integration. Every few seconds we get a snapshot of instantaneous
power readings (watts) from a house: a grid meter, some PV strings, some
batteries, some individually-metered appliances. From that snapshot the engine
answers, for every device currently *drawing* power, **where that power came
from** — `{sink: {source: share}}`, each row summing to 1. Those shares drive
per-device cost and CO₂ attribution.

The property is `PowerInsight.sink_adapters_source_shares`
(`custom_components/power_insight/power_insight.py`).

## The problem

One snapshot gives:

- **Sources** `k` with output `s_k > 0` — grid import, producing PV strings,
  discharging batteries.
- **Sinks** `u` with draw `d_u > 0` — grid export, charging batteries, appliance
  loads, PV standby.
- **One extra sink**, the *home base load* `d_home = Σs − Σd_metered`: everything
  the house consumes that has no sensor on it. Always unrestricted. It is not
  reported in the output, but it competes for power like any other sink, so it
  must be part of the solve. By construction `Σ s_k = Σ d_u` exactly.
- **Allowed sets** `A(u) ⊆ sources`. Users may configure a battery to "charge
  from PV only" or an appliance to "run on excess solar". An empty set means
  unrestricted. This is a *user statement about their energy manager's
  behaviour*, not a wiring fact — there is one busbar and electrons are not
  labelled.

Find `x[u][k] ≥ 0` with `x[u][k] = 0` for `k ∉ A(u)`, such that

```
Σ_k x[u][k] = d_u     for every sink      (each sink's draw is fully explained)
Σ_u x[u][k] = s_k     for every source    (each source's output is fully used)
```

and report `share[u][k] = x[u][k] / d_u`.

This is a transportation problem on a bipartite graph. It is usually
**underdetermined** — many allocations satisfy the constraints — so the model
also has to pick *which* one.

### Scale

Small. A large install is ~8 sources × ~15 sinks; the common case is 3 × 6.
Pure Python, no numpy (measured: numpy loses on vectors this short).

The solve is memoised per snapshot (`PowerInsight._snapshot_cached`, invalidated
by a revision counter that `set_value` and `register_adapter` bump), because the
engine is lazy and dozens of sensor entities read through it on every event.
Measured on a 6-source × 8-sink install: the cold solve costs ~690 µs and every
further read of the same snapshot ~8 µs, so an event with 50 reads went from
34.6 ms to 0.42 ms — **83×**. Without it the exact algorithm would not be
affordable; with it, correctness rather than cost decides the design.

## Requirements

**Hard invariants** (a property test over 250 seeded random topologies checks
all four — `tests/engine/test_source_shares_invariants.py`):

1. Every row sums to 1, or to 0 when every allowed source is idle.
2. No source is attributed beyond its reading.
3. With no home base load, columns balance exactly.
4. **A restriction may only be broken when no allocation could have honoured
   it.** Decided by an independent max-flow oracle in the test, not by the
   engine.

**Selection preferences** (which feasible allocation to pick):

5. Sinks with identical allowed sets get identical rows, whatever their draws —
   never an ordering-dependent tie-break.
6. Equal claimants on a scarce source split it in proportion to demand.
7. A restricted sink that is allowed the grid should draw the grid first. The
   grid is the balancing node, not a generator; local generation is the scarce
   thing. This is deliberate and endorsed: the engine is *attributional*, and
   the resulting large cost figure for a grid-charged battery is the useful
   signal, not a bug.
8. Restrictions are honoured strictly whenever possible. When the configuration
   contradicts the meter (a "PV-only" battery drawing more than PV produced),
   the excess falls back to the general mix.

**Feasibility can override any preference.** They genuinely conflict: in one
random topology the only valid allocation required a battery to take *more* grid
than the preference-blind proportional split gave it.

**Testing constraint.** Expected values in this codebase are hand-derived from
first principles and compared as exact fractions (`4/9`, `17/39`, `6/7`), so a
regression flips a test red rather than silently rewriting the answer. Shares
may be compared at `abs=1e-3` where a value is written as a rounded literal. An
algorithm whose output cannot be hand-derived breaks this convention.

## The counterexample that kills the obvious approach

The natural greedy is: for each source, first set aside what each sink *must*
take from it (its draw minus what its other allowed sources hold), then share
the remainder proportionally. That is **Hall's condition applied to one sink at
a time**, and captivity can be a property of a *group* with no captive member.

Sources: `east 100`, `west 100`, `south 1000`.
Sinks: `A 100 (east|west)`, `B 100 (east|west)`, `C 500 (east|south)`,
home `500`.

`A` and `B` together need 200 W and east+west make exactly 200 W, so every drop
is spoken for and `C` must take all 500 W from south — the only valid answer.
But asked individually, neither `A` nor `B` *must* use east (west alone could
cover either), and `C` needn't either. So east gets shared three ways, `C` takes
33 W of it, and `A`/`B` finish short and spill onto **south**, which they were
never allowed.

Measured on the 250-topology corpus: this fires in **1 of 217 feasible
topologies**, misattributing 0.95% of one sink's row and 2.8% of another's.
Rare and small — but not acceptable.

## Approaches tried, with measurements

| approach | invariant 4 | columns | reproduces hand-derived values | cost/snapshot | size |
|---|---|---|---|---|---|
| phased greedy (singleton captive rule) | **1 of 217 fails** | exact | yes | 12 µs | ~90 lines |
| exact per-edge ceiling used as a *mask* | 1 of 217 fails | exact | yes | 315 µs | +80 lines |
| exact per-edge ceiling used as a *cap*, recomputed per round | **0** | exact | **no** — port lost preferences 5 and 7 | 513 µs | +80 lines |
| critical-set peel, home+unrestricted as slack | **1 of 217 fails** | exact | **all 6, exactly** | 24 µs | ~40 lines |
| Sinkhorn / scarcity pricing | **0** | exact | to 3–4 decimals | 216 µs | **~25 lines** |

**Per-edge ceiling.** For each `(u,k)`, the most `u` could draw from `k` in *any*
allocation that still serves everyone: force `x = min(d_u, s_k)` onto the edge,
reduce both sides, max-flow the remainder, hand back the deficiency. Clamping
every offer to this and recomputing each round closes the gap completely. The
feasibility half is proven; re-expressing the selection preferences inside those
bounds is unsolved — a quick port lost grid-first, captive-first, *and* symmetry
(two identical sinks came out different).

### Is the tier structure the problem?

No — measured, because it is the first thing a reader assumes.

- **The counterexample lives inside a single tier.** In east/west/south there is
  no grid, so tier 1 is empty and `A`, `B`, `C` are all restricted: they share
  tier 2. The failure happens with no tier boundary involved.
- **Tiers do not make the output jumpier.** Perturbing each source by 1 W across
  120 topologies, the worst share movement is **0.0018 for the tiered greedy and
  0.0018 for pricing** — identical. The "tier boundaries cause discontinuities"
  intuition is not supported.
- **What goes wrong is the division rule inside a step**, which commits power
  without knowing what its peers or later steps need. On the corpus
  counterexample tier 1 handed `cons0` 67.7 W of grid although `cons0` had
  2400 W of pv1 available, stranding `bat1` and `cons1`; giving `bat1` the whole
  import instead leaves the remainder feasible.
- **A minimal clamp is not enough.** Keeping `proportional_fill` unchanged and
  capping every offer at the global per-edge ceiling fixes the isolated
  counterexample and keeps blocks 1/2/3A exact, but the corpus gap stays at 2
  (the ceiling goes stale as soon as anything is committed inside a round) and
  the full-topology and block-3B values break. 699 µs.

So the tier skeleton is worth keeping — it is cheap, hand-derivable, and the
only mechanism found that expresses the grid-first preference exactly. What has
to change is how each step divides a source, and that decision needs a global
view.

**Critical-set peel.** Find a tight sink set (`Σd(S) = Σs(N(S))`), peel it with
its sources, recurse; inside a block with no tight set, run the phased fill.

Originally reported as blocked on a degenerate min cut. **Unblocked**, by three
fixes:

1. *Home and every other unrestricted sink move to the slack side* — they are not
   competitors. This removes the identity `Σs = Σd` that made every cut minimal
   and hid the real bottlenecks.
2. *Source→sink edges must be uncapped* in the flow network. Capping them at the
   sink's demand does not change the max-flow value, but it saturates edges that
   the min-cut extraction needs to walk, so residual reachability silently
   returned the wrong set.
3. *Verify the extracted set is actually tight* (`Σd(S) == Σs(N(S))`) before
   peeling. The reachability set is a valid tight set only when the cut really is
   minimum; guard rather than assume.

With those, the peel reproduces **all six hand-derived cases exactly** — the
full-topology scenario, all four source-share blocks, and the east/west/south
counterexample — with exact columns and rows, at 24 µs. That is twice the cost of
the broken greedy and twenty times cheaper than the per-edge ceiling method.

**What is still missing.** One corpus case in 217 still leaks, and the cause is
now precisely known: *no tight set exists at the start*, so the phased fill runs
— and its own commitments **create** tightness. In the failing snapshot the grid
phase hands `cons0` 68 W of grid it does not need (it has 2400 W of pv1
available), and only then are `bat1` and `cons1` stranded. Peeling before the
fill cannot see this; peeling after cannot undo it.

**The completion** is the water-fill of Proposals A/C3, and it is now a small
step rather than a rewrite: instead of committing a whole phase at once, advance
all sinks together and stop at the first *event* — a source exhausting, or a set
going tight — then peel and continue. Each breakpoint is a linear equation in one
unknown, so every intermediate value stays an exact fraction. The peel machinery
this needs already exists and is verified.

**Sinkhorn / scarcity pricing.** Weight every `(u,k)`: 1 if allowed, `1e-9` if
not, `×1e4` for the grid-first preference. Alternately rescale rows to `d_u` and
columns to `s_k` until stable. Repeated column scaling acts as a *price*: a
contested source becomes expensive, so sinks with alternatives drift off it and
leave it to the sinks that have none — the group captivity is handled
automatically, because a price responds to total demand for a source rather than
to one sink at a time. No masks, no tiers, no max-flow, no fallback branch;
restrictions and preferences are the same mechanism at different magnitudes, and
over-subscription spills over on its own.

Satisfies all four invariants on the corpus. Reproduces the hand-derived values
of the full-topology scenario exactly to 4 decimals and the counterexample
correctly. **But it cannot produce exact values**, for two independent reasons:

- *Sublinear convergence* where the answer contains hard zeros: 200 iterations →
  2.3e-3 error, 2 000 → 2.2e-4, 20 000 → 3.4e-5. Reaching 1e-9 would need ~10⁹
  iterations. Snapping dust to zero and re-converging buys ~2×.
- *Preference bias* `≈ 1/weight`: with the grid weight at 1e4 the full-topology
  case plateaus at 1.26e-4 — a battery that should read exactly `1.0` reads
  `0.9999`. Raising the weight shrinks the bias and worsens conditioning.

Median 2 iterations; only the degenerate cases hit the 200-iteration cap.

## Open questions

1. **Is there a formulation that is exact, feasibility-correct, and
   preference-expressive at once?** Feasibility is a flow property; the
   preferences are a fairness/interior property. Every method tried delivers one
   cleanly and the other awkwardly.
2. **Can Sinkhorn's support be used as a stepping stone?** Run the iteration
   only to discover which edges are non-zero, then solve exactly on that support
   with rational arithmetic. Is the support reliably identified, and is the
   allocation on it uniquely determined?
3. **Can the preferences be re-expressed inside per-edge feasibility bounds**
   while preserving symmetry (requirement 5)? That is the one missing piece of
   the max-flow approach. Recomputing the ceiling once per round is measurably
   not tight enough; does it have to be recomputed after every commit, and if so
   can the cost be kept sane?
4. **Tiers for the preference, pricing for the division?** Keep the tier
   skeleton to express grid-first exactly, but replace the per-source division
   inside each tier with the scarcity-price iteration. Untested.
5. **Is the minimal-tight-set extraction fixable** for the `Σs = Σd` degenerate
   case, and would it be materially cheaper than one max-flow per edge?
6. **Is the hard-constraint model the right one at all?** Making `charge_from` a
   preference ordering rather than a hard mask removes the feasibility problem
   entirely — no Hall condition, no max-flow, no fallback. The cost is semantic:
   a "PV only" battery could show grid in its mix. Given that the setting
   describes a controller's behaviour rather than physical wiring, is the hard
   reading defensible?
7. **Does requirement 7 (grid-first) earn its complexity?** It is the only
   non-physical rule in the model and the hardest to carry through any exact
   method. Dropping it makes scarcity pricing considerably better behaved.

## Files

- `custom_components/power_insight/power_insight.py` — `sink_adapters_source_shares`
- `tests/engine/test_source_shares.py` — hand-derived edge cases (4 currently red, by design)
- `tests/engine/test_source_shares_invariants.py` — the four invariants over 250 random topologies
- `tests/engine/test_full_topology.py` — the reference scenario and its expected values
- `docs/dev/engine-calculations.md` — the currently-documented model (describes the older tier order, needs rewriting once this lands)
