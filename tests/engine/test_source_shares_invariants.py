"""Property tests for ``sink_adapters_source_shares`` over random topologies.

The hand-derived scenarios in ``test_source_shares.py`` and
``test_full_topology.py`` pin *what* the provenance attribution answers for a
handful of carefully chosen wirings. This file pins the things that must hold
for *every* wiring, and finds its own counterexamples: a seeded generator builds
a few hundred random topologies and readings, and each test asserts one
invariant across all of them.

Four invariants, in increasing strength:

1. **Rows are normalised.** Every sink's row sums to 1, or to 0 when none of its
   allowed sources is providing this snapshot (the idle collapse).
2. **No source is over-drawn.** The metered sinks together cannot be attributed
   more of a source than that source actually produced. They may be attributed
   *less* — the difference is the unmetered home base load, whose row the engine
   does not expose.
3. **Columns balance exactly when there is no home load.** When the metered
   sinks account for all of gross power there is no unmetered remainder to hide
   in, so every source column must equal its reading to the watt. This is
   invariant 2 with the inequality closed.
4. **Restrictions are honoured whenever they can be.** A sink may only be shown
   drawing from a source outside its configured set when no allocation existed
   that would have respected every restriction — i.e. when the configuration
   contradicts the meter. Whether such an allocation exists is decided here by
   an independent max-flow oracle (:func:`_is_feasible`), not by the engine.

Invariant 4 is the interesting one. The attribution algorithm reserves, for each
sink, the demand its *other* allowed sources cannot cover — Hall's feasibility
condition applied one sink at a time. Hall's condition is really about every
*group* of sinks, and captivity can be a property of a group with no captive
member: two batteries each restricted to (east, west) and each drawing 100 W are
individually fine (either string could cover either battery) but jointly need
every watt the two strings make. Checking sinks one at a time cannot see that,
so a third sink allowed to use east may take a slice the pair needed. The oracle
turns "we know of no counterexample" into a number: how many of N random
topologies hit it.

These tests need no hand-derived expected values, so they complement the
scenario files rather than duplicating them: the scenarios say what the answer
is, these say what an answer must never be.

Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery ``+``
produce/discharge / ``-`` standby/charge; consumer ``-`` = load.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from tests.engine.scenario_framework import Adapter, Cell, State, Topology

#: Cases per test. Every test draws the same set (same seed), so a failure in
#: one is reproducible in the others.
CASE_COUNT = 250
SEED = 20260730

#: Watts. Readings are whole numbers, so the max-flow oracle stays exact.
TOL = 1e-6


@dataclass(frozen=True)
class Case:
    """One random wiring plus readings, and the facts derived from them."""

    topology: Topology
    state: State
    #: uid -> watts, for the adapters currently providing.
    sources: dict[str, int]
    #: uid -> watts drawn, for the metered adapters currently drawing.
    sinks: dict[str, int]
    #: uid -> the sources it is allowed to draw (already masked to the sources
    #: that are actually providing); empty means unrestricted.
    allowed: dict[str, tuple[str, ...]]
    #: The sinks that carry a restriction at all. Needed because ``allowed``
    #: masks a restriction whose every target is idle down to the same empty
    #: tuple an unrestricted sink has.
    restricted: frozenset[str]
    #: Gross power minus the metered draw — the unmetered home base load.
    home: int

    def describe(self) -> str:
        parts = [f"{u}={v}" for u, v in self.sources.items()]
        parts += [f"{u}=-{v}{list(self.allowed[u]) or ''}" for u, v in self.sinks.items()]
        return f"sources/sinks: {', '.join(parts)}, home={self.home}"


# ---------------------------------------------------------------------------
# Random topology generator
# ---------------------------------------------------------------------------


def _split(rng: random.Random, total: int, parts: int) -> list[int]:
    """Split ``total`` into ``parts`` non-negative whole numbers."""
    if parts == 0:
        return []
    cuts = sorted(rng.randint(0, total) for _ in range(parts - 1))
    bounds = [0, *cuts, total]
    return [bounds[i + 1] - bounds[i] for i in range(parts)]


def _make_case(rng: random.Random) -> Case | None:
    """Build one random wiring + readings, or ``None`` for a degenerate draw."""
    n_pv = rng.randint(1, 3)
    n_bat = rng.randint(0, 3)
    n_cons = rng.randint(0, 3)

    pv_uids = [f"pv{i}" for i in range(n_pv)]
    bat_uids = [f"bat{i}" for i in range(n_bat)]
    cons_uids = [f"cons{i}" for i in range(n_cons)]

    # Roles, then the readings that follow from them.
    grid_importing = rng.random() < 0.7
    pv_producing = {uid: rng.random() < 0.7 for uid in pv_uids}
    bat_role = {uid: rng.choices(("charge", "discharge", "idle"),
                                 (0.5, 0.3, 0.2))[0] for uid in bat_uids}

    readings: dict[str, int] = {}
    sources: dict[str, int] = {}
    for uid in pv_uids:
        power = rng.randrange(2, 60) * 50 if pv_producing[uid] else -rng.randrange(0, 3) * 10
        readings[uid] = power
        if power > 0:
            sources[uid] = power
    for uid in bat_uids:
        if bat_role[uid] == "discharge":
            power = rng.randrange(2, 30) * 50
            readings[uid] = power
            sources[uid] = power
        else:
            readings[uid] = 0  # charging draw is filled in below
    grid_power = rng.randrange(2, 40) * 50 if grid_importing else 0
    if grid_importing:
        sources["grid"] = grid_power

    gross = sum(sources.values())
    if gross <= 0:
        return None

    # Sinks: charging batteries, standby PV, consumer loads, and an exporting
    # grid. Their total is drawn as a fraction of gross so the unmetered home
    # base load is never negative; a fifth of the cases use the whole of gross
    # so invariant 3 has cases to check.
    sink_uids = [uid for uid in bat_uids if bat_role[uid] == "charge"]
    sink_uids += [uid for uid in pv_uids if not pv_producing[uid]]
    sink_uids += cons_uids
    if not grid_importing:
        sink_uids.append("grid")
    if not sink_uids:
        return None

    fraction = 1.0 if rng.random() < 0.2 else rng.uniform(0.3, 0.95)
    budget = int(gross * fraction)
    draws = _split(rng, budget, len(sink_uids))
    sinks = {uid: d for uid, d in zip(sink_uids, draws) if d > 0}
    if not sinks:
        return None

    for uid, draw in zip(sink_uids, draws):
        if uid == "grid":
            grid_power = -draw
        elif uid in pv_uids:
            readings[uid] = -draw
        else:
            readings[uid] = -draw
    readings["grid"] = grid_power
    if not grid_importing and grid_power == 0:
        return None  # neither importing nor exporting: the grid is idle

    # Restrictions: half the batteries/consumers get pinned to 1-2 other
    # adapters. The target may well be idle this snapshot -- that is the point.
    targets = ["grid", *pv_uids, *bat_uids]
    restrictions: dict[str, tuple[str, ...]] = {}
    for uid in bat_uids + cons_uids:
        pool = [t for t in targets if t != uid]
        if pool and rng.random() < 0.5:
            k = rng.randint(1, min(2, len(pool)))
            restrictions[uid] = tuple(rng.sample(pool, k))

    adapters = [Adapter.grid()]
    adapters += [Adapter.pv(uid, exports=True) for uid in pv_uids]
    adapters += [Adapter.battery(uid, charge_from=restrictions.get(uid, ()))
                 for uid in bat_uids]
    adapters += [Adapter.consumer(uid, power_from=restrictions.get(uid, ()))
                 for uid in cons_uids]

    # Mask each restriction down to the sources actually providing: a sink
    # pinned to an idle PV has no allowed source at all this snapshot.
    allowed = {
        uid: tuple(t for t in restrictions.get(uid, ()) if t in sources)
        if uid in restrictions else ()
        for uid in sinks
    }
    return Case(
        restricted=frozenset(uid for uid in sinks if uid in restrictions),
        topology=Topology(*adapters),
        state=State(price=0.30, **readings),
        sources=sources,
        sinks=sinks,
        allowed=allowed,
        home=gross - sum(sinks.values()),
    )


def _cases() -> list[Case]:
    rng = random.Random(SEED)
    out: list[Case] = []
    while len(out) < CASE_COUNT:
        case = _make_case(rng)
        if case is not None:
            out.append(case)
    return out


# ---------------------------------------------------------------------------
# Feasibility oracle: is there *any* allocation honouring every restriction?
# ---------------------------------------------------------------------------


def _max_flow(capacity: dict[str, dict[str, int]], src: str, dst: str) -> int:
    """Edmonds-Karp. Capacities are whole watts, so this is exact."""
    total = 0
    while True:
        parent: dict[str, str | None] = {src: None}
        queue = [src]
        while queue and dst not in parent:
            node = queue.pop(0)
            for nxt, cap in capacity.get(node, {}).items():
                if cap > 0 and nxt not in parent:
                    parent[nxt] = node
                    queue.append(nxt)
        if dst not in parent:
            return total

        path, node = [], dst
        while parent[node] is not None:
            path.append((parent[node], node))
            node = parent[node]
        bottleneck = min(capacity[a][b] for a, b in path)
        for a, b in path:
            capacity[a][b] -= bottleneck
            capacity.setdefault(b, {})[a] = capacity.setdefault(b, {}).get(a, 0) + bottleneck
        total += bottleneck


def _is_feasible(case: Case) -> bool:
    """True when every sink can be served entirely from its allowed sources.

    Solves the transportation problem exactly (max-flow), including the
    unmetered home load as an unrestricted sink, so it is a genuine independent
    check rather than a re-run of the engine's own reasoning.
    """
    demand = dict(case.sinks)
    if case.home > 0:
        demand["__home__"] = case.home
    capacity: dict[str, dict[str, int]] = {"__src__": {}, "__dst__": {}}
    for uid, power in case.sources.items():
        capacity["__src__"][f"s:{uid}"] = power
        capacity.setdefault(f"s:{uid}", {})
    for uid, draw in demand.items():
        capacity.setdefault(f"t:{uid}", {})["__dst__"] = draw
        allowed = case.allowed.get(uid, ())
        for source_uid in case.sources:
            if not allowed or source_uid in allowed:
                capacity[f"s:{source_uid}"][f"t:{uid}"] = draw
    return _max_flow(capacity, "__src__", "__dst__") == sum(demand.values())


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def _report(failures: list[str], checked: int, invariant: str) -> None:
    if not failures:
        return
    shown = "\n".join(f"  - {line}" for line in failures[:5])
    extra = f"\n  ... and {len(failures) - 5} more" if len(failures) > 5 else ""
    raise AssertionError(
        f"{invariant}\n{len(failures)} violation(s) across {checked} random "
        f"topologies:\n{shown}{extra}"
    )


def test_rows_are_normalised() -> None:
    """Every sink's row sums to 1, or to 0 when all its allowed sources are idle."""
    failures = []
    cases = _cases()
    for case in cases:
        engine = Cell(case.topology, case.state).build_engine()
        for uid, row in engine.sink_adapters_source_shares.items():
            total = sum(row.values())
            if abs(total - 1.0) > 1e-9 and abs(total) > 1e-9:
                failures.append(f"{uid} row sums to {total:.6f}; {case.describe()}")
    _report(failures, len(cases), "Every provenance row must sum to 1 (or 0 when idle).")


def test_no_source_is_overdrawn() -> None:
    """The metered sinks cannot be attributed more of a source than it produced."""
    failures = []
    cases = _cases()
    for case in cases:
        engine = Cell(case.topology, case.state).build_engine()
        rows = engine.sink_adapters_source_shares
        for source_uid, power in case.sources.items():
            drawn = sum(
                row.get(source_uid, 0.0) * case.sinks[uid]
                for uid, row in rows.items()
                if uid in case.sinks
            )
            if drawn > power + TOL:
                failures.append(
                    f"{source_uid} produced {power} W but {drawn:.1f} W was "
                    f"attributed to the metered sinks; {case.describe()}"
                )
    _report(
        failures,
        len(cases),
        "No source may be attributed beyond its reading (the slack is the home load).",
    )


def test_unattributed_power_is_exactly_the_unreportable_draw() -> None:
    """Whatever the metered rows leave over must be power with nowhere to go.

    Two draws are deliberately absent from the result: the unmetered home base
    load, which has no adapter, and any sink restricted to sources that are all
    idle, which collapses to an all-zeros row rather than being forced onto
    sources the user excluded. Everything else must be accounted for exactly, so
    the shortfall across all sources equals precisely those two together. This
    is the strict form of "no source is over-drawn" — it pins the slack instead
    of only bounding it.
    """
    failures = []
    cases = _cases()
    for case in cases:
        engine = Cell(case.topology, case.state).build_engine()
        rows = engine.sink_adapters_source_shares
        unattributed = 0.0
        for source_uid, power in case.sources.items():
            drawn = sum(
                row.get(source_uid, 0.0) * case.sinks[uid]
                for uid, row in rows.items()
                if uid in case.sinks
            )
            unattributed += power - drawn
        stranded = sum(
            draw for uid, draw in case.sinks.items()
            if uid in case.restricted and not case.allowed[uid]
        )
        expected = case.home + stranded
        if abs(unattributed - expected) > 1e-6 * max(1.0, expected):
            failures.append(
                f"{unattributed:.1f} W unattributed, expected {expected:.1f} W "
                f"(home {case.home} + stranded {stranded:.0f}); {case.describe()}"
            )
    _report(
        failures,
        len(cases),
        "Unattributed power must be exactly the home load plus any stranded draw.",
    )


def test_restrictions_are_honoured_whenever_a_feasible_allocation_exists() -> None:
    """A sink may only show a forbidden source when no valid allocation existed.

    This is the Hall-condition check: the engine reserves demand one sink at a
    time, which cannot see a group of sinks that is collectively captive. The
    max-flow oracle decides feasibility independently, so a violation here is a
    genuine counterexample -- a topology where honouring every restriction was
    possible and the attribution failed to.
    """
    failures = []
    cases = _cases()
    feasible = 0
    for case in cases:
        if not _is_feasible(case):
            continue  # configuration contradicts the meter: falling back is correct
        feasible += 1
        engine = Cell(case.topology, case.state).build_engine()
        for uid, row in engine.sink_adapters_source_shares.items():
            allowed = case.allowed.get(uid, ())
            if not allowed:
                continue
            leaked = {
                source_uid: share
                for source_uid, share in row.items()
                if share > TOL and source_uid not in allowed
            }
            if leaked:
                failures.append(
                    f"{uid} is restricted to {list(allowed)} but was attributed "
                    f"{ {k: round(v, 4) for k, v in leaked.items()} }; {case.describe()}"
                )
    assert feasible, "generator produced no feasible cases"
    _report(
        failures,
        feasible,
        "A restriction may only be broken when no allocation could have honoured it.",
    )
