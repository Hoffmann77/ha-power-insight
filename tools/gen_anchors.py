"""Generate the anchor-case JSON files from topology/state definitions.

Values are read from the engine and written with ``status: unverified``.
Derivations are deliberately NOT written: they are the author's own work,
produced during blind certification. Writing them here would destroy the
independence that makes a certification worth anything.
"""

from __future__ import annotations

import json
import os
import sys
from fractions import Fraction

sys.path.insert(0, "/home/user/ha-power-insight")

from tests.engine.scenario_framework import Adapter, Cell, State, Topology  # noqa: E402

OUT = "/home/user/ha-power-insight/docs/spec/anchors"

CORE = [
    "gross_power",
    "combined_grid_import",
    "combined_grid_export",
    "combined_production",
    "combined_charging_power",
    "combined_discharging_power",
    "combined_standby_power",
    "combined_consumption",
    "home_base_load_power",
    "sink_adapters_source_shares",
    "home_base_load_source_shares",
    "sink_adapters_restriction_deficit",
]


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
        "id": "A-001",
        "title": "Baseline mix, no restrictions",
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
                "focus": [
                    "combined_coe_rate",
                    "combined_lcoe_rate",
                    "combined_avoided_cost_rate",
                    "combined_saving_rate",
                ],
            },
            {
                "id": "standby_and_idle",
                "note": "pv1 draws standby (a sink); cons1 sits at 0 W (neither group).",
                "readings": dict(grid=1000, pv1=-20, bat1=-400, cons1=0),
                "price": 0.30,
                "focus": ["gross_power_standby_ratio", "gross_power_charging_ratio"],
            },
        ],
    },
    {
        "id": "A-002",
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
                "focus": [],
            },
            {
                "id": "source_in_standby",
                "note": "pv1 is drawing standby, so it is a sink; bat1's only allowed source does not exist.",
                "readings": dict(grid=1000, pv1=-20, bat1=-400, cons1=-100),
                "price": 0.30,
                "focus": [],
            },
        ],
    },
    {
        "id": "A-003",
        "title": "Group captivity (Hall's condition)",
        "summary": (
            "Two batteries are each allowed both strings, and neither is "
            "individually stuck — but together they need every watt the two "
            "strings make. Deciding feasibility one sink at a time cannot see "
            "that; this is the case the max-flow solver exists for."
        ),
        "decides": [
            "Feasibility is a property of groups of sinks, not of single sinks.",
            "A flexible sink must not take local power a tight group needs.",
            "When two captive groups contend and the configuration cannot be "
            "satisfied, which one yields.",
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
                "focus": [],
            },
            {
                "id": "unsatisfiable_overlap",
                "note": (
                    "bat_c now draws 100 W and is captive to east alone. Captive "
                    "demand (300 W) exceeds local supply (200 W): someone must be "
                    "deficited. OPEN QUESTION - see the handoff."
                ),
                "readings": dict(grid=200, east=100, west=100, bat_a=-100, bat_b=-100, bat_c=-100),
                "price": 0.30,
                "focus": [],
            },
        ],
    },
    {
        "id": "A-004",
        "title": "Export",
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
                "focus": [
                    "source_adapters_export_power",
                    "source_adapters_export_shares",
                    "combined_export_compensation_rate",
                    "gross_power_export_ratio",
                ],
            },
            {
                "id": "export_with_standby",
                "note": "pv2 in standby while the house exports; standby competes in the allocation.",
                "readings": dict(grid=-600, pv1=800, pv2=-50, bat1=200, bat2=200, cons1=-400),
                "price": 0.25,
                "focus": [
                    "source_adapters_standby_power",
                    "gross_power_standby_ratio",
                    "gross_power_applicable_consumption_ratio",
                ],
            },
            {
                "id": "discharge_dynamic_prices",
                "note": "Both batteries discharging; the mix they charged on is in the past.",
                "readings": dict(grid=-300, pv1=0, pv2=-50, bat1=400, bat2=400, cons1=-400),
                "price": 0.25,
                "focus": [
                    "source_adapters_dynamic_coe",
                    "source_adapters_dynamic_lcoe",
                    "combined_export_compensation_rate",
                ],
            },
            {
                "id": "pure_export_zero_gross",
                "note": "Nothing is producing and the grid is exporting: gross power is exactly 0.",
                "readings": dict(grid=-500, pv1=0, pv2=0, bat1=0, bat2=0, cons1=0),
                "price": 0.25,
                "focus": ["gross_power_export_ratio", "gross_power_consumption_ratio"],
            },
        ],
    },
]


def build(case):
    topo = Topology(*case["topology"])
    out = {
        "$schema": "../anchor-case.schema.json",
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
        props = CORE + [p for p in st["focus"] if p not in CORE]
        expectations = []
        for name in props:
            expectations.append(
                {
                    "property": name,
                    "value": encode(getattr(engine, name)),
                    "derivation": [],
                    "certification": {"status": "unverified"},
                }
            )
        out["states"].append(
            {
                "id": st["id"],
                "note": st["note"],
                "readings": {k: rat(v) for k, v in st["readings"].items()},
                "price": rat(st["price"]),
                "expectations": expectations,
            }
        )
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
