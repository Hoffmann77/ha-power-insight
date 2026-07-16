"""Shared building blocks for class-per-scenario ``PowerInsight`` engine tests.

This module is *infrastructure*, not a test file (its name does not start with
``test_`` so pytest never collects it directly). It provides the two ingredients
that fully determine every derived engine quantity — a device configuration and
a set of entity readings — plus one helper that assembles them into an engine.

A scenario test pins exactly one device and one reading set and asserts engine
properties against hand-written expected values (good for edge cases: zero gross
power, pure export, unavailable sensors, adapter routing, …). See
``test_engine_property_scenarios.py`` for the pattern::

    class TestMyScenario:
        DEVICE = PRESET_DEVICES["grid_pv_battery"]     # or a custom DeviceConfig
        ENTITIES = {GRID_POWER: 1000.0, ...}            # exactly one reading set

        @pytest.fixture
        def pi(self):
            return build_engine_for(self.DEVICE, self.ENTITIES)

        def test_gross_power(self, pi):
            assert pi.gross_power == pytest.approx(4000.0)

Device configuration — preset or custom
---------------------------------------

``DEVICE`` is either the *name* of a preset in :data:`PRESET_DEVICES`
(``"grid_only"`` / ``"grid_pv"`` / ``"grid_pv_battery"`` / ``"full"``) or a
custom :class:`DeviceConfig` built from :class:`GridSpec` / :class:`PvSpec` /
:class:`BatterySpec` / :class:`ConsumerSpec`. Every device has exactly one grid
(an engine invariant). Specs are declarative and each ``build()`` yields a fresh
stateful adapter, so presets are safe to reuse across classes.

Entity readings
---------------

``ENTITIES`` is a raw ``{entity_id: watts}`` mapping, already in the engine's
sign convention:

* Grid   — ``+`` import  / ``-`` export
* PV/Bat — ``+`` produce/discharge / ``-`` standby/charge

Preset devices draw their ids from the canonical constants below
(``GRID_POWER`` etc.); custom devices may use their own ids. :func:`build_engine_for`
validates every id against the chosen device and raises ``ValueError`` on one
that is not routable — catching both typos and device/reading mismatches.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from typing import Any, Union

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
# Canonical entity ids used by the preset devices. Custom devices may use their
# own ids instead.
# ---------------------------------------------------------------------------

GRID_POWER = "sensor.grid_power"
GRID_PRICE = "sensor.grid_price"
GRID_CO2 = "sensor.grid_co2"
PV1_POWER = "sensor.pv1_power"
PV2_POWER = "sensor.pv2_power"
PV3_POWER = "sensor.pv3_power"
BAT1_POWER = "sensor.bat1_power"
BAT2_POWER = "sensor.bat2_power"
BAT3_POWER = "sensor.bat3_power"
CONS1_POWER = "sensor.cons1_power"


# ---------------------------------------------------------------------------
# Adapter specs — declarative, decoupled from adapter construction so a preset
# ``DeviceConfig`` can be reused across classes and always yields *fresh* (empty)
# adapters. Every ``build()`` returns a brand-new stateful adapter instance.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GridSpec:
    """One grid adapter. Every device needs exactly one (engine invariant)."""

    uid: str = "grid"
    name: str = "Grid"
    power_entity: str = GRID_POWER
    price_entity: str | None = GRID_PRICE
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
# Preset device configurations
# ---------------------------------------------------------------------------

_PV1 = PvSpec(
    uid="pv1",
    name="PV-1",
    power_entity=PV1_POWER,
    lcoe=0.10,
    lco2_intensity=35.0,
    exports_power=True,
    export_compensation=0.08,
)
_PV2 = PvSpec(
    uid="pv2",
    name="PV-2",
    power_entity=PV2_POWER,
    lcoe=0.12,
    lco2_intensity=40.0,
    exports_power=True,
    export_compensation=0.08,
)
_PV3 = PvSpec(
    uid="pv3",
    name="PV-3",
    power_entity=PV3_POWER,
    lcoe=0.15,
    lco2_intensity=50.0,
    exports_power=False,
    export_compensation=0.0,
)
_CONS1 = ConsumerSpec(uid="cons1", name="Consumer-1", power_entity=CONS1_POWER)


PRESET_DEVICES: dict[str, DeviceConfig] = {
    # Grid connection only — the minimal legal device.
    "grid_only": DeviceConfig(grid=GridSpec()),
    # Grid + one exporting PV system.
    "grid_pv": DeviceConfig(grid=GridSpec(), pv=(_PV1,)),
    # Grid + PV + one battery that charges from grid and PV + a consumer.
    "grid_pv_battery": DeviceConfig(
        grid=GridSpec(),
        pv=(_PV1,),
        batteries=(
            BatterySpec(
                uid="bat1",
                name="Battery-1",
                power_entity=BAT1_POWER,
                lcos=0.15,
                lco2_intensity=50.0,
                charge_from_adapters=("grid", "pv1"),
            ),
        ),
        consumers=(_CONS1,),
    ),
    # The full scenario used by test_power_insight_calculations: 3 PV + 3 bat.
    "full": DeviceConfig(
        grid=GridSpec(),
        pv=(_PV1, _PV2, _PV3),
        batteries=(
            BatterySpec(uid="bat1", name="Battery-1", power_entity=BAT1_POWER),
            BatterySpec(uid="bat2", name="Battery-2", power_entity=BAT2_POWER),
            BatterySpec(uid="bat3", name="Battery-3", power_entity=BAT3_POWER),
        ),
        consumers=(_CONS1,),
    ),
}


# ---------------------------------------------------------------------------
# Engine assembly
# ---------------------------------------------------------------------------

DeviceLike = Union[str, DeviceConfig]


def resolve_device(device: DeviceLike) -> DeviceConfig:
    """Resolve a preset device name or a :class:`DeviceConfig` to the latter."""
    if isinstance(device, DeviceConfig):
        return device
    try:
        return PRESET_DEVICES[device]
    except KeyError:
        raise KeyError(
            f"Unknown preset device {device!r}. Available: {sorted(PRESET_DEVICES)}"
        ) from None


def build_engine_for(device: DeviceLike, entities: dict[str, float | None]) -> Any:
    """Build a :class:`PowerInsight` engine from a device config and readings.

    ``device`` is a :data:`PRESET_DEVICES` name or a :class:`DeviceConfig`;
    ``entities`` is a ``{entity_id: watts}`` mapping in the engine's sign
    convention. Every entity id must be routable for the chosen device (i.e.
    belong to one of its adapters); an unknown id raises ``ValueError`` to catch
    typos and device/reading mismatches. Returns the ready-to-query engine.
    """
    config = resolve_device(device)
    pi = config.build_engine()
    routable = set(pi.entity_mapping)

    unknown = sorted(set(entities) - routable)
    if unknown:
        raise ValueError(
            f"unknown entity id(s) {unknown}. "
            f"Routable for this device: {sorted(routable)}"
        )

    for entity_id, value in entities.items():
        pi.set_value(entity_id, value)

    return pi
