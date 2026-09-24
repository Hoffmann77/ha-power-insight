"""Declarative homes: how every engine-tier test describes a house.

A home is a class whose attributes are its devices, each declared with its
reading — the wiring and the snapshot in one place, like fields on a model::

    class TestIdleAdapterIsInNoFlowGroup(Home):
        \"\"\"Decision: an adapter reading exactly 0 W belongs to neither flow
        group. ...\"\"\"

        grid = Grid(500)
        bat1 = Battery(0)
        plug = Consumer(-100)

        @expect("sink_adapters_source_shares")
        def test_source_shares(self):
            \"\"\"Only the plug gets a provenance row, all of it grid.\"\"\"
            return {"plug": {"grid": 1}}

The attribute name is the adapter's uid — the key in ``charge_from``,
``power_from`` and every expected map. The first argument is the device's
power reading in watts, ``None`` for an unavailable sensor; everything after
it is the device's static config, with the same keywords and defaults as the
:class:`Adapter` factories. The grid is always ``grid``, and carries the
tariff: ``grid = Grid(300, price=F(3, 10))``. A restriction names the devices
above it directly::

    grid = Grid(400)
    pv1 = Pv(1000)
    bat1 = Battery(-400, charge_from=(grid, pv1))

Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery ``+``
produce/discharge / ``-`` standby/charge; consumer ``-`` = load.

A home is checked when its class is created, so a miswired one fails at
collection: exactly one grid, named ``grid``, every restriction naming a
device of the same home, and every device given a reading.

Tests are ordinary pytest methods on the class. Take ``power_insight`` for a
freshly built engine holding the home's readings, or use :func:`expect`,
whose method takes only ``self`` and *returns* the value an engine property
should have; :func:`matches` is the comparison, the one the whole tier uses.

The same devices, declared *without* readings, are the wiring of a reference
case, whose snapshots then supply the readings — see
``tests/engine/reference/case.py``. Beneath both sit the plain data the
generated homes and the frozen snapshots are built from directly:
:class:`Adapter` (one adapter's kind and config), :class:`Topology` (a set of
adapters), :class:`State` (``uid -> watts`` plus the grid price) and
:class:`Cell` (the two together, ready to build an engine).
"""

from __future__ import annotations

import importlib.util
import inspect
import os
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Callable, ClassVar, Iterable

import pytest

__all__ = [
    "Adapter",
    "Battery",
    "Cell",
    "Consumer",
    "Grid",
    "Home",
    "Pv",
    "State",
    "Topology",
    "expect",
    "matches",
    "show",
]

# ---------------------------------------------------------------------------
# Load the pure-Python engine directly (same importlib trick as the other
# engine-tier tests — no Home Assistant import).
# ---------------------------------------------------------------------------

_MODULE_PATH = os.path.join(
    os.path.dirname(__file__),
    os.pardir,
    os.pardir,
    "custom_components",
    "power_insight",
    "power_insight.py",
)
_spec = importlib.util.spec_from_file_location("power_insight", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

PowerInsight = _mod.PowerInsight
GridAdapter = _mod.GridAdapter
PvAdapter = _mod.PvAdapter
BatteryAdapter = _mod.BatteryAdapter
ConsumerAdapter = _mod.ConsumerAdapter
FlowRole = _mod.FlowRole

GRID_PRICE_ENTITY = "sensor.grid_price"


# ---------------------------------------------------------------------------
# The plain data beneath a home: Adapter, Topology, State, Cell.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Adapter:
    """One adapter's kind + static config. Build via the classmethod factories.

    A home's devices are declared with :class:`Pv` and friends, which pass
    their config to these factories; the generated homes use them directly.
    """

    kind: str
    #: The adapter's unique id — exactly the key used in State(...), charge_from,
    #: power_from and expected-dict keys. The grid is always ``"grid"``.
    uid: str
    config: dict[str, Any]
    inverted: bool = False
    has_price: bool = True  # whether the grid has a price source entity at all

    # -- factories --------------------------------------------------------

    @classmethod
    def grid(
        cls,
        *,
        inverted: bool = False,
        name: str = "Grid",
        has_price_entity: bool = True,
    ) -> "Adapter":
        return cls(
            "grid",
            "grid",
            {"name": name},
            inverted=inverted,
            has_price=has_price_entity,
        )

    @classmethod
    def pv(
        cls,
        uid: str,
        *,
        lcoe: float | None = 0.10,
        lco2_intensity: float | None = 50.0,
        exports: bool = False,
        export_comp: float = 0.0,
        correction_factor: float = 1.0,
        inverted: bool = False,
        name: str | None = None,
    ) -> "Adapter":
        return cls(
            "pv",
            uid,
            {
                "name": name,
                "lcoe": lcoe,
                "lco2_intensity": lco2_intensity,
                "exports_power": exports,
                "export_compensation": export_comp,
                "correction_factor": correction_factor,
            },
            inverted=inverted,
        )

    @classmethod
    def battery(
        cls,
        uid: str,
        *,
        lcos: float | None = 0.15,
        lco2_intensity: float | None = 100.0,
        exports: bool = False,
        export_comp: float = 0.0,
        charge_from: tuple[str, ...] = (),
        correction_factor: float = 1.0,
        inverted: bool = False,
        name: str | None = None,
    ) -> "Adapter":
        return cls(
            "battery",
            uid,
            {
                "name": name,
                "lcos": lcos,
                "lco2_intensity": lco2_intensity,
                "exports_power": exports,
                "export_compensation": export_comp,
                "charge_from_adapters": tuple(charge_from),
                "correction_factor": correction_factor,
            },
            inverted=inverted,
        )

    @classmethod
    def consumer(
        cls,
        uid: str,
        *,
        power_from: tuple[str, ...] = (),
        inverted: bool = False,
        name: str | None = None,
    ) -> "Adapter":
        return cls(
            "consumer",
            uid,
            {"name": name, "power_from_adapters": tuple(power_from)},
            inverted=inverted,
        )

    # -- derived ----------------------------------------------------------

    @property
    def power_entity(self) -> str:
        return f"sensor.{self.uid}_power"

    @property
    def power_source_uids(self) -> tuple[str, ...]:
        """The uids this adapter restricts its intake to (battery / consumer)."""
        if self.kind == "battery":
            return tuple(self.config["charge_from_adapters"])
        if self.kind == "consumer":
            return tuple(self.config["power_from_adapters"])
        return ()

    def build(self) -> Any:
        """Instantiate the real engine adapter (fresh, no readings)."""
        cfg = self.config
        if self.kind == "grid":
            return GridAdapter(
                unique_id=self.uid,
                verbose_name=cfg["name"],
                power_entity=self.power_entity,
                power_entity_inverted=self.inverted,
                price_entity=GRID_PRICE_ENTITY if self.has_price else None,
                co2_entity=None,
            )
        if self.kind == "pv":
            return PvAdapter(
                unique_id=self.uid,
                verbose_name=cfg["name"] or self.uid,
                power_entity=self.power_entity,
                power_entity_inverted=self.inverted,
                lcoe=cfg["lcoe"],
                lco2_intensity=cfg["lco2_intensity"],
                exports_power=cfg["exports_power"],
                export_compensation=cfg["export_compensation"],
                correction_factor=cfg["correction_factor"],
            )
        if self.kind == "battery":
            return BatteryAdapter(
                unique_id=self.uid,
                verbose_name=cfg["name"] or self.uid,
                power_entity=self.power_entity,
                power_entity_inverted=self.inverted,
                lcos=cfg["lcos"],
                lco2_intensity=cfg["lco2_intensity"],
                exports_power=cfg["exports_power"],
                export_compensation=cfg["export_compensation"],
                charge_from_adapters=list(cfg["charge_from_adapters"]),
                # Frozen homes stored before batteries took a factor have none.
                correction_factor=cfg.get("correction_factor", 1.0),
            )
        if self.kind == "consumer":
            return ConsumerAdapter(
                unique_id=self.uid,
                verbose_name=cfg["name"] or self.uid,
                power_entity=self.power_entity,
                power_entity_inverted=self.inverted,
                power_from_adapters=list(cfg["power_from_adapters"]),
            )
        raise ValueError(f"unknown adapter kind {self.kind!r}")


@dataclass
class Topology:
    """One house: exactly one grid plus any PV / battery / consumer adapters.

    Validated at construction: exactly one grid, unique uids, and every battery
    ``charge_from`` / consumer ``power_from`` target present.
    """

    adapters: tuple[Adapter, ...]
    name: str = ""  # the home's name, for test ids and messages

    def __init__(self, *adapters: Adapter, name: str = "") -> None:
        self.adapters = tuple(adapters)
        self.name = name
        self._validate()

    def _validate(self) -> None:
        grids = [a for a in self.adapters if a.kind == "grid"]
        if len(grids) != 1:
            raise ValueError(f"topology needs exactly one grid, got {len(grids)}")
        uids = [a.uid for a in self.adapters]
        dupes = {u for u in uids if uids.count(u) > 1}
        if dupes:
            raise ValueError(f"duplicate adapter uid(s) {sorted(dupes)}")
        known = set(uids)
        for a in self.adapters:
            for src in a.power_source_uids:
                if src not in known:
                    field = "charge_from" if a.kind == "battery" else "power_from"
                    raise ValueError(
                        f"{a.kind} {a.uid!r} {field} references unknown adapter "
                        f"{src!r}; known: {sorted(known)}"
                    )

    @property
    def uids(self) -> frozenset[str]:
        return frozenset(a.uid for a in self.adapters)

    def build_engine(self) -> Any:
        pi = PowerInsight()
        for a in self.adapters:
            pi.register_adapter(a.build())
        return pi


@dataclass(frozen=True)
class State:
    """A named set of readings: ``uid -> power`` plus the grid ``price``.

    ``State(grid=-1000, pv1=2000, price=0.30)``. ``price`` is reserved for the
    grid price (EUR/kWh); every other kwarg is an adapter uid -> power (W), with
    ``None`` modelling an unavailable sensor.
    """

    readings: dict[str, float | None]
    price: float | None = None
    name: str = ""  # the snapshot's name, for test ids and messages

    def __init__(
        self, *, price: float | None = None, name: str = "", **readings: float | None
    ) -> None:
        object.__setattr__(self, "readings", dict(readings))
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "name", name)

    def __getattr__(self, item: str) -> float | None:
        # Let formula-style tests write ``state.pv1`` for a reading.
        try:
            return self.readings[item]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(item) from exc


@dataclass(frozen=True)
class Cell:
    """A topology with one set of readings, ready to build an engine."""

    topology: Topology
    state: State

    @property
    def id(self) -> str:
        parts = [self.topology.name, self.state.name]
        return "-".join(p for p in parts if p) or "cell"

    def build_engine(self) -> Any:
        pi = self.topology.build_engine()
        for uid, value in self.state.readings.items():
            pi.set_value(f"sensor.{uid}_power", value)
        if self.state.price is not None:
            pi.set_value(GRID_PRICE_ENTITY, self.state.price)
        return pi


def check_compatible(topology: Topology, state: State) -> None:
    """A state must name exactly the topology's adapter uids (safety rail)."""
    want = topology.uids
    have = frozenset(state.readings)
    if want != have:
        missing = sorted(want - have)
        extra = sorted(have - want)
        raise ValueError(
            f"state {state.name!r} is incompatible with topology "
            f"{topology.name!r}: missing readings {missing}, unexpected {extra}. "
            f"(A state must supply exactly the topology's uids {sorted(want)}.)"
        )


# ---------------------------------------------------------------------------
# Comparing an engine value with a hand-written one.
# ---------------------------------------------------------------------------


def matches(expected: Any, actual: Any, *, abs_tol: float | None = None) -> bool:
    """Whether an engine attribute equals a hand-written expected value.

    The single comparator for the whole engine tier, so "did the engine give
    the right answer" means one thing everywhere.

    Maps compare key set first, at every level: a leaked or missing row is a
    real disagreement, not a rounding one. ``None`` is a value in its own right
    — the engine publishing nothing at all — so it matches only another
    ``None``, and never a zero.

    ``abs_tol`` is the per-value absolute tolerance; ``None`` falls back to
    ``pytest.approx``'s relative tolerance, which is what an expectation
    written as an exact fraction wants.
    """
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(expected) != set(actual):
            return False
        return all(matches(v, actual[k], abs_tol=abs_tol) for k, v in expected.items())
    if isinstance(actual, dict):
        return False
    return actual == pytest.approx(expected, abs=abs_tol)


def show(value: Any) -> str:
    """A value in the most readable exact form: ``1200``, ``8/15``, a map."""
    if value is None:
        return "nothing at all"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, dict):
        return (
            "{" + ", ".join(f"{k}: {show(v)}" for k, v in sorted(value.items())) + "}"
        )
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(show(v) for v in value) + "]"
    exact = Fraction(value).limit_denominator(1_000_000)
    return str(exact.numerator) if exact.denominator == 1 else str(exact)



# ---------------------------------------------------------------------------
# Devices — one per class attribute.
# ---------------------------------------------------------------------------

#: A device declared without a reading: the wiring of a reference case, whose
#: snapshots supply the readings.
NO_READING: Any = type("NoReading", (), {"__repr__": lambda self: "NO_READING"})()


class Device:
    """One device of a home: its power reading plus its static config."""

    #: The :class:`Adapter` factory this device's config is passed to.
    factory: ClassVar[Callable[..., Adapter]]

    def __init__(self, power: float | None = NO_READING, **config: Any) -> None:
        # Check the keywords now, so a typo fails on the line that has it.
        inspect.signature(self.factory).bind(*self._uid_args("uid"), **config)
        self.power = power
        self.config = config
        self.uid = ""

    def __set_name__(self, owner: type, name: str) -> None:
        self.uid = name

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.power!r})"

    def _uid_args(self, uid: str) -> tuple[str, ...]:
        return (uid,)

    @property
    def adapter(self) -> Adapter:
        return self.factory(*self._uid_args(self.uid), **_resolve(self.config))


class Grid(Device):
    """The grid meter. ``price`` is the tariff in EUR/kWh (``None``: unknown)."""

    factory = staticmethod(Adapter.grid)

    def __init__(
        self,
        power: float | None = NO_READING,
        *,
        price: float | None = None,
        **config: Any,
    ) -> None:
        super().__init__(power, **config)
        self.price = price

    def _uid_args(self, uid: str) -> tuple[str, ...]:
        return ()  # the grid's uid is always "grid"


class Pv(Device):
    factory = staticmethod(Adapter.pv)


class Battery(Device):
    factory = staticmethod(Adapter.battery)


class Consumer(Device):
    factory = staticmethod(Adapter.consumer)


def _resolve(config: dict[str, Any]) -> dict[str, Any]:
    """``charge_from`` / ``power_from`` may name devices; the adapter wants uids."""
    return {
        key: tuple(v.uid if isinstance(v, Device) else v for v in value)
        if key in ("charge_from", "power_from")
        else value
        for key, value in config.items()
    }


def declared_devices(cls: type) -> tuple[Device, ...]:
    """The devices a class declares, its bases' included, in declaration order."""
    found: dict[str, Device] = {}
    for klass in reversed(cls.__mro__):
        found.update(
            (name, obj) for name, obj in vars(klass).items() if isinstance(obj, Device)
        )
    return tuple(found.values())


def wiring(cls: type, devices: Iterable[Device], *, base: type) -> Topology:
    """The topology ``devices`` declare, checked; errors name ``cls``.

    ``base`` is the framework class being subclassed: a device may not take a
    name it already uses, nor ``price`` / ``name``, which the readings reserve.
    """
    devices = tuple(devices)
    reserved = set(dir(base)) | {"price", "name"}
    for device in devices:
        if device.uid in reserved:
            raise TypeError(
                f"{cls.__name__}: a device may not be called {device.uid!r}, "
                f"which is reserved"
            )
        if isinstance(device, Grid) and device.uid != "grid":
            raise TypeError(
                f"{cls.__name__}: declare the grid as 'grid = Grid(...)', "
                f"not {device.uid!r}"
            )
    try:
        return Topology(*(d.adapter for d in devices), name=cls.__name__)
    except ValueError as exc:
        raise TypeError(f"{cls.__name__}: {exc}") from None


# ---------------------------------------------------------------------------
# Home — the base class.
# ---------------------------------------------------------------------------


class Home:
    """A home: devices, with their readings, as class attributes; tests as methods.

    See the module docstring. Subclass it as ``TestSomething`` so pytest
    collects it; a subclass declaring no devices is abstract and not checked.
    """

    #: The home's devices, in declaration order (set per subclass).
    devices: ClassVar[tuple[Device, ...]] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.devices = declared_devices(cls)
        if not cls.devices:
            return
        wiring(cls, cls.devices, base=Home)
        unread = [d.uid for d in cls.devices if d.power is NO_READING]
        if unread:
            raise TypeError(
                f"{cls.__name__}: {unread} have no reading — give each device "
                f"its watts first, e.g. 'pv1 = Pv(600)' ('None' if unavailable)"
            )

    @classmethod
    def cell(cls) -> Cell:
        """The home as a (topology, state) pair, ready to build an engine."""
        grid = next(d for d in cls.devices if isinstance(d, Grid))
        state = State(
            price=grid.price,
            name=cls.__name__,
            **{d.uid: d.power for d in cls.devices},
        )
        return Cell(wiring(cls, cls.devices, base=Home), state)

    @pytest.fixture
    def power_insight(self) -> Any:
        """A freshly built engine holding this home's readings."""
        return self.cell().build_engine()


# ---------------------------------------------------------------------------
# @expect
# ---------------------------------------------------------------------------


def expect(
    attribute: str, *, abs_tol: float | None = None
) -> Callable[[Callable[[Any], Any]], Callable[[Any, Any], None]]:
    """Turn a method that *returns* an expected value into a test.

    The method takes only ``self`` and returns what ``power_insight.<attribute>``
    should be; the comparison is :func:`matches` (maps compare key sets first,
    ``None`` matches only ``None``)::

        @expect("home_base_load_source_shares")
        def test_base_load(self):
            return {"grid": F(8, 9), "pv1": F(1, 9)}

    ``abs_tol`` sets a per-value absolute tolerance, for expectations that
    really must be written rounded; the default keeps ``pytest.approx``'s
    relative tolerance, which is what an exact fraction wants.
    """

    def decorator(fn: Callable[[Any], Any]) -> Callable[[Any, Any], None]:
        def wrapper(self: Any, power_insight: Any) -> None:
            expected = fn(self)
            actual = getattr(power_insight, attribute)
            state = self.cell().state
            readings = ", ".join(f"{k}={show(v)}" for k, v in state.readings.items())
            if state.price is not None:
                readings += f", price={show(state.price)}"
            assert matches(expected, actual, abs_tol=abs_tol), (
                f"\n{attribute}\n"
                f"  readings: {readings}\n\n"
                f"  expected: {show(expected)}\n"
                f"  actual:   {show(actual)}\n"
            )

        # Copy identity for pytest's node id and docstring, but not
        # ``__wrapped__``: ``inspect.signature`` would follow it to ``fn`` and
        # hide the ``power_insight`` parameter pytest must inject.
        wrapper.__name__ = fn.__name__
        wrapper.__qualname__ = fn.__qualname__
        wrapper.__doc__ = fn.__doc__
        wrapper.__module__ = fn.__module__
        wrapper.expected = fn  # type: ignore[attr-defined]
        wrapper.attribute = attribute  # type: ignore[attr-defined]
        return wrapper

    return decorator
