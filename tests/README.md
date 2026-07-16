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

- `test_power_insight_calculations.py` — full grid + PV + battery + consumer
  scenario; each expectation is re-derived from the engine's own formulas.
- `test_engine_property_scenarios.py` — class-per-scenario edge cases with
  hand-written expected values, built on `engine_property_framework.py`.
- `test_correction_factor.py`, `test_release_bugfixes.py`,
  `test_storage_dynamic_lcoe.py` — targeted regression tests.

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
