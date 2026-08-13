"""Generate printable certification worksheets from the anchor cases.

A worksheet states the problem and withholds the answer. That is the whole
point: a value you derived independently, without the engine's number in front
of you, is evidence. A value you nodded along to is not.

So three things are deliberately *not* printed:

* **The expectation being derived.** Obviously.
* **The flows between devices.** They are the answer to the provenance
  properties, so the wiring diagram shows devices and restrictions only.
* **The state's ``note``.** Those read like "{bat_a, bat_b} exactly exhaust
  east+west, so the 200 W home load must be served entirely from the grid" —
  which is the conclusion. Good documentation, ruinous exam paper.

What *is* printed: the topology and its static config, the readings, and any
expectation already certified — because a derivation that can lean on trusted
numbers is minutes rather than an evening.

Problems are issued in dependency order (from ``properties.json``), so by the
time a sheet asks for a cost rate the channel watts underneath it are already
given.

Usage::

    uv run python tools/worksheet.py                     # next 6 pending
    uv run python tools/worksheet.py --count 12
    uv run python tools/worksheet.py --case A-003 --all
    uv run python tools/worksheet.py --pdf               # also render a PDF

Answers are entered later against the manifest each run writes, so a sheet
worked on paper on Tuesday can be typed up on Friday.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import html
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ANCHORS = ROOT / "docs" / "spec" / "anchors"
CATALOG = ROOT / "docs" / "spec" / "properties.json"
OUT_DIR = ROOT / "worksheets"

# Config keys worth printing on a sheet, in the order they read best.
CONFIG_LABELS = [
    ("has_price_entity", "price entity"),
    ("lcoe", "LCOE"),
    ("lcos", "LCOS"),
    ("exports_power", "may export"),
    ("export_compensation", "export comp."),
    ("correction_factor", "correction"),
    ("charge_from_adapters", "may charge from"),
    ("power_from_adapters", "may draw from"),
]


def load_catalog() -> dict:
    return json.loads(CATALOG.read_text())["properties"]


def load_cases() -> list[dict]:
    return [json.loads(pathlib.Path(p).read_text()) for p in sorted(glob.glob(str(ANCHORS / "A-*.json")))]


def dependency_rank(catalog: dict) -> dict[str, int]:
    """Position of each property in a topological order of the catalog."""
    rank: dict[str, int] = {}

    def visit(name: str, stack: tuple[str, ...] = ()) -> None:
        if name in rank or name not in catalog:
            return
        if name in stack:
            raise ValueError(f"dependency cycle at {name}")
        for dep in catalog[name]["depends_on"]:
            visit(dep, stack + (name,))
        rank[name] = len(rank)

    for name in catalog:
        visit(name)
    return rank


def fmt_config(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(value) if value else "unrestricted"
    return str(value)


# ---------------------------------------------------------------------------
# Answer fields. The key structure is printed; every number is blank.
# ---------------------------------------------------------------------------


def blank(width: str = "5.5em") -> str:
    return f'<span class="blank" style="min-width:{width}"></span>'


def answer_field(shape: str, value, unit: str) -> str:
    """Render blanks shaped like the answer, without revealing any of it.

    Keys are structural — which sinks are drawing, which sources exist — and a
    reader can already see them in the readings. Numbers are the answer.
    ``map_derived_keys`` is the exception: *which* keys appear is itself what
    is being worked out, so the rows are left blank too.
    """
    suffix = f' <span class="unit">{html.escape(unit)}</span>' if unit else ""

    if shape == "map_derived_keys":
        rows = "".join(
            f'<div class="arow">{blank("9em")} = {blank()}{suffix}</div>' for _ in range(4)
        )
        return f'<div class="answer"><p class="hint">List only the entries that apply — there may be none.</p>{rows}</div>'

    if shape == "map_fixed_keys" and isinstance(value, dict):
        if not value:
            return f'<div class="answer"><p class="hint">Expected to be empty — confirm, or list what belongs here.</p><div class="arow">{blank("9em")} = {blank()}{suffix}</div></div>'
        # No per-row unit here: the Answer heading already carries it, and
        # repeating "share" down a column is just noise.
        cells = "".join(
            f'<div class="arow"><span class="key">{html.escape(k)}</span> {blank()}</div>'
            for k in value
        )
        return f'<div class="answer">{cells}</div>'

    if shape == "nested_map_fixed_keys" and isinstance(value, dict):
        if not value:
            return f'<div class="answer"><p class="hint">Expected to be empty — confirm, or list what belongs here.</p></div>'
        columns: list[str] = []
        for row in value.values():
            for col in row:
                if col not in columns:
                    columns.append(col)
        head = "".join(f"<th>{html.escape(c)}</th>" for c in columns)
        body = "".join(
            "<tr><th>"
            + html.escape(sink)
            + "</th>"
            + "".join(f"<td>{blank('4.5em')}</td>" for _ in columns)
            + "</tr>"
            for sink in value
        )
        return f'<div class="answer"><table class="grid"><tr><th></th>{head}</tr>{body}</table></div>'

    return f'<div class="answer"><div class="arow">{blank("7em")}{suffix}</div></div>'


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def collect(cases: list[dict], catalog: dict, case_filter: str | None) -> list[dict]:
    """Pending problems, grouped per (case, state), in dependency order."""
    rank = dependency_rank(catalog)
    blocks = []
    for case in cases:
        if case_filter and case["id"] != case_filter:
            continue
        for state in case["states"]:
            pending, given = [], []
            for exp in state["expectations"]:
                if exp["property"] not in catalog:
                    continue
                (given if exp["certification"]["status"] == "verified" else pending).append(exp)
            pending.sort(key=lambda e: rank.get(e["property"], 10_000))
            given.sort(key=lambda e: rank.get(e["property"], 10_000))
            if pending:
                blocks.append({"case": case, "state": state, "pending": pending, "given": given})
    return blocks


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

CSS = """
@page { size: A4; margin: 14mm 13mm 12mm; }
* { box-sizing: border-box; }
body { font: 10.5pt/1.45 "Helvetica Neue", Helvetica, Arial, sans-serif; color: #111; margin: 0; }
h1 { font-size: 15pt; margin: 0 0 2mm; }
.sheetmeta { font: 8.5pt ui-monospace, Menlo, monospace; color: #555; margin-bottom: 5mm; }
.state { page-break-after: always; }
.state:last-child { page-break-after: auto; }
.statehead { border-bottom: 1.5pt solid #111; padding-bottom: 2mm; margin-bottom: 3mm; }
.statehead h2 { font-size: 12.5pt; margin: 0; }
.statehead .ids { font: 9pt ui-monospace, Menlo, monospace; color: #555; }
table.devices { width: 100%; border-collapse: collapse; margin-bottom: 4mm; font-size: 9pt; }
table.devices th, table.devices td { border: 0.5pt solid #bbb; padding: 1.2mm 2mm; text-align: left; vertical-align: top; }
table.devices th { background: #f0f0f0; font-weight: 600; }
table.devices td.num { font-family: ui-monospace, Menlo, monospace; text-align: right; white-space: nowrap; }
.given { border: 0.5pt solid #999; background: #f7f7f7; padding: 2mm 3mm; margin-bottom: 4mm; font-size: 9pt; }
.given h3, .problem h3 { font-size: 8.5pt; letter-spacing: .08em; text-transform: uppercase; color: #444; margin: 0 0 1.5mm; }
.given .g { font-family: ui-monospace, Menlo, monospace; }
.problem { border: 0.8pt solid #111; padding: 3mm; margin-bottom: 4mm; page-break-inside: avoid; }
.problem .ptitle { font-size: 11pt; font-weight: 700; margin: 0 0 1mm; }
.problem .pid { font: 8.5pt ui-monospace, Menlo, monospace; color: #666; float: right; }
.problem .def { font-size: 9pt; margin: 0 0 2mm; }
.problem .formula { font: 9pt ui-monospace, Menlo, monospace; background: #f2f2f2; padding: 1.5mm 2mm; margin-bottom: 2mm; }
.problem ol { margin: 0 0 2.5mm; padding-left: 5mm; font-size: 9pt; }
.problem ol li { margin-bottom: 0.8mm; }
.note { font-size: 8.5pt; font-style: italic; color: #444; border-left: 1.5pt solid #999; padding-left: 2mm; margin: 0 0 2.5mm; }
.answer { margin: 2mm 0 0; }
.arow { margin-bottom: 2mm; font-family: ui-monospace, Menlo, monospace; font-size: 9.5pt; }
.arow .key { display: inline-block; min-width: 6em; }
.blank { display: inline-block; border-bottom: 0.8pt solid #111; height: 1.15em; vertical-align: -0.2em; }
.unit { font-size: 8.5pt; color: #555; }
table.grid { border-collapse: collapse; font-size: 9.5pt; }
table.grid th { font: 9pt ui-monospace, Menlo, monospace; padding: 1mm 3mm 1mm 0; text-align: left; color: #333; }
table.grid td { padding: 1mm 3mm 1mm 0; }
.hint { font-size: 8.5pt; color: #555; margin: 0 0 1.5mm; }
.working { border: 0.5pt dashed #999; height: 30mm; margin-top: 2mm; }
.working span { font-size: 8pt; color: #888; padding: 1mm 2mm; display: block; }
"""


def render(blocks: list[dict], sheet_id: str, limit: int | None) -> tuple[str, list[dict]]:
    manifest: list[dict] = []
    issued = 0
    parts = [
        "<!doctype html><meta charset='utf-8'>",
        f"<title>Certification sheet {html.escape(sheet_id)}</title>",
        f"<style>{CSS}</style>",
        f"<h1>Power Insight — certification sheet</h1>",
        f"<p class='sheetmeta'>{html.escape(sheet_id)} · derive each value without looking at the engine, "
        f"then enter answers with <code>tools/certify.py --sheet {html.escape(sheet_id)}</code></p>",
    ]

    for block in blocks:
        if limit is not None and issued >= limit:
            break
        case, state = block["case"], block["state"]
        take = block["pending"] if limit is None else block["pending"][: limit - issued]
        if not take:
            continue

        parts.append("<section class='state'>")
        parts.append(
            f"<div class='statehead'><h2>{html.escape(case['title'])}</h2>"
            f"<div class='ids'>{html.escape(case['id'])} / {html.escape(state['id'])}"
            f" &nbsp;·&nbsp; grid price {html.escape(str(state['price']))} EUR/kWh</div></div>"
        )

        # Wiring and readings. No flows, no note: both are the answer.
        rows = []
        for adapter in case["topology"]:
            cfg = adapter.get("config", {})
            bits = [
                f"{label} {fmt_config(cfg[key])}"
                for key, label in CONFIG_LABELS
                if key in cfg
            ]
            reading = state["readings"].get(adapter["uid"])
            rows.append(
                f"<tr><td><b>{html.escape(adapter['uid'])}</b></td>"
                f"<td>{html.escape(adapter['kind'])}</td>"
                f"<td class='num'>{html.escape('—' if reading is None else str(reading))}</td>"
                f"<td>{html.escape('; '.join(bits))}</td></tr>"
            )
        parts.append(
            "<table class='devices'><tr><th>device</th><th>kind</th><th>reading (W)</th>"
            "<th>configuration</th></tr>" + "".join(rows) + "</table>"
        )

        if block["given"]:
            gs = "".join(
                f"<div class='g'>{html.escape(e['property'])} = {html.escape(json.dumps(e['value']))}</div>"
                for e in block["given"]
            )
            parts.append(f"<div class='given'><h3>Given — already certified</h3>{gs}</div>")

        for exp in take:
            prop = exp["property"]
            meta = block_meta = CATALOG_CACHE[prop]
            issued += 1
            pid = f"{case['id']}/{state['id']}/{prop}"
            manifest.append(
                {"n": issued, "case": case["id"], "state": state["id"], "property": prop}
            )
            steps = "".join(f"<li>{html.escape(s)}</li>" for s in meta["worksheet_steps"])
            formula = (
                f"<div class='formula'>{html.escape(meta['formula'])}</div>"
                if meta.get("formula")
                else ""
            )
            note = (
                f"<p class='note'>{html.escape(meta['note'])}</p>" if meta.get("note") else ""
            )
            parts.append(
                f"<div class='problem'>"
                f"<span class='pid'>{issued:02d} · {html.escape(pid)}</span>"
                f"<p class='ptitle'>{html.escape(meta['title'])}</p>"
                f"<p class='def'>{html.escape(meta['definition'])}</p>"
                f"{formula}{note}"
                f"<h3>Steps</h3><ol>{steps}</ol>"
                f"<h3>Answer &nbsp;<span style='font-weight:400;text-transform:none;letter-spacing:0'>"
                f"({html.escape(meta['unit'])})</span></h3>"
                f"{answer_field(meta['answer_shape'], exp['value'], meta['unit'])}"
                f"<div class='working'><span>working</span></div>"
                f"</div>"
            )
        parts.append("</section>")

    return "\n".join(parts), manifest


CATALOG_CACHE: dict = {}


def to_pdf(html_path: pathlib.Path, pdf_path: pathlib.Path) -> bool:
    candidates = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    chrome = next((c for c in candidates if "headless" not in c), None)
    if not chrome:
        return False
    subprocess.run(
        [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            html_path.as_uri(),
        ],
        check=True,
        capture_output=True,
    )
    return pdf_path.exists()


def main() -> int:
    global CATALOG_CACHE
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--count", type=int, default=6, help="problems to issue (default 6)")
    parser.add_argument("--all", action="store_true", help="issue every pending problem")
    parser.add_argument("--case", help="restrict to one case id, e.g. A-003")
    parser.add_argument("--pdf", action="store_true", help="also render a PDF")
    parser.add_argument("--out", default=str(OUT_DIR), help="output directory")
    parser.add_argument("--id", help="sheet id (default: today's date)")
    args = parser.parse_args()

    CATALOG_CACHE = load_catalog()
    blocks = collect(load_cases(), CATALOG_CACHE, args.case)
    total = sum(len(b["pending"]) for b in blocks)
    if not total:
        print("Nothing pending — every catalogued expectation is certified.")
        return 0

    sheet_id = args.id or dt.date.today().isoformat()
    limit = None if args.all else args.count
    document, manifest = render(blocks, sheet_id, limit)

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    html_path = out / f"sheet-{sheet_id}.html"
    html_path.write_text(document)
    (out / f"sheet-{sheet_id}.json").write_text(
        json.dumps({"id": sheet_id, "problems": manifest}, indent=2) + "\n"
    )

    print(f"{len(manifest)} problem(s) issued of {total} pending → {html_path}")
    if args.pdf:
        pdf_path = out / f"sheet-{sheet_id}.pdf"
        if to_pdf(html_path, pdf_path):
            print(f"PDF → {pdf_path}")
        else:
            print("No Chromium found; open the HTML and print from the browser.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
