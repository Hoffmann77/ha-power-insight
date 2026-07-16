"""Shared building blocks for class-per-scenario ``PowerInsight`` engine tests.

This module is *infrastructure*, not a test file (its name does not start with
``test_`` so pytest never collects it directly). A scenario lists the adapters
that make up the device, each with its reading, using :func:`Add`; every other
detail (adapter config, uid, entity id) comes from a named preset and the
adapter's index.

A scenario test subclasses :class:`EngineScenario`, sets ``DEVICES``, and each
``test_`` method asserts one engine property against a hand-written expected
value (good for edge cases: zero gross power, pure export, unavailable sensors,
adapter routing, …)::

    class TestBatteryChargingSplit(EngineScenario):
        DEVICES = [
            Add("grid", power=1000, price=0.30),
            Add("pv_with_export", 1, power=3000),
            Add("battery", 1, power=-500, charge_from=["grid", "pv1"]),
            Add("consumer", 1, power=-800),
        ]

        def test_gross_power(self, power_insight):
            assert power_insight.gross_power == pytest.approx(4000.0)

``Add(preset, number=1, *, power, price=None, charge_from=None, inverted=False, **overrides)``
---------------------------------------------------------------------------------------------

* ``preset`` — an :data:`ADAPTER_PRESETS` key that fixes the adapter kind and
  its default config (``"grid"`` / ``"pv_with_export"`` / ``"pv_no_export"`` /
  ``"battery"`` / ``"consumer"``).
* ``number`` — the adapter index. It derives the uid and entity id:
  ``pv`` 1 → uid ``"pv1"``, entity ``"sensor.pv1_power"``; ``battery`` → ``"bat1"``;
  ``consumer`` → ``"cons1"``; ``grid`` is always uid ``"grid"`` (index ignored).
* ``power`` — the power reading in watts (engine sign convention below).
  ``None`` models an unavailable sensor.
* ``price`` — grid only: the price reading (EUR/kWh). Omit → price unavailable.
* ``charge_from`` — battery only: the uids this battery charges from
  (e.g. ``["grid", "pv1"]``).
* ``inverted`` — set ``power_entity_inverted`` (a +reading then means the
  opposite sign — e.g. grid ``power=600, inverted=True`` is 600 W export).
* ``**overrides`` — override the preset's config for this adapter
  (``lcoe`` / ``lcos`` / ``exports_power`` / ``export_compensation`` /
  ``lco2_intensity`` / ``correction_factor`` / ``name``). Use it when an
  expected value depends on a config number you want visible at the test site.

Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery ``+``
produce/discharge / ``-`` standby/charge; consumer ``-`` = load.

:func:`build_engine` turns a ``DEVICES`` list into a ready-to-query engine,
validating that there is exactly one grid, that indices don't collide, and that
every ``charge_from`` target exists (raising ``ValueError`` otherwise).
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Load the pure-Python engine directly, bypassing all Home Assistant imports
# (same trick the other engine tests use).
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
# Adapter specs — declarative, decoupled from adapter construction so each
# ``build()`` yields a fresh (empty) adapter. ``build_engine`` assembles these
# from the ``Add`` entries; scenarios normally never touch them directly.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GridSpec:
    """One grid adapter. Every device needs exactly one (engine invariant)."""

    uid: str = "grid"
    name: str = "Grid"
    power_entity: str = "sensor.grid_power"
    price_entity: str | None = "sensor.grid_price"
    co2_entity: str | None = None
    power_entity_inverted: bool = False

    def build(self) -> Any:
        return GridAdapter(
            unique_id=self.uid,
            verbose_name=self.name,
            power_entity=self.power_entity,
            power_entity_inverted=self.power_entity_inverted,
            price_entity=self.price_entity,
            co2_entity=self.co2_entity,
        )


@dataclass(frozen=True)
class PvSpec:
    """One PV-system adapter."""

    uid: str
    power_entity: str
    name: str | None = None
    lcoe: float | None = 0.10
    lco2_intensity: float | None = 50.0
    exports_power: bool = False
    export_compensation: float = 0.0
    power_entity_inverted: bool = False
    correction_factor: float = 1.0

    def build(self) -> Any:
        return PvAdapter(
            unique_id=self.uid,
            verbose_name=self.name or self.uid,
            power_entity=self.power_entity,
            power_entity_inverted=self.power_entity_inverted,
            lcoe=self.lcoe,
            lco2_intensity=self.lco2_intensity,
            exports_power=self.exports_power,
            export_compensation=self.export_compensation,
            correction_factor=self.correction_factor,
        )


@dataclass(frozen=True)
class BatterySpec:
    """One battery adapter."""

    uid: str
    power_entity: str
    name: str | None = None
    lcos: float | None = 0.15
    lco2_intensity: float | None = 100.0
    exports_power: bool = False
    export_compensation: float = 0.0
    charge_from_adapters: tuple[str, ...] = ()
    power_entity_inverted: bool = False
    correction_factor: float = 1.0

    def build(self) -> Any:
        return BatteryAdapter(
            unique_id=self.uid,
            verbose_name=self.name or self.uid,
            power_entity=self.power_entity,
            power_entity_inverted=self.power_entity_inverted,
            lcos=self.lcos,
            lco2_intensity=self.lco2_intensity,
            exports_power=self.exports_power,
            export_compensation=self.export_compensation,
            charge_from_adapters=list(self.charge_from_adapters),
            correction_factor=self.correction_factor,
        )


@dataclass(frozen=True)
class ConsumerSpec:
    """One consumer adapter."""

    uid: str
    power_entity: str
    name: str | None = None
    power_entity_inverted: bool = False

    def build(self) -> Any:
        return ConsumerAdapter(
            unique_id=self.uid,
            verbose_name=self.name or self.uid,
            power_entity=self.power_entity,
            power_entity_inverted=self.power_entity_inverted,
        )


@dataclass(frozen=True)
class DeviceConfig:
    """A full device configuration: one grid plus any PV/battery/consumers."""

    grid: GridSpec = field(default_factory=GridSpec)
    pv: tuple[PvSpec, ...] = ()
    batteries: tuple[BatterySpec, ...] = ()
    consumers: tuple[ConsumerSpec, ...] = ()

    def build_engine(self) -> Any:
        """Return a fresh :class:`PowerInsight` with all adapters registered."""
        pi = PowerInsight()
        pi.register_adapter(self.grid.build())
        for spec in self.pv:
            pi.register_adapter(spec.build())
        for spec in self.batteries:
            pi.register_adapter(spec.build())
        for spec in self.consumers:
            pi.register_adapter(spec.build())
        return pi


# ---------------------------------------------------------------------------
# Adapter presets + the Add() authoring surface
# ---------------------------------------------------------------------------

# preset -> adapter kind + default config. Config keys are visible here so an
# expected value that depends on one (e.g. export_compensation) is documented.
ADAPTER_PRESETS: dict[str, dict[str, Any]] = {
    "grid": {"kind": "grid"},
    "pv_with_export": {
        "kind": "pv",
        "lcoe": 0.10,
        "lco2_intensity": 35.0,
        "exports_power": True,
        "export_compensation": 0.08,
    },
    "pv_no_export": {
        "kind": "pv",
        "lcoe": 0.15,
        "lco2_intensity": 50.0,
        "exports_power": False,
        "export_compensation": 0.0,
    },
    "battery": {
        "kind": "battery",
        "lcos": 0.15,
        "lco2_intensity": 50.0,
        "exports_power": False,
        "export_compensation": 0.0,
    },
    "consumer": {"kind": "consumer"},
}

_KIND_PREFIX = {"grid": "grid", "pv": "pv", "battery": "bat", "consumer": "cons"}
_OVERRIDE_KEYS = {
    "grid": {"name"},
    "pv": {
        "name", "lcoe", "lco2_intensity", "exports_power",
        "export_compensation", "correction_factor",
    },
    "battery": {
        "name", "lcos", "lco2_intensity", "exports_power",
        "export_compensation", "correction_factor",
    },
    "consumer": {"name"},
}


@dataclass(frozen=True)
class _AddEntry:
    """One adapter in a scenario's ``DEVICES`` list — produced by :func:`Add`."""

    preset: str
    kind: str
    number: int
    power: float | None
    price: float | None
    charge_from: tuple[str, ...] | None
    inverted: bool
    config: dict[str, Any]

    @property
    def uid(self) -> str:
        if self.kind == "grid":
            return "grid"
        return f"{_KIND_PREFIX[self.kind]}{self.number}"

    @property
    def power_entity(self) -> str:
        return f"sensor.{self.uid}_power"


def Add(
    preset: str,
    number: int = 1,
    *,
    power: float | None,
    price: float | None = None,
    charge_from: list[str] | None = None,
    inverted: bool = False,
    **overrides: Any,
) -> _AddEntry:
    """Declare one adapter (with its reading) for a scenario's ``DEVICES`` list.

    See the module docstring for the full parameter reference.
    """
    if preset not in ADAPTER_PRESETS:
        raise ValueError(
            f"Unknown adapter preset {preset!r}. Available: {sorted(ADAPTER_PRESETS)}"
        )
    base = dict(ADAPTER_PRESETS[preset])
    kind = base.pop("kind")

    if price is not None and kind != "grid":
        raise ValueError(f"'price' is only valid for a grid adapter, not {preset!r}")
    if charge_from is not None and kind != "battery":
        raise ValueError(
            f"'charge_from' is only valid for a battery adapter, not {preset!r}"
        )
    bad = set(overrides) - _OVERRIDE_KEYS[kind]
    if bad:
        raise ValueError(
            f"Unknown override(s) {sorted(bad)} for {preset!r}; "
            f"allowed: {sorted(_OVERRIDE_KEYS[kind])}"
        )
    base.update(overrides)

    return _AddEntry(
        preset=preset,
        kind=kind,
        number=number,
        power=power,
        price=price,
        charge_from=tuple(charge_from) if charge_from is not None else None,
        inverted=inverted,
        config=base,
    )


def build_engine(devices: list[_AddEntry]) -> Any:
    """Build a ready-to-query :class:`PowerInsight` from a ``DEVICES`` list.

    Assembles one adapter per :func:`Add` entry, applies its reading, and
    validates the device: exactly one grid, unique indices, and every
    ``charge_from`` target present. Raises ``ValueError`` on any violation.
    """
    grids: list[GridSpec] = []
    pvs: list[PvSpec] = []
    batteries: list[BatterySpec] = []
    consumers: list[ConsumerSpec] = []
    readings: dict[str, float | None] = {}
    uids: set[str] = set()

    for entry in devices:
        uid = entry.uid
        if uid in uids:
            raise ValueError(
                f"duplicate adapter uid {uid!r} "
                f"(preset {entry.preset!r}, number {entry.number})"
            )
        uids.add(uid)
        readings[entry.power_entity] = entry.power
        cfg = entry.config

        if entry.kind == "grid":
            grids.append(
                GridSpec(
                    uid=uid,
                    name=cfg.get("name", "Grid"),
                    power_entity=entry.power_entity,
                    price_entity="sensor.grid_price",
                    power_entity_inverted=entry.inverted,
                )
            )
            if entry.price is not None:
                readings["sensor.grid_price"] = entry.price
        elif entry.kind == "pv":
            pvs.append(
                PvSpec(
                    uid=uid,
                    power_entity=entry.power_entity,
                    name=cfg.get("name"),
                    lcoe=cfg["lcoe"],
                    lco2_intensity=cfg["lco2_intensity"],
                    exports_power=cfg["exports_power"],
                    export_compensation=cfg["export_compensation"],
                    power_entity_inverted=entry.inverted,
                    correction_factor=cfg.get("correction_factor", 1.0),
                )
            )
        elif entry.kind == "battery":
            batteries.append(
                BatterySpec(
                    uid=uid,
                    power_entity=entry.power_entity,
                    name=cfg.get("name"),
                    lcos=cfg["lcos"],
                    lco2_intensity=cfg["lco2_intensity"],
                    exports_power=cfg["exports_power"],
                    export_compensation=cfg["export_compensation"],
                    charge_from_adapters=entry.charge_from or (),
                    power_entity_inverted=entry.inverted,
                    correction_factor=cfg.get("correction_factor", 1.0),
                )
            )
        elif entry.kind == "consumer":
            consumers.append(
                ConsumerSpec(
                    uid=uid,
                    power_entity=entry.power_entity,
                    name=cfg.get("name"),
                    power_entity_inverted=entry.inverted,
                )
            )

    if len(grids) != 1:
        raise ValueError(f"exactly one grid adapter required, got {len(grids)}")

    for battery in batteries:
        for source in battery.charge_from_adapters:
            if source not in uids:
                raise ValueError(
                    f"battery {battery.uid!r} charge_from references unknown "
                    f"adapter {source!r}; known: {sorted(uids)}"
                )

    config = DeviceConfig(
        grid=grids[0],
        pv=tuple(pvs),
        batteries=tuple(batteries),
        consumers=tuple(consumers),
    )
    pi = config.build_engine()
    for entity_id, value in readings.items():
        pi.set_value(entity_id, value)
    return pi


class EngineScenario:
    """Base for scenario test classes: supplies the ``power_insight`` fixture.

    Subclass it, set ``DEVICES`` to a list of :func:`Add` entries, and write
    ``test_`` methods that take the ``power_insight`` fixture. Not collected by
    pytest itself (name does not start with ``Test``).
    """

    DEVICES: list[_AddEntry] = []

    @pytest.fixture
    def power_insight(self) -> Any:
        return build_engine(self.DEVICES)
