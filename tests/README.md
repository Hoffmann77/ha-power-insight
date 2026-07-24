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

- `test_source_shares.py` — the two-tier `sink_adapters_source_shares`
  power-provenance attribution (the richest engine logic).
- `test_flow_view.py` — the dynamic source/sink partition, `gross_power`, the
  gross-power share vectors, and `None`/zero-gross guards.
- `test_engine_stubs.py` — skipped stubs for property families the engine has
  not implemented yet (combined rates/prices, per-source attribution), each with
  a ready topology/state to fill in.
- `test_scenario_framework.py` — self-tests for the framework's validation and
  source-order binding.

```bash
uv run --group engine pytest tests/engine   # HA harness not required
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
