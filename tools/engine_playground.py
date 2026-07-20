"""MockPowerInsight — drive the PowerInsight engine with custom input values.

Self-contained framework: loads the pure-Python engine (``power_insight.py``)
directly, so no Home Assistant install is needed and there is no dependency on
the test suite. Import it, instantiate, mock values, and use it.

``MockPowerInsight`` **is** a ``PowerInsight`` — construct it with adapter configs
(the device topology), feed entity values with :meth:`MockPowerInsight.mock`, then
call any engine method or property on it directly::

    pi = MockPowerInsight(
        Grid(),
        Pv("pv1", exports_power=True, export_compensation=0.08),
        Battery("bat1", charge_from=["grid", "pv1"]),
        Consumer("cons1"),
    )
    pi.mock(grid=1500, grid_price=0.30, pv1=4000, bat1=-800, cons1=-1200)
    pi.gross_power            # 5500.0
    pi.combined_saving_rate   # 0.96
    pi.mock(pv1=0)            # re-mock a slot and read again (chainable)

    pi.print("gross_power", "combined_saving_rate")   # one or many attributes
    pi.print_all()                                    # every property, grouped
    pi.print_all(exclude=["combined_coo_rate"])       # ... minus some

Config vs. value:
  * **config** (constructor) — everything fixed about an adapter: lcoe/lcos,
    export settings, correction_factor, charge_from, name, inverted, …
  * **value** (``.mock()``) — the live sensor readings: each adapter's ``power``
    (keyed by uid) plus the grid's ``grid_price`` / ``grid_co2``. ``None`` models
    an unavailable sensor. Unknown slot names raise with the valid list.

Import it and drive it yourself (run Python from the repo root)::

    from tools.engine_playground import MockPowerInsight, Grid, Pv, Battery, Consumer

    pi = MockPowerInsight(Grid(), Pv("pv1"), Consumer("cons1"))
    pi.mock(grid=1500, grid_price=0.30, pv1=4000, cons1=-1200)
    pi.gross_power
    pi.print_all()

Sign convention (watts):
    grid      +import    / -export
    pv        +produce   / -standby
    battery   +discharge / -charge
    consumer  -load
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Load the pure-Python engine directly, bypassing all Home Assistant imports.
# ---------------------------------------------------------------------------
_MODULE_PATH = os.path.join(
    os.path.dirname(__file__),
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


# ---------------------------------------------------------------------------
# Adapter configs — the constructor arguments of MockPowerInsight. Each is pure
# topology/config; runtime readings are supplied later via .mock().
# ---------------------------------------------------------------------------


@dataclass
class Grid:
    """The single grid connection. Its uid is always ``"grid"``.

    ``with_price`` / ``with_co2`` decide whether a price / co2 sensor exists;
    their readings are mocked via the ``grid_price`` / ``grid_co2`` value slots.
    """

    with_price: bool = True
    with_co2: bool = False
    inverted: bool = False
    name: str = "Grid"


@dataclass
class Pv:
    """A PV-system adapter. ``uid`` (e.g. ``"pv1"``) names its power value slot."""

    uid: str
    lcoe: float | None = 0.10
    lco2_intensity: float | None = 50.0
    exports_power: bool = False
    export_compensation: float = 0.0
    correction_factor: float = 1.0
    inverted: bool = False
    name: str | None = None


@dataclass
class Battery:
    """A battery adapter. ``charge_from`` lists the uids it charges from."""

    uid: str
    charge_from: list[str] = field(default_factory=list)
    lcos: float | None = 0.15
    lco2_intensity: float | None = 100.0
    exports_power: bool = False
    export_compensation: float = 0.0
    correction_factor: float = 1.0
    inverted: bool = False
    name: str | None = None


@dataclass
class Consumer:
    """A consumer adapter."""

    uid: str
    inverted: bool = False
    name: str | None = None


class MockPowerInsight(PowerInsight):
    """A ``PowerInsight`` preconfigured from adapter configs, fed via ``.mock()``.

    Construct with any number of :class:`Grid` / :class:`Pv` / :class:`Battery` /
    :class:`Consumer` configs (exactly one grid). The instance is a real engine,
    so every ``PowerInsight`` property/method works on it directly. Validates
    unique uids and that every ``charge_from`` target exists.
    """

    def __init__(self, *configs: Grid | Pv | Battery | Consumer) -> None:
        super().__init__()
        self.configs = list(configs)
        self._slots: dict[str, str] = {}  # value slot name -> entity_id
        self._values: dict[str, float | None] = {}  # slot name -> mocked value

        grids = [c for c in configs if isinstance(c, Grid)]
        if len(grids) != 1:
            raise ValueError(f"exactly one Grid config required, got {len(grids)}")

        seen: set[str] = set()
        for config in configs:
            self._register(config, seen)

        uids = {"grid"} | {
            c.uid for c in configs if isinstance(c, (Pv, Battery, Consumer))
        }
        for config in configs:
            if isinstance(config, Battery):
                for source in config.charge_from:
                    if source not in uids:
                        raise ValueError(
                            f"Battery {config.uid!r} charge_from references unknown "
                            f"adapter {source!r}; known: {sorted(uids)}"
                        )

    def _add_slot(self, name: str, entity_id: str, seen: set[str]) -> None:
        if name in seen:
            raise ValueError(f"duplicate value slot / uid {name!r}")
        seen.add(name)
        self._slots[name] = entity_id

    def _register(self, config, seen: set[str]) -> None:
        if isinstance(config, Grid):
            price_entity = "sensor.grid_price" if config.with_price else None
            co2_entity = "sensor.grid_co2" if config.with_co2 else None
            self.register_adapter(
                GridAdapter(
                    unique_id="grid",
                    verbose_name=config.name,
                    power_entity="sensor.grid_power",
                    power_entity_inverted=config.inverted,
                    price_entity=price_entity,
                    co2_entity=co2_entity,
                )
            )
            self._add_slot("grid", "sensor.grid_power", seen)
            if price_entity:
                self._add_slot("grid_price", price_entity, seen)
            if co2_entity:
                self._add_slot("grid_co2", co2_entity, seen)

        elif isinstance(config, Pv):
            entity = f"sensor.{config.uid}_power"
            self.register_adapter(
                PvAdapter(
                    unique_id=config.uid,
                    verbose_name=config.name or config.uid,
                    power_entity=entity,
                    power_entity_inverted=config.inverted,
                    lcoe=config.lcoe,
                    lco2_intensity=config.lco2_intensity,
                    exports_power=config.exports_power,
                    export_compensation=config.export_compensation,
                    correction_factor=config.correction_factor,
                )
            )
            self._add_slot(config.uid, entity, seen)

        elif isinstance(config, Battery):
            entity = f"sensor.{config.uid}_power"
            self.register_adapter(
                BatteryAdapter(
                    unique_id=config.uid,
                    verbose_name=config.name or config.uid,
                    power_entity=entity,
                    power_entity_inverted=config.inverted,
                    lcos=config.lcos,
                    lco2_intensity=config.lco2_intensity,
                    exports_power=config.exports_power,
                    export_compensation=config.export_compensation,
                    charge_from_adapters=list(config.charge_from),
                    correction_factor=config.correction_factor,
                )
            )
            self._add_slot(config.uid, entity, seen)

        elif isinstance(config, Consumer):
            entity = f"sensor.{config.uid}_power"
            self.register_adapter(
                ConsumerAdapter(
                    unique_id=config.uid,
                    verbose_name=config.name or config.uid,
                    power_entity=entity,
                    power_entity_inverted=config.inverted,
                )
            )
            self._add_slot(config.uid, entity, seen)

        else:
            raise TypeError(f"unknown config type {type(config).__name__}")

    def mock(self, **values: float | None) -> "MockPowerInsight":
        """Set entity values by slot name; returns ``self`` for chaining.

        Slots are each adapter's uid (its power reading) plus ``grid_price`` /
        ``grid_co2`` when the grid has them. Unknown names raise ``KeyError``.
        Merges with previously mocked values, so re-mocking one slot is fine.
        """
        for name, value in values.items():
            if name not in self._slots:
                raise KeyError(
                    f"unknown value slot {name!r}; known: {sorted(self._slots)}"
                )
            self._values[name] = value
            self.set_value(self._slots[name], value)
        return self

    @property
    def mocked_values(self) -> dict[str, float | None]:
        """Slot name -> value for every slot mocked so far."""
        return dict(self._values)

    # -- printing helpers ---------------------------------------------------

    def _value_of(self, name: str) -> object:
        try:
            return getattr(self, name)
        except Exception as exc:  # noqa: BLE001 — a raising property is a result too
            return f"<raised {type(exc).__name__}: {exc}>"

    def print(self, *names: str) -> None:
        """Print the value(s) of the given engine attribute name(s).

        Accepts one or many names, or a single list/tuple of names::

            pi.print("gross_power")
            pi.print("gross_power", "combined_saving_rate")
            pi.print(["gross_power", "prod_adapters_export_power"])

        Scalars print as ``name  value``; dict (per-adapter) results print a
        header line followed by indented ``uid  value`` lines.
        """
        if len(names) == 1 and isinstance(names[0], (list, tuple)):
            names = tuple(names[0])
        if not names:
            return
        width = max(len(n) for n in names)
        for name in names:
            value = self._value_of(name)
            if isinstance(value, dict):
                print(f"{name}:")
                if not value:
                    print("    {}")
                for uid, inner in value.items():
                    print(f"    {uid:<8} {_fmt(inner)}")
            else:
                print(f"{name:<{width}}  {_fmt(value)}")

    def print_all(self, exclude: str | list[str] | None = None) -> None:
        """Print every engine property, grouped into scalars and per-adapter maps.

        ``exclude`` (a name or list of names) drops specific properties;
        structural/plumbing helpers are always omitted.
        """
        if isinstance(exclude, str):
            exclude = [exclude]
        excluded = _HELPER_PROPS | set(exclude or ())
        names = [n for n in _engine_properties() if n not in excluded]
        self._render_grouped(names)

    def _render_grouped(self, names: list[str]) -> None:
        scalars: list[tuple[str, object]] = []
        maps: list[tuple[str, dict]] = []
        for name in names:
            value = self._value_of(name)
            (maps if isinstance(value, dict) else scalars).append((name, value))

        if scalars:
            print("=" * 72)
            print("SCALAR / COMBINED PROPERTIES")
            print("=" * 72)
            width = max(len(n) for n, _ in scalars)
            for name, value in scalars:
                print(f"  {name:<{width}}  {_fmt(value)}")
            print()

        if maps:
            print("=" * 72)
            print("PER-ADAPTER PROPERTIES  (uid -> value)")
            print("=" * 72)
            for name, value in maps:
                print(f"  {name}")
                if not value:
                    print("      {}")
                for uid, inner in value.items():
                    print(f"      {uid:<8} {_fmt(inner)}")
                print()

        if not scalars and not maps:
            print("No properties to print.")


# Structural helpers (entity/uid plumbing), not calculation results. Hidden by
# default; shown with ``--all``.
_HELPER_PROPS = {
    "entity_mapping",
    "uid_mapping",
    "prod_adapters",
    "gross_power_adapters",
    "source_entities",
    "source_entities_power",
    "source_entities_price",
    "source_entities_co2",
    "mocked_values",
}


def _engine_properties() -> list[str]:
    """Public ``@property`` names on ``PowerInsight``, in definition order."""
    names: list[str] = []
    for cls in reversed(PowerInsight.__mro__):
        for name, attr in vars(cls).items():
            if isinstance(attr, property) and not name.startswith("_"):
                if name not in names:
                    names.append(name)
    return names


def _fmt(value: object) -> str:
    if value is None:
        return "None"
    if isinstance(value, float):
        return f"{value:.6g}"
    return repr(value)
