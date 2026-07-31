"""Modules to calculate the grid status."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from enum import Enum
from typing import Any, Callable


_LOGGER = logging.getLogger(__name__)

UNIT_PREFIXES = {None: 1, "k": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}


class FlowRole(Enum):
    """The instantaneous power-flow role of an adapter.

    This is the *flow axis*: a per-snapshot classification derived purely from
    an adapter's current signed power, orthogonal to its static *identity* axis
    (grid / pv / battery / consumer). The engine's internal sign convention is
    uniform — positive power means the adapter is providing, negative means it
    is drawing — so a single rule classifies every adapter kind:

    * ``SOURCE`` — providing power now (grid import, PV producing, battery
      discharging).
    * ``SINK`` — drawing power now (grid export, PV standby, battery charging,
      consumer load).
    * ``IDLE`` — reading is exactly ``0`` W.
    * ``UNKNOWN`` — the power sensor is unavailable (``None``).
    """

    SOURCE = "source"
    SINK = "sink"
    IDLE = "idle"
    UNKNOWN = "unknown"


class AdapterContainer:
    """Container for adapters."""

    def __init__(self) -> None:
        """Initialize instance."""
        self.adapters = []
        self.uid_mapping = {}

    @property
    def source_entities(self) -> list[str]:
        """Return all source entities."""
        return self.source_entities_power

    @property
    def source_entities_power(self) -> list[str]:
        """Return the entities that affect power related attributes."""
        entities = []
        for adapter in self.adapters:
            entities += adapter.source_entities_power

        return entities

    @property
    def entity_mapping(self) -> dict:
        """Return the source entities mapped to the corresponding adapter."""
        mapping = {}
        for adapter in self.adapters:
            for entity in adapter.source_entities:
                mapping[entity] = adapter

        return mapping

    def __iter__(self):
        """Return iterator."""
        return iter(self.adapters)

    def add(self, adapter):
        """Add the given adapter."""
        self.adapters.append(adapter)

        self.uid_mapping[adapter.uid] = adapter

    # def get_by_key(self, uid: str):
    #     """Return the adapter by uid."""
    #     return self.uid_mapping.get(uid)


class PvSystemAdapters(AdapterContainer):
    """Container for production adapters."""

    pass


class BatteryAdapters(AdapterContainer):
    """Container for battery adapters."""

    pass


class ConsumerAdapters(AdapterContainer):
    """Container for production adapters."""

    pass



# --------------------------------------------------------------------------->
# TRANSPORTATION SOLVE (power provenance)
#
# Working out where each drawing adapter's power came from is a transportation
# problem on a bipartite graph: sources with a fixed output, sinks with a fixed
# draw, and forbidden pairings coming from the per-device source restrictions.
# It is normally *underdetermined* — many allocations satisfy the totals — so
# the solve has two jobs: find allocations that are valid at all (feasibility),
# and pick one specific allocation out of them (selection).
#
# Feasibility is a property of *groups*. A set of sinks can collectively exhaust
# the sources it is allowed while no single member is individually stuck, so any
# rule that reasons one sink at a time will eventually hand a source to a sink
# that had alternatives and strand one that had none. That is why these helpers
# use max flow: a minimum cut names the bottleneck group directly.
#
# They are pure functions over plain dicts, independent of the adapter objects,
# so the algorithm can be reasoned about on paper. See
# docs/dev/engine-calculations.md.
# --------------------------------------------------------------------------->

_EPS = 1e-9
#: Safety bound on the local-generation loop; it converges in a few passes.
_MAX_FILL_ROUNDS = 64
_FLOW_SRC = "\x00source"
_FLOW_DST = "\x00sink"
#: The unmetered home base load, as a sink in the solve. Never reported.
_HOME = "\x00home"
#: A restriction that permits *nothing*. The empty tuple already means the
#: opposite (unrestricted, the whole mix), so a sink that may draw no source at
#: all needs a non-empty restriction no real uid can match.
_NOTHING = ("\x00nothing",)


def _permits(sources: tuple[str, ...], source_uid: str) -> bool:
    """Whether a sink restricted to ``sources`` may draw ``source_uid``.

    An empty restriction means unrestricted — the whole mix.
    """
    return not sources or source_uid in sources


def _max_flow(capacity: dict, source: str, target: str) -> tuple[float, set]:
    """Edmonds-Karp max flow. Mutates ``capacity`` into the residual graph.

    Returns ``(value, reachable)``, where ``reachable`` is the set of nodes
    still reachable from ``source`` once no augmenting path is left — the source
    side of a minimum cut, and therefore the bottleneck the flow ran into.
    """
    total = 0.0
    while True:
        parent: dict[str, str | None] = {source: None}
        queue = [source]
        while queue and target not in parent:
            node = queue.pop(0)
            for nxt, cap in capacity.get(node, {}).items():
                if cap > _EPS and nxt not in parent:
                    parent[nxt] = node
                    queue.append(nxt)
        if target not in parent:
            return total, set(parent)

        path, node = [], target
        while parent[node] is not None:
            path.append((parent[node], node))
            node = parent[node]
        added = min(capacity[a][b] for a, b in path)
        for a, b in path:
            capacity[a][b] -= added
            capacity.setdefault(b, {})[a] = capacity.setdefault(b, {}).get(a, 0.0) + added
        total += added


def _flow_network(supply: dict, demand: dict, allowed: dict, skip=None) -> dict:
    """Build ``super-source -> sources -> sinks -> super-sink``.

    Source-to-sink edges are deliberately *uncapped*. Capping them at the sink's
    draw does not change the flow value — the sink's own edge already bounds it —
    but it saturates edges the minimum-cut extraction has to walk, which makes
    ``_tight_set`` silently report the wrong group.
    """
    unbounded = sum(supply.values()) + sum(demand.values()) + 1.0
    capacity: dict[str, dict[str, float]] = {_FLOW_SRC: {}, _FLOW_DST: {}}
    for source_uid, power in supply.items():
        capacity[_FLOW_SRC]["s:" + source_uid] = power
        capacity.setdefault("s:" + source_uid, {})
    for uid, draw in demand.items():
        capacity.setdefault("t:" + uid, {})[_FLOW_DST] = draw
        for source_uid in supply:
            if _permits(allowed[uid], source_uid) and (uid, source_uid) != skip:
                capacity["s:" + source_uid]["t:" + uid] = unbounded

    return capacity


def _flow_value(supply: dict, demand: dict, allowed: dict, skip=None) -> float:
    """Total draw servable from the allowed sources, optionally without one edge."""
    if not supply or not demand:
        return 0.0

    return _max_flow(_flow_network(supply, demand, allowed, skip), _FLOW_SRC, _FLOW_DST)[0]


def _exact_reserves(supply: dict, demand: dict, allowed: dict) -> dict | None:
    """Return ``{(sink, source): watts}`` the pairing must carry in *every* plan.

    Deleting one pairing and re-running the flow says how much of the total draw
    depended on it — Hall's condition asked of every group of sinks at once.
    The cheap approximation (a sink's draw minus what its *other* sources hold)
    is the same question asked of one sink at a time, and it cannot see a group
    that is collectively captive while no member is individually.

    ``None`` when the restrictions cannot all be honoured, so the caller falls
    back instead of reserving against an impossible plan.
    """
    wanted = sum(demand.values())
    if _flow_value(supply, demand, allowed) + _EPS < wanted:
        return None

    return {
        (uid, source_uid): max(
            0.0, wanted - _flow_value(supply, demand, allowed, (uid, source_uid))
        )
        for uid in demand
        for source_uid in supply
        if _permits(allowed[uid], source_uid)
    }


def _tight_set(supply: dict, demand: dict, allowed: dict) -> tuple:
    """Find a group of sinks that exactly exhausts every source it may use.

    Such a group has no freedom left, and no sink outside it may touch those
    sources, so it can be split off and solved on its own. Read off the minimum
    cut of a single max flow. Returns ``(None, None)`` when nothing binds.
    """
    if not supply or not demand:
        return None, None

    value, reachable = _max_flow(
        _flow_network(supply, demand, allowed), _FLOW_SRC, _FLOW_DST
    )
    if value + _EPS < sum(demand.values()):
        return None, None

    group = [uid for uid in demand if "t:" + uid not in reachable]
    if not group or len(group) == len(demand):
        return None, None

    sources = [s for s in supply if any(_permits(allowed[u], s) for u in group)]
    # The reachable set is a tight group only when that cut really is minimum;
    # verifying costs two sums and is cheaper than proving it.
    if abs(sum(demand[u] for u in group) - sum(supply[s] for s in sources)) > _EPS:
        return None, None

    return group, sources


def _fill_block(supply: dict, demand: dict, allowed: dict, grid_uid: str) -> tuple:
    """Serve restricted sinks from a block: grid first, then local generation.

    Per source, each claimant is first given the reserve it cannot obtain
    anywhere else; whatever is left over is split in proportion to the draw each
    claimant still has outstanding. Splitting proportionally (rather than
    serving claimants one at a time) is what makes two sinks with the same
    restriction come out with the same row whatever their draws.

    Returns ``(allocation, unused supply, deficit)``.
    """
    pool = dict(supply)
    outstanding = dict(demand)
    allocation = {uid: {s: 0.0 for s in supply} for uid in demand}

    def local(uid):
        return [s for s in pool if s != grid_uid and _permits(allowed[uid], s)]

    def reserves():
        live_demand = {u: n for u, n in outstanding.items() if n > _EPS}
        live_supply = {s: p for s, p in pool.items() if p > _EPS}
        if not live_demand or not live_supply:
            return {}
        found = _exact_reserves(live_supply, live_demand, allowed)
        return {} if found is None else found

    def serve(source_uid, claimants, reserved):
        """Give out one source: reserves first, remainder proportional to draw."""
        total_reserved = sum(reserved.values())
        if total_reserved > pool[source_uid]:
            scale = pool[source_uid] / total_reserved
            reserved = {u: r * scale for u, r in reserved.items()}
        spare = pool[source_uid] - sum(reserved.values())
        rest = {u: outstanding[u] - reserved[u] for u in claimants}
        total_rest = sum(rest.values())
        return {
            u: reserved[u] + (spare * rest[u] / total_rest if total_rest else 0.0)
            for u in claimants
        }

    def commit(uid, offers):
        """Take the offers, scaled down if they exceed what the sink still needs."""
        wanted = sum(offers.values())
        if wanted <= _EPS:
            return False
        scale = min(1.0, outstanding[uid] / wanted)
        moved = False
        for source_uid, offer in offers.items():
            taken = min(offer * scale, pool[source_uid])
            if taken <= _EPS:
                continue
            allocation[uid][source_uid] += taken
            pool[source_uid] -= taken
            outstanding[uid] -= taken
            moved = True

        return moved

    # The grid is the balancing node rather than a generator, so a restricted
    # sink that is allowed it draws it before competing for local generation.
    if pool.get(grid_uid, 0.0) > _EPS:
        claimants = [
            uid for uid in demand
            if allowed[uid] and grid_uid in allowed[uid] and outstanding[uid] > _EPS
        ]
        if claimants:
            found = reserves()
            reserved = {
                uid: found.get(
                    (uid, grid_uid),
                    max(0.0, outstanding[uid] - sum(pool[s] for s in local(uid))),
                )
                for uid in claimants
            }
            offers = serve(grid_uid, claimants, reserved)
            for uid in claimants:
                commit(uid, {grid_uid: offers[uid]})

    # Local generation. Repeated because a sink capped at its own draw frees up
    # supply the others can still claim.
    for _ in range(_MAX_FILL_ROUNDS):
        active = [
            uid for uid in demand
            if allowed[uid] and outstanding[uid] > _EPS
            and any(pool[s] > _EPS for s in local(uid))
        ]
        if not active:
            break

        found = reserves()
        offers = {uid: {} for uid in active}
        for source_uid in supply:
            if source_uid == grid_uid or pool[source_uid] <= _EPS:
                continue
            claimants = [uid for uid in active if source_uid in local(uid)]
            if not claimants:
                continue
            reserved = {
                uid: found.get(
                    (uid, source_uid),
                    max(
                        0.0,
                        outstanding[uid]
                        - sum(pool[s] for s in local(uid) if s != source_uid),
                    ),
                )
                for uid in claimants
            }
            for uid, offer in serve(source_uid, claimants, reserved).items():
                offers[uid][source_uid] = offer

        # Every sink commits; ``any`` over a generator would short-circuit and
        # silently skip the rest of the round.
        moved = [commit(uid, offers[uid]) for uid in active]
        if not any(moved):
            break

    deficit = {
        uid: outstanding[uid]
        for uid in demand
        if allowed[uid] and outstanding[uid] > _EPS
    }
    return allocation, pool, deficit


def _allocate(supply: dict, demand: dict, allowed: dict, grid_uid: str) -> tuple:
    """Attribute every sink's draw to sources. Returns ``(allocation, deficit)``.

    Restricted sinks are served first, because they are the ones feasibility can
    strand; unrestricted sinks (including the home base load) take whatever is
    left, which they can always do. Before serving a group, any *tight* subset
    is split off and solved on its own — that group has no freedom, and leaving
    it in would let a flexible sink take supply the group needed.
    """
    restricted = {uid: d for uid, d in demand.items() if allowed[uid]}
    flexible = {uid: d for uid, d in demand.items() if not allowed[uid]}
    allocation = {uid: {s: 0.0 for s in supply} for uid in demand}
    deficit: dict[str, float] = {}
    unused = []

    blocks = [(dict(supply), restricted)]
    while blocks:
        block_supply, block_demand = blocks.pop()
        if not block_demand:
            unused.append(block_supply)
            continue

        group, sources = _tight_set(block_supply, block_demand, allowed)
        if group is None:
            served, spare, short = _fill_block(
                block_supply, block_demand, allowed, grid_uid
            )
            for uid, row in served.items():
                for source_uid, watts in row.items():
                    allocation[uid][source_uid] += watts
            deficit.update(short)
            unused.append(spare)
            continue

        blocks.append(({s: block_supply[s] for s in sources},
                       {u: block_demand[u] for u in group}))
        blocks.append(({s: p for s, p in block_supply.items() if s not in sources},
                       {u: d for u, d in block_demand.items() if u not in group}))

    remaining = {s: 0.0 for s in supply}
    for spare in unused:
        for source_uid, watts in spare.items():
            remaining[source_uid] += watts

    # Unrestricted sinks share what is left, and so does any restricted draw its
    # own sources could not cover — the configuration and the meter disagree, so
    # the restriction is relaxed as a last resort rather than leaving watts
    # unattributed. ``deficit`` records exactly how much that was.
    tail = dict(flexible)
    for uid, watts in deficit.items():
        tail[uid] = tail.get(uid, 0.0) + watts
    available = sum(remaining.values())
    if available > _EPS:
        for uid, draw in tail.items():
            for source_uid in supply:
                allocation[uid][source_uid] += draw * remaining[source_uid] / available

    return allocation, deficit


class PowerInsight:
    """Class used for the calculation of the power insights."""

    def __init__(self) -> None:
        """Initialize instance."""
        # Exactly one grid per entry, by design: one config entry models one
        # energy mix at a single grid connection. Multiple grid connections are
        # modelled as multiple config entries, so this stays a singular slot
        # (the config flow enforces it via the ``grid_already_configured`` guard).
        self.grid_adapter = None
        self.pv_system_adapters = PvSystemAdapters()
        self.storage_adapters = BatteryAdapters()
        self.consumer_adapters = ConsumerAdapters()

        # Snapshot cache. Results are pure functions of the stored readings and
        # the registered adapters, so anything derived from them stays valid
        # until one of those changes. ``_revision`` counts those changes;
        # ``_snapshot_cached`` memoises against it. See ``set_value``.
        self._revision = 0
        self._cache: dict[str, Any] = {}
        self._cache_revision = -1

    def _snapshot_cached(self, key: str, compute: Callable[[], Any]) -> Any:
        """Return ``compute()`` for this snapshot, computing it at most once.

        The engine is lazy and holds no state between reads, so every sensor
        entity that reads a property recomputes the whole chain behind it — and
        a typical install has dozens of them reading on every event. Anything
        expensive enough to matter goes through here.

        The cache is dropped whole whenever a reading or the adapter set
        changes, so a stale entry cannot outlive the snapshot it belongs to.
        """
        if self._cache_revision != self._revision:
            self._cache.clear()
            self._cache_revision = self._revision
        if key not in self._cache:
            self._cache[key] = compute()

        return self._cache[key]

    @property
    def entity_mapping(self) -> dict:
        """Return the adapters by it's uid."""
        mapping = {}
        for entity in self.grid_adapter.source_entities:
            mapping[entity] = self.grid_adapter

        mapping.update(self.pv_system_adapters.entity_mapping)
        mapping.update(self.storage_adapters.entity_mapping)
        mapping.update(self.consumer_adapters.entity_mapping)

        return mapping

    @property
    def uid_mapping(self) -> dict:
        """Return the adapters by it's uid."""
        mapping = {
            self.grid_adapter.uid: self.grid_adapter
        }

        mapping.update(self.pv_system_adapters.uid_mapping)
        mapping.update(self.storage_adapters.uid_mapping)
        mapping.update(self.consumer_adapters.uid_mapping)

        return mapping

    # ------------------->
    # ADAPTER HELPERS --->
    # ------------------->

    @property
    def prod_adapters(self) -> list[str]:
        """Return the power producing adatpers."""
        return (
            self.pv_system_adapters.adapters
            + self.storage_adapters.adapters
        )

    @property
    def gross_power_adapters(self) -> list[BasePowerAdapter]:
        """Return the adapters that provide power."""
        return (
            [self.grid_adapter]
            + self.pv_system_adapters.adapters
            + self.storage_adapters.adapters
        )

    # ------------------------------------------------------------------>
    # FLOW VIEW (dynamic source / sink / grid grouping)
    #
    # A per-snapshot partition of the adapters by their current FlowRole,
    # orthogonal to the static identity containers above. Membership follows
    # each adapter's signed power (see FlowRole): a battery is a source while
    # discharging and a sink while charging; a PV is a source while producing
    # and a sink while drawing standby. The grid is the balancing node and is
    # always kept in its own group regardless of direction. Adapters that are
    # IDLE (0 W) or UNKNOWN (sensor unavailable) fall into neither source nor
    # sink, mirroring the engine's None-propagation elsewhere.
    #
    # source_adapters / sink_adapters are the grid-inclusive groups — every
    # adapter power is currently drawn from / flows to — with the grid folded
    # in direction-aware (import -> source, export -> sink) so the two stay
    # disjoint. local_source_adapters / local_sink_adapters are their
    # behind-the-meter subsets (grid excluded).
    #
    # The gross-power split and provenance results below build on these groups;
    # the existing prod_adapters_* / storage_adapters_* / cons_adapters_*
    # families remain the source of truth for all other current results.
    # ------------------------------------------------------------------>

    @property
    def _non_grid_adapters(self) -> list[BasePowerAdapter]:
        """Return every non-grid adapter (the flow-view candidate pool)."""
        return (
            self.pv_system_adapters.adapters
            + self.storage_adapters.adapters
            + self.consumer_adapters.adapters
        )

    @property
    def grid_adapters(self) -> list[BasePowerAdapter]:
        """Return the grid adapters as their own flow group.

        The grid is the balancing node, so it stays in a dedicated group
        whether it is currently importing (source) or exporting (sink). Modelled
        as a list to mirror ``source_adapters`` / ``sink_adapters``, even though
        the engine holds exactly one grid.
        """
        return [self.grid_adapter]

    @property
    def local_source_adapters(self) -> list[BasePowerAdapter]:
        """Return the behind-the-meter adapters currently providing power.

        Producing PV systems and discharging batteries (grid excluded). The
        grid-inclusive superset is ``source_adapters``.
        """
        return [
            adapter for adapter in self._non_grid_adapters
            if adapter.flow_role is FlowRole.SOURCE
        ]

    @property
    def local_sink_adapters(self) -> list[BasePowerAdapter]:
        """Return the behind-the-meter adapters currently drawing power.

        Charging batteries, consumer loads, and PV systems drawing standby
        (grid excluded). The grid-inclusive superset is ``sink_adapters``.
        """
        return [
            adapter for adapter in self._non_grid_adapters
            if adapter.flow_role is FlowRole.SINK
        ]

    @property
    def source_adapters(self) -> list[BasePowerAdapter]:
        """Return every adapter currently providing power, grid included.

        The grid-inclusive provider group: everything power is currently drawn
        *from* this snapshot (grid import, producing PV, discharging batteries).
        The grid is folded in direction-aware — it joins only while importing
        (``FlowRole.SOURCE``) — so ``source_adapters`` and ``sink_adapters`` stay
        disjoint and the grid is never counted on both sides. The behind-the-
        meter subset is ``local_source_adapters``.
        """
        grid = (
            [self.grid_adapter]
            if self.grid_adapter.flow_role is FlowRole.SOURCE
            else []
        )
        return grid + self.local_source_adapters

    @property
    def sink_adapters(self) -> list[BasePowerAdapter]:
        """Return every adapter currently drawing power, grid included.

        The grid-inclusive drawer group: everywhere power currently flows *to*
        this snapshot (grid export, charging batteries, consumer loads, PV
        standby). The grid is folded in direction-aware — it joins only while
        exporting (``FlowRole.SINK``) — so ``source_adapters`` and
        ``sink_adapters`` stay disjoint and the grid is never counted on both
        sides. The behind-the-meter subset is ``local_sink_adapters``.
        """
        grid = (
            [self.grid_adapter]
            if self.grid_adapter.flow_role is FlowRole.SINK
            else []
        )
        return grid + self.local_sink_adapters

    # -------------------------------------------------------------->
    # SOURCE ENTITIES
    # -------------------------------------------------------------->

    @property
    def source_entities(self) -> list[str]:
        """Return every source entity across all adapters."""
        pass

    @property
    def source_entities_power(self) -> list[str]:
        """Return every entity that affects a power result."""
        pass

    @property
    def source_entities_price(self) -> list[str]:
        """Return every entity that affects a price result."""
        pass

    @property
    def source_entities_co2(self) -> list[str]:
        """Return every entity that affects a CO2 result."""
        pass

    # -------------------------------------------------------------->
    # COMBINED POWER VALUES
    # -------------------------------------------------------------->

    @property
    def combined_grid_import(self) -> float | None:
        """Power imported from the grid (W)."""
        return self.grid_adapter.import_power

    @property
    def combined_grid_export(self) -> float | None:
        """Power exported to the grid (W)."""
        return self.grid_adapter.export_power

    @property
    def combined_production(self) -> float | None:
        """Total power generated by the PV adapters (W)."""
        return self._sum_or_none(a.production for a in self.pv_system_adapters)

    @property
    def combined_charging_power(self) -> float | None:
        """Total power charged by the battery adapters (W).

        The batteries' sink-side draw: each battery's ``consumption`` (its
        unsigned charging power), summed. This is the CHG channel total.
        """
        return self._sum_or_none(a.consumption for a in self.storage_adapters)

    @property
    def combined_discharging_power(self) -> float | None:
        """Total power discharged by the battery adapters (W).

        The batteries' source-side output: each battery's ``production`` (its
        unsigned discharge power), summed.
        """
        return self._sum_or_none(a.production for a in self.storage_adapters)

    @property
    def combined_standby_power(self) -> float | None:
        """Total standby power drawn by the PV adapters (W).

        The PV systems' sink-side draw: each PV's ``consumption`` (its night /
        standby draw), summed. This is the STB channel total.
        """
        return self._sum_or_none(a.consumption for a in self.pv_system_adapters)

    @property
    def combined_consumption(self) -> float | None:
        """Self-consumed power: gross minus export, charging and standby (W).

        The CON channel is computed as the residual of the other three channels
        rather than by summing consumer adapters, so it captures the *unmetered
        home base load* alongside the metered consumer loads. Clamped at ``0`` —
        mirroring the ``home_share`` floor in ``sink_adapters_source_shares`` —
        so sensor noise can never surface a negative self-consumption. Returns
        ``None`` whenever gross power is unavailable.
        """
        gross = self.gross_power
        export = self.combined_grid_export
        charging = self.combined_charging_power
        standby = self.combined_standby_power
        if None in (gross, export, charging, standby):
            return None

        return max(0.0, gross - export - charging - standby)

    @property
    def source_adapters_power(self) -> tuple[list[float], list[str]]:
        """Return ``(signed power list, uid index)`` for the source adapters.

        Source adapters are all currently providing (grid import, producing PV,
        discharging batteries), so every reading is positive. A ``None`` entry
        never occurs: an unavailable sensor makes an adapter ``UNKNOWN``, which
        excludes it from the group.
        """
        arr = []
        index = []

        for adapter in self.source_adapters:
            index.append(adapter.uid)
            arr.append(adapter.power)

        return arr, index

    @property
    def sink_adapters_power(self) -> tuple[list[float], list[str]]:
        """Return ``(signed power list, uid index)`` for the sink adapters.

        Sink adapters are all currently drawing (grid export, charging
        batteries, consumer loads, PV standby), so every reading is negative.
        """
        arr = []
        index = []

        for adapter in self.sink_adapters:
            index.append(adapter.uid)
            arr.append(adapter.power)

        return arr, index

    @property
    def gross_power(self) -> float | None:
        """Total power entering the system (W): grid import + PV + discharge.

        Equal to the sum of the source-adapter readings. Returns ``None`` when
        any inflow-capable adapter (grid / PV / battery) has an unavailable
        power sensor, since the total would then be unreliable — a consumer
        sensor dropping out does not affect it.
        """
        for adapter in self.gross_power_adapters:
            if adapter.power is None:
                return None

        power_arr, _ = self.source_adapters_power
        return float(sum(power_arr))

    @property
    def source_adapters_gross_power_shares(self) -> tuple[list[float], list[str]]:
        """Return ``(share list, uid index)`` — each source's fraction of gross power.

        The shares of the currently-providing adapters (grid import, producing
        PV, discharging batteries); they sum to 1. Returns an empty list and
        index when gross power is unavailable. Mirrors ``source_adapters_power``
        so the two stay positionally aligned.
        """
        gross = self.gross_power
        if gross is None:
            return [], []

        power_arr, index = self.source_adapters_power
        if gross == 0.0:
            return [0.0] * len(index), index

        return [power / gross for power in power_arr], index

    @property
    def sink_adapters_gross_power_shares(self) -> tuple[list[float], list[str]]:
        """Return ``(share list, uid index)`` — each sink's fraction of gross power.

        The shares of the currently-drawing adapters (grid export, charging
        batteries, consumer loads, PV standby); the readings are unsigned here.
        Unlike the source shares these need not sum to 1: the remainder up to 1
        is the unmetered home load. Returns an empty list and index when gross
        power is unavailable.
        """
        gross = self.gross_power
        if gross is None:
            return [], []

        power_arr, index = self.sink_adapters_power
        if gross == 0.0:
            return [0.0] * len(index), index

        return [abs(power) / gross for power in power_arr], index

    @property
    def _source_allocation(self) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
        """Solve this snapshot's provenance once: ``(allocation, deficit)``.

        ``allocation`` is ``{sink_uid: {source_uid: watts}}`` covering every
        drawing adapter; ``deficit`` is ``{sink_uid: watts}`` for the restricted
        sinks whose own allowed sources could not cover their draw.

        The unmetered home base load takes part in the solve as an ordinary
        unrestricted sink — it competes for power like anything else — but it
        has no adapter, so it never appears in the result.
        """
        return self._snapshot_cached("source_allocation", self._solve_source_allocation)

    def _allowed_source_uids(self, adapter) -> tuple[str, ...]:
        """Return the source uids ``adapter`` may draw from as a sink.

        For an ordinary sink this is its configured restriction (a battery's
        ``charge_from_adapters``, a consumer's ``power_from_adapters``), empty
        meaning unrestricted.

        The exporting grid is the exception: it may only draw the sources that
        are allowed to feed it. ``exports_power`` is a property of the device or
        its control software — a German home battery generally may not feed the
        public grid at all — not a preference about who gets compensated, so a
        device that cannot export cannot supply the EXP channel either. When
        nothing at all may export, the restriction becomes ``_NOTHING`` rather
        than the empty tuple, which would read as "unrestricted" and reopen the
        whole mix.
        """
        if adapter is not self.grid_adapter:
            return tuple(adapter.power_source_uids)

        exporters = tuple(
            source.uid for source in self.source_adapters
            if getattr(source, "exports_power", False)
        )
        return exporters or _NOTHING

    def _solve_source_allocation(self) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
        """Do the work behind ``_source_allocation``; call that, not this."""
        gross = self.gross_power
        if gross is None:
            return {}, {}

        power_arr, index = self.source_adapters_power
        if not index:
            # Nothing is currently providing; provenance is undefined.
            return {}, {}

        supply = {uid: float(power) for uid, power in zip(index, power_arr)}
        demand: dict[str, float] = {}
        allowed: dict[str, tuple[str, ...]] = {}
        for adapter in self.sink_adapters:
            demand[adapter.uid] = abs(float(adapter.power))
            allowed[adapter.uid] = self._allowed_source_uids(adapter)

        # A sink restricted to sources that are all idle has nothing to be
        # attributed to. It collapses to an all-zeros row rather than being
        # forced onto sources the user excluded — but its draw still came from
        # somewhere, so it stays in the home remainder below.
        demand_by_uid = dict(demand)
        stranded = [
            uid for uid, sources in allowed.items()
            if sources and not any(_permits(sources, s) for s in supply)
        ]
        for uid in stranded:
            del demand[uid]
            del allowed[uid]

        demand[_HOME] = max(0.0, gross - sum(demand.values()))
        allowed[_HOME] = ()

        allocation, deficit = _allocate(
            supply, demand, allowed, self.grid_adapter.uid
        )
        allocation.pop(_HOME, None)
        for uid in stranded:
            allocation[uid] = {source_uid: 0.0 for source_uid in supply}
            # Not one watt of it could come from a configured source, so the
            # whole draw is a deficit even though the row says nothing.
            deficit[uid] = demand_by_uid[uid]

        return allocation, deficit

    @property
    def sink_adapters_source_shares(self) -> dict[str, dict[str, float]]:
        """Return ``{sink_uid: {source_uid: share}}`` — each sink's power provenance.

        For every currently-drawing adapter, the fraction of its power supplied
        by each source adapter (grid import, producing PV, discharging
        batteries). Each row sums to 1, or to 0 when every source the sink is
        allowed happens to be idle.

        Two guarantees hold for every snapshot, and are checked over random
        topologies by ``tests/engine/test_source_shares_invariants.py``:

        * **Sources balance.** The watts attributed to a source across all sinks
          equal its reading. No source is over-drawn and none is left over.
        * **Restrictions hold whenever they can.** A sink is only ever shown a
          source outside its configured set when *no* allocation could have
          honoured every restriction at once. How much that was is reported by
          ``sink_adapters_restriction_deficit``.

        Beyond those, the allocation is chosen so that a restricted sink allowed
        the grid draws the grid before local generation (the grid is the
        balancing node; local generation is the scarce thing worth attributing),
        and so that sinks competing for the same scarce source split it in
        proportion to their draw — which means two sinks with the same
        restriction always get the same row, whatever their draws.

        Empty when gross power is unavailable or nothing is providing. See
        ``docs/dev/engine-calculations.md`` for the model.
        """
        allocation, _ = self._source_allocation

        shares = {}
        for uid, row in allocation.items():
            total = sum(row.values())
            shares[uid] = {
                source_uid: (watts / total if total > _EPS else 0.0)
                for source_uid, watts in row.items()
            }

        return shares

    @property
    def sink_adapters_restriction_deficit(self) -> dict[str, float]:
        """Return ``{sink_uid: watts}`` drawn from outside a sink's allowed sources.

        Zero almost always. A non-zero figure is never an engine failure — the
        configured sources are a statement about how the user believes their
        energy manager behaves, so it means the meter disagrees with that
        belief: either the manager did something else this snapshot (a "PV only"
        battery topping up off the grid under cloud), or the configuration is
        stale. Reported per sink so the mix it explains sits next to it.

        Only restricted sinks appear; an unrestricted sink cannot have one.
        """
        _, deficit = self._source_allocation

        return deficit


    # -------------------------------------------------------------->
    # GROSS POWER RATIOS
    # -------------------------------------------------------------->

    # The four channels partition gross power (EXP / CON / CHG / STB), so these
    # ratios sum to 1 whenever every input is available. Each is simply the
    # channel's combined power over gross power.

    @property
    def gross_power_export_ratio(self) -> float | None:
        """Fraction of gross power returned to the grid."""
        return self._gross_ratio(self.combined_grid_export)

    @property
    def gross_power_consumption_ratio(self) -> float | None:
        """Fraction of gross power self-consumed."""
        return self._gross_ratio(self.combined_consumption)

    @property
    def gross_power_standby_ratio(self) -> float | None:
        """Fraction of gross power used as adapter standby."""
        return self._gross_ratio(self.combined_standby_power)

    @property
    def gross_power_charging_ratio(self) -> float | None:
        """Fraction of gross power charged into storage."""
        return self._gross_ratio(self.combined_charging_power)

    # -------------------------------------------------------------->
    # APPLICABLE GROSS POWER RATIOS
    # -------------------------------------------------------------->

    @property
    def gross_power_applicable_consumption_ratio(self) -> float | None:
        """Self-consumption ratio excluding export and charging.

        Of the *applicable* gross power — what is left once export and charging
        are set aside (``gross − export − charging``, i.e. consumption plus
        standby) — the fraction that is actually self-consumed. It answers "of
        the power that stayed home and was not stored, how much did I use rather
        than lose to standby?", so it reads 1.0 with no standby draw.
        """
        gross = self.gross_power
        export = self.combined_grid_export
        charging = self.combined_charging_power
        consumption = self.combined_consumption
        if None in (gross, export, charging, consumption):
            return None

        return self._divide(consumption, gross - export - charging)

    # -------------------------------------------------------------->
    # COMBINED MONETARY RATES
    # -------------------------------------------------------------->

    @property
    def combined_export_compensation_rate(self) -> float | None:
        """Combined export compensation rate (EUR/h)."""
        pass

    @property
    def combined_avoided_cost_rate(self) -> float | None:
        """Combined avoided-cost rate from self-consumption (EUR/h)."""
        pass

    @property
    def combined_coe_rate(self) -> float | None:
        """Combined cost-of-electricity rate (EUR/h)."""
        pass

    @property
    def combined_lcoe_rate(self) -> float | None:
        """Combined levelized cost-of-electricity rate (EUR/h)."""
        pass

    @property
    def combined_coo_rate(self) -> float | None:
        """Combined cost-of-operations rate (EUR/h)."""
        pass

    @property
    def combined_lcoo_rate(self) -> float | None:
        """Combined levelized cost-of-operations rate (EUR/h)."""
        pass

    @property
    def combined_saving_rate(self) -> float | None:
        """Combined cost-saving rate (EUR/h)."""
        pass

    @property
    def combined_levelized_saving_rate(self) -> float | None:
        """Combined levelized cost-saving rate (EUR/h)."""
        pass

    @property
    def combined_lcoe_rate_corrected(self) -> float | None:
        """Combined levelized cost rate with per-adapter correction applied."""
        pass

    @property
    def combined_lcoo_rate_corrected(self) -> float | None:
        """Combined levelized operating-cost rate with correction applied."""
        pass

    @property
    def combined_levelized_saving_rate_corrected(self) -> float | None:
        """Combined levelized saving rate with correction applied."""
        pass

    @property
    def combined_financial_return_rate(self) -> float | None:
        """Combined financial return rate (savings + export compensation)."""
        pass

    @property
    def combined_levelized_financial_return_rate(self) -> float | None:
        """Combined levelized financial return rate (base)."""
        pass

    @property
    def combined_levelized_financial_return_rate_corrected(self) -> float | None:
        """Combined levelized financial return rate with correction applied."""
        pass

    @property
    def levelized_correction_factors(self) -> dict[str, float]:
        """Return uid -> correction_factor for prod adapters with an LCOE."""
        pass

    # -------------------------------------------------------------->
    # COMBINED PRICES
    # -------------------------------------------------------------->

    @property
    def combined_coe(self) -> float | None:
        """Combined cost of electricity (EUR/kWh)."""
        pass

    @property
    def combined_lcoe(self) -> float | None:
        """Combined levelized cost of electricity (EUR/kWh)."""
        pass

    # -------------------------------------------------------------->
    # SOURCE ADAPTERS
    # -------------------------------------------------------------->

    # The provider side, keyed by source uid (grid import, producing PV,
    # discharging battery). The share of gross power each source supplies is
    # source_adapters_gross_power_shares (foundation, above).

    @property
    def source_adapters_export_power(self) -> dict:
        """Watts of each source's output that is exported."""
        pass

    @property
    def source_adapters_export_shares(self) -> dict:
        """Each source's share of total exported power."""
        pass

    @property
    def source_adapters_export_ratios(self) -> dict:
        """Fraction of each source's output that is exported."""
        pass

    @property
    def source_adapters_consumption_power(self) -> dict:
        """Watts of each source's output that is self-consumed."""
        pass

    @property
    def source_adapters_consumption_shares(self) -> dict:
        """Each source's share of total self-consumption."""
        pass

    @property
    def source_adapters_consumption_ratios(self) -> dict:
        """Fraction of each source's output that is self-consumed."""
        pass

    @property
    def source_adapters_charging_power(self) -> dict:
        """Watts of each source's output that goes to battery charging."""
        pass

    @property
    def source_adapters_charging_shares(self) -> dict:
        """Each source's share of total charging power."""
        pass

    @property
    def source_adapters_charging_ratios(self) -> dict:
        """Fraction of each source's output that goes to charging."""
        pass

    @property
    def source_adapters_standby_power(self) -> dict:
        """Watts of each source's output that goes to device standby."""
        pass

    @property
    def source_adapters_standby_shares(self) -> dict:
        """Each source's share of total standby power."""
        pass

    @property
    def source_adapters_standby_ratios(self) -> dict:
        """Fraction of each source's output that goes to standby."""
        pass

    @property
    def source_adapters_coe_rate(self) -> dict:
        """Cost-of-electricity rate per source (EUR/h)."""
        pass

    @property
    def source_adapters_lcoe_rate(self) -> dict:
        """Levelized cost-of-electricity rate per source (EUR/h)."""
        pass

    @property
    def source_adapters_coo_rates(self) -> dict:
        """Cost-of-operations rate per source (EUR/h)."""
        pass

    @property
    def source_adapters_lcoo_rates(self) -> dict:
        """Levelized cost-of-operations rate per source (EUR/h)."""
        pass

    @property
    def source_adapters_export_compensation_rates(self) -> dict:
        """Export compensation rate per source (EUR/h)."""
        pass

    @property
    def source_adapters_avoided_cost_rates(self) -> dict:
        """Avoided-cost rate per source (EUR/h)."""
        pass

    @property
    def source_adapters_cost_saving_rates(self) -> dict:
        """Cost-saving rate per source (EUR/h)."""
        pass

    @property
    def source_adapters_levelized_cost_saving_rates(self) -> dict:
        """Levelized cost-saving rate per source (EUR/h)."""
        pass

    @property
    def source_adapters_financial_return_rates(self) -> dict:
        """Financial return rate per source (EUR/h)."""
        pass

    @property
    def source_adapters_levelized_financial_return_rates(self) -> dict:
        """Levelized financial return rate per source (EUR/h)."""
        pass

    @property
    def source_adapters_dynamic_coe(self) -> dict[str, float | None]:
        """Blended cost of electricity per source (EUR/kWh); batteries use their charge mix."""
        pass

    @property
    def source_adapters_dynamic_lcoe(self) -> dict[str, float | None]:
        """Blended levelized cost of electricity per source (EUR/kWh)."""
        pass

    # -------------------------------------------------------------->
    # SINK ADAPTERS
    # -------------------------------------------------------------->

    # The drawer side, keyed by sink uid (grid export, charging battery, PV
    # standby, consumer load). Where each sink's power comes from is
    # sink_adapters_source_shares (foundation, above).

    @property
    def sink_adapters_consumption_shares(self) -> dict:
        """Each consuming sink's share of total self-consumption."""
        pass

    @property
    def sink_adapters_coo_rates(self) -> dict:
        """Cost-of-operations rate per sink (EUR/h)."""
        pass

    @property
    def sink_adapters_lcoo_rates(self) -> dict:
        """Levelized cost-of-operations rate per sink (EUR/h)."""
        pass

    #
    # Utility methods
    #

    def get_adapter_by_entity(self, entity: str) -> AbstractBaseAdapter | None:
        """Return the adapter that corresponds to the entity."""
        return self.entity_mapping.get(entity)

    def get_adapter_by_uid(self, uid: str):
        return self.uid_mapping.get(uid)

    def set_value(self, entity_id: str, new_value: float | None) -> bool:
        """Update the value of the given entity_id to new_value.

        Returns True if the stored value changed, False if it was already
        identical.  EventHandler uses this to suppress unnecessary custom events
        when a source entity fires state_changed but the numeric value is the same.
        """
        adapter = self.get_adapter_by_entity(entity_id)
        if adapter is None:
            return False

        changed = adapter.set_value(entity_id, new_value)
        if changed:
            # A new snapshot: everything derived from the old one is stale.
            self._revision += 1

        return changed

    def register_adapter(self, adapter) -> None:
        """Register an adapter."""
        # The adapter set is an input to every result, so adding one invalidates
        # the snapshot just as a new reading does.
        self._revision += 1
        if isinstance(adapter, GridAdapter):
            self.grid_adapter = adapter
            _LOGGER.debug(f"Registered Grid adapter: {adapter}.")

        elif isinstance(adapter, PvAdapter):
            self.pv_system_adapters.add(adapter)
            _LOGGER.debug(f"Registered PV-System adapter: {adapter}.")

        elif isinstance(adapter, BatteryAdapter):
            self.storage_adapters.add(adapter)
            _LOGGER.debug(f"Registered Battery adapter: {adapter}.")

        elif isinstance(adapter, BaseConsumerAdapter):
            self.consumer_adapters.add(adapter)
            _LOGGER.debug(f"Registered consumption adapter: {adapter}.")

        else:
            raise ValueError(f"Error registering adapter `{adapter}`.")

    def _sum_or_none(self, values) -> float | None:
        """Sum ``values``, propagating ``None`` (an unavailable input).

        Returns ``0.0`` for an empty iterable (a container with no adapters),
        and ``None`` as soon as any value is ``None`` — so a whole-home total
        goes unavailable if any of its contributing sensors does.
        """
        total = 0.0
        for value in values:
            if value is None:
                return None
            total += value

        return total

    def _gross_ratio(self, numerator: float | None) -> float | None:
        """Return ``numerator / gross_power``, propagating unavailability.

        ``None`` when either operand is unavailable; ``0.0`` when gross power is
        zero (guarded by ``_divide``). Shared by the ``gross_power_*_ratio``
        channel properties.
        """
        gross = self.gross_power
        if numerator is None or gross is None:
            return None

        return self._divide(numerator, gross)

    def _to_kilo(self, power: float) -> float:
        """Convert the value into the kilo prefix."""
        if power == 0.0:
            return 0.0

        return power / 1000

    def _divide(self, to_divide: float, divide_by: float) -> float:
        """Divide ``to_divide`` by ``divide_by``, guarding both operands.

        Returns ``0.0`` when the numerator is zero or the denominator is zero
        (or falsy). Guarding the denominator prevents ``ZeroDivisionError`` in
        the ratio properties for degenerate states — e.g. a pure grid-export
        reading where ``gross_power`` is ``0.0`` while ``grid_export > 0``.
        """
        if to_divide == 0.0 or not divide_by:
            return 0.0

        return to_divide / divide_by





class AbstractBaseAdapter(ABC):
    """Abstract base adapter."""

    def __init__(self, unique_id, verbose_name, **kwargs) -> None:
        """Initialize base adapter."""
        self.uid = unique_id
        self.verbose_name = verbose_name
        self._values = {}

    @property
    def correction_factor(self) -> float:
        """Return the levelized-cost correction factor (1.0 unless overridden).

        Adapters with an editable lifetime cost (PV/battery) override this with
        ``current_lcoe / default_lcoe``. The factor is time-constant, so it can
        be applied to an accumulated base total to retroactively rescale it.
        """
        return 1.0

    @property
    def power_source_uids(self) -> list[str]:
        """Return the source uids this adapter is restricted to draw power from.

        An empty list means unrestricted (the adapter draws from the whole
        source mix). Only battery and smart-plug consumer adapters override this
        to expose their configured restriction; every other adapter kind stays
        unrestricted. Consumed by ``PowerInsight.sink_adapters_source_shares``
        to give restricted sinks first pick of their allowed sources.

        The config flow surfaces the empty-vs-restricted choice as an explicit
        "whole mix" / "specific devices" mode, but the engine only ever sees the
        resulting list: empty is the whole mix, non-empty is the restriction.
        """
        return []

    # @property
    # def source_entities(self) -> list[str]:
    #     """Return the source entities for this adapter."""
    #     return (
    #         self.source_entities_power
    #         + self.source_entities_price
    #         + self.source_entities_co2
    #     )

    # @property
    # @abstractmethod
    # def source_entities_power(self) -> list[str]:
    #     """Return the source price entities for this adapter."""
    #     pass

    # @property
    # @abstractmethod
    # def source_entities_price(self) -> list[str]:
    #     """Return the source power entities for this adapter."""
    #     pass

    # @property
    # @abstractmethod
    # def source_entities_co2(self) -> list[str]:
    #     """Return the source co2 entities for this adapter."""
    #     pass

    def set_value(self, entity_id, value) -> bool:
        """Set the value for an entity, returning True if it changed."""
        changed = self._values.get(entity_id) != value
        self._values[entity_id] = value
        return changed


class BasePowerAdapter(AbstractBaseAdapter):
    """Base class representing a power adapter."""

    def __init__(
        self,
        unique_id: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool = False,
        **kwargs,
    ) -> None:
        """Initialize power adapter."""
        super().__init__(unique_id, verbose_name, **kwargs)

        self._power_entity = power_entity
        self._invert_power = power_entity_inverted
        self._values[power_entity] = None

    @property
    def source_entities(self) -> list[str]:
        """Return the source entities for this adapter."""
        return (
            self.source_entities_power
        )

    @property
    def source_entities_power(self) -> list[str]:
        """Return the source price entities for this adapter."""
        return [self._power_entity]

    @property
    def power(self) -> float | None:
        """Return the power in Watts.

        Applies the ``power_entity_inverted`` flag so a source sensor using the
        opposite sign convention is normalised to this integration's convention
        (grid: + import / - export; pv/battery: + producing / - consuming).
        """
        power = self._values.get(self._power_entity)
        if power is None:
            return None

        return -power if self._invert_power else power

    @property
    def flow_role(self) -> FlowRole:
        """Return this adapter's instantaneous power-flow role.

        Classifies the adapter from its current signed power using the engine's
        uniform convention (positive = providing, negative = drawing). See
        :class:`FlowRole` for the categories. Subclasses whose sign convention
        differs (e.g. a consumer can never *provide*) override this.
        """
        power = self.power
        if power is None:
            return FlowRole.UNKNOWN
        if power > 0:
            return FlowRole.SOURCE
        if power < 0:
            return FlowRole.SINK
        return FlowRole.IDLE

    def _multiply_cons(self, value: float) -> float | None:
        """Return ``value`` scaled by this adapter's consumption (in kW).

        Only meaningful on adapters that expose a ``consumption`` property
        (production and consumer adapters); it is defined here so both share a
        single implementation.
        """
        if (cons := self.consumption) is None:
            return None

        if cons == 0.0:
            return 0.0

        return (cons / 1000) * value


class BasePowerProvidingAdapter(BasePowerAdapter):

    @property
    def source_entities(self) -> list[str]:
        """Return the source entities for this adapter."""
        return (
            self.source_entities_power
            + self.source_entities_price
            + self.source_entities_co2
        )

    @property
    @abstractmethod
    def source_entities_price(self) -> list[str]:
        """Return the source power entities for this adapter."""
        pass

    @property
    @abstractmethod
    def source_entities_co2(self) -> list[str]:
        """Return the source co2 entities for this adapter."""
        pass


class GridAdapter(BasePowerProvidingAdapter):
    """Grid power adapter."""

    ADAPTER_TYPES = ("grid",)

    def __init__(
        self,
        unique_id: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool = False,
        price_entity: str | None = None,
        co2_entity: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            unique_id, verbose_name, power_entity, power_entity_inverted, **kwargs,
        )
        self._price_entity = price_entity
        if self._price_entity is not None:
            self._values[self._price_entity] = None

        self._co2_entity = co2_entity
        if self._co2_entity is not None:
            self._values[self._co2_entity] = None

    @property
    def source_entities_price(self) -> list[str]:
        """Return the source power entities for this adapter."""
        if self._price_entity is None:
            return []

        return [self._price_entity]

    @property
    def source_entities_co2(self) -> list[str]:
        """Return the source co2 entities for this adapter."""
        if self._co2_entity is None:
            return []

        return [self._co2_entity]

    @property
    def import_power(self) -> float | None:
        """Return the power imported from the grid."""
        if self.power is not None:
            return self.power if self.power > 0. else 0.

        return None

    @property
    def export_power(self) -> float | None:
        """Return the power exported to the grid."""
        if self.power is not None:
            return self.power * -1. if self.power < 0. else 0.

        return None

    @property
    def coe(self) -> float | None:
        """Return the cost of electicity in Euro/kwh."""
        if (_entity := self._price_entity) is None:
            return None

        return self._values.get(_entity)

    @property
    def coe_rate(self) -> float | None:
        """Return the cost of electicity rate in Euro/h."""
        if (coe := self.coe) is None:
            return None

        if (power := self.import_power) is None:
            return None
        elif power == 0.0:
            return 0.0

        return (power / 1000) * coe

    @property
    def lcoe(self) -> float | None:
        """Return the levelized cost of electicity in Euro/kwh."""
        return self.coe

    @property
    def lcoe_rate(self) -> float | None:
        """Return the levelized cost of electicity rate in Euro/h."""
        if (lcoe := self.lcoe) is None:
            return None

        if (power := self.import_power) is None:
            return None
        elif power == 0.0:
            return 0.0

        return (power / 1000) * lcoe

    @property
    def co2_intensity(self) -> float | None:
        """Return the co2 intensity g/kwh."""
        pass

    @property
    def co2_intensity_rate(self) -> float | None:
        """Return the co2 intensity rate in g/h."""
        pass

    @property
    def lco2_intensity(self) -> float | None:
        """Return the levelized co2 intensity g/kwh."""
        pass

    @property
    def lco2_intensity_rate(self) -> float | None:
        """Return the levelized co2 intensity rate in g/h."""
        pass

class BaseProductionAdapter(BasePowerProvidingAdapter):
    """Grid power adapter."""

    def __init__(
        self,
        unique_id: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool = False,
        exports_power: bool = False,
        export_compensation: float = 0.0,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            unique_id, verbose_name, power_entity, power_entity_inverted, **kwargs,
        )
        self.exports_power = exports_power
        self.export_compensation = export_compensation

    @property
    def source_entities_price(self) -> list:
        """Return the source price entities for this adapter."""
        return []

    @property
    def source_entities_co2(self) -> list:
        """Return the source co2 entities for this adapter."""
        return []

    @property
    def production(self) -> float | None:
        """Return the amount of power that is generated."""
        if self.power is not None:
            return self.power if self.power > 0. else 0.

        return None

    @property
    def consumption(self) -> float | None:
        """Return the amount of power that is consumed."""
        if self.power is not None:
            return self.power * -1. if self.power < 0. else 0.

        return None

    # @property
    # def exportable_power(self) -> float | None:
    #     """Return the exportable power."""
    #     if not self.exports_power:
    #         return 0.0

    #     if self.combined_production is None:
    #         return None

    #     return self.combined_production

    @property
    def coe(self) -> float | None:
        """Return the cost of electicity in Euro/kwh."""
        return 0.0

    @property
    def coe_rate(self) -> float | None:
        """Return the cost of electicity rate in Euro/h."""
        if (coe := self.coe) is None:
            return None

        return self._multiply_prod(coe)

    @property
    def lcoe(self) -> float | None:
        """Return the levelized cost of electicity in Euro/kwh."""
        return self.coe

    @property
    def lcoe_rate(self) -> float | None:
        """Return the levelized cost of electicity rate in Euro/h."""
        if (lcoe := self.lcoe) is None:
            return None

        return self._multiply_prod(lcoe)

    @property
    def co2_intensity(self) -> float | None:
        """Return the co2 intensity g/kwh."""
        return 0.0

    @property
    def co2_intensity_rate(self) -> float | None:
        """Return the co2 intensity rate in g/h."""
        if (co2_intensity := self.co2_intensity) is None:
            return None

        return self._multiply_prod(co2_intensity)

    @property
    def lco2_intensity(self) -> float | None:
        """Return the levelized co2 intensity g/kwh."""
        return 0.0

    @property
    def lco2_intensity_rate(self) -> float | None:
        """Return the levelized co2 intensity rate in g/h."""
        if (lco2_intensity := self.lco2_intensity) is None:
            return None

        return self._multiply_prod(lco2_intensity)

    def get_power_from_ratio(self, share: float)  -> float | None:
        """Return the power."""
        if (production := self.production) is None:
            return None

        return production * share

    def get_coo_rate(self, coe: float) -> float | None:
        """Return the cost of operations rate."""
        return self._multiply_cons(coe)

    def get_lcoo_rate(self, lcoe: float) -> float | None:
        """Return the cost of operations rate."""
        return self._multiply_cons(lcoe)

    def _multiply_prod(self, value: float) -> float | None:
        """Return the given value multiplied with the consumption."""
        if (prod := self.production) is None:
            return None

        if prod == 0.0:
            return 0.0

        return (prod / 1000) * value


class PvAdapter(BaseProductionAdapter):
    """Photovoltaic system adapter."""

    ADAPTER_TYPES = ("pv_system",)

    def __init__(
        self,
        unique_id: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool,
        lcoe: float | None,
        lco2_intensity: float | None,
        exports_power: bool,
        export_compensation: float,
        correction_factor: float = 1.0,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            unique_id,
            verbose_name,
            power_entity,
            power_entity_inverted=power_entity_inverted,
            exports_power=exports_power,
            export_compensation=export_compensation,
            **kwargs,
        )
        self._lcoe = lcoe
        self._lco2_intensity = lco2_intensity
        self._correction_factor = correction_factor

    @property
    def lcoe(self) -> float | None:
        """Return the (base) levelized cost of electicity in Euro/kwh."""
        return self._lcoe

    @property
    def correction_factor(self) -> float:
        """Return the levelized-cost correction factor for this PV system."""
        return self._correction_factor

class BatteryAdapter(BaseProductionAdapter):
    """Battery adapter."""

    ADAPTER_TYPES = ("battery",)

    def __init__(
        self,
        unique_id: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool,
        lcos: float | None,
        lco2_intensity: float | None,
        exports_power: bool,
        export_compensation: float,
        charge_from_adapters: list[str] | None = None,
        correction_factor: float = 1.0,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            unique_id,
            verbose_name,
            power_entity,
            power_entity_inverted=power_entity_inverted,
            exports_power=exports_power,
            export_compensation=export_compensation,
            **kwargs,
        )
        self._lcos = lcos
        self._lco2_intensity = lco2_intensity
        # Normalise: None (field not yet configured) becomes an empty list.
        self.charge_from_adapters: list[str] = (
            charge_from_adapters if charge_from_adapters is not None else []
        )
        self._correction_factor = correction_factor

    @property
    def lcoe(self) -> float | None:
        """Return the (base) levelized cost of electicity in Euro/kwh."""
        return self._lcos

    @property
    def correction_factor(self) -> float:
        """Return the levelized-cost correction factor for this battery."""
        return self._correction_factor

    @property
    def power_source_uids(self) -> list[str]:
        """Sources this battery charges from (its ``charge_from_adapters``).

        Empty means the whole mix — the config flow's "whole mix" source mode
        stores an empty list, which the engine reads as unrestricted.
        """
        return self.charge_from_adapters

class BaseConsumerAdapter(BasePowerAdapter):
    """Base adapter for consumers."""

    def __init__(
        self,
        unique_id: str,
        verbose_name: str,
        power_entity: str,
        power_entity_inverted: bool = False,
        power_from_adapters: list[str] | None = None,
        **kwargs,
    ) -> None:
        """Initialize instance."""
        super().__init__(
            unique_id, verbose_name, power_entity, power_entity_inverted, **kwargs,
        )
        # Normalise: None (field not yet configured) becomes an empty list.
        # These are the sources this consumer draws from (e.g. a smart plug set
        # to run only on excess solar); empty means it draws the general mix.
        self.power_from_adapters: list[str] = (
            power_from_adapters if power_from_adapters is not None else []
        )

    @property
    def power_source_uids(self) -> list[str]:
        """Sources this consumer draws from (its ``power_from_adapters``)."""
        return self.power_from_adapters

    @property
    def consumption(self) -> float | None:
        """Return the amount of power that is consumed."""
        if self.power is not None:
            return self.power * -1. if self.power < 0 else 0

        return None

    @property
    def flow_role(self) -> FlowRole:
        """Return this consumer's instantaneous power-flow role.

        A consumer is a pure sink: it can only draw power. A positive reading
        (which the engine's convention would treat as providing) is therefore
        reported as ``IDLE`` rather than ``SOURCE``.
        """
        role = super().flow_role
        return FlowRole.IDLE if role is FlowRole.SOURCE else role

    def get_coo_rate(self, coe: float) -> float | None:
        """Return the cost of operations rate."""
        return self._multiply_cons(coe)

    def get_lcoo_rate(self, lcoe: float) -> float | None:
        """Return the cost of operations rate."""
        return self._multiply_cons(lcoe)


class ConsumerAdapter(BaseConsumerAdapter):

    pass
