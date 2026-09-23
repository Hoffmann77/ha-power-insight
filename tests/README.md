# Test layout

Tests are split into **two tiers, one directory per dependency group**. Each
tier maps to a CI job, and every tier is auto-discovered by directory — adding
a file to an existing tier needs no CI change.

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

Engine tests use the **source-order scenario framework** (`scenario_framework.py`,
wired in `conftest.py`). A scenario is a class whose methods come in repeating
blocks of `@topology` → `@state` → `test_` methods, and each test binds to the
block declared above it (found by source line). See the module docstring for the
authoring surface.

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
it gets a block. `automatic/` generalises what the formulas and laws say to
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
   *meant* to be that way — add a hand-derived block to `manual/` and a note
   to [`docs/dev/engine-calculations.md`](../docs/dev/engine-calculations.md),
   so the decision is enforced even if the snapshots are re-frozen later.

In CI, a failing engine job puts the same table of moved outputs in the job
summary.

```bash
uv run --group engine pytest tests/engine   # HA harness not required
```

### `automatic/` — value-free checks over generated homes

Nothing here holds an expected number; each check is true of *every* home, and
runs over a few hundred seeded random ones (`random_homes.py` — varied prices,
LCOE/LCOS, export permissions, restrictions that name the grid, and a tenth
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
  meter dropping out, and the model's conservation laws. The catalog's `unit`
  says how each property must react. Known breaches are held strictly (an
  `xfail(strict=True)`, a `PUBLISH_WHILE_UNAVAILABLE` list), so a fix fails
  the test until the marker is removed.
- `test_source_shares_invariants.py` — the provenance root's own guarantees:
  rows are normalised, no source is over-drawn, and a restriction is only broken
  when no allocation could honour it (decided by an independent max-flow
  oracle).

### `manual/` — one hand-derived harness per engine decision

Each module covers one area with one class — `test_power_flow.py`
(`TestPowerFlow`: where each sink's power comes from), `test_edge_readings.py`
(`TestEdgeReadings`: missing and degenerate readings) — and each decision is
one block in it: the smallest `@topology` and `@state` that tell the decision
apart from its alternatives, then `@expect_attribute` claims derived **by
hand** from the decision, never read back from the engine. The `@state`
docstring names the decision and its note in
[`docs/dev/engine-calculations.md`](../docs/dev/engine-calculations.md), so a
red test here reads as "this decision no longer holds". Any engine property can
be claimed, catalogued or not (the restriction deficit, say).

**Add a block whenever a decision is made** — together with its note, and with
the engine fix when the decision was found as a bug. A red block means either
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
  reference cases (and its decision a block in `manual/`), so the snapshot
  covers it from then on.

### `reference/` — the fixed homes shown in the docs

Ten small homes, one module per case: a wiring, a few snapshots of readings,
and prose in docstrings. They assert nothing. `tools/snapshot.py` passes every
snapshot through the engine and writes every catalogued property to
`docs/spec/cases/*.json`, which the docs site renders. The JSON is committed,
and `reference/test_corpus.py` fails when it no longer matches the engine, so a
docs version cut from any commit freezes that commit's own results.

The prose lives in docstrings: a case class's is the page summary (everything
above its `Shows:` list), and a `@state`'s is the caption under its snapshot
card, where a paragraph opening `Open question:` becomes a callout.

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
- `test_scenario_framework.py` — self-tests for the framework's validation and
  source-order binding.

### Known gaps

- **Correction factors.** The eight `*_corrected` properties are not in the
  catalog, and no engine test sets a factor other than 1.0; the integration
  tier covers them in `test_correction_flow.py`.
- **Open finding** held by `manual/test_power_flow.py`: two sinks with the
  same restriction can get different rows when the draws exactly exhaust the
  sources (strict xfail on the `unequal_draws` block).
- **Open findings** held by `test_laws.py`: the proportional split still drifts
  when a PV system is split in two with a base load present (the strict xfail),
  six properties still publish while a meter is unavailable
  (`PUBLISH_WHILE_UNAVAILABLE`), and readings that overdraw break source
  balance, so the conservation law only checks balanced homes.

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
