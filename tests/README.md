# Test layout

Tests are split into **two tiers, one directory per dependency group**. Each
tier maps to CI — the engine tier as one job per suite (`manual`, `automatic`,
`frozen`, `docs` for `reference/`, and `other` for the rest), the integration
tier as one job — and every tier is auto-discovered by directory: adding a
file, or a new engine directory, needs no CI change.

| Tier          | Directory        | Home Assistant | Network | How it loads the code                          |
| ------------- | ---------------- | -------------- | ------- | ---------------------------------------------- |
| Engine        | `engine/`        | No             | No      | imports `power_insight.py` via `importlib`     |
| Integration   | `integration/`   | Yes            | No      | loads the component through `pytest-homeassistant-custom-component` |

Both tiers are deterministic and PR-gating. This integration talks to no
external service, so — unlike a data-source integration — there is no live
network tier or golden-reference tier.

## Engine tier (`engine/`)

Pure-Python tests for the `PowerInsight` calculation engine. They import
`custom_components/power_insight/power_insight.py` directly via `importlib`,
so they need **no Home Assistant** and run in a few seconds.

Every hand-written home in the tier is a **declarative home** (`home.py`): a
class whose devices are class attributes, declared with their readings —
`grid = Grid(500)`, `bat1 = Battery(-400, charge_from=(grid, pv1))` — and whose
tests are plain methods, most of them a one-line `@expect("<property>")`
claim. A reference case declares the same devices without readings and gives
each snapshot its own inner `Snapshot` class (see `reference/` below). The
generated homes and the frozen snapshots use the plain data beneath —
`Adapter`, `Topology`, `State`, `Cell` — directly. See `home.py`'s docstring
for the authoring surface.

The strategy is to **assume the engine is right** rather than try to derive
every output by hand, and to layer three kinds of check on top of that
assumption, plus the docs showcase:

| Directory | Question | Values written by hand |
| --- | --- | --- |
| `manual/` | Does each modelling decision we know about still hold? | a few per decision |
| `automatic/` | Does every property obey its formula and the model's laws, in any home? | none |
| `frozen/` | Did this change move any engine output at all? | none — recorded from the engine |
| `reference/` | What does the engine compute for these fixed homes? (docs showcase) | none — nothing is asserted |

`manual/` is where knowledge accumulates: every time a decision is discovered,
it gets a class. `automatic/` generalises what the formulas and laws say to
hundreds of homes. `frozen/` catches everything else by noticing *change* —
it cannot say an output is right, only that it moved, which is exactly what a
reviewer needs to see.

### Changing the engine

1. Make the change and run `uv run --group engine pytest tests/engine`.
2. If `frozen/` fails, it lists every output that moved, in which home. If
   nothing should have moved, that list is your bug report.
3. If the moves are intended, accept them — this re-freezes the snapshots and
   re-publishes the docs results in one go:

   ```bash
   uv run --group engine python tools/snapshot.py
   ```

   Commit the regenerated files with the change. The PR diff then shows every
   moved output, and the PR template asks you to say why they moved.
4. If the change settles a modelling decision — a moved output that is now
   *meant* to be that way — add a hand-derived class to `manual/` and a note
   to [`docs/dev/engine-calculations.md`](../docs/dev/engine-calculations.md),
   so the decision is enforced even if the snapshots are re-frozen later.

In CI, a failing `engine-tests (frozen)` or `engine-tests (docs)` job puts the
same table of moved outputs in the job summary.

```bash
uv run --group engine pytest tests/engine   # HA harness not required
```

### `automatic/` — value-free checks over generated homes

Nothing here holds an expected number; each check is true of *every* home, and
runs over a few hundred seeded random ones (`random_homes.py` — varied prices,
LCOE/LCOS and correction factors, export permissions, restrictions that name the grid, and a tenth
with readings that slightly overdraw, as unsynchronised sensors do).

- `test_identities.py` — one executable formula per catalogued property, in
  terms of the readings, the configuration and the published properties it
  depends on. Because each identity is stated over its *published* inputs, the
  checks chain: only the provenance allocation (`sink_adapters_source_shares`)
  is left as a root. A guard test fails when a property is added to the catalog
  without an identity.
- `test_laws.py` — how all properties must move together under a change whose
  effect is known in advance: scaling power, scaling prices, renaming and
  reordering devices, adding idle devices, splitting a PV system in two, a
  meter dropping out, a correction factor acting as a change of LCOE, every
  breakdown by correction target reconciling with its rates, and the model's
  conservation laws. The catalog's `unit`
  says how each property must react. Known breaches are held strictly (an
  `xfail(strict=True)`, a `PUBLISH_WHILE_UNAVAILABLE` list), so a fix fails
  the test until the marker is removed.
- `test_source_shares_invariants.py` — the provenance root's own guarantees:
  rows are normalised, no source is over-drawn, and a restriction is only broken
  when no allocation could honour it (decided by an independent max-flow
  oracle).

### `manual/` — one hand-derived harness per engine decision

One module per question, following the sections of the decision log:

| Module | Question |
| --- | --- |
| `test_flow_roles.py` | Which devices count as sources, which as sinks? |
| `test_allocation_rules.py` | Among valid allocations, which one is chosen? |
| `test_feasibility.py` | Which allocations honour every restriction at all? |
| `test_restrictions.py` | What does a restriction mean, and what if it cannot hold? |
| `test_costs.py` | What does the power cost, per channel and per device? |
| `test_savings.py` | Who is credited with the money local power saves? |
| `test_battery_pricing.py` | When is a battery's energy paid for, and at what price? |
| `test_edge_readings.py` | What is published when readings are missing or odd? |

In each module, **one class per decision**, named after it (class names are
unique across the whole engine tier). The class declares the smallest home
that tells the decision apart from its alternatives, and its tests claim
values derived **by hand** from the decision, never read back from the
engine:

```python
class TestBrokenRestrictionIsReported(Home):
    """Decision: when the meter contradicts a restriction, the restriction
    is relaxed and the shortfall reported as a deficit (...).

    cons1 may only use pv1, draws 500 W, and pv1 makes 300 W. ...
    """

    grid = Grid(800)
    pv1 = Pv(300)
    cons1 = Consumer(-500, power_from=(pv1,))

    @expect("sink_adapters_restriction_deficit")
    def test_restriction_deficit(self):
        """The 200 W cons1 took from a forbidden source is its deficit."""
        return {"cons1": 200}
```

Every test method has a docstring that says, in words a first-time reader
can follow, what it checks and why that value is right. The class docstring
opens with the decision and names its note in
[`docs/dev/engine-calculations.md`](../docs/dev/engine-calculations.md), so a
red test — `TestBrokenRestrictionIsReported::test_restriction_deficit` — reads
as "this decision no longer holds". Any engine property can be claimed,
catalogued or not (the restriction deficit, say); a test that needs more than
one comparison takes the `power_insight` fixture and asserts.

**Add a class whenever a decision is made** — together with its note, and with
the engine fix when the decision was found as a bug. `test_decisions.py`
enforces it: every `Decision:` note in `engine-calculations.md` must end with
`Pinned by `TestX` in `tests/engine/manual/test_y.py`` (classes that exist,
in that module) or `Not pinned in the engine tier:` and a reason; every class
here must be named in the log, its docstring must open with the decision it
pins, and each of its test methods must have a docstring. A red harness means either
the engine or the derivation is wrong; resolving which is a human call. Never
paste an answer out of a failing test's `actual:` line.

### `frozen/` — has any engine output moved?

`snapshots/reference.json` and `snapshots/generated.json` record every
catalogued output — plus the restriction deficit — for every reference-case
snapshot and for 60 fixed generated homes. `test_frozen.py` recomputes them and
fails with a table of whatever moved. `store.py` holds the machinery:

- Generated homes' *inputs* are stored in the file and replayed, never
  re-drawn, so changing the random generator cannot make the snapshot noisy.
  Re-drawing is deliberate: `tools/snapshot.py --redraw`.
- Values are stored to 12 significant digits and compared at a relative
  tolerance of 1e-9, so float noise from a refactor is not a change.
- A frozen corpus only notices what its homes exercise. The reserve bug fixed
  alongside `two-pv-systems` moved outputs in that one home and in none of the
  60 generated ones. When a bug is found, give its home a place in the
  reference cases (and its decision a class in `manual/`), so the snapshot
  covers it from then on.

### `reference/` — the fixed homes shown in the docs

Ten small homes, one module per case: a wiring, a few snapshots of readings,
and prose in docstrings. They assert nothing. `tools/snapshot.py` passes every
snapshot through the engine and writes every catalogued property to
`docs/spec/cases/*.json`, which the docs site renders. The JSON is committed,
and `reference/test_corpus.py` fails when it no longer matches the engine, so a
docs version cut from any commit freezes that commit's own results.

A case declares its devices bare and one `Snapshot` per set of readings:

```python
class PvExport(ReferenceCase):
    """The same two devices, with the PV system now permitted to export. ...

    Shows:

    * An exporting grid is a sink, not a source with a negative reading.
    """

    case_id = "pv-export"
    title = "PV export"

    grid = Grid()
    pv1 = Pv(lcoe=0.10, exports=True, export_comp=0.08)

    class ExportSurplus(Snapshot):
        """The PV system outruns the house; the surplus leaves through the grid."""

        grid = -400
        pv1 = 900
        price = F(1, 4)
```

A snapshot must read exactly the case's devices, and publishes under its class
name in snake_case (`export_surplus`). The prose lives in docstrings: a case
class's is the page summary (everything above its `Shows:` list), and a
snapshot's is the caption under its card, where a paragraph opening `Open
question:` becomes a callout.

If you cannot run the command locally, **Actions → Update engine snapshots →
Run workflow** does it on the branch you pick and commits the result (tick *dry
run* to only see what moved). It is manual on purpose: re-freezing is accepting
that outputs moved, a decision for the reviewer, not something to automate. A
commit pushed by that workflow uses `GITHUB_TOKEN`, and GitHub does not start
new workflow runs for those, so re-run the checks from the Actions tab (or push
anything else) if your PR needs green checks to merge.

### Beside the three

- `test_flow_view.py` — the source/sink partition and the gross-power share
  vectors. These return adapter *objects* and `(vector, uid index)` pairs,
  which no catalogued property describes. Membership, disjointness and index
  order only.
- `test_snapshot_cache.py` — that the per-snapshot memo never outlives the
  reading it was computed from: a question about time, which no single
  snapshot can ask.
- `test_home.py` — self-tests for the declarative homes and reference cases:
  the checks at class creation, and that `@expect` really fails on a wrong
  value.

### Known gaps

- **Correction factors in the frozen corpora.** The generated homes were
  frozen before they drew correction factors, and no reference case sets one,
  so every frozen corrected output is at a factor of 1. Nothing is lost: the
  laws pin the corrected results to the uncorrected ones, which are frozen,
  and the identities run over random homes that do draw factors.
- **Open findings** held by `test_laws.py`: six properties still publish while
  a meter is unavailable (`PUBLISH_WHILE_UNAVAILABLE`), and readings that
  overdraw break source balance, so the conservation law only checks balanced
  homes.

## Integration tier (`integration/`)

Home Assistant layer tests — config flow, subentry flows, setup, sensor state
derivation, currency handling, and end-to-end wiring. Shared fixtures and
`MockConfigEntry` builders live in `integration/conftest.py`.

```bash
uv run --group dev pytest tests/integration
```

## Running everything

```bash
uv run pytest tests           # both tiers
```

The top-level `conftest.py` drops the integration tier from collection when
`pytest-homeassistant-custom-component` is not installed, so the engine tier
stays runnable in a minimal environment.
