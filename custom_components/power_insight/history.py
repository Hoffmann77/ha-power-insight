"""Carried-over history: what a device earned before Power Insight counted it.

Users adopt Power Insight years after their PV system or battery went in, and
the device's app knows what happened since: kWh produced, fed in, charged and
discharged, sometimes the money saved. This module turns those figures into
the amounts each running total carries over. The sensor layer adds them when
a total is reported; nothing here is accumulated, and the engine never sees it.

Two stages, matching docs/dev/carried-over-history.md:

* :func:`solve` runs when the history is saved. It splits the period's energy
  between the devices with the engine's own allocator, so the past follows the
  same rules as the live readings, and resolves amounts entered for the whole
  home into per-device ones. The result, one :class:`Record` per device, is
  stored and then frozen: removing a device later moves no one else's past.
* :func:`history_totals` runs whenever a total is read. It prices one record's
  flows at the *current* corrected LCOE / LCOS, which is what lets a lifetime
  cost edit restate the history like everything else.

Pure Python: no Home Assistant imports.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta

from .power_insight import allocate

PV_SYSTEM = "pv_system"
BATTERY = "battery"

#: Devices set up within this window of the grid share one history period,
#: and with it the grid's home-level figures.
SHARED_PERIOD = timedelta(hours=24)

_EPS = 1e-6

#: How far entered figures may disagree before they are refused: the larger
#: of 1 kWh and 1 % of the figures compared. App figures are rounded, usually
#: to whole kWh, and come from different meters (the inverter's, the grid
#: meter), which differ by a fraction of a percent; refusing that would refuse
#: correct figures. A mismatch within it is absorbed, one beyond it is a
#: mistake worth pointing at.
SLACK_KWH = 1.0
SLACK_SHARE = 0.01


def _slack(*figures: float | None) -> float:
    """The disagreement tolerated between ``figures`` (kWh)."""
    largest = max((abs(f) for f in figures if f is not None), default=0.0)
    return max(SLACK_KWH, SLACK_SHARE * largest)

# Node names for the solve. They cannot collide with a subentry id.
_EXPORT = "\x00export"
_HOME = "\x00home"
_NO_GRID = "\x00grid"


def _charging(uid: str) -> str:
    """The sink a battery charges through; its discharge is the source ``uid``."""
    return f"{uid}\x00charging"


# Input fields, named as the form will name them, so a problem can point at one.
FIELD_PRODUCED = "produced"
FIELD_CHARGED = "charged"
FIELD_GRID_CHARGED = "grid_charged"
FIELD_DISCHARGED = "discharged"
FIELD_FED_IN = "fed_in"
FIELD_INTO_BATTERIES = "into_batteries"
FIELD_TARIFF = "tariff"
FIELD_SAVINGS = "savings"
FIELD_EXPORT_COMPENSATION = "export_compensation"

# Problems that refuse a save. The codes become the form's error keys.
ERROR_PARTIAL_ENERGY = "history_partial_energy"
ERROR_GRID_CHARGED_EXCEEDS_CHARGED = "history_grid_charged_exceeds_charged"
ERROR_FED_IN_EXCEEDS_OUTPUT = "history_fed_in_exceeds_output"
ERROR_FED_IN_EXCEEDS_HOME = "history_fed_in_exceeds_home"
ERROR_FED_IN_EXCEEDS_PRODUCTION = "history_fed_in_exceeds_production"
ERROR_CHARGING_NOT_COVERED = "history_charging_not_covered"
ERROR_DOES_NOT_BALANCE = "history_does_not_balance"
ERROR_FED_IN_REQUIRED = "history_fed_in_required"
ERROR_TARIFF_REQUIRED = "history_tariff_required"
ERROR_SAVINGS_NOT_SPLITTABLE = "history_savings_not_splittable"
ERROR_EXPORT_COMPENSATION_NOT_SPLITTABLE = "history_export_compensation_not_splittable"

# Why a total carries no history (the inclusion rule: every term or nothing).
MISSING_WAITING = "waiting"
MISSING_ENERGY = "no_energy"
MISSING_TARIFF = "no_tariff"
MISSING_FEED_IN_TARIFF = "no_feed_in_tariff"
MISSING_PRICE = "no_price"

# The running totals that carry history, by sensor description key.
TOTAL_COST_SAVINGS = "total_cost_savings"
TOTAL_LEVELIZED_COST_SAVINGS = "total_levelized_cost_savings"
TOTAL_EXPORT_COMPENSATION = "total_export_compensation"
TOTAL_FINANCIAL_RETURN = "total_financial_return"
TOTAL_LEVELIZED_FINANCIAL_RETURN = "total_levelized_financial_return"
TOTAL_OPERATING_COST = "total_operating_cost"
TOTAL_LEVELIZED_OPERATING_COST = "total_levelized_operating_cost"

PV_TOTALS = (
    TOTAL_COST_SAVINGS,
    TOTAL_LEVELIZED_COST_SAVINGS,
    TOTAL_EXPORT_COMPENSATION,
    TOTAL_FINANCIAL_RETURN,
    TOTAL_LEVELIZED_FINANCIAL_RETURN,
)
# A PV system's operating cost is its standby draw, which no app reports.
BATTERY_TOTALS = PV_TOTALS + (TOTAL_OPERATING_COST, TOTAL_LEVELIZED_OPERATING_COST)


def shares_period(grid_since: datetime, device_since: datetime) -> bool:
    """Whether a device's history covers the same period as the grid's.

    Devices set up together are counted from (nearly) the same moment, so the
    grid meter's totals describe them jointly and can be split between them.
    A device added later is *standalone*: the grid's totals for its period
    mix in devices that were already being counted live.
    """
    return abs(device_since - grid_since) <= SHARED_PERIOD


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HomeInputs:
    """The figures entered on the grid: totals for the whole home."""

    grid_uid: str
    fed_in: float | None = None
    tariff: float | None = None
    savings: float | None = None
    export_compensation: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> HomeInputs:
        return cls(**data)


@dataclass(frozen=True)
class DeviceInputs:
    """One PV system's or battery's figures from its app, as entered.

    Every device of the home is passed, with or without history, because a
    device without one still decides whether the home's totals can be split.
    ``feed_in_tariff`` defaults (in the caller) to the configured export
    compensation; ``tariff`` and ``into_batteries`` are only asked of a
    standalone device.
    """

    uid: str
    kind: str
    exports: bool = False
    charge_from: tuple[str, ...] = ()  # a battery's restriction; empty = every PV
    standalone: bool = False
    produced: float | None = None
    charged: float | None = None
    grid_charged: float | None = None
    discharged: float | None = None
    fed_in: float | None = None
    into_batteries: float | None = None
    tariff: float | None = None
    feed_in_tariff: float | None = None
    savings: float | None = None
    export_compensation: float | None = None
    levelized_savings: float | None = None

    def to_dict(self) -> dict:
        return {**asdict(self), "charge_from": list(self.charge_from)}

    @classmethod
    def from_dict(cls, data: dict) -> DeviceInputs:
        return cls(**{**data, "charge_from": tuple(data.get("charge_from", ()))})

    @property
    def has_energy(self) -> bool:
        """Whether the device has a kWh history (else amounts at most)."""
        if self.kind == PV_SYSTEM:
            return self.produced is not None
        return self.charged is not None and self.discharged is not None

    @property
    def output(self) -> float:
        """What the device delivered over the period: produced or discharged."""
        value = self.produced if self.kind == PV_SYSTEM else self.discharged
        return value or 0.0

    @property
    def local_charged(self) -> float:
        """A battery's charging that came from local generation."""
        return (self.charged or 0.0) - (self.grid_charged or 0.0)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Flows:
    """Where one device's energy went over the history period (kWh)."""

    to_home: float
    exported: float
    from_grid: float = 0.0
    from_pv: dict[str, float] = field(default_factory=dict)  # a battery's charging

    def to_dict(self) -> dict:
        return {
            "to_home": self.to_home,
            "exported": self.exported,
            "from_grid": self.from_grid,
            "from_pv": dict(self.from_pv),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Flows:
        return cls(
            to_home=data["to_home"],
            exported=data["exported"],
            from_grid=data.get("from_grid", 0.0),
            from_pv=dict(data.get("from_pv", {})),
        )


@dataclass(frozen=True)
class Record:
    """One device's solved history: what :func:`history_totals` prices.

    ``flows`` is ``None`` for an amounts-only history and while the split is
    waiting for another device (``waiting_for``). The amounts are the entered
    ones, or this device's share of an amount entered for the whole home.
    """

    uid: str
    kind: str
    exports: bool
    tariff: float | None = None
    feed_in_tariff: float | None = None
    flows: Flows | None = None
    savings: float | None = None
    export_compensation: float | None = None
    levelized_savings: float | None = None
    waiting_for: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "kind": self.kind,
            "exports": self.exports,
            "tariff": self.tariff,
            "feed_in_tariff": self.feed_in_tariff,
            "flows": None if self.flows is None else self.flows.to_dict(),
            "savings": self.savings,
            "export_compensation": self.export_compensation,
            "levelized_savings": self.levelized_savings,
            "waiting_for": list(self.waiting_for),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Record:
        flows = data.get("flows")
        return cls(
            uid=data["uid"],
            kind=data["kind"],
            exports=data.get("exports", False),
            tariff=data.get("tariff"),
            feed_in_tariff=data.get("feed_in_tariff"),
            flows=None if flows is None else Flows.from_dict(flows),
            savings=data.get("savings"),
            export_compensation=data.get("export_compensation"),
            levelized_savings=data.get("levelized_savings"),
            waiting_for=tuple(data.get("waiting_for", ())),
        )


@dataclass(frozen=True)
class Problem:
    """A reason to refuse a save, pointing at the figure that is off."""

    code: str
    uid: str | None = None  # the device (the grid's uid for a home figure)
    field: str | None = None


@dataclass(frozen=True)
class Solution:
    """What :func:`solve` found: records to store, or problems to show."""

    records: dict[str, Record]
    problems: list[Problem]


# ---------------------------------------------------------------------------
# Solve (on save)
# ---------------------------------------------------------------------------


def solve(home: HomeInputs, devices: Iterable[DeviceInputs]) -> Solution:
    """Split the history between the devices and resolve home-level amounts.

    ``devices`` is every PV system and battery of the home. Records come back
    only for devices with some history, and only when nothing is refused.
    """
    devices = [d for d in devices if d.kind in (PV_SYSTEM, BATTERY)]
    problems = [p for d in devices for p in _check(d)]
    devices = [_within(d) for d in devices]
    shared = [d for d in devices if not d.standalone]

    own_fed_in = sum(d.fed_in for d in shared if d.has_energy and d.fed_in is not None)
    if home.fed_in is not None and own_fed_in > home.fed_in + _slack(home.fed_in, own_fed_in):
        problems.append(Problem(ERROR_FED_IN_EXCEEDS_HOME, home.grid_uid, FIELD_FED_IN))
    if problems:
        return Solution({}, problems)

    flows, waiting, problems = _split_shared(home, shared)
    pv_uids = [d.uid for d in devices if d.kind == PV_SYSTEM]
    for device in devices:
        if device.standalone and device.has_energy:
            found, issue = _standalone_flows(device, pv_uids)
            if issue is not None:
                problems.append(issue)
            else:
                flows[device.uid] = found
    if problems:
        return Solution({}, problems)

    records = {
        d.uid: _record(d, home, flows.get(d.uid), () if d.standalone else waiting)
        for d in devices
        if d.has_energy
        or d.savings is not None
        or d.export_compensation is not None
        or d.levelized_savings is not None
        or not d.standalone  # may still get a share of a home-level amount
    }
    problems = _resolve_home_amounts(home, shared, records, waiting)
    if problems:
        return Solution({}, problems)

    return Solution(
        {uid: record for uid, record in records.items() if _has_history(record)}, []
    )


def _check(device: DeviceInputs) -> list[Problem]:
    """The figures one device's own form can already refuse."""
    problems: list[Problem] = []
    uid = device.uid

    def refuse(code: str, field_name: str) -> None:
        problems.append(Problem(code, uid, field_name))

    if device.kind == PV_SYSTEM:
        if not device.has_energy:
            for name in (FIELD_FED_IN, FIELD_INTO_BATTERIES):
                if getattr(device, name) is not None:
                    refuse(ERROR_PARTIAL_ENERGY, FIELD_PRODUCED)
                    break
            return problems
    else:
        given = [
            name for name in (FIELD_CHARGED, FIELD_DISCHARGED, FIELD_GRID_CHARGED, FIELD_FED_IN)
            if getattr(device, name) is not None
        ]
        if given and not device.has_energy:
            missing = FIELD_CHARGED if device.charged is None else FIELD_DISCHARGED
            refuse(ERROR_PARTIAL_ENERGY, missing)
            return problems
        if not device.has_energy:
            return problems
        if (device.grid_charged or 0.0) > device.charged + _slack(device.charged):
            refuse(ERROR_GRID_CHARGED_EXCEEDS_CHARGED, FIELD_GRID_CHARGED)

    if (device.fed_in or 0.0) > device.output + _slack(device.output):
        refuse(ERROR_FED_IN_EXCEEDS_OUTPUT, FIELD_FED_IN)
    if device.standalone:
        if device.exports and device.fed_in is None:
            refuse(ERROR_FED_IN_REQUIRED, FIELD_FED_IN)
        if device.tariff is None:
            refuse(ERROR_TARIFF_REQUIRED, FIELD_TARIFF)

    return problems


def _within(device: DeviceInputs) -> DeviceInputs:
    """Absorb a disagreement :func:`_check` tolerated: no part can exceed its whole.

    A battery's grid charging is at most what it charged, and a device's own
    feed-in at most what it produced or discharged.
    """
    if not device.has_energy:
        return device
    changes = {}
    if device.fed_in is not None and device.fed_in > device.output:
        changes["fed_in"] = device.output
    if device.kind == BATTERY and (device.grid_charged or 0.0) > device.charged:
        changes["grid_charged"] = device.charged
    return replace(device, **changes) if changes else device


def _split_shared(
    home: HomeInputs, shared: list[DeviceInputs]
) -> tuple[dict[str, Flows], tuple[str, ...], list[Problem]]:
    """Split the shared period's energy with the engine's allocator.

    Three things differ from a live snapshot (see the plan): grid import is
    not a source, because on period totals "the grid goes first" would hand a
    battery all of its charging; batteries never charge each other; and an
    own feed-in is assigned before the solve, so only the rest of the home's
    feed-in is split.

    Returns ``(flows, waiting_for, problems)``. While a device the split
    needs has no kWh history, nothing is split and ``waiting_for`` names it.
    """
    energetic = [d for d in shared if d.has_energy]
    if not energetic:
        return {}, (), []

    pvs = [d.uid for d in energetic if d.kind == PV_SYSTEM]
    splitters = [d.uid for d in energetic if d.exports and d.fed_in is None]
    charging = {
        d.uid: [p for p in pvs if not d.charge_from or p in d.charge_from]
        for d in energetic
        if d.kind == BATTERY and d.local_charged > _EPS
    }

    # Who else could have produced that energy, but has no kWh to show for it?
    absent = [d for d in shared if not d.has_energy]
    waiting = [
        d.uid for d in absent
        if (splitters and d.exports)
        or (
            d.kind == PV_SYSTEM
            and any(
                not b.charge_from or d.uid in b.charge_from
                for b in energetic if b.uid in charging
            )
        )
    ]
    if splitters and home.fed_in is None:
        waiting.append(home.grid_uid)
    if waiting:
        return {}, tuple(waiting), []

    own_fed_in = sum(d.fed_in for d in energetic if d.fed_in is not None)
    export = max(home.fed_in - own_fed_in, 0.0) if splitters else 0.0

    supply = {d.uid: d.output - (d.fed_in or 0.0) for d in energetic}
    demand: dict[str, float] = {}
    allowed: dict[str, tuple[str, ...]] = {}
    if export > _EPS:
        demand[_EXPORT] = export
        allowed[_EXPORT] = tuple(splitters)
    for uid, sources in charging.items():
        if not sources:
            return {}, (), [Problem(ERROR_CHARGING_NOT_COVERED, uid, FIELD_CHARGED)]
        battery = next(d for d in energetic if d.uid == uid)
        demand[_charging(uid)] = battery.local_charged
        allowed[_charging(uid)] = tuple(sources)

    total_supply = sum(supply.values())
    residual = total_supply - sum(demand.values())
    if residual < -_slack(total_supply):
        return {}, (), [Problem(ERROR_DOES_NOT_BALANCE)]
    if residual < 0:
        # Over-booked by less than the tolerance: scale export and charging
        # down together to what was produced, so every source still balances.
        scale = total_supply / (total_supply - residual)
        demand = {sink: kwh * scale for sink, kwh in demand.items()}
    demand[_HOME] = max(residual, 0.0)
    allowed[_HOME] = ()

    allocation, deficit = allocate(supply, demand, allowed, _NO_GRID)
    # The allocator covers a shortfall by relaxing a restriction, its last
    # resort. In the history that only happens for a shortfall within the
    # tolerance, and a restriction is a fact here (a battery that may not feed
    # in never did), so the relaxed part goes to the home instead: the
    # shortfall stays unattributed and every source still balances.
    for sink, sources in allowed.items():
        if not sources:
            continue
        row = allocation.get(sink, {})
        for source, kwh in row.items():
            if kwh > 0 and source not in sources:
                allocation[_HOME][source] = allocation[_HOME].get(source, 0.0) + kwh
                row[source] = 0.0
    # A shortfall is measured against the figure that was entered: the home's
    # whole feed-in (not the remainder after own feed-ins), a battery's charging.
    entered = {_EXPORT: home.fed_in}
    entered.update({_charging(d.uid): d.charged for d in energetic if d.kind == BATTERY})
    problems = [
        Problem(ERROR_FED_IN_EXCEEDS_PRODUCTION, home.grid_uid, FIELD_FED_IN)
        if sink == _EXPORT
        else Problem(ERROR_CHARGING_NOT_COVERED, sink.split("\x00")[0], FIELD_CHARGED)
        for sink, short in deficit.items()
        if short > _slack(entered.get(sink))
    ]
    if problems:
        return {}, (), problems

    exported = allocation.get(_EXPORT, {})
    flows = {}
    for device in energetic:
        uid = device.uid
        from_pv: dict[str, float] = {}
        if device.kind == BATTERY:
            row = allocation.get(_charging(uid), {})
            from_pv = {p: _round(row.get(p, 0.0)) for p in charging.get(uid, ())}
        flows[uid] = Flows(
            to_home=_round(allocation[_HOME].get(uid, 0.0)),
            exported=_round(
                device.fed_in if device.fed_in is not None else exported.get(uid, 0.0)
            ),
            from_grid=(device.grid_charged or 0.0) if device.kind == BATTERY else 0.0,
            from_pv=from_pv,
        )
    return flows, (), []


def _standalone_flows(
    device: DeviceInputs, pv_uids: list[str]
) -> tuple[Flows | None, Problem | None]:
    """A device added later stands alone: no shared totals to split.

    A PV system's energy into batteries earns it nothing, so it only lowers
    what reached the home. A battery's local charging is split evenly over the
    PV systems it may charge from: there are no period totals to weigh them
    by, and it only decides whose LCOE prices that charging.
    """
    exported = device.fed_in or 0.0
    if device.kind == PV_SYSTEM:
        to_home = device.output - exported - (device.into_batteries or 0.0)
        if to_home < -_slack(device.output):
            return None, Problem(ERROR_DOES_NOT_BALANCE, device.uid, FIELD_INTO_BATTERIES)
        return Flows(to_home=_round(max(to_home, 0.0)), exported=exported), None

    local = device.local_charged
    sources = [p for p in pv_uids if not device.charge_from or p in device.charge_from]
    if local > _EPS and not sources:
        return None, Problem(ERROR_CHARGING_NOT_COVERED, device.uid, FIELD_CHARGED)
    share = local / len(sources) if local > _EPS else 0.0
    return Flows(
        to_home=_round(device.output - exported),
        exported=exported,
        from_grid=device.grid_charged or 0.0,
        from_pv={p: _round(share) for p in sources} if share else {},
    ), None


def _record(
    device: DeviceInputs,
    home: HomeInputs,
    flows: Flows | None,
    waiting_for: tuple[str, ...],
) -> Record:
    return Record(
        uid=device.uid,
        kind=device.kind,
        exports=device.exports,
        tariff=device.tariff if device.standalone else home.tariff,
        feed_in_tariff=device.feed_in_tariff,
        flows=flows,
        savings=device.savings,
        export_compensation=device.export_compensation,
        levelized_savings=device.levelized_savings,
        waiting_for=waiting_for if device.has_energy else (),
    )


def _resolve_home_amounts(
    home: HomeInputs,
    shared: list[DeviceInputs],
    records: dict[str, Record],
    waiting: tuple[str, ...],
) -> list[Problem]:
    """Deal amounts entered for the whole home out to the shared devices.

    What the devices entered themselves is taken off first; the rest goes to
    the others, in proportion to their calculated savings, or to their
    exported kWh for export compensation. A single device simply gets it.
    While the split is waiting there is nothing to weigh by, so the amount
    waits too. Mutates ``records``.
    """
    problems: list[Problem] = []
    uids = [d.uid for d in shared]

    def deal(attr, total, weigh, candidates, error, field_name):
        entered = sum(
            getattr(records[u], attr) for u in uids
            if getattr(records[u], attr) is not None
        )
        rest = total - entered
        if not candidates:
            if abs(rest) > _EPS:
                problems.append(Problem(error, home.grid_uid, field_name))
            return
        if len(candidates) == 1:
            _replace(records, candidates[0], **{attr: _round(rest)})
            return
        if waiting:
            for uid in candidates:
                _replace(records, uid, waiting_for=waiting)
            return
        weights = {u: weigh(records[u]) for u in candidates}
        if any(w is None or w < 0 for w in weights.values()) or sum(
            weights.values()
        ) <= _EPS:
            problems.append(Problem(error, home.grid_uid, field_name))
            return
        scale = rest / sum(weights.values())
        for uid, weight in weights.items():
            _replace(records, uid, **{attr: _round(weight * scale)})

    if home.savings is not None:
        deal(
            "savings",
            home.savings,
            _calculated_savings,
            [u for u in uids if records[u].savings is None],
            ERROR_SAVINGS_NOT_SPLITTABLE,
            FIELD_SAVINGS,
        )
    if home.export_compensation is not None:
        deal(
            "export_compensation",
            home.export_compensation,
            lambda r: None if r.flows is None else r.flows.exported,
            [u for u in uids if records[u].exports and records[u].export_compensation is None],
            ERROR_EXPORT_COMPENSATION_NOT_SPLITTABLE,
            FIELD_EXPORT_COMPENSATION,
        )
    return problems


def _calculated_savings(record: Record) -> float | None:
    """A record's standard savings from its kWh, or ``None``; must be > 0 to weigh by."""
    try:
        value = _energy_savings(record)
    except _Missing:
        return None
    return value if value > _EPS else None


def _replace(records: dict[str, Record], uid: str, **changes) -> None:
    records[uid] = replace(records[uid], **changes)


def _has_history(record: Record) -> bool:
    return (
        record.flows is not None
        or record.waiting_for != ()
        or record.savings is not None
        or record.export_compensation is not None
        or record.levelized_savings is not None
    )


def _round(value: float) -> float:
    """Drop the solver's float noise; a microwatt-hour is far below any app."""
    return round(value, 6)


# ---------------------------------------------------------------------------
# Price (on read)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Totals:
    """One device's carried-over value per running total, and why not."""

    values: dict[str, float | None]
    missing: dict[str, str]


class _Missing(Exception):
    """A term of a total is unknown, so the total carries no history."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _need(value: float | None, reason: str) -> float:
    if value is None:
        raise _Missing(reason)
    return value


def _cost(kwh: float, price: float | None, reason: str) -> float:
    """``kwh × price``; energy that is not there costs nothing whatever its price."""
    if abs(kwh) <= _EPS:
        return 0.0
    return kwh * _need(price, reason)


def _flows(record: Record) -> Flows:
    if record.flows is None:
        raise _Missing(MISSING_WAITING if record.waiting_for else MISSING_ENERGY)
    return record.flows


def _energy_savings(record: Record) -> float:
    """Standard savings from the kWh: the tariff avoided, less grid charging."""
    flows = _flows(record)
    return _cost(flows.to_home, record.tariff, MISSING_TARIFF) - _cost(
        flows.from_grid, record.tariff, MISSING_TARIFF
    )


def history_totals(
    record: Record, price: Callable[[str], float | None]
) -> Totals:
    """Price one device's history for every running total it carries.

    ``price(uid)`` is a device's current levelized price per kWh (LCOE / LCOS
    times its correction factor), or ``None`` when it has none. Pricing at
    read time is what makes a lifetime cost edit restate the history.

    Entered amounts are taken as they are; only the cost of the energy behind
    a levelized total follows the price. A total missing any term carries no
    history at all, and ``missing`` says why.
    """

    def savings() -> float:
        if record.savings is not None:
            return record.savings
        return _energy_savings(record)

    def energy_cost() -> float:
        """The levelized cost of what the device delivered, and of its charging."""
        flows = _flows(record)
        cost = _cost(flows.to_home, price(record.uid), MISSING_PRICE)
        for source, kwh in flows.from_pv.items():
            cost += _cost(kwh, price(source), MISSING_PRICE)
        return cost

    def levelized_savings() -> float:
        if record.flows is None and record.levelized_savings is not None:
            return record.levelized_savings
        return savings() - energy_cost()

    def exported() -> float:
        return _flows(record).exported if record.exports else 0.0

    def export_compensation() -> float:
        if record.export_compensation is not None:
            return record.export_compensation
        return _cost(exported(), record.feed_in_tariff, MISSING_FEED_IN_TARIFF)

    def operating_cost() -> float:
        return _cost(_flows(record).from_grid, record.tariff, MISSING_TARIFF)

    def levelized_operating_cost() -> float:
        flows = _flows(record)
        return operating_cost() + sum(
            _cost(kwh, price(source), MISSING_PRICE)
            for source, kwh in flows.from_pv.items()
        )

    formulas: dict[str, Callable[[], float]] = {
        TOTAL_COST_SAVINGS: savings,
        TOTAL_LEVELIZED_COST_SAVINGS: levelized_savings,
        TOTAL_EXPORT_COMPENSATION: export_compensation,
        TOTAL_FINANCIAL_RETURN: lambda: savings() + export_compensation(),
        TOTAL_LEVELIZED_FINANCIAL_RETURN: lambda: (
            levelized_savings()
            + export_compensation()
            - _cost(exported(), price(record.uid), MISSING_PRICE)
        ),
        TOTAL_OPERATING_COST: operating_cost,
        TOTAL_LEVELIZED_OPERATING_COST: levelized_operating_cost,
    }
    keys = BATTERY_TOTALS if record.kind == BATTERY else PV_TOTALS

    values: dict[str, float | None] = {}
    missing: dict[str, str] = {}
    for key in keys:
        try:
            values[key] = formulas[key]()
        except _Missing as err:
            values[key] = None
            missing[key] = err.reason
    return Totals(values, missing)
