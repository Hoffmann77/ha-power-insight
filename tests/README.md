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
- `reference/` — the hand-derived reference corpus, published to the docs site
  (see below).

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

It is nine small homes, one module per case. Each is an ordinary scenario class
whose `@expect` methods claim values somebody worked out **by hand from the
model**, with the engine's answer not in view:

```python
class TestGridOnly(ReferenceCase):
    """One meter and nothing else. ...

    Decides:

    * With no local device, the whole gross power is the home base load.
    """

    case_id = "grid-only"
    title = "Grid only"

    @topology
    def wiring(self):
        return (Adapter.grid(),)

    @state
    def import_only(self):
        """The house runs on the grid alone; every watt is base load."""
        return State(grid=1200, price=F(3, 10))

    @expect("gross_power")
    def test_import_only_gross_power(self):
        return 1200
```

`@expect("<property>")` is `expect_attribute` with the tolerance the property's
unit deserves, looked up from `docs/spec/properties.json` — so a misspelled
name raises at import rather than passing silently. Return `None` to claim the
engine should publish *nothing at all* here; that is asserted just as strictly
as a number and never matches a zero. Derive nothing for a property and simply
write no method: nothing is published and nothing is asserted.

A red test means **either** the engine is broken **or** the derivation was, and
the corpus has no opinion about which — that call is yours, and it is the whole
point. There is no third state to park a disagreement in.

Never paste an answer out of a failing test's `actual:` line. That records what
the code already does, which proves nothing and quietly turns the corpus into a
changelog.

**The same classes are the documentation.** `ReferenceCase.publish()` reads a
case back out — wiring, readings, prose, and every claimed value — using the
same source-order binding pytest binds by, so a published page cannot describe
a snapshot differently from the way it is asserted. The prose lives in
docstrings: the class's is the page summary (everything above its `Decides:`
list), and a `@state`'s is the caption under its snapshot card, where a
paragraph opening `Open question:` becomes a callout.

`tools/export_cases.py` writes that out to `docs/spec/cases/*.json`, and
`reference/test_corpus.py` fails if what is on disk no longer matches:

```bash
uv run --group engine python tools/export_cases.py           # re-export
uv run --group engine python tools/export_cases.py --check   # just check
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
