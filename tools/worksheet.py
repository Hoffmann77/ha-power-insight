"""Generate printable certification worksheets from the reference cases.

A worksheet states the problem and withholds the answer. That is the whole
point: a value you derived independently, without the engine's number in front
of you, is evidence. A value you nodded along to is not.

One worksheet is **one snapshot** — one case's topology under one set of
readings. It opens with the wiring, the readings and the configuration, then
works through the pending values a page at a time, in an order where nothing is
asked before the figures it is built on. It closes with a transcription page
you copy your answers onto before typing them into ``tools/certify.py``.

A page is a *derivation*, not a property. Values the catalog groups — gross
power and the production inside it, grid import and export, the three views of
one channel — share a page, because they are one piece of work and splitting
them asked the same question three times.

So four things are deliberately *not* printed:

* **The expectation being derived.** Obviously.
* **The flows between devices.** They are the answer to the provenance
  properties, so the wiring picture shows devices and restrictions only.
* **Any total over the readings.** The supply column's total *is*
  ``gross_power``, which is the first problem on the sheet. Segments yes,
  sums no.
* **The state's ``note``.** Those read like "{bat_a, bat_b} exactly exhaust
  east+west, so the 200 W home load must be served entirely from the grid" —
  which is the conclusion. Good documentation, ruinous exam paper.

What *is* printed: the topology and its static config, the readings, and any
expectation already certified — because a derivation that can lean on trusted
numbers is minutes rather than an evening.

Usage::

    uv run python tools/worksheet.py                       # every pending snapshot
    uv run python tools/worksheet.py --case pv-export      # one case's snapshots
    uv run python tools/worksheet.py --case pv-export --state export_all
    uv run python tools/worksheet.py --pdf                 # also render PDFs

Each snapshot writes ``sheet-<case>-<state>.{html,pdf,json}``. Answers are
entered later against the manifest, so a sheet worked on paper on Tuesday can
be typed up on Friday::

    uv run python tools/certify.py --sheet <case>-<state>
"""

from __future__ import annotations

import argparse
import glob
import html
import json
import os
import pathlib
import re
import subprocess
import sys
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parent.parent
CASES = ROOT / "docs" / "spec" / "cases"
CATALOG = ROOT / "docs" / "spec" / "properties.json"
OUT_DIR = ROOT / "worksheets"

#: The virtual sink. It is not a device and has no sensor: it is whatever the
#: house consumed that nothing measured, which is why it appears on the wiring
#: picture with a blank where every other node carries a reading.
HOME = "home"

#: Page numbers are fixed before anything is rendered, because the dependency
#: strip on each problem page points at the page its inputs were derived on.
PAGE_SNAPSHOT = 1
PAGE_FIRST_PROBLEM = 2

# What a device's energy costs, split from the routing table below because they
# are different questions and the sheet asks them on different pages. The CO2
# intensities are deliberately absent: nothing on the sheet is priced in grams,
# so printing them is a column of noise on every page 1.
PRICE_LABELS = [
    ("has_price_entity", "price entity", None),
    ("lcoe", "LCOE", "EUR/kWh"),
    ("lcos", "LCOS", "EUR/kWh"),
    ("export_compensation", "export comp.", "EUR/kWh"),
    ("correction_factor", "correction", None),
]

# Where a device's energy is allowed to go, and where it may come from.
ROUTING_LABELS = [
    ("exports_power", "may export", None),
    ("charge_from_adapters", "charges from", None),
    ("power_from_adapters", "draws from", None),
]

KIND_LABEL = {
    "grid": "Grid",
    "pv": "PV string",
    "battery": "Battery",
    "consumer": "Consumer",
    HOME: "Home base load",
}

# The diagram's light palette, copied from the website component so a printed
# sheet and the docs page colour the same device the same way.
KIND_COLOR = {
    "grid": "#3d6b9e",
    "pv": "#b3861e",
    "battery": "#b05577",
    "consumer": "#38897c",
    HOME: "#7a8290",
}

# Device glyphs on a -11..11 box, from the website's icon set.
GLYPHS = {
    "grid": (
        '<path d="M-5.5 9 L0 -9 L5.5 9 M-8 -2.5 L8 -2.5 M-6 -6 L6 -6 '
        'M-8 -2.5 L-3 3 M8 -2.5 L3 3" fill="none" stroke-width="1.6"/>'
    ),
    "pv": (
        '<g fill="none" stroke-width="1.6">'
        '<rect x="-9" y="-8" width="18" height="11" rx="1"/>'
        '<path d="M-3 -8 V3 M3 -8 V3 M-9 -2.5 H9 M0 3 V8 M-4 8 H4"/></g>'
    ),
    "battery": (
        '<g fill="none" stroke-width="1.6">'
        '<rect x="-5" y="-6.5" width="10" height="15" rx="1.5"/>'
        '<path d="M-2 -8.5 H2"/>'
        '<path d="M-2.5 5 H2.5 M-2.5 1.5 H2.5" stroke-width="1.4"/></g>'
    ),
    "consumer": (
        '<path d="M2.5 -9 L-6 1.5 L-1 1.5 L-2.5 9 L6 -1.5 L1 -1.5 Z" '
        'fill="currentColor" stroke="none"/>'
    ),
    HOME: (
        '<g fill="none" stroke-width="1.6">'
        '<path d="M-9 0.5 L0 -8 L9 0.5"/>'
        '<path d="M-6.5 -1.5 V8 H6.5 V-1.5"/></g>'
    ),
}

#: How close a hand-derived answer has to be, by unit — certify.py's own table,
#: printed on the sheet so nobody carries a share to eight decimals that will be
#: accepted at three.
TOLERANCE_NOTE = {
    "W": "exact",
    "share": "3 decimals",
    "ratio": "3 decimals",
    "EUR/h": "4 decimals",
    "EUR/kWh": "4 decimals",
}


# ---------------------------------------------------------------------------
# Exact rationals, formatted the way the docs diagram formats them
# ---------------------------------------------------------------------------


def rat(stored: str | int | None) -> Fraction | None:
    """Parse a stored rational — ``"400"``, ``"-600"``, ``"8/15"``."""
    if stored is None:
        return None
    text = str(stored).strip()
    if "/" in text:
        num, _, den = text.partition("/")
        return Fraction(int(num), int(den))
    return Fraction(text)


def fmt_unit(stored, unit: str | None) -> tuple[str, str | None]:
    """One stored scalar in its catalog unit, plus its exact fraction.

    Both forms, for the reason the website gives: the fraction is what someone
    checks a derivation against, the decimal is what they read off the page.
    """
    value = rat(stored)
    if value is None:
        return "—", None
    frac = str(stored) if "/" in str(stored) else None
    if unit == "W":
        text = f"{value} W" if value.denominator == 1 else f"{float(value):.1f} W"
    elif unit in ("share", "ratio"):
        pct = float(value) * 100
        text = f"{pct:g}%"
    elif unit == "EUR/h":
        text = f"{round(float(value), 3):g} €/h"
    elif unit == "EUR/kWh":
        text = f"{float(value):.4f} €/kWh"
    elif unit == "g/kWh":
        text = f"{float(value):g} g/kWh"
    else:
        text = f"{round(float(value), 3):g}"
    return text, frac


def fmt_config(key: str, value, unit: str | None) -> tuple[str, str | None]:
    if isinstance(value, bool):
        return ("yes" if value else "no"), None
    if isinstance(value, list):
        return (", ".join(value) if value else "unrestricted"), None
    return fmt_unit(value, unit)


def humanize(ident: str) -> str:
    text = ident.replace("_", " ").replace("-", " ")
    return text[:1].upper() + text[1:]


# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------


def load_catalog() -> dict:
    return json.loads(CATALOG.read_text())


def load_cases() -> list[dict]:
    """Every case, in the index's order — which is the order they were authored
    in, and reads better than the alphabetical order a glob would give."""
    index = json.loads((CASES / "index.json").read_text())
    return [json.loads((CASES / e["file"]).read_text()) for e in index["cases"]]


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


def problem_order(props: list[str], catalog: dict) -> list[str]:
    """Pending properties in the order they are asked.

    Layer first, dependency rank within it: the layers are the vocabulary the
    rest of the spec uses, and grouping by them makes a long sheet read as four
    stretches rather than one undifferentiated run. That only works because the
    catalog's layers happen to be monotone over its dependencies — which the
    rail below checks rather than assumes, since a future property that depends
    upwards would silently start asking questions out of order.
    """
    rank = dependency_rank(catalog)
    key = lambda p: (catalog[p]["layer"], rank.get(p, 10_000))  # noqa: E731
    for prop in props:
        for dep in catalog[prop]["depends_on"]:
            if dep in catalog and key(dep) >= key(prop):
                raise ValueError(
                    f"{prop} would be asked before its input {dep}: layer "
                    f"{catalog[dep]['layer']} depends on layer {catalog[prop]['layer']}"
                )
    return sorted(props, key=key)


def anchor_of(prop: str, catalog: dict) -> str:
    """The property whose page ``prop`` is asked on — itself, or its group's."""
    return catalog[prop].get("page", prop)


def paginate(props: list[str], catalog: dict) -> list[list[str]]:
    """Group properties into pages, in the order the pages are worked.

    A property that names another in ``page`` is asked on that one's page. That
    is how the catalog says *these are one derivation*: gross power and the
    production inside it, grid import and export, the three views of a channel.
    Splitting those over a page each asked the same question three times and
    made a sheet twice as long as the work in it.
    """
    order = problem_order(props, catalog)
    groups: dict[str, list[str]] = {}
    for prop in order:
        groups.setdefault(anchor_of(prop, catalog), []).append(prop)
    # An anchor whose own slot is already certified still opens its page — the
    # page is named after it either way, and its companions still need asking.
    for anchor in groups:
        if anchor in groups[anchor]:
            groups[anchor].remove(anchor)
            groups[anchor].insert(0, anchor)
    ranked = problem_order(list(groups), catalog)
    return [groups[a] for a in ranked]


def collect(cases: list[dict], catalog: dict, case_id: str | None, state_id: str | None):
    """One worksheet per snapshot that still has something to derive."""
    sheets = []
    for case in cases:
        if case_id and case["id"] != case_id:
            continue
        for state in case["states"]:
            if state_id and state["id"] != state_id:
                continue
            pending, given = [], []
            for exp in state["expectations"]:
                if exp["property"] not in catalog:
                    continue
                # "Given" means somebody has already derived it, whether or
                # not the engine agreed — a disputed value is still a value
                # this snapshot's later derivations may lean on.
                answered = exp["certification"]["status"] in ("verified", "disputed")
                (given if answered else pending).append(exp)
            if not pending:
                continue
            by_prop = {e["property"]: e for e in pending}
            groups = paginate(list(by_prop), catalog)
            sheets.append(
                {
                    "case": case,
                    "state": state,
                    "pages": [[by_prop[p] for p in group] for group in groups],
                    "pending": [by_prop[p] for g in groups for p in g],
                    "given": {e["property"]: e for e in given},
                }
            )
    return sheets

# ---------------------------------------------------------------------------
# Answer fields. The key structure is printed; every number is blank.
# ---------------------------------------------------------------------------


def blank(width: str = "5.5em") -> str:
    return f'<span class="blank" style="min-width:{width}"></span>'


def roster(uids: list[str]) -> list[str]:
    """The candidate keys a map-valued answer may use — not its key set.

    Printing the engine's keys would give away half of several questions:
    whether a battery that may not export appears in the export attribution at
    all is exactly what ``mixed-export-house`` is asking. Printing every device
    in the snapshot gives away nothing — that roster is on page 1 already — and
    turns four anonymous ruled lines into a table you can strike rows out of.

    The home base load is never on it. It has no adapter, so it is never a key
    in any of these maps; what it draws is published by its own properties.
    """
    return list(uids)


def answer_field(meta: dict, uids: list[str]) -> str:
    """Render blanks shaped like the answer, revealing nothing about it.

    Laid out as the docs value ledger lays out a published value — key on the
    left, figure on the right, one hairline per entry, the unit stated once in
    the header — so a number written here and the same number carried onto the
    next page's input strip look alike.

    A map's roster runs in two columns. Six devices stacked in one column cost
    more of the page than the working did, and the roster is a checklist rather
    than something read in order.
    """
    shape, unit = meta["answer_shape"], meta["unit"]
    nested = shape == "nested_map_fixed_keys"

    if shape in ("map_derived_keys", "map_fixed_keys", "nested_map_fixed_keys"):
        rows = "".join(
            f'<div class="arow"><i class="akey">{esc(uid)}</i>{blank()}</div>'
            for uid in roster(uids)
        )
        hint = (
            "one row per candidate sink, as source = value, source = value"
            if nested
            else "strike out the rows that do not belong"
        )
        body = f'<div class="agrid{" wide" if nested else ""}">{rows}</div>'
    else:
        hint = ""
        body = f'<div class="arow"><i class="akey">=</i>{blank()}</div>'

    head = (
        '<div class="ahead"><span>Answer</span>'
        + (f'<span class="ahint">{esc(hint)}</span>' if hint else "")
        + f'<span class="aunit">{esc(unit)}</span></div>'
    )
    return f'<div class="answer">{head}{body}</div>'


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

CSS = """
@page { size: A4; margin: 13mm 12mm 10mm; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font: 10.5pt/1.45 "Helvetica Neue", Helvetica, Arial, sans-serif;
  color: #24292f;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
code { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }

/* One .page is one printed side: fixed height, column layout, and whichever
   child is marked .grow eats the slack. That is the whole point of a page per
   derivation — the working space is however much of the sheet the questions
   did not need. */
.page { height: 272mm; display: flex; flex-direction: column; page-break-after: always; }
.page:last-child { page-break-after: auto; }
.grow { flex: 1 1 auto; min-height: 0; }

.crumb {
  display: flex; justify-content: space-between; align-items: baseline;
  font: 8pt ui-monospace, Menlo, monospace; color: #6a737d;
  border-bottom: 0.5pt solid #d8dde3; padding-bottom: 1.5mm; margin-bottom: 4mm;
  letter-spacing: .04em;
}
.crumb .layer { text-transform: uppercase; letter-spacing: .1em; }
.foot {
  margin-top: 3mm; padding-top: 1.5mm; border-top: 0.5pt solid #d8dde3;
  font: 7.5pt ui-monospace, Menlo, monospace; color: #8b949e;
  display: flex; justify-content: space-between;
}

h1 { font-size: 16pt; margin: 0 0 1.5mm; letter-spacing: -.01em; }
h2 { font-size: 13pt; margin: 0 0 2mm; }
.sub { font: 9pt ui-monospace, Menlo, monospace; color: #6a737d; margin: 0 0 6mm; }
.shead { font-size: 8pt; letter-spacing: .1em; text-transform: uppercase;
         color: #6a737d; margin: 0 0 2mm; }

/* ---- page 1: the snapshot ------------------------------------------- */
.diag { display: flex; gap: 0; }
.col { flex: 1 1 0; min-width: 0; }
.colhead { font: 8pt ui-monospace, Menlo, monospace; letter-spacing: .12em;
           color: #6a737d; text-align: center; margin: 0 0 3mm; }
.spine { width: 22mm; flex: none; position: relative; }
.spine::before {
  content: ""; position: absolute; left: 50%; top: 6mm; bottom: 3mm;
  border-left: 0.8pt dashed #c3c9d1;
}
.withheld { text-align: center; font-size: 7.5pt; color: #9aa1ab;
            margin: 1mm 0 0; letter-spacing: .03em; }
.card {
  border: 0.8pt solid #d8dde3; border-left: 2.2pt solid var(--c);
  border-radius: 1.2mm; padding: 3mm 3mm; margin-bottom: 3.5mm;
  display: grid; grid-template-columns: 9mm 1fr auto; column-gap: 2.5mm;
  align-items: center;
}
.card.virt { border-style: dashed; border-left-style: solid; }
.card .gly { width: 8mm; height: 8mm; grid-row: span 2; color: var(--c); }
.card .uid { font: 600 11.5pt ui-monospace, Menlo, monospace; }
.card .kind { font-size: 8pt; color: #6a737d; }
.card .read { font: 700 14pt ui-monospace, Menlo, monospace; text-align: right;
              white-space: nowrap; }
.card .read.na { color: #c77e12; font-size: 9.5pt; font-weight: 400; }
.card .role { grid-column: 2 / 4; font-size: 8pt; color: #6a737d; margin-top: .8mm; }
.band { margin-top: 2mm; }
.bandrow { display: grid; grid-template-columns: repeat(2, 1fr); column-gap: 22mm; }
.bandrow .card { opacity: .85; }

.tables > div + div { margin-top: 5mm; }
table.cfg { width: 100%; border-collapse: collapse; font-size: 8.5pt; }
table.cfg th, table.cfg td { border-bottom: 0.5pt solid #e6e9ee; padding: 1.6mm 2mm;
                             text-align: left; vertical-align: top; }
table.cfg thead th { background: #f6f8fa; border-bottom: 0.8pt solid #d8dde3;
                     font-weight: 600; color: #444d56; white-space: nowrap; }
table.cfg td.num, table.cfg th.num { text-align: right;
                                     font-family: ui-monospace, Menlo, monospace;
                                     white-space: nowrap; }
table.cfg td.uid { font-family: ui-monospace, Menlo, monospace; font-weight: 600;
                   white-space: nowrap; }
.frac { color: #8b949e; font-size: 7.5pt; margin-left: .6em; }
.tariffline { font-size: 9.5pt; margin: 0 0 2.5mm; }
.tariffline b { font-family: ui-monospace, Menlo, monospace; }

.given { border: 0.5pt solid #cfd6dd; background: #f6f8fa; border-radius: 1.2mm;
         padding: 2.5mm 3mm; margin-top: 5mm; font-size: 9pt; }
.given .g { font-family: ui-monospace, Menlo, monospace; }

.legend { display: flex; gap: 5mm; margin-top: 5mm; }
.legend > div { flex: 1 1 0; border: 0.5pt solid #d8dde3; border-radius: 1.2mm;
                padding: 2.5mm 3mm; font-size: 8.5pt; }
.legend ul { margin: 0; padding-left: 4mm; }
.legend li { margin-bottom: 1mm; }
.legend dl { margin: 0; display: grid; grid-template-columns: auto 1fr;
             gap: .6mm 3mm; font-size: 8.5pt; }
.legend dt { font-family: ui-monospace, Menlo, monospace; }
.legend dd { margin: 0; color: #444d56; }

/* ---- derivation pages ------------------------------------------------- */
.ptitle { font-size: 14pt; font-weight: 700; margin: 0 0 3mm; }
.block { margin-bottom: 4mm; }
.block + .block { border-top: 0.5pt solid #e6e9ee; padding-top: 3mm; }
.bhead { display: flex; align-items: baseline; gap: 2.5mm; margin: 0 0 1.5mm;
         flex-wrap: wrap; }
.bhead .bname { font-size: 11pt; font-weight: 700; }
.pname { font: 9pt ui-monospace, Menlo, monospace; color: #24292f;
         background: #f0f2f5; padding: .6mm 1.6mm; border-radius: .8mm; }
.sensor { font-size: 7.5pt; color: #8b949e; }
.def { font-size: 9pt; margin: 0 0 2mm; }
.formula { font: 8.5pt ui-monospace, Menlo, monospace; background: #f6f8fa;
           border-left: 2pt solid #d8dde3; padding: 1.8mm 2.5mm; margin: 0 0 2mm;
           word-break: break-word; }
.note { font-size: 8pt; font-style: italic; color: #57606a;
        border-left: 1.5pt solid #d8dde3; padding-left: 2.5mm; margin: 0 0 2mm; }
.inputs { border: 0.5pt solid #d8dde3; border-radius: 1.2mm; padding: 2mm 3mm;
          margin: 0 0 4mm; }
.inputs .irow { display: flex; align-items: baseline; gap: 2.5mm;
                font-size: 9pt; padding: .8mm 0; }
.inputs .iname { flex: none; font-family: ui-monospace, Menlo, monospace;
                 font-size: 8.5pt; }
.inputs .ititle { flex: 1 1 auto; font-size: 8pt; color: #8b949e; }
.inputs .ival { font-family: ui-monospace, Menlo, monospace; white-space: nowrap;
                min-width: 7em; text-align: right; }
.inputs .blank { min-width: 7em; }
.inputs .from { flex: none; width: 13mm; text-align: right;
                font: 7.5pt ui-monospace, Menlo, monospace; color: #8b949e;
                white-space: nowrap; }
.inputs .none { font-size: 8.5pt; color: #6a737d; margin: 0; }
ol.steps { margin: 0 0 2.5mm; padding-left: 5mm; font-size: 8.5pt; }
ol.steps li { margin-bottom: .8mm; }

/* The answer, laid out like a published value: label, rule, unit up top. */
.answer { border: 0.6pt solid #c3c9d1; border-radius: 1.2mm; overflow: hidden; }
.ahead { display: flex; justify-content: space-between; align-items: baseline;
         background: #f0f2f5; border-bottom: 0.5pt solid #d8dde3;
         padding: 1.2mm 3mm; font-size: 7.5pt; letter-spacing: .1em;
         text-transform: uppercase; color: #57606a; }
.ahead .aunit { letter-spacing: 0; text-transform: none; font-size: 8pt;
                font-family: ui-monospace, Menlo, monospace; }
.ahead .ahint { flex: 1 1 auto; text-align: center; letter-spacing: 0;
                text-transform: none; font-size: 7.5pt; color: #8b949e; }
.agrid { display: grid; grid-template-columns: 1fr 1fr; column-gap: 6mm;
         padding: 1.5mm 3mm; }
.agrid.wide { grid-template-columns: 1fr; }
.arow { display: flex; align-items: baseline; gap: 3mm; padding: 1.6mm 0;
        font-family: ui-monospace, Menlo, monospace; font-size: 9.5pt; }
.answer > .arow { padding: 2mm 3mm; }
.answer > .arow .akey { min-width: 1.5em; }
.arow .blank { flex: 1 1 auto; }
.akey { flex: none; min-width: 5.5em; font-style: normal; color: #57606a; }
.blank { display: inline-block; border-bottom: 0.8pt solid #24292f; height: 1.2em; }
.work { border: 0.5pt dashed #c3c9d1; border-radius: 1.2mm; margin-top: 3mm;
        position: relative; min-height: 18mm;
        background-image: repeating-linear-gradient(
          to bottom, #f0f3f6 0 0.2mm, transparent 0.2mm 7mm); }
.work span { position: absolute; top: 1mm; right: 2mm; font-size: 7pt;
             color: #aab1b9; letter-spacing: .08em; text-transform: uppercase; }

/* A page carrying three or four derivations tightens rather than overflowing. */
.dense .ptitle, .denser .ptitle { font-size: 12.5pt; margin-bottom: 2mm; }
.dense .block, .denser .block { margin-bottom: 2.5mm; }
.dense .block + .block { padding-top: 2mm; }
.denser .block { margin-bottom: 1.8mm; }
.denser .block + .block { padding-top: 1.5mm; }
.dense .def, .denser .def { font-size: 8.5pt; margin-bottom: 1.5mm; }
.dense .formula, .denser .formula { font-size: 8pt; padding: 1.4mm 2mm;
                                    margin-bottom: 1.5mm; }
.dense ol.steps, .denser ol.steps { font-size: 8pt; margin-bottom: 2mm; }
.dense .note, .denser .note { font-size: 7.5pt; margin-bottom: 1.5mm; }
.dense .bhead, .denser .bhead { margin-bottom: 1mm; }
.dense .bname, .denser .bname { font-size: 10pt; }
.dense .arow, .denser .arow { padding: 1.2mm 0; font-size: 9pt; }
.denser .arow { padding: 0.9mm 0; }
.dense .inputs, .denser .inputs { margin-bottom: 2.5mm; padding: 1.5mm 3mm; }
.dense .inputs .irow, .denser .inputs .irow { padding: .4mm 0; font-size: 8.5pt; }
.dense .agrid, .denser .agrid { padding: 1mm 3mm; }
.dense .ahead, .denser .ahead { padding: .9mm 3mm; }
.denser .work { min-height: 14mm; }

/* ---- transcription --------------------------------------------------- */
table.tx { width: 100%; border-collapse: collapse; font-size: 8.5pt; }
table.tx th, table.tx td { border-bottom: 0.5pt solid #e6e9ee; padding: 1.35mm 2mm;
                           text-align: left; }
table.tx thead th { background: #f6f8fa; border-bottom: 0.8pt solid #d8dde3;
                    font-size: 7.5pt; letter-spacing: .06em; text-transform: uppercase;
                    color: #444d56; }
table.tx td.p { font: 7.5pt ui-monospace, Menlo, monospace; color: #8b949e;
                width: 8mm; }
table.tx td.n { font: 7.5pt ui-monospace, Menlo, monospace; }
table.tx td.v { border-bottom: 0.8pt solid #24292f; width: 26mm; }
table.tx td.ref { width: 26mm; font: 7pt ui-monospace, Menlo, monospace;
                  color: #8b949e; white-space: nowrap; }
.txcols { display: flex; gap: 6mm; align-items: flex-start; }
.txcols > table { flex: 1 1 0; min-width: 0; }
table.tx tr.lay td { background: #f6f8fa; font-size: 7.5pt; letter-spacing: .08em;
                     text-transform: uppercase; color: #6a737d; }
"""


def esc(text) -> str:
    return html.escape(str(text))


def device_card(uid: str, kind: str, reading, role: str, virtual: bool = False) -> str:
    text, _ = fmt_unit(reading, "W")
    if virtual:
        value = f'<span class="read na">{blank("4.5em")}</span>'
    elif reading is None:
        value = '<span class="read na">sensor unavailable</span>'
    else:
        value = f'<span class="read">{esc(text)}</span>'
    return (
        f'<div class="card{" virt" if virtual else ""}" style="--c:{KIND_COLOR[kind]}">'
        f'<svg class="gly" viewBox="-11 -11 22 22" stroke="currentColor" '
        f'stroke-linecap="round" stroke-linejoin="round">{GLYPHS[kind]}</svg>'
        f'<span class="uid">{esc(uid)}</span>{value}'
        f'<span class="kind">{esc(KIND_LABEL[kind])}</span>'
        f'<span class="role">{esc(role)}</span></div>'
    )


def role_text(kind: str, reading: Fraction | None) -> str:
    """What the sign of a reading means for this kind of device.

    Nothing derived here: the reading is printed alongside, so naming its sign
    only saves the reader translating a convention they will otherwise have to
    keep in their head for thirty pages.
    """
    if reading is None:
        return "unavailable — this snapshot has no value for it"
    if reading == 0:
        return "idle — neither source nor sink"
    positive = reading > 0
    if kind == "grid":
        return "importing → source" if positive else "exporting → restricted sink"
    if kind == "pv":
        return "producing → source" if positive else "standby draw → sink"
    if kind == "battery":
        return "discharging → source" if positive else "charging → sink"
    return "feeding → source" if positive else "load → sink"


def crumb(left: str, middle: str, right: str) -> str:
    return (
        f'<div class="crumb"><span class="layer">{esc(left)}</span>'
        f"<span>{esc(middle)}</span><span>{esc(right)}</span></div>"
    )


def foot(sheet_id: str, page: int, total: int) -> str:
    return (
        f'<div class="foot"><span>{esc(sheet_id)}</span>'
        f"<span>page {page} of {total}</span></div>"
    )


def given_text(value, unit: str) -> str:
    """A certified value, as it reads on a sheet.

    A certified null is not an empty slot: it is somebody having derived that
    the engine should publish no value at all here. It prints as *nothing*,
    which is also the word ``certify.py`` accepts for it — JSON's ``null``
    reads as an absence, which is the opposite of what it means.
    """
    if value is None:
        return "nothing"
    if isinstance(value, dict):
        return json.dumps(value)
    text, frac = fmt_unit(value, unit)
    return f"{text} = {frac}" if frac else text


def config_table(topology: list[dict], keys: list[tuple], caption: str) -> str:
    """One table over the topology, for the config keys it actually uses."""
    used = [
        (key, label, unit)
        for key, label, unit in keys
        if any(key in a.get("config", {}) for a in topology)
    ]
    if not used:
        return ""
    head = "".join(
        f'<th class="{"num" if unit else ""}">{esc(label)}</th>' for _, label, unit in used
    )
    rows = []
    for adapter in topology:
        cfg = adapter.get("config", {})
        if not any(key in cfg for key, _, _ in used):
            continue
        cells = []
        for key, _, unit in used:
            if key not in cfg:
                cells.append(f'<td class="{"num" if unit else ""}">·</td>')
                continue
            text, frac = fmt_config(key, cfg[key], unit)
            extra = f'<span class="frac">= {esc(frac)}</span>' if frac else ""
            cells.append(f'<td class="{"num" if unit else ""}">{esc(text)}{extra}</td>')
        rows.append(f'<tr><td class="uid">{esc(adapter["uid"])}</td>{"".join(cells)}</tr>')
    if not rows:
        return ""
    return (
        f'<p class="shead">{esc(caption)}</p>'
        f'<table class="cfg"><thead><tr><th>device</th>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def render_snapshot_page(sheet: dict, props: dict, sheet_id: str, total: int) -> str:
    """Page 1 — the wiring and the readings, and nothing derived from them.

    The devices sit in two columns the way they do on the docs diagram, but the
    flows between them are not drawn and neither column carries a total: the
    supply total is ``gross_power``, which is the first thing the sheet asks.
    """
    case, state = sheet["case"], sheet["state"]
    sources, sinks, neither = [], [], []
    idle = unavailable = False
    for adapter in case["topology"]:
        uid, kind = adapter["uid"], adapter["kind"]
        reading = rat(state["readings"].get(uid))
        card = device_card(uid, kind, state["readings"].get(uid), role_text(kind, reading))
        if reading is None:
            unavailable = True
            neither.append(card)
        elif reading > 0:
            sources.append(card)
        elif reading < 0:
            sinks.append(card)
        else:
            # Every device keeps its card, whichever band it lands in: the page
            # is the topology, and a device that dropped off it because it read
            # zero is one the deriver has to remember unaided.
            idle = True
            neither.append(card)

    # The home base load is a sink on every snapshot, and its size is a derived
    # property in its own right — hence a card with a blank where the others
    # carry a reading.
    sinks.append(
        device_card(HOME, HOME, None, "unmetered remainder — derive it", virtual=True)
    )

    parts = [
        '<section class="page">',
        crumb("the snapshot", f"{case['id']} / {state['id']}", "readings — given"),
        f"<h1>{esc(case['title'])}</h1>",
        f'<p class="sub">{esc(case["id"])} / {esc(state["id"])} · '
        f"{len(sheet['pending'])} values over {len(sheet['pages'])} pages</p>",
        '<div class="diag">',
        '<div class="col"><p class="colhead">SOURCES</p>'
        + ("".join(sources) or '<div class="card">No source this snapshot.</div>')
        + "</div>",
        '<div class="spine"></div>',
        '<div class="col"><p class="colhead">SINKS</p>' + "".join(sinks) + "</div>",
        "</div>",
    ]

    if neither:
        caveats = []
        if idle:
            caveats.append("A reading of exactly zero is neither a source nor a sink")
        if unavailable:
            caveats.append(
                "no reading at all is not a reading of zero, and whether it makes "
                "a value unavailable or merely absent is part of what several of "
                "these properties decide"
            )
        parts.append(
            '<div class="band"><p class="colhead">NEITHER</p>'
            f'<div class="bandrow">{"".join(neither)}</div>'
            f'<p class="withheld">{esc("; ".join(caveats))}.</p></div>'
        )

    parts.append(
        '<p class="withheld">Flows between these devices are not drawn — '
        "which source served which sink is what you are deriving.</p>"
    )
    parts.append('<div class="grow"></div>')

    # Two tables, not one: what energy costs is a different question from where
    # it is allowed to go, and the sheet asks them on different pages.
    price_text, price_frac = fmt_unit(state["price"], "EUR/kWh")
    parts.append(
        '<p class="tariffline">Grid price '
        f"<b>{esc(price_text)}</b>"
        + (f'<span class="frac">= {esc(price_frac)}</span>' if price_frac else "")
        + " · the tariff every avoided cost is priced against.</p>"
    )
    parts.append('<div class="tables">')
    parts.append(
        "<div>"
        + config_table(case["topology"], PRICE_LABELS, "Tariffs — what this device's energy costs")
        + "</div>"
    )
    parts.append(
        "<div>"
        + config_table(
            case["topology"], ROUTING_LABELS, "Routing — where its power may come from and go"
        )
        + "</div>"
    )
    parts.append("</div>")

    if sheet["given"]:
        entries = "".join(
            f'<div class="g">{esc(prop)} = '
            f"{esc(given_text(exp['value'], props[prop]['unit']))}</div>"
            for prop, exp in sheet["given"].items()
        )
        parts.append(
            '<div class="given"><p class="shead">Given — already certified</p>'
            f"{entries}</div>"
        )

    units = sorted({props[e["property"]]["unit"] for e in sheet["pending"]})
    tolerances = "".join(
        f"<dt>{esc(unit)}</dt><dd>{esc(TOLERANCE_NOTE.get(unit, 'exact'))}</dd>"
        for unit in units
    )
    parts.append(
        '<div class="legend">'
        "<div><p class='shead'>Sign convention</p><ul>"
        "<li><b>Grid</b> — positive imports, negative exports.</li>"
        "<li><b>PV and battery</b> — positive produces or discharges, negative "
        "draws standby or charges.</li>"
        "<li><b>Consumer</b> — negative is a load.</li>"
        "<li>Exactly zero is idle; no reading at all is not zero.</li></ul></div>"
        "<div><p class='shead'>Recording an answer</p><ul>"
        "<li>Exact rationals are welcome — <code>8/15</code> beats "
        "<code>0.533</code>.</li>"
        "<li><b>nothing</b> is an answer: the engine should publish no value "
        "here. It is not zero.</li>"
        "<li>Copy each result onto the last page as you go.</li></ul></div>"
        f"<div><p class='shead'>Accepted precision</p><dl>{tolerances}</dl></div>"
        "</div>"
    )
    parts.append(foot(sheet_id, PAGE_SNAPSHOT, total))
    parts.append("</section>")
    return "".join(parts)


def input_strip(group: list[str], props: dict, sheet: dict, pages: dict) -> str:
    """The values this page's derivations are built on, and where they live.

    Certified inputs arrive filled in; the rest point at the page you derived
    them on. Carrying a value forward was the main reason to flip back through
    a sheet, and this makes it a glance. Inputs derived on this very page are
    left out — they are a few centimetres up.
    """
    rows = []
    seen = set()
    for prop in group:
        for dep in props[prop]["depends_on"]:
            if dep in seen or dep in group or dep not in props:
                continue
            seen.add(dep)
            given = sheet["given"].get(dep)
            if given is not None and not isinstance(given["value"], dict):
                value = f'<span class="ival">{esc(given_text(given["value"], props[dep]["unit"]))}</span>'
                source = "given, p.1"
            elif given is not None:
                value = '<span class="ival">see p.1</span>'
                source = "given, p.1"
            else:
                value = blank("7em")
                source = f"your p.{pages[dep]}" if dep in pages else ""
            rows.append(
                f'<div class="irow"><span class="iname">{esc(dep)}</span>'
                f'<span class="ititle">{esc(props[dep]["title"])}</span>{value}'
                f'<span class="from">{esc(source)}</span></div>'
            )
    body = "".join(rows) or (
        '<p class="none">None derived — this page comes straight off the '
        "readings and the configuration on page 1.</p>"
    )
    return f'<div class="inputs"><p class="shead">Inputs</p>{body}</div>'


def render_page(
    group: list[dict],
    sheet: dict,
    sheet_id: str,
    catalog: dict,
    layers: dict,
    pages: dict,
    page: int,
    total: int,
    uids: list[str],
) -> str:
    """One page: every property the catalog groups onto it, then the working."""
    props = catalog["properties"]
    names = [exp["property"] for exp in group]
    # The page is named after the property that anchors it, even on the day
    # that one is already certified and only its companions are still pending.
    anchor = props[anchor_of(names[0], props)]
    layer = anchor["layer"]
    title = anchor.get("page_title", anchor["title"])

    blocks = []
    seen_notes: set[str] = set()
    for name in names:
        meta = props[name]
        sensor = (
            f'<span class="sensor">sensor: {esc(", ".join(meta["sensors"]))}</span>'
            if meta.get("sensors")
            else '<span class="sensor">no sensor of its own — an input to the '
            "values it shares this page with</span>"
        )
        steps = "".join(f"<li>{esc(s)}</li>" for s in meta["worksheet_steps"])
        # The three views of a channel carry the same caveat. Printing it three
        # times costs a third of the working space and reads as an oversight.
        note = meta.get("note")
        if note in seen_notes:
            note = None
        elif note:
            seen_notes.add(note)
        blocks.append(
            '<div class="block">'
            f'<div class="bhead"><span class="bname">{esc(meta["title"])}</span>'
            f'<span class="pname">{esc(name)}</span>{sensor}</div>'
            f'<p class="def">{esc(meta["definition"])}</p>'
            + (
                f'<div class="formula">{esc(meta["formula"])}</div>'
                if meta.get("formula")
                else ""
            )
            + (f'<ol class="steps">{steps}</ol>' if steps else "")
            + (f'<p class="note">{esc(note)}</p>' if note else "")
            + answer_field(dict(meta, property=name), uids)
            + "</div>"
        )

    # Typography tightens as a page fills. Every page is one sheet — the page
    # numbers on the input strips say so — so a page that would overflow has to
    # give somewhere, and giving a point of leading is better than giving the
    # working space or splitting a derivation across a fold.
    density = "" if len(names) < 3 else " dense" if len(names) == 3 else " denser"
    return "".join(
        [
            f'<section class="page{density}">',
            crumb(
                f"layer {layer} · {layers.get(str(layer), '')}",
                f"{sheet['case']['id']} / {sheet['state']['id']}",
                f"{len(names)} value{'s' if len(names) > 1 else ''}",
            ),
            f'<p class="ptitle">{esc(title)}</p>',
            input_strip(names, props, sheet, pages),
            "".join(blocks),
            '<div class="work grow"><span>working</span></div>',
            foot(sheet_id, page, total),
            "</section>",
        ]
    )


def render_transcription_page(
    sheet: dict, sheet_id: str, catalog: dict, layers: dict, pages: dict, total: int
) -> str:
    """The last page: every answer in one column, ready to be typed in.

    Two tables side by side rather than one long one — seventy values do not
    fit down a single A4 page, and a transcription sheet that runs onto a
    second page stops being the one place the snapshot is visible at once.
    """
    props = catalog["properties"]
    rows = []
    layer = None
    for exp in sheet["pending"]:
        prop = exp["property"]
        if props[prop]["layer"] != layer:
            layer = props[prop]["layer"]
            rows.append(
                f'<tr class="lay"><td colspan="3">{layer} · '
                f'{esc(layers.get(str(layer), ""))}</td></tr>'
            )
        # A map does not fit on a line and pretending otherwise would invite a
        # half-copied answer. It stays on its own page and gets typed in from
        # there; the column is for the scalars, where a value that contradicts
        # one above it is the whole reason this page exists.
        value = (
            '<td class="v"></td>'
            if props[prop]["answer_shape"] == "scalar"
            else f'<td class="ref">read off p.{pages[prop]}</td>'
        )
        rows.append(
            f'<tr><td class="p">p.{pages[prop]}</td>'
            f'<td class="n">{esc(prop)}</td>{value}</tr>'
        )

    half = (len(rows) + 1) // 2
    # Never start a column on a layer heading that belongs to the rows above it.
    if half < len(rows) and 'class="lay"' in rows[half - 1]:
        half -= 1
    head = '<thead><tr><th>page</th><th>property</th><th>value</th></tr></thead>'
    tables = "".join(
        f'<table class="tx">{head}<tbody>{"".join(part)}</tbody></table>'
        for part in (rows[:half], rows[half:])
        if part
    )
    return "".join(
        [
            '<section class="page">',
            crumb("transcription", f"{sheet['case']['id']} / {sheet['state']['id']}", ""),
            "<h2>Answers</h2>",
            '<p class="sub">Copy each result here as you finish its page, then '
            f"type this page in with <code>tools/certify.py --sheet "
            f"{esc(sheet_id)}</code>.</p>",
            f'<div class="txcols">{tables}</div>',
            '<div class="grow"></div>',
            foot(sheet_id, total, total),
            "</section>",
        ]
    )


def render(sheet: dict, catalog: dict) -> tuple[str, str, dict]:
    """One snapshot as one document, plus the manifest certify.py replays."""
    case, state = sheet["case"], sheet["state"]
    sheet_id = f"{case['id']}-{state['id']}"
    layers = catalog.get("layers", {})
    uids = [a["uid"] for a in case["topology"]]

    pages = {
        exp["property"]: PAGE_FIRST_PROBLEM + i
        for i, group in enumerate(sheet["pages"])
        for exp in group
    }
    # Snapshot, one page per group, transcription last — so the last page
    # number and the page count are the same number.
    total = PAGE_FIRST_PROBLEM + len(sheet["pages"])

    parts = [
        "<!doctype html><meta charset='utf-8'>",
        f"<title>Certification sheet {esc(sheet_id)}</title>",
        f"<style>{CSS}</style>",
        render_snapshot_page(sheet, catalog["properties"], sheet_id, total),
    ]
    manifest = []
    n = 0
    for i, group in enumerate(sheet["pages"]):
        page = PAGE_FIRST_PROBLEM + i
        parts.append(
            render_page(
                group, sheet, sheet_id, catalog, layers, pages, page, total, uids
            )
        )
        for exp in group:
            n += 1
            manifest.append(
                {
                    "n": n,
                    "case": case["id"],
                    "state": state["id"],
                    "property": exp["property"],
                    "page": page,
                }
            )
    parts.append(
        render_transcription_page(sheet, sheet_id, catalog, layers, pages, total)
    )

    return (
        sheet_id,
        "\n".join(parts),
        {"id": sheet_id, "case": case["id"], "state": state["id"], "problems": manifest},
    )

# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def find_chrome() -> str | None:
    """Any Chromium that can print to PDF — local, CI runner, or developer box."""
    explicit = os.environ.get("CHROME_PATH")
    if explicit and pathlib.Path(explicit).exists():
        return explicit
    import shutil

    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    for pattern in (
        "/opt/pw-browsers/chromium-*/chrome-linux/chrome",
        "/opt/pw-browsers/chromium/chrome",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ):
        for candidate in sorted(glob.glob(pattern)):
            if "headless" not in candidate:
                return candidate
    return None


def to_pdf(chrome: str, html_path: pathlib.Path, pdf_path: pathlib.Path) -> bool:
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


def pdf_pages(pdf_path: pathlib.Path) -> int:
    """Sheets in a rendered PDF, or 0 if they cannot be counted.

    The check this exists for: every page of a worksheet is one printed side,
    and the page numbers on the input strips are computed before anything is
    rendered. A page that grows past the paper takes the numbering with it, and
    it does so quietly — the sheet still prints, it just stops pointing at the
    right pages. Counting what came out is the cheapest way to be told.
    """
    try:
        blob = pdf_path.read_bytes()
    except OSError:
        return 0
    return len(re.findall(rb"/Type\s*/Page[^s]", blob))


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--case", help="restrict to one case id, e.g. group-captivity")
    parser.add_argument("--state", help="restrict to one snapshot id within the case")
    parser.add_argument("--pdf", action="store_true", help="also render a PDF per sheet")
    parser.add_argument("--out", default=str(OUT_DIR), help="output directory")
    args = parser.parse_args()

    catalog = load_catalog()
    sheets = collect(load_cases(), catalog["properties"], args.case, args.state)
    if not sheets:
        print("Nothing pending — every catalogued expectation is certified.")
        return 0

    chrome = find_chrome() if args.pdf else None
    if args.pdf and not chrome:
        print("No Chromium found; open the HTML and print from the browser.", file=sys.stderr)

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for sheet in sheets:
        sheet_id, document, manifest = render(sheet, catalog)
        html_path = out / f"sheet-{sheet_id}.html"
        html_path.write_text(document)
        (out / f"sheet-{sheet_id}.json").write_text(json.dumps(manifest, indent=2) + "\n")
        pages = PAGE_FIRST_PROBLEM + len(sheet["pages"])
        line = (
            f"{sheet_id}: {len(manifest['problems'])} value(s) over "
            f"{len(sheet['pages'])} derivation pages, {pages} pages total"
        )
        if chrome and to_pdf(chrome, html_path, out / f"sheet-{sheet_id}.pdf"):
            line += " → pdf"
            printed = pdf_pages(out / f"sheet-{sheet_id}.pdf")
            if printed and printed != pages:
                line += (
                    f"  ** {printed} sheets printed, not {pages}: a page has "
                    f"outgrown the paper and the page references are now wrong **"
                )
        print(line)

    print(f"\n{len(sheets)} worksheet(s) in {out}")
    print("Enter answers with: uv run python tools/certify.py --sheet <case>-<state>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
