"""Every catalogued property, as an executable formula over its inputs.

Each property in ``docs/spec/properties.json`` gets exactly one *identity*
here: a short function that says what the property equals, in terms of the raw
readings, the adapters' configuration and the published properties it depends
on. The test builds a couple of hundred random homes (``random_homes.py``) and
checks every identity against the engine in each of them.

What this buys: a property is checked once, as a formula, rather than once per
reference snapshot as a number. Because every identity is stated in terms of
its *published* dependencies, the checks chain — if the inputs to a property
are right, the property is right — so the only values left needing a human are
the roots, where no formula exists:

* ``sink_adapters_source_shares`` — the provenance allocation. Its shape and
  guarantees are pinned over random wirings by
  ``test_source_shares_invariants.py``; which of the valid allocations it
  picks is a decision, and each decision is pinned by a hand-derived class in
  ``tests/engine/manual/``.

Everything else is a consequence of provenance plus the model's documented
conventions (``docs/dev/engine-calculations.md``), and each identity's
docstring says which convention it encodes. Write an identity from the model,
never from the engine's code: one read off the implementation only proves the
code equals itself.

Identities cover *available* snapshots — those whose readings overdraw the
sources included, stated over the balanced readings (``Snap``). What happens
when a sensor drops out is a law (``test_laws.py``), not a formula.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from tests.engine.automatic.random_homes import Home, random_homes
from tests.engine.home import matches, show

CATALOG = json.loads(
    (Path(__file__).parents[3] / "docs" / "spec" / "properties.json").read_text()
)["properties"]

#: Tolerance for every comparison. Random homes use whole watts and cent
#: prices, so a real disagreement is many orders of magnitude above this.
ABS_TOL = 1e-9

#: Properties with no formula, and where their correctness is argued instead.
ROOTS = {
    "sink_adapters_source_shares": "test_source_shares_invariants.py",
}

CON, EXP, CHG, STB = "consumption", "export", "charging", "standby"


# ---------------------------------------------------------------------------
# One snapshot: the readings and configuration, plus the engine to ask.
# ---------------------------------------------------------------------------


class Snap:
    """The facts an identity may use, named the way the model names them."""

    def __init__(self, home: Home) -> None:
        self.home = home
        self.e = home.engine()
        self.price = home.price
        self.reading = home.readings
        self.kind = {a.uid: a.kind for a in home.adapters}
        # A consumer can only draw: a positive consumer reading is idle.
        self.raw_sources = {
            uid: w
            for uid, w in self.reading.items()
            if w > 0 and self.kind[uid] != "consumer"
        }
        self.raw_sinks = {uid: -w for uid, w in self.reading.items() if w < 0}
        # Meet in the middle: when the sinks read more than the sources, every
        # reading moves in proportion to its size by the least that balances.
        supplied, drawn = sum(self.raw_sources.values()), sum(self.raw_sinks.values())
        self.shift = (drawn - supplied) / (drawn + supplied) if drawn > supplied else 0.0
        self.imbalance = max(0.0, drawn - supplied)
        #: The balanced readings every derived result is built on.
        self.sources = {u: w * (1 + self.shift) for u, w in self.raw_sources.items()}
        self.sinks = {u: w * (1 - self.shift) for u, w in self.raw_sinks.items()}

    def of(self, kind: str) -> list[str]:
        return self.home.uids(kind)

    @property
    def devices(self) -> list[str]:
        """Every PV system and battery — the devices with a P&L."""
        return self.of("pv") + self.of("battery")

    @property
    def source_family(self) -> list[str]:
        """Every adapter that can supply power — the keys of a per-source map."""
        return ["grid", *self.devices]

    @property
    def sink_family(self) -> list[str]:
        """Every adapter that can draw power — the keys of a per-sink map."""
        return list(self.kind)

    def channel(self, sink: str) -> str:
        """The channel a drawing adapter's watts land in."""
        return {"grid": EXP, "battery": CHG, "pv": STB}.get(self.kind[sink], CON)

    def marginal(self, source: str) -> float:
        """What a kWh from ``source`` costs at the margin: local fuel is free."""
        return self.price if source == "grid" else 0.0

    def levelized(self, source: str) -> float:
        """As marginal, but a local source carries its own LCOE / LCOS."""
        if source == "grid":
            return self.price
        cfg = self.home.adapter(source).config
        return cfg["lcoe"] if self.kind[source] == "pv" else cfg["lcos"]

    def corrected(self, source: str) -> float:
        """As levelized, with the lifetime cost restated by the device's factor.

        The factor is ``current / default`` lifetime cost, so it multiplies
        the price itself; the grid has no lifetime cost and never scales.
        """
        if source == "grid":
            return self.price
        return self.levelized(source) * self.home.adapter(source).config["correction_factor"]

    def compensation(self, source: str) -> float:
        """Feed-in tariff; a device that may not export earns nothing."""
        if source == "grid":
            return 0.0
        cfg = self.home.adapter(source).config
        return cfg["export_compensation"] if cfg["exports_power"] else 0.0

    def draw_watts(self, sink: str) -> dict[str, float]:
        """``{source: watts}`` a sink drew, from its provenance row."""
        row = self.e.sink_adapters_source_shares.get(sink, {})
        return {src: share * self.sinks[sink] for src, share in row.items()}

    def home_watts(self) -> dict[str, float]:
        """``{source: watts}`` the unmetered base load drew."""
        load = self.e.home_base_load_power
        return {
            src: share * load
            for src, share in self.e.home_base_load_source_shares.items()
        }


def kw(watts: float) -> float:
    return watts / 1000


def ratio(a: float, b: float) -> float:
    """``a / b``, reading zero when there is nothing to divide by."""
    return a / b if b else 0.0


def priced(watts: dict[str, float], price: Callable[[str], float]) -> float:
    """What ``{source: watts}`` costs per hour at each source's price."""
    return sum(kw(w) * price(src) for src, w in watts.items())


def channel_watts(s: Snap, channel: str) -> dict[str, float]:
    """``{source: watts}`` routed into ``channel`` by the provenance rows."""
    out = dict.fromkeys(s.source_family, 0.0)
    rows = [s.draw_watts(k) for k in s.sinks if s.channel(k) == channel]
    if channel == CON:
        rows.append(s.home_watts())
    for row in rows:
        for src, w in row.items():
            out[src] += w
    return out


def published_channel(s: Snap, channel: str) -> dict[str, float]:
    return getattr(s.e, f"source_adapters_{channel}_power")


# ---------------------------------------------------------------------------
# The identities, in catalog order.
# ---------------------------------------------------------------------------

IDENTITIES: dict[str, Callable[[Snap], Any]] = {}


def identity(name: str) -> Callable:
    def register(fn: Callable[[Snap], Any]) -> Callable[[Snap], Any]:
        if name not in CATALOG:
            raise KeyError(f"{name!r} is not a catalogued property")
        if name in IDENTITIES:
            raise KeyError(f"{name!r} already has an identity")
        IDENTITIES[name] = fn
        return fn

    return register


# Layer 1 — readings and totals.


@identity("gross_power")
def _(s):
    """Σ reading over every adapter currently providing."""
    return sum(s.sources.values())


@identity("combined_grid_import")
def _(s):
    return max(s.reading["grid"], 0)


@identity("combined_grid_export")
def _(s):
    return max(-s.reading["grid"], 0)


@identity("combined_production")
def _(s):
    return sum(max(s.reading[u], 0) for u in s.of("pv"))


@identity("combined_charging_power")
def _(s):
    """The CHG channel: what the batteries drew, balanced."""
    return sum(s.sinks.get(u, 0.0) for u in s.of("battery"))


@identity("combined_discharging_power")
def _(s):
    return sum(max(s.reading[u], 0) for u in s.of("battery"))


@identity("combined_standby_power")
def _(s):
    """The STB channel: what the PV systems drew, balanced."""
    return sum(s.sinks.get(u, 0.0) for u in s.of("pv"))


@identity("metering_imbalance")
def _(s):
    """What the metered sinks read beyond the sources, from the raw readings."""
    return s.imbalance


@identity("combined_consumption")
def _(s):
    """CON is the residual: gross − export − charging − standby, floored at 0.

    The export is the balanced one, like every channel.
    """
    e = s.e
    rest = (
        e.gross_power
        - s.sinks.get("grid", 0.0)
        - e.combined_charging_power
        - e.combined_standby_power
    )
    return rest if rest > 1e-9 * max(1.0, e.gross_power) else 0.0


@identity("home_base_load_power")
def _(s):
    """Gross minus every metered draw, floored at 0.

    Every metered draw is attributed somewhere — a sink whose allowed sources
    are all idle is relaxed onto what did supply — so none of it is base load.
    """
    rest = s.e.gross_power - sum(s.sinks.values())
    return rest if rest > 1e-9 * max(1.0, s.e.gross_power) else 0.0


# Layer 2 — provenance. The metered rows are the root; the base load's row is
# whatever each source has left once the metered sinks are served.


@identity("sink_adapters_source_power")
def _(s):
    """Each share of a sink's row times its balanced draw; zeros when idle."""
    return {
        k: {src: s.draw_watts(k).get(src, 0.0) for src in s.source_family}
        if k in s.sinks else {src: 0.0 for src in s.source_family}
        for k in s.sink_family
    }


@identity("home_base_load_source_shares")
def _(s):
    """Each source's reading, less what the metered rows took, over the base load."""
    load = s.e.home_base_load_power
    left = {src: s.sources.get(src, 0.0) for src in s.source_family}
    for k in s.sinks:
        for src, w in s.draw_watts(k).items():
            left[src] -= w
    return {src: ratio(w, load) for src, w in left.items()}


# Layer 3a — the channel split of gross power.


@identity("gross_power_export_ratio")
def _(s):
    return ratio(s.sinks.get("grid", 0.0), s.e.gross_power)


@identity("gross_power_consumption_ratio")
def _(s):
    return ratio(s.e.combined_consumption, s.e.gross_power)


@identity("gross_power_charging_ratio")
def _(s):
    return ratio(s.e.combined_charging_power, s.e.gross_power)


@identity("gross_power_standby_ratio")
def _(s):
    return ratio(s.e.combined_standby_power, s.e.gross_power)


# Layer 3b — per-source channel power, routed through provenance.


@identity("source_adapters_consumption_power")
def _(s):
    """Every consumer's row plus the base load's row, summed per source."""
    return channel_watts(s, CON)


@identity("source_adapters_export_power")
def _(s):
    return channel_watts(s, EXP)


@identity("source_adapters_standby_power")
def _(s):
    return channel_watts(s, STB)


@identity("source_adapters_charging_power")
def _(s):
    return channel_watts(s, CHG)


# Layer 3c — per-source ratios (down a source) and shares (across a channel).


def _ratios(channel: str) -> Callable[[Snap], dict]:
    def fn(s):
        watts = published_channel(s, channel)
        return {src: ratio(w, s.sources.get(src, 0.0)) for src, w in watts.items()}

    return fn


def _shares(channel: str) -> Callable[[Snap], dict]:
    def fn(s):
        watts = published_channel(s, channel)
        total = sum(watts.values())
        return {src: ratio(w, total) for src, w in watts.items()}

    return fn


@identity("source_adapters_export_shares")
def _(s):
    watts = s.e.source_adapters_export_power
    return {src: ratio(w, s.sinks.get("grid", 0.0)) for src, w in watts.items()}


for _channel in (CON, EXP, CHG, STB):
    identity(f"source_adapters_{_channel}_ratios")(_ratios(_channel))
for _channel in (CON, CHG, STB):
    identity(f"source_adapters_{_channel}_shares")(_shares(_channel))


@identity("sink_adapters_consumption_shares")
def _(s):
    """Each consumer's draw over CON; the rest of CON is the base load."""
    return {
        k: ratio(s.sinks.get(k, 0.0), s.e.combined_consumption)
        for k in s.of("consumer")
    }


# Layer 4 — money. Marginal prices: the tariff for the grid, zero for local
# generation. Levelized prices: local sources carry their own LCOE / LCOS.


@identity("combined_coe_rate")
def _(s):
    """Only imported watts have a marginal price."""
    return kw(s.sources.get("grid", 0.0)) * s.price


@identity("combined_lcoe_rate")
def _(s):
    """Every source's output at its own levelized price."""
    return priced(s.sources, s.levelized)


@identity("combined_lcoe_rate_corrected")
def _(s):
    """Every source's output at its own corrected levelized price."""
    return priced(s.sources, s.corrected)


@identity("combined_avoided_cost_rate")
def _(s):
    """Locally supplied CON watts, valued at the tariff they displaced."""
    watts = s.e.source_adapters_consumption_power
    return kw(sum(w for src, w in watts.items() if src != "grid")) * s.price


@identity("combined_saving_rate")
def _(s):
    """What local supply avoided, less what the devices' own draw cost.

    A battery's energy cost is booked when it charges, so the only thing netted
    against the avoided cost is the devices' own draw at the margin.
    """
    return s.e.combined_avoided_cost_rate - s.e.combined_device_operating_cost_rate


@identity("combined_export_compensation_rate")
def _(s):
    return priced(s.e.source_adapters_export_power, s.compensation)


@identity("source_adapters_dynamic_coe")
def _(s):
    """A discharging battery's marginal price is 0: it was booked at charge time.

    A source delivering nothing has no price: nothing was bought.
    """
    return {
        src: s.marginal(src) if src in s.sources else None
        for src in s.source_family
    }


@identity("source_adapters_dynamic_lcoe")
def _(s):
    """A discharging battery falls back to its flat LCOS."""
    return {
        src: s.levelized(src) if src in s.sources else None
        for src in s.source_family
    }


@identity("source_adapters_coe_rate")
def _(s):
    dynamic = s.e.source_adapters_dynamic_coe
    return {
        src: kw(s.sources[src]) * dynamic[src] if src in s.sources else 0.0
        for src in s.source_family
    }


@identity("source_adapters_export_compensation_rates")
def _(s):
    exported = s.e.source_adapters_export_power
    return {src: kw(exported[src]) * s.compensation(src) for src in s.source_family}


def _own_draw(price: Callable[[Snap], Callable[[str], float]]) -> Callable:
    """Each PV / battery's own draw at its supply mix; 0 when not drawing."""

    def fn(s):
        return {
            d: priced(s.draw_watts(d), price(s)) if d in s.sinks else 0.0
            for d in s.devices
        }

    return fn


def _sink_cost(price: Callable[[Snap], Callable[[str], float]]) -> Callable:
    """Every drawing adapter's row at its sources' prices; 0 when not drawing."""

    def fn(s):
        return {
            k: priced(s.draw_watts(k), price(s)) if k in s.sinks else 0.0
            for k in s.sink_family
        }

    return fn


identity("source_adapters_coo_rates")(_own_draw(lambda s: s.marginal))
identity("source_adapters_lcoo_rates")(_own_draw(lambda s: s.levelized))
identity("sink_adapters_coo_rates")(_sink_cost(lambda s: s.marginal))
identity("sink_adapters_lcoo_rates")(_sink_cost(lambda s: s.levelized))
identity("source_adapters_lcoo_rates_corrected")(_own_draw(lambda s: s.corrected))


def _local(watts: dict[str, float]) -> float:
    return sum(w for src, w in watts.items() if src != "grid")


@identity("sink_adapters_avoided_cost_rates")
def _(s):
    """A consumer's locally supplied watts at the tariff; 0 when not drawing."""
    return {
        k: kw(_local(s.draw_watts(k))) * s.price if k in s.sinks else 0.0
        for k in s.of("consumer")
    }


@identity("home_base_load_avoided_cost_rate")
def _(s):
    return kw(_local(s.home_watts())) * s.price


def price_per_kwh(rate: float, gross: float) -> float | None:
    """A rate over gross power; no price at all when nothing was delivered."""
    return rate / kw(gross) if gross else None


@identity("combined_coe")
def _(s):
    return price_per_kwh(s.e.combined_coe_rate, s.e.gross_power)


@identity("combined_lcoe")
def _(s):
    return price_per_kwh(s.e.combined_lcoe_rate, s.e.gross_power)


def _channel_cost(channel: str, price: Callable[[Snap], Callable]) -> Callable:
    def fn(s):
        return priced(published_channel(s, channel), price(s))

    return fn


identity("combined_consumption_cost_rate")(_channel_cost(CON, lambda s: s.marginal))
identity("combined_levelized_consumption_cost_rate")(
    _channel_cost(CON, lambda s: s.levelized)
)
identity("combined_charging_cost_rate")(_channel_cost(CHG, lambda s: s.marginal))
identity("combined_levelized_export_cost_rate")(
    _channel_cost(EXP, lambda s: s.levelized)
)
identity("combined_levelized_standby_cost_rate")(
    _channel_cost(STB, lambda s: s.levelized)
)
identity("combined_lcoo_rate_corrected")(_channel_cost(CHG, lambda s: s.corrected))


@identity("combined_device_operating_cost_rate")
def _(s):
    """The device view: charging plus PV standby, summed over devices."""
    return sum(s.e.source_adapters_coo_rates.values())


@identity("combined_levelized_device_operating_cost_rate_corrected")
def _(s):
    """The device view at corrected prices, summed over devices."""
    return sum(s.e.source_adapters_lcoo_rates_corrected.values())


def _saving(price: str) -> Callable:
    """Producing: CON watts × (tariff − own price). Drawing: −own draw cost.

    ``price`` is ``marginal``, ``levelized`` or ``corrected``: which price a
    device's own energy, and its own draw, is valued at. Idle devices read 0
    rather than going absent.
    """
    own_costs = {
        "marginal": "source_adapters_coo_rates",
        "levelized": "source_adapters_lcoo_rates",
        "corrected": "source_adapters_lcoo_rates_corrected",
    }

    def fn(s):
        own_cost = getattr(s.e, own_costs[price])
        served = s.e.source_adapters_consumption_power
        own = getattr(s, price)
        out = {}
        for d in s.devices:
            if d in s.sources:
                out[d] = kw(served[d]) * (s.price - own(d))
            elif d in s.sinks:
                out[d] = -own_cost[d]
            else:
                out[d] = 0.0
        return out

    return fn


identity("adapters_saving_rates")(_saving("marginal"))
identity("adapters_levelized_saving_rates")(_saving("levelized"))
identity("adapters_levelized_saving_rates_corrected")(_saving("corrected"))


@identity("combined_levelized_saving_rate_corrected")
def _(s):
    return sum(s.e.adapters_levelized_saving_rates_corrected.values())


@identity("adapters_financial_return_rates")
def _(s):
    """Saving plus export earnings."""
    comp = s.e.source_adapters_export_compensation_rates
    return {
        d: saving + comp.get(d, 0.0)
        for d, saving in s.e.adapters_saving_rates.items()
    }


@identity("adapters_levelized_financial_return_rates")
def _(s):
    """Levelized saving plus export earnings, less the exported watts at own cost."""
    comp = s.e.source_adapters_export_compensation_rates
    exported = s.e.source_adapters_export_power
    return {
        d: saving + comp.get(d, 0.0) - kw(exported.get(d, 0.0)) * s.levelized(d)
        for d, saving in s.e.adapters_levelized_saving_rates.items()
    }


@identity("adapters_levelized_financial_return_rates_corrected")
def _(s):
    """As the levelized return, with every own cost at its corrected price."""
    comp = s.e.source_adapters_export_compensation_rates
    exported = s.e.source_adapters_export_power
    return {
        d: saving + comp.get(d, 0.0) - kw(exported.get(d, 0.0)) * s.corrected(d)
        for d, saving in s.e.adapters_levelized_saving_rates_corrected.items()
    }


@identity("combined_financial_return_rate")
def _(s):
    return sum(s.e.adapters_financial_return_rates.values())


@identity("combined_levelized_financial_return_rate_corrected")
def _(s):
    return sum(s.e.adapters_levelized_financial_return_rates_corrected.values())


# ---------------------------------------------------------------------------
# The tests.
# ---------------------------------------------------------------------------

_SNAPS: list[Snap] | None = None


def _snaps() -> list[Snap]:
    global _SNAPS
    if _SNAPS is None:
        _SNAPS = [Snap(home) for home in random_homes()]
    return _SNAPS


def test_every_catalogued_property_has_exactly_one_identity_or_is_a_root() -> None:
    missing = set(CATALOG) - set(IDENTITIES) - set(ROOTS)
    both = set(IDENTITIES) & set(ROOTS)
    assert not missing, f"no identity for {sorted(missing)}"
    assert not both, f"a root cannot also have an identity: {sorted(both)}"


@pytest.mark.parametrize("name", list(IDENTITIES))
def test_identity(name: str) -> None:
    failures = []
    for s in _snaps():
        expected = IDENTITIES[name](s)
        actual = getattr(s.e, name)
        if not matches(expected, actual, abs_tol=ABS_TOL):
            failures.append(
                f"{s.home.describe()}\n"
                f"      expected {show(expected)}\n"
                f"      actual   {show(actual)}"
            )
    if failures:
        shown = "\n  - ".join(failures[:3])
        pytest.fail(
            f"{name} broke its identity in {len(failures)} of {len(_snaps())} "
            f"random homes:\n  - {shown}",
            pytrace=False,
        )
