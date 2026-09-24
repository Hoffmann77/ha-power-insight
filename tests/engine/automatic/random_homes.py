"""Random homes for the engine tier's value-free tests.

``test_identities.py`` and ``test_laws.py`` hold no hand-derived numbers: they
check what must be true of *any* snapshot, so they need many snapshots, and
this module makes them. Each :class:`Home` is one wiring plus one physically
plausible set of readings. Most balance — the sinks draw no more than the
sources provide — and a tenth overdraw slightly, the way unsynchronised
sensors do.

Everything a result can hinge on is varied, not just the readings: the grid
price, every device's LCOE / LCOS and its correction factor, which devices may
export and what they are paid for it, and restrictions that can name the grid
as well as local devices. The draw is seeded, so a failure reproduces.

Sign convention (watts): grid ``+`` import / ``-`` export; pv/battery ``+``
produce/discharge / ``-`` standby/charge; consumer ``-`` = load.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from tests.engine.home import Adapter, Cell, State, Topology

SEED = 20260923
COUNT = 200

#: The correction factors a PV system or battery is drawn with: mostly an
#: unedited lifetime cost, otherwise one restated up or down.
FACTORS = (1.0, 1.0, 0.8, 1.25, 1.5, 2.0)


@dataclass(frozen=True)
class Home:
    """One random wiring and its readings."""

    adapters: tuple[Adapter, ...]
    readings: dict[str, float | None]
    price: float | None

    @property
    def topology(self) -> Topology:
        return Topology(*self.adapters)

    @property
    def state(self) -> State:
        return State(price=self.price, **self.readings)

    def engine(self):
        return Cell(self.topology, self.state).build_engine()

    @property
    def balanced(self) -> bool:
        """Whether the metered sinks draw no more than the sources provide."""
        powers = [
            (a.kind, self.readings[a.uid]) for a in self.adapters
        ]
        gross = sum(w for kind, w in powers if w and w > 0 and kind != "consumer")
        drawn = sum(-w for _, w in powers if w and w < 0)
        return drawn <= gross

    def adapter(self, uid: str) -> Adapter:
        return next(a for a in self.adapters if a.uid == uid)

    def uids(self, kind: str) -> list[str]:
        return [a.uid for a in self.adapters if a.kind == kind]

    def with_readings(self, **changes: float | None) -> "Home":
        return replace(self, readings={**self.readings, **changes})

    def describe(self) -> str:
        parts = []
        for a in self.adapters:
            restriction = list(a.power_source_uids)
            parts.append(f"{a.uid}={self.readings[a.uid]}{restriction or ''}")
        return f"{', '.join(parts)}, price={self.price}"


def _split(rng: random.Random, total: int, parts: int) -> list[int]:
    """Split ``total`` into ``parts`` non-negative multiples of ten."""
    cuts = sorted(rng.randint(0, total // 10) * 10 for _ in range(parts - 1))
    bounds = [0, *cuts, total]
    return [bounds[i + 1] - bounds[i] for i in range(parts)]


def _make_home(rng: random.Random, factor_rng: random.Random) -> Home | None:
    pv = [f"pv{i}" for i in range(rng.randint(0, 3))]
    bat = [f"bat{i}" for i in range(rng.randint(0, 2))]
    cons = [f"cons{i}" for i in range(rng.randint(0, 3))]

    readings: dict[str, float] = {}
    sources: dict[str, int] = {}
    sinks: list[str] = []

    grid_role = rng.choices(("import", "export", "idle"), (0.55, 0.4, 0.05))[0]
    if grid_role == "import":
        sources["grid"] = rng.randrange(1, 60) * 50
    elif grid_role == "export":
        sinks.append("grid")
    for uid in pv:
        if rng.random() < 0.75:
            sources[uid] = rng.randrange(1, 80) * 50
        else:
            sinks.append(uid)  # standby draw
    for uid in bat:
        role = rng.choices(("charge", "discharge", "idle"), (0.45, 0.4, 0.15))[0]
        if role == "discharge":
            sources[uid] = rng.randrange(1, 40) * 50
        elif role == "charge":
            sinks.append(uid)
        else:
            readings[uid] = 0
    sinks += cons

    gross = sum(sources.values())
    if gross == 0:
        return None

    # A fifth of the homes put the whole of gross power through metered sinks,
    # so there is no base load to hide a rounding error in. A few draw slightly
    # *more* than gross: sensors are not read at the same instant, and the
    # engine has to survive readings that do not quite balance.
    fraction = rng.choices(
        (1.0, rng.uniform(1.01, 1.1), rng.uniform(0.2, 0.95)), (0.2, 0.1, 0.7)
    )[0]
    budget = int(gross * fraction) // 10 * 10
    draws = _split(rng, budget, len(sinks)) if sinks else []
    for uid, draw in zip(sinks, draws):
        readings[uid] = -draw
    readings.update(sources)
    readings.setdefault("grid", 0)
    # A standby PV system that happened to draw nothing is simply idle.

    # Restrictions may name the grid: the grid-anchored allocation tier.
    targets = ["grid", *pv, *bat]
    restrictions = {}
    for uid in bat + cons:
        pool = [t for t in targets if t != uid]
        if rng.random() < 0.5:
            restrictions[uid] = tuple(rng.sample(pool, rng.randint(1, min(2, len(pool)))))

    lcoe = (0.05, 0.08, 0.12, 0.20)
    lcos = (0.10, 0.15, 0.25)
    comp = (0.0, 0.06, 0.08)
    adapters = [Adapter.grid()]
    adapters += [
        Adapter.pv(
            uid,
            lcoe=rng.choice(lcoe),
            exports=rng.random() < 0.8,
            export_comp=rng.choice(comp),
            correction_factor=factor_rng.choice(FACTORS),
        )
        for uid in pv
    ]
    adapters += [
        Adapter.battery(
            uid,
            lcos=rng.choice(lcos),
            exports=rng.random() < 0.3,
            export_comp=rng.choice(comp),
            charge_from=restrictions.get(uid, ()),
            correction_factor=factor_rng.choice(FACTORS),
        )
        for uid in bat
    ]
    adapters += [
        Adapter.consumer(uid, power_from=restrictions.get(uid, ())) for uid in cons
    ]
    price = rng.choice((0.18, 0.25, 0.30, 0.42))
    return Home(tuple(adapters), readings, price)


def random_homes(count: int = COUNT, seed: int = SEED) -> list[Home]:
    """``count`` random homes, the same ones every call."""
    rng = random.Random(seed)
    # The factors come from a stream of their own, so adding them left every
    # other draw — and therefore every home — exactly as it was.
    factor_rng = random.Random(seed + 1)
    homes: list[Home] = []
    while len(homes) < count:
        home = _make_home(rng, factor_rng)
        if home is not None:
            homes.append(home)
    return homes
