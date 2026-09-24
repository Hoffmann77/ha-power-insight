"""Laws: how every property must respond when a home is changed in a known way.

An identity (``test_identities.py``) says what one property equals. A law says
how *all* of them move together under a transformation whose effect is known
without computing anything — scale every reading, rename every device, add a
device that does nothing — and checks that across every catalogued property
at once, in a couple of hundred random homes. No expected value is written
down anywhere; each home is its own reference.

The catalog's ``unit`` field is what makes that possible: it says how a
property must react. Watts and euros per hour scale with power; shares, ratios
and per-kWh prices do not. Money scales with price; watts, shares and ratios do
not.

Laws catch what identities cannot: a result that depends on something it
should not (a device's name, the order adapters were registered in, whether
an installation is metered as one PV system or two), a lost unit conversion that happens to
cancel in a formula, and whether unavailability propagates the way the model
promises.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import pytest

from tests.engine.automatic.random_homes import Home, random_homes
from tests.engine.home import Adapter, matches, show

CATALOG = json.loads(
    (Path(__file__).parents[3] / "docs" / "spec" / "properties.json").read_text()
)["properties"]
PROPERTIES = list(CATALOG)

ABS_TOL = 1e-9

#: How each unit responds to scaling every power, and to scaling every price.
POWER_SCALED = {"W", "EUR/h"}
PRICE_SCALED = {"EUR/h", "EUR/kWh"}

HOMES = random_homes()


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def results(home: Home) -> dict[str, Any]:
    """Every catalogued property of one home."""
    engine = home.engine()
    return {name: getattr(engine, name) for name in PROPERTIES}


def scale(value: Any, k: float) -> Any:
    """``value`` with every number in it multiplied by ``k``."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {key: scale(v, k) for key, v in value.items()}
    return value * k


def rekey(value: Any, names: dict[str, str]) -> Any:
    """``value`` with every map key renamed through ``names``, at every level."""
    if isinstance(value, dict):
        return {names.get(key, key): rekey(v, names) for key, v in value.items()}
    return value


def check(law: str, homes: list[Home], compare: Callable[[Home], list[str]]) -> None:
    """Run ``compare`` over ``homes`` and fail with the first few breaches."""
    failures = []
    for home in homes:
        for problem in compare(home):
            failures.append(f"{problem}\n      in {home.describe()}")
    if failures:
        shown = "\n  - ".join(failures[:4])
        pytest.fail(
            f"{law}\n{len(failures)} breach(es) across {len(homes)} homes:\n  - {shown}",
            pytrace=False,
        )


def differences(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    return [
        f"{name}: expected {show(expected[name])}, got {show(actual[name])}"
        for name in expected
        if not matches(expected[name], actual[name], abs_tol=ABS_TOL)
    ]


def with_config(adapter: Adapter, **changes: Any) -> Adapter:
    return replace(adapter, config={**adapter.config, **changes})


# ---------------------------------------------------------------------------
# The laws.
# ---------------------------------------------------------------------------


def test_scaling_every_power_scales_watts_and_money_only() -> None:
    """Three times the power: three times the watts and euros per hour, and not
    one share, ratio or per-kWh price changes."""
    k = 3

    def compare(home: Home) -> list[str]:
        before = results(home)
        after = results(
            replace(home, readings={u: w * k for u, w in home.readings.items()})
        )
        expected = {
            name: scale(value, k) if CATALOG[name]["unit"] in POWER_SCALED else value
            for name, value in before.items()
        }
        return differences(expected, after)

    check("Scaling every reading must scale only W and EUR/h.", HOMES, compare)


def test_scaling_every_price_scales_money_only() -> None:
    """Every tariff, LCOE, LCOS and feed-in rate doubled: every monetary result
    doubles, and no watt, share or ratio moves — prices never steer routing."""
    k = 2

    def compare(home: Home) -> list[str]:
        adapters = []
        for a in home.adapters:
            if a.kind == "pv":
                a = with_config(
                    a,
                    lcoe=a.config["lcoe"] * k,
                    export_compensation=a.config["export_compensation"] * k,
                )
            elif a.kind == "battery":
                a = with_config(
                    a,
                    lcos=a.config["lcos"] * k,
                    export_compensation=a.config["export_compensation"] * k,
                )
            adapters.append(a)
        before = results(home)
        after = results(replace(home, adapters=tuple(adapters), price=home.price * k))
        expected = {
            name: scale(value, k) if CATALOG[name]["unit"] in PRICE_SCALED else value
            for name, value in before.items()
        }
        return differences(expected, after)

    check("Scaling every price must scale only EUR/h and EUR/kWh.", HOMES, compare)


def test_names_and_registration_order_do_not_matter() -> None:
    """Rename every device and register them in reverse: the same results under
    the new names. No tie may be broken by a name or by who came first."""

    def compare(home: Home) -> list[str]:
        names = {a.uid: f"z_{a.uid}" for a in home.adapters if a.kind != "grid"}
        adapters = []
        for a in reversed(home.adapters):
            if a.kind == "grid":
                adapters.append(a)
                continue
            renamed = replace(a, uid=names[a.uid])
            restriction = tuple(names.get(u, u) for u in a.power_source_uids)
            if a.kind == "battery":
                renamed = with_config(renamed, charge_from_adapters=restriction)
            elif a.kind == "consumer":
                renamed = with_config(renamed, power_from_adapters=restriction)
            adapters.append(renamed)
        before = results(home)
        after = results(
            Home(
                tuple(adapters),
                {names.get(u, u): w for u, w in home.readings.items()},
                home.price,
            )
        )
        return differences(rekey(before, names), after)

    check("Renaming and reordering devices must change nothing.", HOMES, compare)


def test_an_idle_device_changes_nothing() -> None:
    """A PV system, a battery and a plug all reading 0 W join the home. Every
    result is as before; the only new entries are theirs, and read 0."""
    idle = {"idle_pv": Adapter.pv("idle_pv"), "idle_bat": Adapter.battery("idle_bat"),
            "idle_plug": Adapter.consumer("idle_plug")}

    def strip(value: Any, found: list[Any]) -> Any:
        if isinstance(value, dict):
            kept = {}
            for key, v in value.items():
                if key in idle:
                    found.append(v)
                else:
                    kept[key] = strip(v, found)
            return kept
        return value

    def compare(home: Home) -> list[str]:
        before = results(home)
        after = results(
            Home(
                (*home.adapters, *idle.values()),
                {**home.readings, **dict.fromkeys(idle, 0)},
                home.price,
            )
        )
        found: list[Any] = []
        stripped = {name: strip(value, found) for name, value in after.items()}
        problems = differences(before, stripped)
        if any(v != 0 for v in found):
            problems.append(f"an idle device read non-zero: {found}")
        return problems

    check("Adding idle devices must change nothing.", HOMES, compare)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Open: the allocation is not split-invariant. With a sink restricted "
        "to *several* sources and an unmetered base load in the house, the "
        "export no longer splits in proportion to what each source has left "
        "once one source becomes two. Repro: grid=-1300, east=west=1000, "
        "carport=200, plug=-400[east, west] gives the export 0.886 from east "
        "and west together, where one 2000 W system gets 1600/1800. (The "
        "spurious deficit this law also found is fixed and "
        "pinned by the two-pv-systems reference case.)"
    ),
)
def test_splitting_a_pv_system_in_two_changes_nothing_in_total() -> None:
    """One producing PV system replaced by two identical half-size ones.

    Whole-home results must not move, and for every result keyed by source the
    two halves must add back up to what the single array had. A user should not
    get different numbers for metering one installation as one PV system or as
    two (an inverter reporting each MPP tracker, say).
    """
    # Results read *down* a source (its own ratios, its price) are the same for
    # each half rather than adding up.
    per_source = {
        "source_adapters_consumption_ratios", "source_adapters_export_ratios",
        "source_adapters_charging_ratios", "source_adapters_standby_ratios",
        "source_adapters_dynamic_coe", "source_adapters_dynamic_lcoe",
    }

    def merge(value: Any, a: str, b: str, into: str, *, add: bool) -> Any:
        if not isinstance(value, dict):
            return value
        out = {k: merge(v, a, b, into, add=add) for k, v in value.items()
               if k not in (a, b)}
        if a in value:
            if add:
                out[into] = value[a] + value[b]
            else:
                if not matches(value[a], value[b], abs_tol=ABS_TOL):
                    return {"halves disagree": (value[a], value[b])}
                out[into] = value[a]
        return out

    candidates = [
        h for h in HOMES
        if any(a.kind == "pv" and h.readings[a.uid] > 0 for a in h.adapters)
    ]

    def compare(home: Home) -> list[str]:
        pv = next(a for a in home.adapters if a.kind == "pv" and home.readings[a.uid] > 0)
        a_uid, b_uid = f"{pv.uid}a", f"{pv.uid}b"
        adapters = []
        for a in home.adapters:
            if a is pv:
                adapters += [replace(pv, uid=a_uid), replace(pv, uid=b_uid)]
                continue
            if pv.uid in a.power_source_uids:
                restriction = tuple(
                    s for u in a.power_source_uids
                    for s in ((a_uid, b_uid) if u == pv.uid else (u,))
                )
                key = "charge_from_adapters" if a.kind == "battery" else "power_from_adapters"
                a = with_config(a, **{key: restriction})
            adapters.append(a)
        readings = {u: w for u, w in home.readings.items() if u != pv.uid}
        readings[a_uid] = readings[b_uid] = home.readings[pv.uid] / 2
        before = results(home)
        after = results(Home(tuple(adapters), readings, home.price))
        merged = {
            name: merge(value, a_uid, b_uid, pv.uid, add=name not in per_source)
            for name, value in after.items()
        }
        return differences(before, merged)

    check("Splitting a PV system in two must not change any total.",
          candidates, compare)


def test_an_unavailable_meter_publishes_nothing_downstream() -> None:
    """A grid, PV or battery sensor drops out: gross power is unknowable, so
    every property built on it publishes nothing at all — never a zero, never an
    empty map. The raw totals that do not read the missing sensor are unmoved.

    ``PUBLISH_WHILE_UNAVAILABLE`` lists the properties that do not yet obey.
    They are held to it strictly the other way: once one starts obeying, this
    test fails until it is taken off the list.
    """
    reads = {
        "combined_grid_import": "grid", "combined_grid_export": "grid",
        "combined_production": "pv", "combined_standby_power": "pv",
        "combined_charging_power": "battery", "combined_discharging_power": "battery",
    }

    still_publishing: set[str] = set()

    def compare(home: Home) -> list[str]:
        before = results(home)
        problems = []
        for dropped in [a for a in home.adapters if a.kind != "consumer"]:
            after = results(home.with_readings(**{dropped.uid: None}))
            for name, value in after.items():
                if reads.get(name, dropped.kind) == dropped.kind:
                    if value is None:
                        continue
                    if name in PUBLISH_WHILE_UNAVAILABLE:
                        still_publishing.add(name)
                    else:
                        problems.append(
                            f"{dropped.uid} unavailable, {name} = {show(value)}"
                        )
                elif not matches(before[name], value, abs_tol=ABS_TOL):
                    problems.append(f"{dropped.uid} unavailable moved {name}")
        return problems

    check("An unavailable meter must collapse everything downstream to nothing.",
          HOMES, compare)
    fixed = set(PUBLISH_WHILE_UNAVAILABLE) - still_publishing
    assert not fixed, f"now publish nothing — take them off the list: {sorted(fixed)}"


#: Properties that still publish a value while gross power is unknowable.
#: Five return an empty map, which a sensor reads the same as "no such device";
#: ``source_adapters_coe_rate`` returns a zero for every local source.
PUBLISH_WHILE_UNAVAILABLE = {
    "sink_adapters_consumption_shares",
    "sink_adapters_coo_rates",
    "sink_adapters_lcoo_rates",
    "sink_adapters_avoided_cost_rates",
    "source_adapters_export_compensation_rates",
    "source_adapters_coe_rate",
}


def test_the_books_balance() -> None:
    """The model's conservation laws.

    * Every source's watts land in exactly one of the four channels.
    * Every euro of gross cost lands in exactly one channel's cost bucket, at
      marginal and at levelized prices alike.
    * The avoided cost measured at the sources equals the avoided cost
      measured at the loads, base load included.
    * Self-consumption and the base load are never negative — this one in
      every home, including those whose readings overdraw the sources.

    Open question: when the readings overdraw (the metered sinks draw more
    than the sources provide, as unsynchronised sensors do), the engine
    attributes a source more watts than it read, so the first two do not hold
    there. The engine docs promise source balance "in every snapshot"; either
    that promise or the overdraw handling has to give, so for now the balance
    is only checked where the readings balance.
    """
    channels = ("consumption", "export", "charging", "standby")

    def compare(home: Home) -> list[str]:
        e = home.engine()
        problems = []
        if e.combined_consumption < 0 or e.home_base_load_power < 0:
            problems.append("negative self-consumption or base load")
        if not home.balanced:
            return problems
        for source, reading in home.readings.items():
            if reading is None or reading <= 0 or source.startswith("cons"):
                continue
            routed = sum(
                getattr(e, f"source_adapters_{c}_power")[source] for c in channels
            )
            if not matches(reading, routed, abs_tol=ABS_TOL):
                problems.append(f"{source} read {reading} W but {show(routed)} W was routed")
        for levelized, total in ((False, e.combined_coe_rate), (True, e.combined_lcoe_rate)):
            prefix = "combined_levelized_" if levelized else "combined_"
            buckets = sum(getattr(e, f"{prefix}{c}_cost_rate") for c in channels)
            if not matches(total, buckets, abs_tol=ABS_TOL):
                problems.append(
                    f"{'levelized' if levelized else 'marginal'} channel costs "
                    f"{show(buckets)} ≠ gross cost {show(total)}"
                )
        at_sources = sum(e.source_adapters_avoided_cost_rates.values())
        at_loads = (
            sum(e.sink_adapters_avoided_cost_rates.values())
            + e.home_base_load_avoided_cost_rate
        )
        if not matches(at_sources, at_loads, abs_tol=ABS_TOL):
            problems.append(
                f"avoided cost {show(at_sources)} at the sources ≠ {show(at_loads)} at the loads"
            )
        return problems

    check("The books must balance.", HOMES, compare)
