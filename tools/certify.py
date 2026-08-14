"""Enter hand-derived answers against an issued worksheet and stamp the corpus.

The corpus holds no value this tool did not put there. Slots arrive empty from
``tools/gen_cases.py``, and the only way one gets filled is somebody working it
out from the model and typing it in here — which is why the engine can be
meaningfully asserted against the result afterwards.

The contract this tool exists to enforce: a certification means *a human worked
this out independently and got the same number*. The engine is consulted live,
at the moment you answer, and never before — its answer is not in the case
file to be glimpsed, so blindness is now a property of the data rather than a
discipline this tool has to maintain.

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

Map-valued properties are entered free-form, as ``key = value`` lines. Which
keys belong in the answer is part of what you are deriving — whether a grid
that is importing appears in the export attribution at all, say — so the tool
does not hand you the key set to fill in.

``nothing`` is an answer, and a common one: it derives that the engine should
report no value at all here, and is stored as a literal null. An empty line is
not that — it skips the problem and leaves the slot pending.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.engine.scenario_framework import engine_from_corpus  # noqa: E402

CASES = ROOT / "docs" / "spec" / "cases"
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


#: A derived answer of "nothing" — the model says the engine should report no
#: value here. Stored as a literal JSON null, because expectation values are
#: literal: there is no in-band marker standing in for one.
#:
#: This tool needs its own sentinel only because an empty line at the prompt
#: already means "skip this problem, leave the slot alone", which is a
#: different thing from answering. It never reaches the corpus.
NOTHING = object()


def rat(text: str):
    """Parse an exact rational, a decimal, or an answer of nothing."""
    text = text.strip()
    if text.lower() in ("none", "nothing", "null", "unavailable"):
        return NOTHING
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


def collect_answer(shape: str, unit: str):
    """Prompt for an answer, in the shape the property's answer takes.

    Nothing is pre-filled and no key set is offered, because there is no
    engine answer in the file to derive one from — and because which keys
    belong in a map is itself part of the derivation. A scalar is one number;
    a map is free-form ``key = value`` lines; a nested map is one line per
    sink. Returns nested Fractions, or ``None`` to skip.
    """
    if shape == "scalar":
        raw = ask(f"    answer ({unit}, or `nothing`): ")
        return None if not raw.strip() else rat(raw)

    if shape in ("map_derived_keys", "map_fixed_keys"):
        print(f"    list each entry as `key = value` ({unit}); blank line ends, "
              f"`none` if the answer has no entries")
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

    if shape == "nested_map_fixed_keys":
        print(f"    one line per sink: `sink: source = value, source = value` "
              f"({unit}); blank line ends, `none` if the answer has no entries")
        nested: dict[str, dict[str, Fraction]] = {}
        while True:
            raw = ask("      > ").strip()
            if not raw:
                return nested if nested else None
            if raw.lower() == "none":
                return {}
            sink, _, rest = raw.partition(":")
            if not rest.strip():
                print("      expected `sink: source = value, ...`")
                continue
            row: dict[str, Fraction] = {}
            try:
                for pair in rest.split(","):
                    key, _, val = pair.partition("=")
                    row[key.strip()] = rat(val)
            except (ValueError, ZeroDivisionError):
                print("      could not read that row")
                continue
            nested[sink.strip()] = row

    raise ValueError(f"unknown answer shape {shape!r}")


def matches(mine, actual, unit: str) -> bool:
    """Compare a hand-derived answer against the engine's live answer."""
    if mine is NOTHING or actual is None:
        return mine is NOTHING and actual is None
    if isinstance(actual, dict):
        if not isinstance(mine, dict) or set(mine) != set(actual):
            return False
        return all(matches(mine[k], actual[k], unit) for k in actual)
    if not isinstance(mine, Fraction):
        return False
    return close_enough(mine, Fraction(actual).limit_denominator(1_000_000), unit)


def encode(value):
    """The engine's answer as exact rational strings, in the corpus's shape."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, bool):
        return value
    return str(Fraction(value).limit_denominator(1_000_000))


def store(mine):
    """A hand-derived answer in the corpus's shape.

    Exact rational strings, maps of them, or a literal ``null`` where the
    derived answer is that there is no value.
    """
    if mine is NOTHING:
        return None
    if isinstance(mine, dict):
        return {k: store(v) for k, v in mine.items()}
    return str(mine)


def render_engine(actual) -> str:
    return "nothing" if actual is None else render(encode(actual))


def render(value) -> str:
    return json.dumps(value)


def render_answer(mine) -> str:
    if mine is NOTHING:
        return "nothing"
    if isinstance(mine, Fraction):
        return str(mine)
    if isinstance(mine, dict):
        return json.dumps({k: render_answer(v) for k, v in mine.items()})
    return str(mine)


# ---------------------------------------------------------------------------
# Corpus access
# ---------------------------------------------------------------------------


def load_case(case_id: str) -> tuple[pathlib.Path, dict]:
    path = CASES / f"{case_id}.json"
    return path, json.loads(path.read_text())


def save_case(path: pathlib.Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def find_state(case: dict, state_id: str) -> dict | None:
    for state in case["states"]:
        if state["id"] == state_id:
            return state
    return None


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
    index = json.loads((CASES / "index.json").read_text())["cases"]
    # Wide enough for the longest case id in the corpus, so the ladder's longer
    # names do not shove the columns out of line.
    w = max((len(e["id"]) for e in index), default=17)
    print(f"{'case':{w}s} {'certified':>12s} {'disputed':>9s}")
    for entry in index:
        case = json.loads((CASES / entry["file"]).read_text())
        c_total = c_ver = c_dis = 0
        for state in case["states"]:
            for exp in state["expectations"]:
                c_total += 1
                status = exp["certification"]["status"]
                c_ver += status == "verified"
                c_dis += status == "disputed"
        total, verified, disputed = total + c_total, verified + c_ver, disputed + c_dis
        print(f"{case['id']:{w}s} {f'{c_ver}/{c_total}':>12s} {c_dis:>9d}   {case['title']}")
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
        state = find_state(case, state_id)
        meta = catalog.get(prop)
        if exp is None or state is None or meta is None:
            print(f"  ?? {case_id}/{state_id}/{prop} no longer exists — skipping")
            skipped += 1
            continue
        if exp["certification"]["status"] == "verified":
            print(f"  ✓ {problem['n']:02d} {prop} already certified — skipping")
            continue

        # Asked now, after the problem is on screen and before the answer is
        # typed. It is never written to the case file, so there is nothing in
        # the corpus for a future deriver to read the answer off.
        actual = getattr(engine_from_corpus(case, state), prop)

        print(f"  {problem['n']:02d}  {meta['title']}  [{case_id}/{state_id}/{prop}]")
        try:
            mine = collect_answer(meta["answer_shape"], meta["unit"])
        except (ValueError, ZeroDivisionError) as err:
            print(f"      could not read that ({err}) — skipping\n")
            skipped += 1
            continue

        if mine is None:
            print("      skipped\n")
            skipped += 1
            continue

        if matches(mine, actual, meta["unit"]):
            note = ask("    ✓ agrees. one-line working (optional): ").strip()
            exp["value"] = store(mine)
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
            again = collect_answer(meta["answer_shape"], meta["unit"])
        except (ValueError, ZeroDivisionError):
            again = None

        if again is not None and matches(again, actual, meta["unit"]):
            note = ask("    ✓ agrees. one-line working (optional): ").strip()
            exp["value"] = store(again)
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
        print(f"\n    Recorded as disputed. The engine says: {render_engine(actual)}")
        print("    Yours:", render_answer(standing))
        print("    Neither is assumed right. Work out which, then either fix the")
        print("    engine or re-certify this value.\n")
        # The derived value goes in as the published one. A dispute means the
        # corpus and the engine disagree, and the corpus is the specification —
        # so it states what the model says, not what the code does. What the
        # code says is not recorded here at all: the test recomputes it live,
        # and a stale copy of it in the file would only ever mislead.
        exp["value"] = store(standing)
        exp["certification"] = {
            "status": "disputed",
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
