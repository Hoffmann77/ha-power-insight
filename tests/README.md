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
so they need **no Home Assistant** and run in a fraction of a second.

All engine tests use the **source-order scenario framework**
(`scenario_framework.py`, wired in `conftest.py`). A scenario is a class that
concentrates on one aspect of the engine; inside it, methods appear in repeating
blocks of `@topology` → `@state` → `test_` methods, and each test binds to the
block declared above it (found by source line). See the module docstring for the
authoring surface.

- `test_source_shares.py` — the three-tier `sink_adapters_source_shares`
  power-provenance attribution (the richest engine logic).
- `test_flow_view.py` — the dynamic source/sink partition, `gross_power`, the
  gross-power share vectors, and `None`/zero-gross guards.
- `test_engine_stubs.py` — skipped stubs for property families the engine has
  not implemented yet (combined rates/prices, per-source attribution), each with
  a ready topology/state to fill in.
- `test_scenario_framework.py` — self-tests for the framework's validation and
  source-order binding.
- `test_reference_corpus.py` — asserts the engine against the hand-derived
  reference corpus in `reference/` (see below).

Expected values are hand-derived, compared with `pytest.approx`: exact values
(`0.5`, `2/3`) at the default tolerance, rounded shares/ratios to three decimals
(`abs=1e-3`). The engine's own modelling decisions are recorded in
[`docs/dev/engine-calculations.md`](../docs/dev/engine-calculations.md).

```bash
uv run --group engine pytest tests/engine   # HA harness not required
```

### The reference corpus (`engine/reference/`)

The scenario files above are the regression net: they pin what the engine does
so a change that moves a number goes red. The **reference corpus** answers a
different question — whether what the engine does is *right*.

It is nine small homes, one module per case, each holding a wiring, a few
snapshots of it, and a dict of answers somebody worked out **by hand from the
model**, with the engine's answer not in view:

```python
Snapshot(
    id="import_only",
    note="The house runs on the grid alone; every watt is unmetered base load.",
    readings=dict(grid=1200),
    price=F(3, 10),
    answers={
        "gross_power": 1200,
        "home_base_load_source_shares": {"grid": 1},
        "combined_export_compensation_rate": 0,
    },
)
```

`test_reference_corpus.py` generates one test per written answer. A value can be
a number, a map, or `None` (the model saying the engine should publish nothing
at all here — asserted just as strictly). Leave a property out and no test is
generated: an empty slot is honest, a guessed one is worse than none.

A red test means **either** the engine is broken **or** the derivation was, and
the corpus has no opinion about which — that call is yours, and it is the whole
point. There is no third state to park a disagreement in.

Never paste an answer out of a failing test's `engine says:` line. That records
what the code already does, which proves nothing and quietly turns the corpus
into a changelog.

The same cases are published to the documentation site. `tools/export_cases.py`
projects them into `docs/spec/cases/*.json`, and CI fails if that output is
stale:

```bash
uv run --group engine python tools/export_cases.py           # re-export
uv run --group engine python tools/export_cases.py --check   # what CI runs
```

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
