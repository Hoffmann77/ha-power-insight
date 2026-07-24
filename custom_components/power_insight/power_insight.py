"""Modules to calculate the grid status."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from enum import Enum

import numpy as np

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
        pass

    @property
    def combined_grid_export(self) -> float | None:
        """Power exported to the grid (W)."""
        pass

    @property
    def combined_production(self) -> float | None:
        """Total power generated by the PV adapters (W)."""
        pass

    @property
    def combined_charging_power(self) -> float | None:
        """Total power charged by the battery adapters (W)."""
        pass

    @property
    def combined_discharging_power(self) -> float | None:
        """Total power discharged by the battery adapters (W)."""
        pass

    @property
    def combined_standby_power(self) -> float | None:
        """Total standby power drawn by the PV adapters (W)."""
        pass

    @property
    def combined_consumption(self) -> float | None:
        """Self-consumed power: gross minus export, charging and standby (W)."""
        pass

    @property
    def source_adapters_power(self) -> tuple[np.ndarray, list[str]]:
        """Return ``(signed power array, uid index)`` for the source adapters.

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

        return np.array(arr), index

    @property
    def sink_adapters_power(self) -> tuple[np.ndarray, list[str]]:
        """Return ``(signed power array, uid index)`` for the sink adapters.

        Sink adapters are all currently drawing (grid export, charging
        batteries, consumer loads, PV standby), so every reading is negative.
        """
        arr = []
        index = []

        for adapter in self.sink_adapters:
            index.append(adapter.uid)
            arr.append(adapter.power)

        return np.array(arr), index

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
        return float(power_arr.sum())

    @property
    def source_adapters_gross_power_shares(self) -> tuple[np.ndarray, list[str]]:
        """Return ``(share array, uid index)`` — each source's fraction of gross power.

        The shares of the currently-providing adapters (grid import, producing
        PV, discharging batteries); they sum to 1. Returns an empty array and
        index when gross power is unavailable. Mirrors ``source_adapters_power``
        so the numpy pipeline stays composable.
        """
        gross = self.gross_power
        if gross is None:
            return np.array([]), []

        power_arr, index = self.source_adapters_power
        if gross == 0.0:
            return np.zeros(len(index)), index

        return power_arr / gross, index

    @property
    def sink_adapters_gross_power_shares(self) -> tuple[np.ndarray, list[str]]:
        """Return ``(share array, uid index)`` — each sink's fraction of gross power.

        The shares of the currently-drawing adapters (grid export, charging
        batteries, consumer loads, PV standby); the readings are unsigned here.
        Unlike the source shares these need not sum to 1: the remainder up to 1
        is the unmetered home load. Returns an empty array and index when gross
        power is unavailable.
        """
        gross = self.gross_power
        if gross is None:
            return np.array([]), []

        power_arr, index = self.sink_adapters_power
        if gross == 0.0:
            return np.zeros(len(index)), index

        return np.abs(power_arr) / gross, index

    @property
    def sink_adapters_source_shares(self) -> dict[str, dict[str, float]]:
        """Return ``{sink_uid: {source_uid: share}}`` — each sink's power provenance.

        For every currently-drawing adapter, the fraction of its power supplied
        by each source adapter (grid import, producing PV, discharging
        batteries). Each row sums to 1 (a sink whose allowed sources are all
        idle collapses to all-zeros).

        The attribution is three-tier, honouring per-device source restrictions
        (a battery's ``charge_from_adapters``, a consumer's
        ``power_from_adapters``, both surfaced as ``power_source_uids``):

        * **Priority tier** — sinks restricted to specific non-grid sources
          (a battery charging on PV only, a smart-plug consumer on excess
          solar). They get first pick of their allowed sources, weighted by
          each source's share of gross power. This tier is active **only while
          the grid is importing**: giving a grid-excluded sink first claim on
          the scarce local sources is only meaningful when the grid-capable
          sinks have the grid to fall back on. With no grid import there is
          nothing to fall back to, so every sink shares the sources in a single
          pass on equal footing (the tier is empty).
        * **Home base-load tier** — the unmetered home load (the gross power no
          sink accounts for). It consumes the remaining *local* generation next,
          falling back on the grid for its deficit, so a scarce local source can
          be exhausted before the flexible grid-capable sinks see it. Unmetered,
          it never appears in the result — it only depletes the pool. Active
          only while the grid is importing, for the same scarcity reason.
        * **Leftover tier** — every other sink (unrestricted, or allowed to draw
          the grid, or *any* sink when the grid is not importing). They split
          the power the priority and home tiers left behind — the full
          availability when both are empty — each still respecting its own
          restriction if it has one.

        Empty when gross power is unavailable.
        """
        availability, index = self.source_adapters_gross_power_shares
        if not index:
            # Gross power unavailable, or nothing is currently providing.
            return {}

        sink_share_arr, sink_index = self.sink_adapters_gross_power_shares
        sink_shares = dict(zip(sink_index, sink_share_arr))
        grid_uid = self.grid_adapter.uid
        # The grid is a source only while it is importing; the priority tier
        # exists only then (see docstring).
        grid_importing = grid_uid in index

        def restricted_row(sources: list[str], weights: np.ndarray) -> np.ndarray:
            """Weights masked to the allowed sources (all sources if unrestricted)."""
            if not sources:
                return weights.copy()
            mask = np.array([1.0 if uid in sources else 0.0 for uid in index])
            return weights * mask

        def normalise(row: np.ndarray) -> np.ndarray:
            total = row.sum()
            return row / total if total > 0 else np.zeros_like(row)

        # Partition the sinks. A sink is a priority sink only when the grid is
        # importing and it is restricted to sources that exclude the grid — a
        # grid-capable (or unrestricted) sink is flexible and waits for leftover.
        priority, leftover = [], []
        for adapter in self.sink_adapters:
            sources = adapter.power_source_uids
            if grid_importing and sources and grid_uid not in sources:
                priority.append(adapter)
            else:
                leftover.append(adapter)

        result: dict[str, dict[str, float]] = {}

        # Priority tier draws from the full availability vector, consuming it.
        consumed = np.zeros(len(index))
        for adapter in priority:
            shares = normalise(restricted_row(adapter.power_source_uids, availability))
            result[adapter.uid] = {uid: float(s) for uid, s in zip(index, shares)}
            consumed += shares * sink_shares[adapter.uid]

        # Leftover tier draws from what the priority tier left behind (the full
        # availability when the priority tier is empty).
        leftover_availability = np.clip(availability - consumed, 0.0, None)

        # Home base-load tier. The unmetered home load — the gross power no sink
        # accounts for — sits between the priority and the flexible grid-capable
        # sinks: it consumes the remaining *local* generation first (the grid is
        # its fallback), so the leftover sinks that can draw the grid only claim
        # the local generation the home load did not eat. Like the priority tier
        # this scarcity ordering is meaningful only while the grid is importing;
        # with no import every sink already shares the sources in a single pass.
        # The load is unmetered, so it never appears in ``result`` — it only
        # depletes ``leftover_availability``.
        if grid_importing:
            home_share = max(0.0, 1.0 - float(sum(sink_shares.values())))
            grid_i = index.index(grid_uid)
            local_mask = np.array([0.0 if uid == grid_uid else 1.0 for uid in index])
            local_residual = leftover_availability * local_mask
            # Local drawn first (capped at what is left), grid covers the rest.
            local_take = min(home_share, float(local_residual.sum()))
            home_consumed = normalise(local_residual) * local_take
            home_consumed[grid_i] += home_share - local_take
            leftover_availability = np.clip(
                leftover_availability - home_consumed, 0.0, None
            )

        for adapter in leftover:
            shares = normalise(
                restricted_row(adapter.power_source_uids, leftover_availability)
            )
            result[adapter.uid] = {uid: float(s) for uid, s in zip(index, shares)}

        return result


    # -------------------------------------------------------------->
    # GROSS POWER RATIOS
    # -------------------------------------------------------------->

    @property
    def gross_power_export_ratio(self) -> float | None:
        """Fraction of gross power returned to the grid."""
        pass

    @property
    def gross_power_consumption_ratio(self) -> float | None:
        """Fraction of gross power self-consumed."""
        pass

    @property
    def gross_power_standby_ratio(self) -> float | None:
        """Fraction of gross power used as adapter standby."""
        pass

    @property
    def gross_power_charging_ratio(self) -> float | None:
        """Fraction of gross power charged into storage."""
        pass

    # -------------------------------------------------------------->
    # APPLICABLE GROSS POWER RATIOS
    # -------------------------------------------------------------->

    @property
    def gross_power_applicable_consumption_ratio(self) -> float | None:
        """Self-consumption ratio excluding export and charging."""
        pass

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
        if adapter is not None:
            return adapter.set_value(entity_id, new_value)
        return False

    def register_adapter(self, adapter) -> None:
        """Register an adapter."""
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

        An empty list means unrestricted (the adapter draws from the general
        mix). Only battery and smart-plug consumer adapters override this to
        expose their configured restriction; every other adapter kind stays
        unrestricted. Consumed by ``PowerInsight.sink_adapters_source_shares``
        to give restricted sinks first pick of their allowed sources.
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
        """Sources this battery charges from (its ``charge_from_adapters``)."""
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
