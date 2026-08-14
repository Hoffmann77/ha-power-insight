"""Generate the reference-case JSON files from topology/state definitions.

Values are read from the engine and written with ``status: unverified``.
Derivations are deliberately NOT written: they are the author's own work,
produced during blind certification. Writing them here would destroy the
independence that makes a certification worth anything.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.engine.scenario_framework import Adapter, Cell, State, Topology  # noqa: E402

OUT = str(ROOT / "docs" / "spec" / "cases")
CATALOG = ROOT / "docs" / "spec" / "properties.json"

# Every property the catalog documents, in catalog order — which is dependency
# order, so a state's expectations read from readings up to the monetary model.
# The docs render the whole set: a property the engine answers but the corpus
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


CASES = [
    {
        "id": "baseline-mix",
        "title": "Baseline mix",
        "summary": (
            "The degenerate baseline every other case is read against. Nothing is "
            "restricted, so each sink simply mirrors the raw availability of the "
            "sources, and the unmetered home load competes for power like any "
            "other sink."
        ),
        "decides": [
            "An unrestricted sink's provenance row is the raw source mix.",
            "The unmetered home base load participates in the allocation.",
            "PV standby is a sink, not negative production.",
            "An adapter reading exactly 0 W belongs to neither flow group.",
        ],
        "topology": [
            Adapter.grid(),
            Adapter.pv("pv1", lcoe=0.10, exports=True),
            Adapter.battery("bat1", lcos=0.15),
            Adapter.consumer("cons1"),
        ],
        "states": [
            {
                "id": "import_mix",
                "note": "Grid importing alongside PV; battery charging, one load.",
                "readings": dict(grid=800, pv1=600, bat1=-600, cons1=-500),
                "price": 0.30,
            },
            {
                "id": "standby_and_idle",
                "note": "pv1 draws standby (a sink); cons1 sits at 0 W (neither group).",
                "readings": dict(grid=1000, pv1=-20, bat1=-400, cons1=0),
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
        "id": "grid-export",
        "title": "Grid export",
        "summary": (
            "With the grid exporting it stops being a source and becomes a sink "
            "- and a restricted one, because only devices configured to export "
            "may feed it. That single reversal switches on the export channel, "
            "the compensation family and the discharge price rules at once."
        ),
        "decides": [
            "An exporting grid is a restricted sink, not a source.",
            "A device that cannot export is excluded from the export mix.",
            "Standby draw is routed through the provenance allocation, not by gross share.",
            "A discharging battery is priced at its flat LCOS; its marginal price is zero.",
            "Zero gross power guards to zero rather than dividing by zero.",
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
            {
                "id": "pure_export_zero_gross",
                "note": "Nothing is producing and the grid is exporting: gross power is exactly 0.",
                "readings": dict(grid=-500, pv1=0, pv2=0, bat1=0, bat2=0, cons1=0),
                "price": 0.25,
            },
        ],
    },
]


def existing_certifications(case_id):
    """Certifications and derivations already recorded for this case.

    Regenerating must never destroy hand-certification work: those are
    mornings of somebody's derivation, keyed by (state, property) rather than
    by file position so they survive the case being reshaped around them. A
    certification whose *value* has changed is dropped deliberately -- it was a
    claim about the old number and no longer holds.
    """
    path = os.path.join(OUT, f"{case_id}.json")
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        prior = json.load(fh)
    kept = {}
    for state in prior.get("states", []):
        for exp in state.get("expectations", []):
            cert = exp.get("certification", {})
            if cert.get("status") == "unverified" and not exp.get("derivation"):
                continue
            kept[(state["id"], exp["property"])] = (
                exp.get("value"),
                exp.get("derivation", []),
                cert,
            )
    return kept


def build(case):
    topo = Topology(*case["topology"])
    prior = existing_certifications(case["id"])
    out = {
        "$schema": "../reference-case.schema.json",
        "id": case["id"],
        "title": case["title"],
        "summary": case["summary"],
        "decides": case["decides"],
        "topology": [adapter_json(a) for a in case["topology"]],
        "states": [],
    }
    for st in case["states"]:
        state = State(price=st["price"], **st["readings"])
        engine = Cell(topo, state).build_engine()
        expectations = []
        for name in PROPERTIES:
            value = encode(getattr(engine, name))
            # A property the engine cannot answer this snapshot is left out
            # rather than published as null: the corpus states what the engine
            # computes, and "nothing" is not a value anyone can certify.
            if value is None:
                continue
            derivation, certification = [], {"status": "unverified"}
            kept = prior.get((st["id"], name))
            if kept is not None:
                old_value, old_derivation, old_certification = kept
                if old_value == value:
                    derivation, certification = old_derivation, old_certification
                else:
                    print(
                        f"  ! {case['id']}/{st['id']}/{name}: value changed, "
                        f"dropping a {old_certification.get('status')} certification"
                    )
            expectations.append(
                {
                    "property": name,
                    "value": value,
                    "derivation": derivation,
                    "certification": certification,
                }
            )
        entry = {
            "id": st["id"],
            "note": st["note"],
            "readings": {k: rat(v) for k, v in st["readings"].items()},
            "price": rat(st["price"]),
            "expectations": expectations,
        }
        if st.get("open_question"):
            entry["open_question"] = st["open_question"]
        out["states"].append(entry)
    return out


os.makedirs(OUT, exist_ok=True)
index = {"cases": []}
for case in CASES:
    data = build(case)
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
            "certified": 0,
            "total": sum(len(s["expectations"]) for s in data["states"]),
        }
    )
    print(f"wrote {path}  ({len(data['states'])} states, "
          f"{sum(len(s['expectations']) for s in data['states'])} expectations)")

with open(os.path.join(OUT, "index.json"), "w") as fh:
    json.dump(index, fh, indent=2)
    fh.write("\n")
print("wrote index.json")
