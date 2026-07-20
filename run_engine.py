#!/usr/bin/env python3
"""Run the PowerInsight engine with custom input values — a dev scratchpad.

Edit the ``DEVICES`` list below to model a device and its live sensor readings,
then run::

    uv run python run_engine.py            # print every engine property
    uv run python run_engine.py gross      # only properties matching "gross"
    uv run python run_engine.py --all      # include structural/helper properties

Each ``Device(...)`` line declares one adapter and its current reading, using the
same declarative presets as the engine scenario tests
(``tests/engine/engine_property_framework.py`` — see its docstring for the full
``Device()`` reference: presets, overrides, sign convention). ``build_engine()``
assembles a ready-to-query ``PowerInsight``; this script then evaluates every
public engine property and prints the results, grouped into scalars and
per-adapter maps.

No Home Assistant install is needed — the engine (``power_insight.py``) is pure
Python and is loaded directly, exactly like the engine-tier tests.
"""

from __future__ import annotations

import os
import sys

# Make the engine scenario framework importable regardless of the working dir.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tests", "engine"))

from engine_property_framework import (  # noqa: E402
    Device,
    PowerInsight,
    build_engine,
)

# ---------------------------------------------------------------------------
# EDIT ME — declare the device and its sensor readings.
#
# Sign convention (watts):
#   grid      +import  / -export
#   pv        +produce / -standby
#   battery   +discharge / -charge
#   consumer  -load
#
# ``power=None`` models an unavailable sensor. ``price`` is grid-only.
# ``charge_from`` is battery-only. Pass config overrides as keywords, e.g.
# ``Device("pv_with_export", 1, power=4000, lcoe=0.12, export_compensation=0.09)``.
# ---------------------------------------------------------------------------
DEVICES = [
    Device("grid", power=1500, price=0.30),
    Device("pv_with_export", 1, power=4000),
    Device("battery", 1, power=-800, charge_from=["grid", "pv1"]),
    Device("consumer", 1, power=-1200),
]

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


def _print_inputs(devices: list) -> None:
    print("=" * 72)
    print("INPUTS")
    print("=" * 72)
    for dev in devices:
        parts = [f"power={dev.power}"]
        if dev.price is not None:
            parts.append(f"price={dev.price}")
        if dev.charge_from:
            parts.append(f"charge_from={list(dev.charge_from)}")
        if dev.inverted:
            parts.append("inverted=True")
        print(f"  {dev.uid:<8} {dev.preset:<20} " + "  ".join(parts))
    print()


def main(argv: list[str]) -> int:
    show_all = "--all" in argv
    filters = [a.lower() for a in argv if not a.startswith("-")]

    engine = build_engine(DEVICES)

    _print_inputs(DEVICES)

    scalars: list[tuple[str, object]] = []
    maps: list[tuple[str, dict]] = []

    for name in _engine_properties():
        if name in _HELPER_PROPS and not show_all:
            continue
        if filters and not any(f in name.lower() for f in filters):
            continue
        try:
            value = getattr(engine, name)
        except Exception as exc:  # noqa: BLE001 — a raising property is a result too
            value = f"<raised {type(exc).__name__}: {exc}>"
        if isinstance(value, dict):
            maps.append((name, value))
        else:
            scalars.append((name, value))

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
        print("No properties matched the given filter(s).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
