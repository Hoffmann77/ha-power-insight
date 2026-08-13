"""Enter hand-derived answers against an issued worksheet and stamp the corpus.

The contract this tool exists to enforce: a certification means *a human worked
this out independently and got the same number*. So the engine's value is never
shown before you answer.

On a mismatch it asks you to re-check first, still without revealing anything —
most mismatches are arithmetic slips, and revealing the answer at that point
would turn the exercise into agreeing with the engine. Only once you stand by
your answer does it show what the engine says, and then the disagreement is
*recorded*, not resolved. Deciding whether the engine or the derivation is wrong
is the interesting part, and it is yours.

Usage::

    uv run python tools/certify.py --sheet 2026-08-13
    uv run python tools/certify.py --status

Answers accept exact rationals or decimals: ``1400``, ``-600``, ``8/15``,
``0.533``. Press Enter on a prompt to skip a problem and leave it pending.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import pathlib
import subprocess
import sys
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parent.parent
ANCHORS = ROOT / "docs" / "spec" / "anchors"
CATALOG = ROOT / "docs" / "spec" / "properties.json"
SHEETS = ROOT / "worksheets"

# How close a hand-derived answer has to be, by unit. Shares and ratios are
# written as rounded literals on paper, so three decimals is the bar; money is
# quoted to the cent-per-hour; watts should come out exact.
TOLERANCE = {
    "share": 1e-3,
    "ratio": 1e-3,
    "EUR/h": 1e-4,
    "EUR/kWh": 1e-4,
    "W": 1e-6,
}


def rat(text: str) -> Fraction:
    """Parse an exact rational or a decimal."""
    text = text.strip()
    if "/" in text:
        num, _, den = text.partition("/")
        return Fraction(int(num.strip()), int(den.strip()))
    return Fraction(text)


def close_enough(mine: Fraction, theirs: Fraction, unit: str) -> bool:
    tol = TOLERANCE.get(unit, 1e-6)
    diff = abs(float(mine) - float(theirs))
    if diff <= tol:
        return True
    scale = abs(float(theirs))
    return scale > 1 and diff <= tol * scale


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:  # pragma: no cover - git absent or not a repo
        return "unknown"


def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


# ---------------------------------------------------------------------------
# Collecting an answer, shaped by the property
# ---------------------------------------------------------------------------


def collect_answer(shape: str, value, unit: str):
    """Prompt for an answer in the same shape as the stored value.

    Returns the answer as nested Fractions, or ``None`` to skip.
    """
    if shape == "scalar":
        raw = ask(f"    answer ({unit}): ")
        return None if not raw.strip() else rat(raw)

    if shape == "map_derived_keys":
        print(f"    list each entry as `key = value` ({unit}); blank line ends, "
              f"`none` if there are no entries")
        out: dict[str, Fraction] = {}
        while True:
            raw = ask("      > ").strip()
            if not raw:
                return out if out else None
            if raw.lower() == "none":
                return {}
            key, _, val = raw.partition("=")
            if not val.strip():
                print("      expected `key = value`")
                continue
            out[key.strip()] = rat(val)

    if shape == "map_fixed_keys":
        if not isinstance(value, dict) or not value:
            raw = ask(f"    expected empty; press Enter to confirm, or type `key = value`: ").strip()
            if not raw:
                return {}
            key, _, val = raw.partition("=")
            return {key.strip(): rat(val)}
        out = {}
        for key in value:
            raw = ask(f"      {key} ({unit}): ")
            if not raw.strip():
                return None
            out[key] = rat(raw)
        return out

    if shape == "nested_map_fixed_keys":
        if not isinstance(value, dict) or not value:
            ask("    expected empty; press Enter to confirm: ")
            return {}
        columns: list[str] = []
        for row in value.values():
            for col in row:
                if col not in columns:
                    columns.append(col)
        out = {}
        for sink in value:
            raw = ask(f"      {sink} ({' '.join(columns)}): ")
            if not raw.strip():
                return None
            parts = raw.replace(",", " ").split()
            if len(parts) != len(columns):
                print(f"      expected {len(columns)} values, got {len(parts)}")
                return None
            out[sink] = {col: rat(p) for col, p in zip(columns, parts)}
        return out

    raise ValueError(f"unknown answer shape {shape!r}")


def matches(mine, stored, unit: str) -> bool:
    """Compare a hand answer against the stored value, shape-aware."""
    if isinstance(stored, str):
        return isinstance(mine, Fraction) and close_enough(mine, rat(stored), unit)
    if isinstance(stored, dict):
        if not isinstance(mine, dict) or set(mine) != set(stored):
            return False
        return all(matches(mine[k], stored[k], unit) for k in stored)
    return False


def render(value) -> str:
    return json.dumps(value)


def render_answer(mine) -> str:
    if isinstance(mine, Fraction):
        return str(mine)
    if isinstance(mine, dict):
        return json.dumps({k: render_answer(v) for k, v in mine.items()})
    return str(mine)


# ---------------------------------------------------------------------------
# Corpus access
# ---------------------------------------------------------------------------


def load_case(case_id: str) -> tuple[pathlib.Path, dict]:
    path = ANCHORS / f"{case_id}.json"
    return path, json.loads(path.read_text())


def save_case(path: pathlib.Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def find_expectation(case: dict, state_id: str, prop: str) -> dict | None:
    for state in case["states"]:
        if state["id"] == state_id:
            for exp in state["expectations"]:
                if exp["property"] == prop:
                    return exp
    return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_status() -> int:
    total = verified = disputed = 0
    print(f"{'case':8s} {'certified':>12s} {'disputed':>9s}")
    for path in sorted(ANCHORS.glob("A-*.json")):
        case = json.loads(path.read_text())
        c_total = c_ver = c_dis = 0
        for state in case["states"]:
            for exp in state["expectations"]:
                c_total += 1
                status = exp["certification"]["status"]
                c_ver += status == "verified"
                c_dis += status == "disputed"
        total, verified, disputed = total + c_total, verified + c_ver, disputed + c_dis
        print(f"{case['id']:8s} {f'{c_ver}/{c_total}':>12s} {c_dis:>9d}   {case['title']}")
    pct = 100 * verified / total if total else 0
    print(f"\n{verified} of {total} certified ({pct:.0f}%), {disputed} disputed")
    return 0


def cmd_sheet(sheet_id: str, who: str) -> int:
    manifest_path = SHEETS / f"sheet-{sheet_id}.json"
    if not manifest_path.exists():
        print(f"No manifest at {manifest_path}.", file=sys.stderr)
        print("Issue a sheet first: uv run python tools/worksheet.py", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text())
    catalog = json.loads(CATALOG.read_text())["properties"]
    commit = git_commit()
    today = dt.date.today().isoformat()

    caches: dict[str, tuple[pathlib.Path, dict]] = {}
    certified = skipped = disputed = 0

    print(f"Sheet {sheet_id} — {len(manifest['problems'])} problem(s). "
          f"Enter to skip one; Ctrl-C to stop.\n")

    for problem in manifest["problems"]:
        case_id, state_id, prop = problem["case"], problem["state"], problem["property"]
        if case_id not in caches:
            caches[case_id] = load_case(case_id)
        path, case = caches[case_id]
        exp = find_expectation(case, state_id, prop)
        meta = catalog.get(prop)
        if exp is None or meta is None:
            print(f"  ?? {case_id}/{state_id}/{prop} no longer exists — skipping")
            skipped += 1
            continue
        if exp["certification"]["status"] == "verified":
            print(f"  ✓ {problem['n']:02d} {prop} already certified — skipping")
            continue

        print(f"  {problem['n']:02d}  {meta['title']}  [{case_id}/{state_id}/{prop}]")
        try:
            mine = collect_answer(meta["answer_shape"], exp["value"], meta["unit"])
        except (ValueError, ZeroDivisionError) as err:
            print(f"      could not read that ({err}) — skipping\n")
            skipped += 1
            continue

        if mine is None:
            print("      skipped\n")
            skipped += 1
            continue

        if matches(mine, exp["value"], meta["unit"]):
            note = ask("    ✓ agrees. one-line working (optional): ").strip()
            exp["certification"] = {
                "status": "verified",
                "by": who,
                "date": today,
                "method": "blind",
                "engine_commit": commit,
            }
            if note:
                exp["derivation"] = [{"text": note}]
            save_case(path, case)
            certified += 1
            print()
            continue

        # Mismatch. Re-check before anything is revealed: most are slips, and
        # showing the answer here would turn derivation into agreement.
        print("    ✗ that does not match. Re-check your working and enter again,")
        print("      or press Enter to stand by it and record a disagreement.")
        try:
            again = collect_answer(meta["answer_shape"], exp["value"], meta["unit"])
        except (ValueError, ZeroDivisionError):
            again = None

        if again is not None and matches(again, exp["value"], meta["unit"]):
            note = ask("    ✓ agrees. one-line working (optional): ").strip()
            exp["certification"] = {
                "status": "verified",
                "by": who,
                "date": today,
                "method": "blind",
                "attempts": 2,
                "engine_commit": commit,
            }
            if note:
                exp["derivation"] = [{"text": note}]
            save_case(path, case)
            certified += 1
            print()
            continue

        standing = again if again is not None else mine
        print(f"\n    Recorded as disputed. The engine says: {render(exp['value'])}")
        print("    Yours:", render_answer(standing))
        print("    Neither is assumed right. Work out which, then either fix the")
        print("    engine or re-certify this value.\n")
        exp["certification"] = {
            "status": "disputed",
            "claimed": json.loads(render_answer(standing))
            if isinstance(standing, dict)
            else str(standing),
            "by": who,
            "date": today,
            "engine_commit": commit,
        }
        save_case(path, case)
        disputed += 1

    print(f"\n{certified} certified, {disputed} disputed, {skipped} skipped.")
    if disputed:
        print("Disputed values are recorded in the case files — resolve them before publishing.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sheet", help="sheet id to enter answers for, e.g. 2026-08-13")
    parser.add_argument("--status", action="store_true", help="show certification progress")
    parser.add_argument("--by", default="", help="who is certifying (recorded)")
    args = parser.parse_args()

    if args.status or not args.sheet:
        return cmd_status()
    return cmd_sheet(args.sheet, args.by or "")


if __name__ == "__main__":
    raise SystemExit(main())
