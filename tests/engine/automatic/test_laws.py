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
    result is as before; the only new entries are theirs, and read their idle
    value — 0 for an amount, share or ratio, nothing at all for a price."""
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

    def is_idle(name: str, value: Any) -> bool:
        if isinstance(value, dict):
            return all(is_idle(name, v) for v in value.values())
        if CATALOG[name]["unit"] == "EUR/kWh":
            return value is None
        return value == 0

    def compare(home: Home) -> list[str]:
        before = results(home)
        after = results(
            Home(
                (*home.adapters, *idle.values()),
                {**home.readings, **dict.fromkeys(idle, 0)},
                home.price,
            )
        )
        problems = []
        for name, value in after.items():
            found: list[Any] = []
            stripped = strip(value, found)
            problems += differences({name: before[name]}, {name: stripped})
            if not all(is_idle(name, v) for v in found):
                problems.append(f"an idle device read non-idle in {name}: {found}")
        return problems

    check("Adding idle devices must change nothing.", HOMES, compare)


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

    def combine(x: Any, y: Any) -> Any:
        """The two halves' values added up, map by map."""
        if isinstance(x, dict) and isinstance(y, dict) and x.keys() == y.keys():
            return {k: combine(x[k], y[k]) for k in x}
        if x is None or y is None or isinstance(x, dict) or isinstance(y, dict):
            return {"halves do not add": (x, y)}
        return x + y

    def merge(value: Any, a: str, b: str, into: str, *, add: bool) -> Any:
        if not isinstance(value, dict):
            return value
        out = {k: merge(v, a, b, into, add=add) for k, v in value.items()
               if k not in (a, b)}
        if a in value:
            if add:
                out[into] = merge(combine(value[a], value[b]), a, b, into, add=add)
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
    empty map. The raw totals that do not read the missing sensor are unmoved,
    and a channel total over devices the house does not have stays a confident
    zero: the missing meter says nothing about a device that is not there.
    """
    reads = {
        "combined_grid_import": "grid", "combined_grid_export": "grid",
        "combined_production": "pv", "combined_discharging_power": "battery",
    }
    # Channel totals are balanced across every meter, so they follow gross
    # power — unless there is nothing to sum at all.
    sums_over = {"combined_charging_power": "battery", "combined_standby_power": "pv"}

    def compare(home: Home) -> list[str]:
        before = results(home)
        problems = []
        for dropped in [a for a in home.adapters if a.kind != "consumer"]:
            after = results(home.with_readings(**{dropped.uid: None}))
            for name, value in after.items():
                if name in sums_over and not home.uids(sums_over[name]):
                    if value != 0:
                        problems.append(f"{name} over no devices = {show(value)}")
                elif reads.get(name, dropped.kind) == dropped.kind:
                    if value is not None:
                        problems.append(
                            f"{dropped.uid} unavailable, {name} = {show(value)}"
                        )
                elif not matches(before[name], value, abs_tol=ABS_TOL):
                    problems.append(f"{dropped.uid} unavailable moved {name}")
        return problems

    check("An unavailable meter must collapse everything downstream to nothing.",
          HOMES, compare)


def test_a_missing_price_moves_no_watt_and_invents_no_number() -> None:
    """The grid tariff drops out. Routing never depends on prices, so no watt,
    share or ratio moves; every monetary value is either exactly what it was
    — it never needed the tariff — or nothing at all, and never a different
    number. What cannot be known without the tariff (the cost of an import)
    is blank."""
    money = {"EUR/h", "EUR/kWh"}

    def leaves(before: Any, after: Any, name: str) -> list[str]:
        if isinstance(before, dict) and isinstance(after, dict):
            if set(before) != set(after):
                return [f"{name} changed its keys"]
            return [p for k in before for p in leaves(before[k], after[k], f"{name}.{k}")]
        if after is None or matches(before, after, abs_tol=ABS_TOL):
            return []
        return [f"{name}: {show(before)} became {show(after)}"]

    def compare(home: Home) -> list[str]:
        before = results(home)
        after = results(replace(home, price=None))
        problems = []
        for name in PROPERTIES:
            if CATALOG[name]["unit"] in money:
                problems += leaves(before[name], after[name], name)
            else:
                problems += differences({name: before[name]}, {name: after[name]})
        if home.readings["grid"] > 0 and after["combined_coe_rate"] is not None:
            problems.append("an import was costed without a tariff")
        return problems

    check("A missing price must blank only what needs it.",
          [h for h in HOMES if h.price is not None], compare)


def test_every_map_is_keyed_by_its_whole_family() -> None:
    """Every per-device map carries a key for every device of its family —
    idle, drawing or supplying — at every level, so a device never drops out
    of a map because it went quiet. The catalog's ``keys`` names the family."""
    kinds = {
        "sources": {"grid", "pv", "battery"},
        "sinks": {"grid", "pv", "battery", "consumer"},
        "consumers": {"consumer"},
        "devices": {"pv", "battery"},
    }
    maps = {name: doc["keys"] for name, doc in CATALOG.items() if "keys" in doc}

    def compare(home: Home) -> list[str]:
        engine = home.engine()
        problems = []
        for name, keys in maps.items():
            levels = [keys] if isinstance(keys, str) else list(keys)
            value = getattr(engine, name)
            if value is None:
                continue  # unknowable as a whole: the unavailability law's business
            stack = [(value, levels)]
            while stack:
                mapping, (level, *rest) = stack.pop()
                want = {a.uid for a in home.adapters if a.kind in kinds[level]}
                if set(mapping) != want:
                    problems.append(
                        f"{name} keyed by {sorted(mapping)}, not the {level} {sorted(want)}"
                    )
                    break
                stack += [(v, rest) for v in mapping.values() if rest and v is not None]
        return problems

    check("Every map must be keyed by its whole family.", HOMES, compare)


def test_the_books_balance() -> None:
    """The model's conservation laws.

    * Every source's watts land in exactly one of the four channels, and each
      channel carries exactly what its meters say: the export channel the grid
      export, the charging channel what the batteries drew, the standby channel
      what the PV systems drew.
    * All of that in every home, those whose readings overdraw the sources
      included — once the readings are balanced by meeting in the middle:
      sources up by ``1 + λ``, sinks down by ``1 − λ``, with
      ``λ = (drawn − supplied) / (drawn + supplied)`` when the sinks read more,
      and 0 otherwise. The gap is published as ``metering_imbalance``.
    * Every euro of gross cost lands in exactly one channel's cost bucket, at
      marginal and at levelized prices alike.
    * The avoided cost measured at the sources equals the avoided cost
      measured at the loads, base load included.
    * Self-consumption and the base load are never negative.
    """
    channels = ("consumption", "export", "charging", "standby")

    def compare(home: Home) -> list[str]:
        e = home.engine()
        problems = []
        if e.combined_consumption < 0 or e.home_base_load_power < 0:
            problems.append("negative self-consumption or base load")
        kind = {a.uid: a.kind for a in home.adapters}
        supplied = sum(
            w for u, w in home.readings.items() if w and w > 0 and kind[u] != "consumer"
        )
        drawn = sum(-w for w in home.readings.values() if w and w < 0)
        shift = (drawn - supplied) / (drawn + supplied) if drawn > supplied else 0.0
        if not matches(max(0.0, drawn - supplied), e.metering_imbalance, abs_tol=ABS_TOL):
            problems.append(f"imbalance {show(e.metering_imbalance)} W, readings say "
                            f"{show(drawn - supplied)} W")
        for source, reading in home.readings.items():
            if reading is None or reading <= 0 or kind[source] == "consumer":
                continue
            routed = sum(
                getattr(e, f"source_adapters_{c}_power")[source] for c in channels
            )
            if not matches(reading * (1 + shift), routed, abs_tol=ABS_TOL):
                problems.append(f"{source} read {reading} W but {show(routed)} W was routed")

        def metered(kinds: set[str]) -> float:
            return sum(-w for u, w in home.readings.items() if w < 0 and kind[u] in kinds)

        for channel, meters, total in (
            ("export", {"grid"}, None),
            ("charging", {"battery"}, e.combined_charging_power),
            ("standby", {"pv"}, e.combined_standby_power),
        ):
            expected = metered(meters) * (1 - shift)
            carried = sum(getattr(e, f"source_adapters_{channel}_power").values())
            for value in (carried, total):
                if value is not None and not matches(expected, value, abs_tol=ABS_TOL):
                    problems.append(
                        f"the {channel} channel carried {show(value)} W, "
                        f"its meters read {show(expected)} W once balanced"
                    )
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


# ---------------------------------------------------------------------------
# Corrections: a factor is a restated lifetime cost.
# ---------------------------------------------------------------------------

#: Every corrected property, and the property it restates. The combined
#: twins are not catalogued themselves — no sensor shows them uncorrected.
CORRECTED = {
    name: name.removesuffix("_corrected")
    for name in PROPERTIES
    if name.endswith("_corrected")
}

#: Each ``*_components`` family, and the uncorrected property it splits.
COMPONENTS = {
    "source_adapters_lcoo_rate_components": "source_adapters_lcoo_rates",
    "sink_adapters_lcoo_rate_components": "sink_adapters_lcoo_rates",
    "adapters_levelized_saving_rate_components": "adapters_levelized_saving_rates",
    "adapters_levelized_financial_return_rate_components":
        "adapters_levelized_financial_return_rates",
}


def factors(home: Home) -> dict[str, float]:
    """Each PV system's and battery's correction factor; the grid's is 1."""
    return {
        a.uid: a.config["correction_factor"]
        for a in home.adapters
        if a.kind in ("pv", "battery")
    }


def restated(home: Home) -> Home:
    """``home`` with every factor folded into the lifetime cost it corrects."""
    adapters = []
    for a in home.adapters:
        if a.kind in ("pv", "battery"):
            price = "lcoe" if a.kind == "pv" else "lcos"
            a = with_config(
                a,
                **{price: a.config[price] * a.config["correction_factor"]},
                correction_factor=1.0,
            )
        adapters.append(a)
    return replace(home, adapters=tuple(adapters))


def uncorrected(home: Home) -> Home:
    """``home`` with every lifetime cost as it was entered."""
    return replace(home, adapters=tuple(
        with_config(a, correction_factor=1.0) if a.kind in ("pv", "battery") else a
        for a in home.adapters
    ))


def test_a_correction_is_a_restated_lifetime_cost() -> None:
    """A device corrected by ``k`` is the same device with its LCOE / LCOS
    times ``k``: every corrected result equals the uncorrected one of that
    restated home. And the factor reaches nothing else — every other result is
    what the home reads with no corrections at all."""
    assert any(any(k != 1.0 for k in factors(h).values()) for h in HOMES), (
        "no random home has a correction factor to check"
    )

    def compare(home: Home) -> list[str]:
        engine, restated_engine = home.engine(), restated(home).engine()
        expected = {
            name: getattr(restated_engine, twin) for name, twin in CORRECTED.items()
        }
        actual = {name: getattr(engine, name) for name in CORRECTED}
        plain = {name: v for name, v in results(uncorrected(home)).items()
                 if name not in CORRECTED}
        return differences(expected, actual) + differences(
            plain, {name: getattr(engine, name) for name in plain}
        )

    check("A correction must restate the lifetime cost, and nothing else.",
          HOMES, compare)


def test_the_components_add_up_to_the_total_before_and_after_correction() -> None:
    """Every ``*_components`` row splits a device's rate by whose factor scales
    each part: the parts add up to the uncorrected rate, and each part times
    its own device's factor (the grid's is 1) adds up to the rate the restated
    home reads. That is what lets an accumulated total be corrected long after
    the fact."""

    def compare(home: Home) -> list[str]:
        engine, restated_engine = home.engine(), restated(home).engine()
        k = factors(home)
        problems = []
        for family, base in COMPONENTS.items():
            rows = getattr(engine, family)
            plain, corrected = getattr(engine, base), getattr(restated_engine, base)
            if rows is None:
                if plain is not None:
                    problems.append(f"{family} is None but {base} is {show(plain)}")
                continue
            for uid, parts in rows.items():
                if parts is None:
                    if plain.get(uid) is not None:
                        problems.append(f"{family}[{uid}] is None, {base} is not")
                    continue
                unknown = set(parts) - {"grid", *k}
                if unknown:
                    problems.append(f"{family}[{uid}] names no device: {sorted(unknown)}")
                    continue
                summed = sum(parts.values())
                weighted = sum(v * k.get(key, 1.0) for key, v in parts.items())
                if not matches(plain.get(uid, 0.0), summed, abs_tol=ABS_TOL):
                    problems.append(
                        f"{family}[{uid}] sums to {show(summed)}, "
                        f"{base} is {show(plain.get(uid))}"
                    )
                if not matches(corrected.get(uid, 0.0), weighted, abs_tol=ABS_TOL):
                    problems.append(
                        f"{family}[{uid}] × factors is {show(weighted)}, "
                        f"corrected {base} is {show(corrected.get(uid))}"
                    )
        return problems

    check("The components must add up, before and after correction.", HOMES, compare)
