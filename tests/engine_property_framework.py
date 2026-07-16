"""Declarative test environment for the ``PowerInsight`` calculation engine.

This module is *infrastructure*, not a test file (its name does not start with
``test_`` so pytest never collects it directly). It lets you assert the return
value of any engine property for a chosen device configuration and a chosen set
of entity readings — the two ingredients that fully determine every derived
quantity.

Unlike ``test_power_insight_calculations.py`` (which re-derives expected values
from the same formulas the engine uses), this framework is built for *edge
cases*: you write the expected value out by hand and the framework checks the
engine agrees. That makes it a good place to pin down degenerate states
(zero gross power, pure export, unavailable sensors, single-vs-multi adapter
routing, …) where a hand-computed number is the whole point of the test.

Two independent axes, each "preset or custom"
---------------------------------------------

* **Device configuration** — ``EngineCase.device`` is either the *name* of a
  preset in :data:`PRESET_DEVICES` (e.g. ``"grid_pv_battery"``) or a custom
  :class:`DeviceConfig` you build inline from :class:`GridSpec` /
  :class:`PvSpec` / :class:`BatterySpec` / :class:`ConsumerSpec`.

* **Entity values** — ``EngineCase.entities`` is either the *name* of a preset
  in :data:`PRESET_ENTITIES` or a raw ``{entity_id: watts}`` mapping. A
  per-case ``entity_overrides`` mapping is merged on top, so a case can say
  "the midday preset, but with the grid sensor unavailable".

All four combinations (preset/custom × preset/custom) work.

Writing a case
--------------

::

    EngineCase(
        name="pure_export_zero_import",
        device="grid_pv",                       # preset device
        entities={GRID_POWER: -3000.0, GRID_PRICE: 0.30, PV1_POWER: 3000.0},
        expected={
            "combined_grid_export": 3000.0,
            "gross_power": 3000.0,
            "gross_power_export_ratio": 1.0,
            "prod_adapters_export_power": {"pv1": 3000.0},
        },
    )

Then either call :func:`assert_engine_case(case)` directly, or parametrize a
test over a list of cases (see ``test_engine_property_cases.py``).

Expected-value matching
-----------------------

Each ``expected`` entry maps a property name on ``PowerInsight`` to its
expected return value. Matching is:

* **numbers** — compared with a tolerance (``rel``/``abs`` per case);
* **None** — the property must return ``None`` (a common "unavailable" edge);
* **dict** — compared by exact key set, recursing into values (per-adapter
  ``{uid: value}`` properties). Wrap with :func:`subset` to check only some
  keys and ignore the rest;
* **callable** — used as a predicate: ``expected(actual)`` must be truthy
  (e.g. ``lambda v: v > 0``);
* anything else — compared with ``==``.

Entity-id validation
---------------------

Every entity id you set must either be routable in the chosen device or be a
known :data:`CANONICAL_ENTITIES` id; otherwise the case fails loudly (this
catches typos like ``sensor.pv1_powr``). Canonical ids that are not present in
a smaller device (e.g. a battery reading on a ``grid_pv`` device) are simply
ignored, so a single "full" entity preset can drive smaller devices too.
"""

from __future__ import annotations

import importlib.util
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable, Union

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
# Canonical entity ids
#
# Preset devices draw their entity ids from this shared vocabulary so the same
# preset entity set can drive any of them. Custom devices may use their own ids.
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

CANONICAL_ENTITIES: frozenset[str] = frozenset(
    {
        GRID_POWER,
        GRID_PRICE,
        GRID_CO2,
        PV1_POWER,
        PV2_POWER,
        PV3_POWER,
        BAT1_POWER,
        BAT2_POWER,
        BAT3_POWER,
        CONS1_POWER,
    }
)


# ---------------------------------------------------------------------------
# Adapter specs — declarative, decoupled from adapter construction so a preset
# ``DeviceConfig`` can be reused across cases and always yields *fresh* (empty)
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

    def routable_entities(self) -> set[str]:
        """Return every entity id that this device's adapters accept."""
        return set(self.build_engine().entity_mapping)


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
# Preset entity value sets (keyed against the canonical entity ids). Values are
# raw watts already in the engine's sign convention:
#   Grid   : + import  / - export
#   PV/Bat : + produce/discharge / - standby/charge
# Any canonical id absent from the chosen device is ignored, so these presets
# work for the small devices too.
# ---------------------------------------------------------------------------

PRESET_ENTITIES: dict[str, dict[str, float | None]] = {
    # Grid imports, PV-1 producing, PV-3 in standby, Bat-1 discharging.
    "morning": {
        GRID_POWER: 1000.0,
        GRID_PRICE: 0.30,
        PV1_POWER: 2000.0,
        PV2_POWER: 0.0,
        PV3_POWER: -30.0,
        BAT1_POWER: 500.0,
        BAT2_POWER: 0.0,
        BAT3_POWER: 0.0,
        CONS1_POWER: -800.0,
    },
    # Grid exporting, all PV at peak, all batteries charging.
    "midday": {
        GRID_POWER: -3000.0,
        GRID_PRICE: 0.30,
        PV1_POWER: 3000.0,
        PV2_POWER: 2000.0,
        PV3_POWER: 1500.0,
        BAT1_POWER: -800.0,
        BAT2_POWER: -600.0,
        BAT3_POWER: -400.0,
        CONS1_POWER: 0.0,
    },
    # Grid neutral, PV-1 in standby, batteries discharging.
    "evening": {
        GRID_POWER: 0.0,
        GRID_PRICE: 0.30,
        PV1_POWER: -25.0,
        PV2_POWER: 0.0,
        PV3_POWER: 0.0,
        BAT1_POWER: 800.0,
        BAT2_POWER: 600.0,
        BAT3_POWER: 200.0,
        CONS1_POWER: -800.0,
    },
    # Grid imports, all PV in standby, no battery activity.
    "night": {
        GRID_POWER: 700.0,
        GRID_PRICE: 0.25,
        PV1_POWER: -20.0,
        PV2_POWER: -10.0,
        PV3_POWER: 0.0,
        BAT1_POWER: 0.0,
        BAT2_POWER: 0.0,
        BAT3_POWER: 0.0,
        CONS1_POWER: -300.0,
    },
    # Everything reads zero — a degenerate all-idle state.
    "all_zero": {
        GRID_POWER: 0.0,
        GRID_PRICE: 0.30,
        PV1_POWER: 0.0,
        PV2_POWER: 0.0,
        PV3_POWER: 0.0,
        BAT1_POWER: 0.0,
        BAT2_POWER: 0.0,
        BAT3_POWER: 0.0,
        CONS1_POWER: 0.0,
    },
}


# ---------------------------------------------------------------------------
# Expected-value matching helpers
# ---------------------------------------------------------------------------


class Subset:
    """Marker: match only the listed dict keys, ignoring any extra keys.

    Use via :func:`subset`. Handy for per-adapter ``{uid: value}`` properties
    when a case only cares about one adapter's value.
    """

    __slots__ = ("expected",)

    def __init__(self, expected: Mapping[str, Any]) -> None:
        self.expected = expected


def subset(expected: Mapping[str, Any]) -> Subset:
    """Wrap a mapping so only its keys are checked (extra actual keys allowed)."""
    return Subset(expected)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _compare(actual: Any, expected: Any, rel: float, abs_: float, path: str, out: list[str]) -> None:
    """Append a human-readable message to ``out`` for every mismatch found."""
    # Partial-dict marker.
    if isinstance(expected, Subset):
        if not isinstance(actual, Mapping):
            out.append(f"{path}: expected a mapping (subset match), got {actual!r}")
            return
        for key, exp_val in expected.expected.items():
            if key not in actual:
                out.append(f"{path}[{key!r}]: missing (present keys: {sorted(actual)})")
                continue
            _compare(actual[key], exp_val, rel, abs_, f"{path}[{key!r}]", out)
        return

    # Predicate callable (a plain function/lambda — not a Mapping/number/None).
    if callable(expected) and not isinstance(expected, (Mapping, Subset)):
        try:
            ok = bool(expected(actual))
        except Exception as exc:  # noqa: BLE001 - surface predicate errors as failures
            out.append(f"{path}: predicate raised {type(exc).__name__}: {exc}")
            return
        if not ok:
            out.append(f"{path}: predicate {getattr(expected, '__name__', expected)!r} "
                       f"rejected {actual!r}")
        return

    # Exact-dict match (same key set, recurse into values).
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            out.append(f"{path}: expected a mapping, got {actual!r}")
            return
        exp_keys, act_keys = set(expected), set(actual)
        if exp_keys != act_keys:
            missing = sorted(exp_keys - act_keys)
            extra = sorted(act_keys - exp_keys)
            detail = []
            if missing:
                detail.append(f"missing {missing}")
            if extra:
                detail.append(f"unexpected {extra}")
            out.append(f"{path}: dict key mismatch ({'; '.join(detail)})")
        for key in exp_keys & act_keys:
            _compare(actual[key], expected[key], rel, abs_, f"{path}[{key!r}]", out)
        return

    # None (a very common "unavailable" expectation).
    if expected is None:
        if actual is not None:
            out.append(f"{path}: expected None, got {actual!r}")
        return

    # Numbers — tolerant comparison.
    if _is_number(expected):
        if not _is_number(actual):
            out.append(f"{path}: expected number {expected!r}, got {actual!r}")
        elif not math.isclose(actual, expected, rel_tol=rel, abs_tol=abs_):
            out.append(f"{path}: expected {expected!r}, got {actual!r}")
        return

    # Fallback — exact equality.
    if actual != expected:
        out.append(f"{path}: expected {expected!r}, got {actual!r}")


# ---------------------------------------------------------------------------
# The case object + runner
# ---------------------------------------------------------------------------

DeviceLike = Union[str, DeviceConfig]
EntitiesLike = Union[str, Mapping[str, Union[float, None]]]


@dataclass(frozen=True)
class EngineCase:
    """One declarative edge case.

    Attributes:
        name: Unique, readable id (used as the pytest parametrize id).
        device: A :data:`PRESET_DEVICES` name or a custom :class:`DeviceConfig`.
        entities: A :data:`PRESET_ENTITIES` name or a raw ``{id: watts}`` map.
        expected: ``{property_name: expected_value}`` — see module docstring.
        entity_overrides: Merged on top of the resolved entities.
        rel / abs: Numeric tolerances for :func:`math.isclose`.
        notes: Free-text, echoed in the failure message.
    """

    name: str
    device: DeviceLike
    entities: EntitiesLike
    expected: Mapping[str, Any]
    entity_overrides: Mapping[str, float | None] = field(default_factory=dict)
    rel: float = 1e-9
    abs: float = 1e-12
    notes: str = ""


def resolve_device(device: DeviceLike) -> DeviceConfig:
    """Resolve a device name or object to a :class:`DeviceConfig`."""
    if isinstance(device, DeviceConfig):
        return device
    try:
        return PRESET_DEVICES[device]
    except KeyError:
        raise KeyError(
            f"Unknown preset device {device!r}. Available: {sorted(PRESET_DEVICES)}"
        ) from None


def resolve_entities(entities: EntitiesLike) -> dict[str, float | None]:
    """Resolve an entity-set name or mapping to a plain ``{id: watts}`` dict."""
    if isinstance(entities, Mapping):
        return dict(entities)
    try:
        return dict(PRESET_ENTITIES[entities])
    except KeyError:
        raise KeyError(
            f"Unknown preset entity set {entities!r}. "
            f"Available: {sorted(PRESET_ENTITIES)}"
        ) from None


def build_engine(case: EngineCase) -> Any:
    """Build the engine for ``case``: register adapters and apply entity values.

    Validates every entity id (raising ``ValueError`` on an unknown one) and
    sets the readings. Canonical ids not present in the chosen device are
    accepted but skipped, so a shared entity preset can drive smaller devices.
    """
    device = resolve_device(case.device)
    values = resolve_entities(case.entities)
    values.update(case.entity_overrides)

    pi = device.build_engine()
    routable = set(pi.entity_mapping)
    valid = routable | CANONICAL_ENTITIES

    unknown = sorted(set(values) - valid)
    if unknown:
        raise ValueError(
            f"[{case.name}] unknown entity id(s) {unknown}. "
            f"Routable for this device: {sorted(routable)}"
        )

    for entity_id, value in values.items():
        if entity_id in routable:
            pi.set_value(entity_id, value)

    return pi


def evaluate_case(case: EngineCase) -> tuple[Any, list[str]]:
    """Return ``(engine, failures)`` for ``case`` without asserting.

    ``failures`` is a list of human-readable mismatch strings (empty on pass).
    Reading a property that raises is reported as a failure rather than
    propagating, so one bad property doesn't hide the others.
    """
    pi = build_engine(case)
    failures: list[str] = []
    for prop, expected in case.expected.items():
        try:
            actual = getattr(pi, prop)
        except AttributeError:
            failures.append(f"{prop}: PowerInsight has no such property")
            continue
        except Exception as exc:  # noqa: BLE001 - a property raising IS a failure
            failures.append(f"{prop}: reading raised {type(exc).__name__}: {exc}")
            continue
        _compare(actual, expected, case.rel, case.abs, prop, failures)
    return pi, failures


def assert_engine_case(case: EngineCase) -> Any:
    """Run ``case`` and assert every expected property matches.

    Returns the built :class:`PowerInsight` so callers can make additional
    ad-hoc assertions beyond the declarative ``expected`` block.
    """
    pi, failures = evaluate_case(case)
    if failures:
        header = f"EngineCase {case.name!r} failed ({len(failures)} mismatch(es))"
        if case.notes:
            header += f"\n  notes: {case.notes}"
        body = "\n".join(f"  - {line}" for line in failures)
        raise AssertionError(f"{header}\n{body}")
    return pi
