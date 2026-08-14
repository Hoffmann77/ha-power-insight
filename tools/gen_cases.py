"""Generate the reference-case *scaffolds* from topology/state definitions.

This tool writes the question, never the answer. It emits each case's wiring,
its snapshots' readings, and one empty slot per catalogued property — and stops
there. No value in the corpus is ever produced by this script, or by the engine
it could trivially read them from.

That is the whole design. A corpus generated from the implementation can only
ever record what the code already does, so asserting it back against that code
proves nothing: the engine agreeing with itself is a tautology, and a bug
faithfully recorded is still a bug with a page of documentation behind it. The
values here are a *specification*, so they have to come from somewhere the
implementation cannot reach — a human working the model out from first
principles, on paper, without the engine's answer in view.

Slots are filled by ``tools/worksheet.py`` (issues them, blind) and
``tools/certify.py`` (records the derived answer and what the engine said about
it). ``tests/engine/test_reference_corpus.py`` then asserts the engine against
the filled slots, which is the direction that means something.

Re-running this is safe: a filled slot is carried forward untouched. It is
dropped only when the snapshot it describes has changed underneath it — a
derivation is a claim about a specific set of readings, and it does not survive
those readings being edited.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Only the declarative half of the scenario framework. Nothing here builds an
# engine, and that omission is deliberate rather than incidental.
from tests.engine.scenario_framework import Adapter  # noqa: E402

OUT = str(ROOT / "docs" / "spec" / "cases")
CATALOG = ROOT / "docs" / "spec" / "properties.json"

# Every property the catalog documents, in catalog order — which is dependency
# order, so a state's slots read from readings up to the monetary model. The
# docs render the whole set: a property the catalog documents but the corpus
# never publishes is a metric the reader simply cannot check.
PROPERTIES = list(json.loads(CATALOG.read_text())["properties"])


def rat(x):
    """Exact rational string, or None."""
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    f = Fraction(x).limit_denominator(1_000_000)
    return str(f)


def encode(v):
    if v is None:
        return None
    if isinstance(v, dict):
        return {k: encode(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [encode(x) for x in v]
    return rat(v)


def adapter_json(a: Adapter) -> dict:
    cfg = {k: v for k, v in a.config.items() if v is not None and k != "name"}
    for k, v in list(cfg.items()):
        if isinstance(v, float):
            cfg[k] = rat(v)
        elif isinstance(v, tuple):
            cfg[k] = list(v)
    if a.kind == "grid":
        cfg["has_price_entity"] = a.has_price
    return {"uid": a.uid, "kind": a.kind, "config": cfg}


# The corpus is a ladder. Each case is the *smallest* wiring that can express
# the decision it settles, and the cases are ordered so that every rung adds
# exactly one device or flips exactly one configuration flag against the rung
# above it. A reader climbs; a maintainer looking for where a property was
# pinned reads the generated coverage table instead.
#
# Two rules keep the corpus finite, and both are load-bearing:
#
#   * A case earns its place only if it settles a decision that no lower rung
#     can express. Where a decision *is* expressible lower down, it belongs
#     lower down — a restriction deficit derived by hand across three adapters
#     is a napkin; across six it is an afternoon.
#   * A snapshot earns its place only if it moves a published value that no
#     other snapshot of its case moves.
#
# The last two cases break the one-device-at-a-time growth on purpose. They are
# specialists: Hall's condition quantifies over *subsets* of sinks and cannot
# be shown with fewer than two sources and two restricted sinks, and the mixed
# export permissions only mean anything with two dischargers that differ. They
# are the only cases that are allowed to be large, and neither is the first
# home of any decision.
CASES = [
    {
        "id": "grid-only",
        "title": "Grid only",
        "summary": (
            "One meter and nothing else. Every published property still has a "
            "value here, which makes this the cheapest place in the corpus to "
            "settle what the engine does at the edges: a single source, a house "
            "that draws nothing, and a sensor that has dropped out."
        ),
        "decides": [
            "With no local device, the whole gross power is the unmetered home base load.",
            "A sink with one available source has a provenance row of exactly one.",
            "Marginal and levelized cost agree while the grid is the only source.",
            "An unavailable reading collapses the derived values rather than defaulting to zero.",
        ],
        "topology": [
            Adapter.grid(),
        ],
        "states": [
            {
                "id": "import_only",
                "note": "The house runs on the grid alone; every watt is unmetered base load.",
                "readings": dict(grid=1200),
                "price": 0.30,
            },
            {
                "id": "grid_idle",
                "note": "The meter reads exactly 0 W: gross power is zero and every ratio has to survive it.",
                "readings": dict(grid=0),
                "price": 0.30,
            },
            {
                "id": "grid_unavailable",
                "note": "The grid sensor has dropped out. Nothing downstream of it can be answered.",
                "readings": dict(grid=None),
                "price": 0.30,
                "open_question": (
                    "combined_saving_rate publishes 0 EUR/h here while every "
                    "other rate in layer 4 correctly publishes nothing. Zero is "
                    "a claim — that the house saved exactly nothing this "
                    "snapshot — and the engine is in no position to make it "
                    "with the only meter unavailable."
                ),
            },
        ],
    },
    {
        "id": "pv-self-consumption",
        "title": "PV self-consumption",
        "summary": (
            "One string added to the grid, and nothing restricted. Two sources "
            "are enough for the raw proportional mix, for the divergence "
            "between what power costs now and what it costs levelized, and for "
            "a string that is drawing rather than producing."
        ),
        "decides": [
            "An unrestricted sink's provenance row is the raw source mix.",
            "PV standby is a sink drawing from the mix, not negative production.",
            "Marginal cost and levelized cost diverge as soon as a local source runs.",
            "A source that only draws standby makes the saving rate negative.",
        ],
        "topology": [
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10),
        ],
        "states": [
            {
                "id": "sunny_partial",
                "note": "Grid and string both supplying; the base load takes them in proportion.",
                "readings": dict(grid=800, pv1=600),
                "price": 0.30,
            },
            {
                "id": "pv_covers_all",
                "note": "The string covers the house exactly. The grid is present but contributes nothing.",
                "readings": dict(grid=0, pv1=600),
                "price": 0.30,
            },
            {
                "id": "pv_standby",
                "note": "pv1 draws 20 W standby, so it is a sink served by the grid — and the saving goes negative.",
                "readings": dict(grid=1000, pv1=-20),
                "price": 0.30,
            },
            {
                "id": "pv_unavailable",
                "note": "The string's sensor has dropped out; the grid still reads, but the total cannot be trusted.",
                "readings": dict(grid=1000, pv1=None),
                "price": 0.30,
            },
        ],
    },
    {
        "id": "pv-export",
        "title": "PV export",
        "summary": (
            "The same two devices, with the string now permitted to export. "
            "Reversing the grid changes its kind rather than its sign: it stops "
            "being a source and becomes a sink, which is all it takes to switch "
            "on the export channel and its compensation."
        ),
        "decides": [
            "An exporting grid is a sink, not a source with a negative reading.",
            "Export compensation is earned by the sources the export was drawn from.",
            "The applicable self-consumption ratio measures only what stayed home.",
            "Zero gross power guards to zero rather than dividing by zero.",
        ],
        "topology": [
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10, exports=True, export_comp=0.08),
        ],
        "states": [
            {
                "id": "export_surplus",
                "note": "The string outruns the house; the surplus leaves through the grid.",
                "readings": dict(grid=-400, pv1=900),
                "price": 0.25,
            },
            {
                "id": "export_all",
                "note": "Everything the string makes is exported: the home base load is exactly zero.",
                "readings": dict(grid=-900, pv1=900),
                "price": 0.25,
            },
            {
                "id": "zero_gross",
                "note": "The grid exports while nothing is producing — an impossible meter set that must not divide by zero.",
                "readings": dict(grid=-500, pv1=0),
                "price": 0.25,
            },
        ],
    },
    {
        "id": "metered-load",
        "title": "Metered load",
        "summary": (
            "A consumer with a meter on it, next to the unmetered remainder. "
            "The base load stops being the whole house and becomes what is left "
            "after the metered draw — including when the meters disagree and "
            "there is nothing left."
        ),
        "decides": [
            "A metered consumer gets its own provenance row; the remainder is the home base load.",
            "A metered draw larger than gross power clamps the base load to zero rather than going negative.",
            "A zeroed base load still publishes a share row, of zeros.",
        ],
        "topology": [
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10),
            Adapter.consumer("cons1"),
        ],
        "states": [
            {
                "id": "load_and_base",
                "note": "cons1 draws 500 W of the 1400 W entering the house; the other 900 W is unmetered.",
                "readings": dict(grid=800, pv1=600, cons1=-500),
                "price": 0.30,
            },
            {
                "id": "over_metered",
                "note": "cons1 reads more than the sources supply — the meters disagree, and the base load has nowhere to go but zero.",
                "readings": dict(grid=100, pv1=200, cons1=-400),
                "price": 0.30,
            },
        ],
    },
    {
        "id": "captive-load",
        "title": "Captive load",
        "summary": (
            "The same three devices, with the consumer now restricted to the "
            "string. This is the smallest wiring in which a restriction can be "
            "honoured at all — and the smallest in which one can fail, which is "
            "where the restriction deficit is first published."
        ),
        "decides": [
            "A restricted sink is served from its allowed sources before anything unrestricted shares them.",
            "Serving the captive sink first pushes the unrestricted base load onto the grid.",
            "A draw the allowed sources cannot cover is still attributed, and the shortfall is reported as a restriction deficit.",
        ],
        "topology": [
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10),
            Adapter.consumer("cons1", power_from=("pv1",)),
        ],
        "states": [
            {
                "id": "captive_load",
                "note": "pv1 makes more than cons1 draws, so cons1 runs on solar alone and the base load is pushed onto the grid.",
                "readings": dict(grid=800, pv1=600, cons1=-500),
                "price": 0.30,
            },
            {
                "id": "load_exceeds",
                "note": "cons1 draws 500 W but pv1 makes only 300 W: the missing 200 W came from a source it is not allowed to use.",
                "readings": dict(grid=800, pv1=300, cons1=-500),
                "price": 0.30,
            },
        ],
    },
    {
        "id": "battery-basics",
        "title": "Battery basics",
        "summary": (
            "An unrestricted battery, which is the only device that changes "
            "which side of the diagram it sits on. Charging it is a sink like "
            "any other; discharging it is a source whose energy was paid for in "
            "the past, and a snapshot engine has to price that somehow."
        ),
        "decides": [
            "A charging battery is a sink and takes the same raw mix as any other.",
            "A discharging battery is a source priced at its flat levelized cost of storage.",
            "Its marginal price is zero — the mix it charged on happened earlier, where a snapshot cannot see it.",
            "An adapter reading exactly 0 W belongs to neither flow group.",
        ],
        "topology": [
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10),
            Adapter.consumer("cons1"),
            Adapter.battery("bat1", lcos=0.15),
        ],
        "states": [
            {
                "id": "charging",
                "note": "bat1 charges from the mix, taking the same proportions as the metered load beside it.",
                "readings": dict(grid=800, pv1=600, cons1=-500, bat1=-600),
                "price": 0.30,
            },
            {
                "id": "discharging",
                "note": "The sun is down and bat1 has become a source, supplying two thirds of the house.",
                "readings": dict(grid=200, pv1=0, cons1=-500, bat1=400),
                "price": 0.30,
            },
            {
                "id": "idle",
                "note": "bat1 sits at exactly 0 W: neither a source nor a sink, and absent from both groups.",
                "readings": dict(grid=900, pv1=600, cons1=-500, bat1=0),
                "price": 0.30,
            },
        ],
    },
    {
        "id": "captive-battery",
        "title": "Captive battery",
        "summary": (
            "bat1 may only charge from pv1. That single restriction changes the "
            "answer in two opposite ways depending on whether pv1 is producing: "
            "when it is, the captive sink depletes it before anyone else may "
            "share it; when it is not, the sink has nowhere legal to draw from."
        ),
        "decides": [
            "A captive sink is served from its allowed source before flexible sinks share it.",
            "When every allowed source is idle the row collapses to zero rather than dividing by zero.",
            "The unservable draw is reported as a restriction deficit.",
        ],
        "topology": [
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10, exports=True),
            Adapter.battery("bat1", lcos=0.15, charge_from=("pv1",)),
            Adapter.consumer("cons1"),
        ],
        "states": [
            {
                "id": "captive_depletes_first",
                "note": "pv1 produces exactly what bat1 draws, so bat1 takes all of it.",
                "readings": dict(grid=500, pv1=400, bat1=-400, cons1=-200),
                "price": 0.30,
            },
            {
                "id": "source_in_standby",
                "note": "pv1 is drawing standby, so it is a sink; bat1's only allowed source does not exist.",
                "readings": dict(grid=1000, pv1=-20, bat1=-400, cons1=-100),
                "price": 0.30,
                "open_question": (
                    "home_base_load_power includes the 400 W bat1 drew but could "
                    "not legally be attributed, so the 'unmetered' load contains a "
                    "device that has a meter on it. Its docstring says gross minus "
                    "metered draw, which would be 580 W rather than 980 W."
                ),
            },
        ],
    },
    {
        "id": "group-captivity",
        "title": "Group captivity",
        "summary": (
            "Two batteries are each allowed both strings, and neither is "
            "individually stuck — but together they need every watt the two "
            "strings make. Deciding feasibility one sink at a time cannot see "
            "that; this is the case the max-flow solver exists for."
        ),
        "decides": [
            "Feasibility is a property of groups of sinks, not of single sinks.",
            "A flexible sink must not take local power a tight group needs.",
            "When restrictions cannot all be honoured, the sink with the fewest "
            "permitted alternatives is served first and the deficit falls on the "
            "sinks that had somewhere else to go.",
        ],
        "topology": [
            Adapter.grid(),
            Adapter.pv("east", lcoe=0.10, exports=True),
            Adapter.pv("west", lcoe=0.10, exports=True),
            Adapter.battery("bat_a", lcos=0.15, charge_from=("east", "west")),
            Adapter.battery("bat_b", lcos=0.15, charge_from=("east", "west")),
            Adapter.battery("bat_c", lcos=0.15, charge_from=("east",)),
        ],
        "states": [
            {
                "id": "hall_tight_pair",
                "note": (
                    "bat_c idle. {bat_a, bat_b} exactly exhaust east+west, so the "
                    "200 W home load must be served entirely from the grid."
                ),
                "readings": dict(grid=200, east=100, west=100, bat_a=-100, bat_b=-100, bat_c=0),
                "price": 0.30,
            },
            {
                "id": "unsatisfiable_overlap",
                "note": (
                    "bat_c now draws 100 W and is captive to east alone. Captive "
                    "demand (300 W) exceeds local supply (200 W): someone must be "
                    "deficited."
                ),
                "readings": dict(grid=200, east=100, west=100, bat_a=-100, bat_b=-100, bat_c=-100),
                "price": 0.30,
            },
        ],
    },
    {
        "id": "mixed-export-house",
        "title": "Mixed export house",
        "summary": (
            "Every device class at once, with the export permissions "
            "deliberately unequal: one battery may feed the grid and the other "
            "may not. Nothing here is settled for the first time — this is the "
            "case that checks the rules of the lower rungs still hold when they "
            "all apply together."
        ),
        "decides": [
            "A device that cannot export is excluded from the export mix, even while discharging.",
            "Standby draw is routed through the provenance allocation, not by gross share.",
            "Two dischargers with different levelized costs price the mix between them.",
        ],
        "topology": [
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.pv("pv2", lcoe=0.10, exports=True, export_comp=0.08),
            Adapter.battery("bat1", lcos=0.15, exports=True, export_comp=0.08),
            Adapter.battery("bat2", lcos=0.20, exports=False),
            Adapter.consumer("cons1"),
        ],
        "states": [
            {
                "id": "export_non_exporting_battery",
                "note": "bat2 discharges but may not feed the grid, so the export mix excludes it.",
                "readings": dict(grid=-600, pv1=800, pv2=0, bat1=200, bat2=200, cons1=-400),
                "price": 0.25,
            },
            {
                "id": "export_with_standby",
                "note": "pv2 in standby while the house exports; standby competes in the allocation.",
                "readings": dict(grid=-600, pv1=800, pv2=-50, bat1=200, bat2=200, cons1=-400),
                "price": 0.25,
            },
            {
                "id": "discharge_dynamic_prices",
                "note": "Both batteries discharging; the mix they charged on is in the past.",
                "readings": dict(grid=-300, pv1=0, pv2=-50, bat1=400, bat2=400, cons1=-400),
                "price": 0.25,
            },
        ],
    },
]


def snapshot_fingerprint(topology: list[dict], st: dict) -> str:
    """Identify the *question* a snapshot asks, so an answer can be tied to it.

    A derivation is a claim about one specific set of readings against one
    specific wiring. Edit either and the claim is about a snapshot that no
    longer exists, however sound the arithmetic was. Hashing the inputs lets a
    regeneration tell those two cases apart: reshaping the prose around a
    snapshot keeps its answers, changing what it asks throws them away.
    """
    payload = json.dumps(
        {
            "topology": topology,
            "readings": {k: rat(v) for k, v in st["readings"].items()},
            "price": rat(st["price"]),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def existing_answers(case_id: str) -> dict:
    """Hand-derived answers already recorded for this case.

    These are the only values the corpus has and every one of them cost
    somebody a morning, so regenerating must never quietly drop one. They are
    keyed by (state, property) rather than by file position, so they survive
    the case being reshaped around them, and each carries the fingerprint of
    the snapshot it was derived against.
    """
    path = os.path.join(OUT, f"{case_id}.json")
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        prior = json.load(fh)
    kept = {}
    for state in prior.get("states", []):
        for exp in state.get("expectations", []):
            # Only the two statuses a human can produce. Anything else is an
            # empty slot or a leftover from when this tool wrote values itself,
            # and neither is something to preserve.
            if exp.get("certification", {}).get("status") not in ("verified", "disputed"):
                continue
            kept[(state["id"], exp["property"])] = (state.get("asks"), exp)
    return kept


def build(case):
    topology = [adapter_json(a) for a in case["topology"]]
    prior = existing_answers(case["id"])
    out = {
        "$schema": "../reference-case.schema.json",
        "id": case["id"],
        "title": case["title"],
        "summary": case["summary"],
        "decides": case["decides"],
        "topology": topology,
        "states": [],
    }
    for st in case["states"]:
        asks = snapshot_fingerprint(topology, st)
        expectations = []
        for name in PROPERTIES:
            # An empty slot. Every property gets one on every snapshot, whether
            # or not the engine has an answer for it — whether it does is
            # exactly the sort of thing a derivation is entitled to disagree
            # about, and a slot the scaffold silently omitted could not.
            slot = {
                "property": name,
                "value": None,
                "derivation": [],
                "certification": {"status": "pending"},
            }
            held = prior.get((st["id"], name))
            if held is not None:
                held_asks, held_exp = held
                if held_asks == asks:
                    slot = held_exp
                else:
                    print(
                        f"  ! {case['id']}/{st['id']}/{name}: snapshot changed, "
                        f"dropping a {held_exp['certification'].get('status')} answer"
                    )
            expectations.append(slot)
        entry = {
            "id": st["id"],
            "note": st["note"],
            "asks": asks,
            "readings": {k: rat(v) for k, v in st["readings"].items()},
            "price": rat(st["price"]),
            "expectations": expectations,
        }
        if st.get("open_question"):
            entry["open_question"] = st["open_question"]
        out["states"].append(entry)
    return out


def coverage(built: list[dict]) -> dict:
    """The state of the derivation programme, per property and per rung.

    Once the corpus stopped recording engine output, "which rungs publish a
    distinct value for this property" stopped being answerable — there are no
    values to be distinct until somebody derives them. What replaces it is
    plainer and more useful: how many slots each property has, how many are
    filled, and where the filled ones are. It is a worklist as much as a
    coverage table, and it will read as almost entirely empty for a while.
    That is the honest picture, not a defect in the report.
    """
    catalog = json.loads(CATALOG.read_text())["properties"]
    entries = {}
    for name in PROPERTIES:
        doc = catalog[name]
        entry = {
            "title": doc["title"],
            "layer": doc["layer"],
            "slots": 0,
            "derived": 0,
            "disputed": 0,
            "derived_in": [],
        }
        for case in built:
            for state in case["states"]:
                for exp in state["expectations"]:
                    if exp["property"] != name:
                        continue
                    entry["slots"] += 1
                    status = exp["certification"].get("status")
                    if status == "pending":
                        continue
                    entry["derived"] += 1
                    if status == "disputed":
                        entry["disputed"] += 1
                    if case["id"] not in entry["derived_in"]:
                        entry["derived_in"].append(case["id"])
        entries[name] = entry

    per_case = []
    for case in built:
        slots = sum(len(s["expectations"]) for s in case["states"])
        derived = sum(
            1
            for s in case["states"]
            for e in s["expectations"]
            if e["certification"].get("status") != "pending"
        )
        per_case.append(
            {
                "case": case["id"],
                "case_title": case["title"],
                "decides": case["decides"],
                "slots": slots,
                "derived": derived,
            }
        )

    return {
        "order": [c["id"] for c in built],
        "decisions": per_case,
        "properties": entries,
        "totals": {
            "slots": sum(e["slots"] for e in entries.values()),
            "derived": sum(e["derived"] for e in entries.values()),
            "disputed": sum(e["disputed"] for e in entries.values()),
            "untouched": sorted(n for n, e in entries.items() if e["derived"] == 0),
        },
    }


os.makedirs(OUT, exist_ok=True)
index = {"cases": []}
built = []
for case in CASES:
    data = build(case)
    built.append(data)
    path = os.path.join(OUT, f"{data['id']}.json")
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    index["cases"].append(
        {
            "id": data["id"],
            "title": data["title"],
            "file": f"{data['id']}.json",
            "states": [s["id"] for s in data["states"]],
            "certified": sum(
                1
                for s in data["states"]
                for e in s["expectations"]
                if e["certification"].get("status") == "verified"
            ),
            "total": sum(len(s["expectations"]) for s in data["states"]),
            "pending": sum(
                1
                for s in data["states"]
                for e in s["expectations"]
                if e["certification"].get("status") == "pending"
            ),
        }
    )
    slots = sum(len(s["expectations"]) for s in data["states"])
    print(f"wrote {path}  ({len(data['states'])} states, {slots} slots)")

with open(os.path.join(OUT, "index.json"), "w") as fh:
    json.dump(index, fh, indent=2)
    fh.write("\n")
print("wrote index.json")

cov = coverage(built)
with open(os.path.join(OUT, "coverage.json"), "w") as fh:
    json.dump(cov, fh, indent=2)
    fh.write("\n")
t = cov["totals"]
print(
    f"wrote coverage.json  ({t['derived']} of {t['slots']} slots derived"
    + (f", {t['disputed']} disputed" if t["disputed"] else "")
    + ")"
)
