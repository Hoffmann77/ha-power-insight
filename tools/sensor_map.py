"""Which Home Assistant sensor reads which engine property: ``sensors.json``.

The docs' flow chart names the sensor behind every value it draws, so a reader
can find the number on their own dashboard. That mapping lives in
``custom_components/power_insight/sensor.py`` — each description's ``value_fn``
reads one engine property — but that module imports Home Assistant, which the
engine tier does not have. So it is read here as *source*, with :mod:`ast`:

- every ``*SensorDescription(...)`` in a ``POWER_INSIGHT_*`` tuple, scoped by the
  tuple it sits in (whole home, home base load, grid, PV, battery, consumer);
- every one built inside ``async_setup_entry`` — the per-source sensors such as
  *Power from {source}* — scoped by the ``for adapter in power_insight.…``
  loop around it.

Names come from ``strings.json``. The result is written next to the case files
by ``tools/snapshot.py`` and checked for staleness by ``test_corpus.py``, so a
sensor added or renamed in the integration reaches the docs in the same commit.
"""

from __future__ import annotations

import ast
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "power_insight"

# Which device a POWER_INSIGHT_* tuple's sensors sit on.
_TUPLE_DEVICE = {
    "POWER_INSIGHT_SENSORS": "combined",
    "POWER_INSIGHT_INTEGRATION_SENSORS": "combined",
    "POWER_INSIGHT_COMBINED_LEDGER_SENSORS": "combined",
    "POWER_INSIGHT_HOME_BASE_LOAD_SENSORS": "home",
    "POWER_INSIGHT_GRID_ADAPTER_SENSORS": "grid",
    "POWER_INSIGHT_GRID_ADAPTER_INTEGRATION_SENSORS": "grid",
    "POWER_INSIGHT_PV_ADAPTER_SENSORS": "pv",
    "POWER_INSIGHT_PV_ADAPTER_INTEGRATION_SENSORS": "pv",
    "POWER_INSIGHT_STORAGE_ADAPTER_SENSORS": "battery",
    "POWER_INSIGHT_STORAGE_ADAPTER_INTEGRATION_SENSORS": "battery",
    "POWER_INSIGHT_CONS_ADAPTER_SENSORS": "consumer",
    "POWER_INSIGHT_CONS_ADAPTER_INTEGRATION_SENSORS": "consumer",
}

# Which device the per-source sensors built in a setup loop sit on.
_LOOP_DEVICE = {
    "pv_system_adapters": "pv",
    "storage_adapters": "battery",
    "consumer_adapters": "consumer",
}

_DESCRIPTIONS = {
    "PowerInsightSensorDescription",
    "PowerInsightIntegrationSensorDescription",
}


def _const(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) else None


def _key(node: ast.AST | None) -> str | None:
    """A description's ``key``, with a per-source f-string as ``…_{source}``."""
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value if isinstance(v, ast.Constant) else "{source}" for v in node.values
        )
    return _const(node)


def _properties(fn: ast.AST | None) -> list[str]:
    """The engine properties a ``value_fn`` lambda reads, in source order."""
    if fn is None:
        return []
    seen: list[str] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "obj"
            and node.attr != "grid_adapter"
            and node.attr not in seen
        ):
            seen.append(node.attr)
    return seen


def _entry(call: ast.Call, device: str, per_source: bool, names: dict) -> dict | None:
    kw = {k.arg: k.value for k in call.keywords}
    translation_key = _const(kw.get("translation_key"))
    if translation_key is None:
        return None
    integration = "integration_value_fn" in kw
    fn = kw.get("integration_value_fn") or kw.get("value_fn")
    props = _properties(fn)
    # `{obj.grid_adapter.uid: obj.combined_grid_import}` re-keys a scalar
    # under the grid's uid: the property itself is not a per-device map.
    wrapped = isinstance(getattr(fn, "body", None), ast.Dict)
    return {
        "device": device,
        "key": _key(kw.get("key")),
        "translation_key": translation_key,
        "name": names.get(translation_key, {}).get("name", translation_key),
        "property": props[0] if props else None,
        # How the property's value is indexed for this sensor: by the sensor's
        # own device, by (device, source), or not at all.
        "index": (
            "device_source" if per_source
            else None if device in ("combined", "home") or wrapped
            else "device"
        ),
        # A `Total …` sensor accumulates the rate over time: a single snapshot
        # cannot show it.
        "accumulates": integration,
    }


def build() -> dict:
    tree = ast.parse((COMPONENT / "sensor.py").read_text())
    names = json.loads((COMPONENT / "strings.json").read_text())["entity"]["sensor"]
    sensors: list[dict] = []

    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in _TUPLE_DEVICE
            and isinstance(node.value, ast.Tuple)
        ):
            device = _TUPLE_DEVICE[node.targets[0].id]
            for call in node.value.elts:
                if isinstance(call, ast.Call):
                    entry = _entry(call, device, False, names)
                    if entry:
                        sensors.append(entry)

    setup = next(
        n for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_setup_entry"
    )
    for loop in ast.walk(setup):
        if not (
            isinstance(loop, ast.For)
            and isinstance(loop.iter, ast.Attribute)
            and loop.iter.attr in _LOOP_DEVICE
        ):
            continue
        device = _LOOP_DEVICE[loop.iter.attr]
        for call in ast.walk(loop):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id in _DESCRIPTIONS
            ):
                entry = _entry(call, device, True, names)
                if entry:
                    sensors.append(entry)

    return {
        "note": (
            "Generated by tools/snapshot.py from custom_components/power_insight/"
            "sensor.py and strings.json. Do not edit."
        ),
        "sensors": sensors,
    }
