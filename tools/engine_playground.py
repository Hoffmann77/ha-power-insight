#!/usr/bin/env python3
"""Run the PowerInsight engine with custom input values — a dev playground.

Self-contained: loads the pure-Python engine (``power_insight.py``) directly, so
no Home Assistant install is needed and there is no dependency on the test suite.

Define the device and its entity values in one place — :func:`define_device` —
and get a ready-to-query engine from :func:`get_power_insight`. Three ways to use
it:

1. Interactively — drops you in a REPL with a ``power_insight`` instance ready::

       uv run python -i tools/engine_playground.py
       >>> power_insight.gross_power
       >>> power_insight.combined_saving_rate

2. From your own script / REPL — import and build::

       from tools.engine_playground import get_power_insight
       pi = get_power_insight()
       pi.storage_adapters_dynamic_lcoe

3. As a report — print every engine property for the defined device::

       uv run python tools/engine_playground.py            # print every property
       uv run python tools/engine_playground.py gross      # names matching "gross"
       uv run python tools/engine_playground.py --all      # include helper properties

The ``Playground`` builder chains one call per adapter, each carrying its entity
value (``power``, grid ``price``) and config.

Sign convention (watts):
    grid      +import    / -export
    pv        +produce   / -standby
    battery   +discharge / -charge
    consumer  -load
``power=None`` models an unavailable sensor.
"""

from __future__ import annotations

import importlib.util
import os
import sys

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


class Playground:
    """Fluent builder for a :class:`PowerInsight` engine plus its readings.

    Each ``grid``/``pv``/``battery``/``consumer`` call registers one adapter and
    records its sensor reading; :meth:`build` applies the readings and returns the
    ready-to-query engine. Uids drive the power entity id (``sensor.<uid>_power``);
    the grid uid is always ``"grid"``.
    """

    def __init__(self) -> None:
        self._engine = PowerInsight()
        self._readings: dict[str, float | None] = {}
        self.inputs: list[tuple[str, str, str]] = []  # (uid, kind, summary)

    def _record(self, uid: str, kind: str, power, extras: dict) -> None:
        self._readings[f"sensor.{uid}_power"] = power
        parts = [f"power={power}"]
        parts += [f"{k}={v!r}" for k, v in extras.items()]
        self.inputs.append((uid, kind, "  ".join(parts)))

    def grid(self, *, power, price=None, co2=None, inverted=False, name="Grid"):
        self._engine.register_adapter(
            GridAdapter(
                unique_id="grid",
                verbose_name=name,
                power_entity="sensor.grid_power",
                power_entity_inverted=inverted,
                price_entity="sensor.grid_price" if price is not None else None,
                co2_entity="sensor.grid_co2" if co2 is not None else None,
            )
        )
        if price is not None:
            self._readings["sensor.grid_price"] = price
        if co2 is not None:
            self._readings["sensor.grid_co2"] = co2
        extras = {}
        if price is not None:
            extras["price"] = price
        if co2 is not None:
            extras["co2"] = co2
        if inverted:
            extras["inverted"] = True
        self._record("grid", "grid", power, extras)
        return self

    def pv(
        self,
        uid,
        *,
        power,
        lcoe=0.10,
        lco2_intensity=50.0,
        exports_power=False,
        export_compensation=0.0,
        correction_factor=1.0,
        inverted=False,
        name=None,
    ):
        self._engine.register_adapter(
            PvAdapter(
                unique_id=uid,
                verbose_name=name or uid,
                power_entity=f"sensor.{uid}_power",
                power_entity_inverted=inverted,
                lcoe=lcoe,
                lco2_intensity=lco2_intensity,
                exports_power=exports_power,
                export_compensation=export_compensation,
                correction_factor=correction_factor,
            )
        )
        self._record(
            uid,
            "pv",
            power,
            {
                "lcoe": lcoe,
                "exports_power": exports_power,
                "export_compensation": export_compensation,
            },
        )
        return self

    def battery(
        self,
        uid,
        *,
        power,
        charge_from=(),
        lcos=0.15,
        lco2_intensity=100.0,
        exports_power=False,
        export_compensation=0.0,
        correction_factor=1.0,
        inverted=False,
        name=None,
    ):
        self._engine.register_adapter(
            BatteryAdapter(
                unique_id=uid,
                verbose_name=name or uid,
                power_entity=f"sensor.{uid}_power",
                power_entity_inverted=inverted,
                lcos=lcos,
                lco2_intensity=lco2_intensity,
                exports_power=exports_power,
                export_compensation=export_compensation,
                charge_from_adapters=list(charge_from),
                correction_factor=correction_factor,
            )
        )
        self._record(
            uid,
            "battery",
            power,
            {"lcos": lcos, "charge_from": list(charge_from)},
        )
        return self

    def consumer(self, uid, *, power, inverted=False, name=None):
        self._engine.register_adapter(
            ConsumerAdapter(
                unique_id=uid,
                verbose_name=name or uid,
                power_entity=f"sensor.{uid}_power",
                power_entity_inverted=inverted,
            )
        )
        self._record(uid, "consumer", power, {"inverted": inverted} if inverted else {})
        return self

    def build(self) -> "PowerInsight":
        for entity_id, value in self._readings.items():
            self._engine.set_value(entity_id, value)
        return self._engine


def define_device() -> Playground:
    """EDIT ME — declare the device, its adapters and their entity values.

    This is the single place to change inputs. Returns the populated builder;
    call :func:`get_power_insight` (or ``.build()``) to get the engine.
    """
    return (
        Playground()
        .grid(power=1500, price=0.30)
        .pv("pv1", power=4000, exports_power=True, export_compensation=0.08)
        .battery("bat1", power=-800, charge_from=["grid", "pv1"])
        .consumer("cons1", power=-1200)
    )


def get_power_insight() -> "PowerInsight":
    """Return a ready-to-query :class:`PowerInsight` for the defined device."""
    return define_device().build()


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


def main(argv: list[str]) -> int:
    show_all = "--all" in argv
    filters = [a.lower() for a in argv if not a.startswith("-")]

    device = define_device()
    engine = device.build()

    print("=" * 72)
    print("INPUTS")
    print("=" * 72)
    for uid, kind, summary in device.inputs:
        print(f"  {uid:<8} {kind:<10} {summary}")
    print()

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


# A ready-to-query engine, importable and available in `python -i` sessions.
power_insight = get_power_insight()


if __name__ == "__main__":
    if sys.flags.interactive:
        # `python -i tools/engine_playground.py` — leave `power_insight` in scope
        # instead of printing the full report and exiting.
        print("power_insight ready — e.g. power_insight.gross_power")
    else:
        raise SystemExit(main(sys.argv[1:]))
