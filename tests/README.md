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

`reference/` is the **only** place an engine value is asserted. Every expectation
about what a property *equals* belongs there, and nothing beside it may restate
one — not on a different wiring, not as an edge case, not "for defence in depth".
If a reference case could assert it, only a reference case does.

The files beside the corpus survive because no reference case could express
them, whatever the catalog grows to. Two of them are a prototype of a
value-free strategy that checks every catalogued property without a single
hand-derived number:

- `test_identities.py` — one executable formula per catalogued property, in
  terms of the readings, the configuration and the published properties it
  depends on, checked over ~200 random homes (`random_homes.py`). Because each
  identity is stated over its *published* inputs, the checks chain: only the
  provenance allocation (`sink_adapters_source_shares`) is left as a root.
  `test_every_catalogued_property_has_exactly_one_identity_or_is_a_root` fails
  when a property is added to the catalog without one.
- `test_laws.py` — how all properties must move together under a change whose
  effect is known in advance: scaling power, scaling prices, renaming and
  reordering devices, adding idle devices, splitting an array into strings, a
  meter dropping out, and the model's conservation laws. The catalog's `unit`
  says how each property must react. Known breaches are held strictly (an
  `xfail(strict=True)`, a `PUBLISH_WHILE_UNAVAILABLE` list), so a fix fails the
  test until the marker is removed.

The rest:

- `reference/` — the hand-derived reference corpus, published to the docs site
  (see below). Every value expectation, for the properties catalogued in
  `docs/spec/properties.json`.
- `test_flow_view.py` — the source/sink partition and the gross-power share
  vectors. The grouping properties return adapter *objects* and the share
  properties return a `(vector, uid index)` pair; neither is a shape the catalog
  can describe or a sensor can render, so there is no property name to state
  them under. Membership, disjointness and index order only.
- `test_source_shares_invariants.py` — what must hold for *every* wiring, over
  a few hundred generated topologies that find their own counterexamples. A
  fixed case states one value; it cannot state "for all".
- `test_snapshot_cache.py` — that the per-snapshot memo never outlives the
  reading it was computed from. A question about time: a reference case builds
  one engine and reads it once, so it cannot see a stale answer.
- `test_scenario_framework.py` — self-tests for the framework's validation and
  source-order binding. The corpus runs *on* this machinery and so cannot test
  it.

Two files were removed once the corpus became the sole owner of values:
`test_full_topology.py` (one rich home, every property) and
`test_source_shares.py` (provenance under grid-anchored restrictions). Both held
only value assertions, so both were the corpus's work sitting in the wrong file.
Their content is not lost but *owed*: see the coverage note below.

Expected values are hand-derived, compared with `pytest.approx`: exact values
(`0.5`, `2/3`) at the default tolerance, rounded shares/ratios to three decimals
(`abs=1e-3`). The engine's own modelling decisions are recorded in
[`docs/dev/engine-calculations.md`](../docs/dev/engine-calculations.md).

```bash
uv run --group engine pytest tests/engine   # HA harness not required
```

### Coverage the corpus still owes

Concentrating every value in `reference/` means the corpus is now the *only*
thing asserting one, and eight of its ten cases are still mostly `TODO`. Two gaps are
open until it catches up, both worth closing before a release:

1. **Derivations.** 64 engine properties reach a user's sensor and the catalog
   now names 50 of them, so every one has a `return TODO` stub waiting in every
   case — 1269 in total. Until a stub is filled the property has no
   assertion anywhere, so the count of skips *is* the size of the gap.

   Fourteen sensor-facing properties are deliberately left out of the catalog,
   and adding them would be a mistake rather than progress:
   - `source_entities_power` / `source_entities_price` are entity-id lists, not
     values, and `sink_adapters_restriction_deficit` is a sensor attribute.
   - the eight `*_corrected` variants equal their base property exactly unless
     somebody has edited a lifetime cost, and every case uses the default
     factor of 1.0 — so cataloguing them would scaffold 192 stubs whose answer
     is another stub's answer, while still never exercising the correction
     arithmetic. Testing that needs a case with a factor other than 1.0, which
     also needs `Adapter.battery()` to accept one (only `Adapter.pv()` does).
     The integration tier covers the behaviour today in
     `test_correction_flow.py`.
   - the three `*_components` are accumulator plumbing, never displayed.
2. **Grid-anchored restrictions.** No case wires a sink with
   `charge_from=("grid", …)`, so the three-tier priority/home/leftover
   allocation — a battery anchored to the grid competing with a flexible sink
   over a short import — has no case that reaches it. One new case closes this.

Until then the generated-topology invariants are the only thing standing over
the provenance solve, and they check shape and conservation, not specific
values.

### The reference corpus (`engine/reference/`)

The scenario files above cover what a value assertion cannot express. The
**reference corpus** holds every value, and answers the question that matters —
whether what the engine does is *right*.

It is ten small homes, one module per case. Each is an ordinary scenario class
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
as a number and never matches a zero.

**Every snapshot already has a method for every property**, in the catalog's
dependency order, most of them still reading `return TODO`. A stub skips rather
than fails and publishes nothing — it claims nothing, because nobody has
claimed anything. Filling one in is a one-line edit:

```python
    @expect("gross_power")
    def test_import_only_gross_power(self):
        return TODO      # <- replace with the value you worked out
```

The skip carries the property's definition, formula and steps straight from the
catalog, so running a case with `-rs` is a worklist with the instructions in it:

```bash
uv run --group engine pytest tests/engine/reference/test_grid_only.py -rs
```

`reference/test_corpus.py` keeps that scaffold complete: add a property to the
catalog and every snapshot tells you it needs a method, rather than the gap
going unnoticed.

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

If you filled a value in and forgot to re-export, **Actions → Export reference
cases → Run workflow** does it on the branch you pick and commits the result.
It is manual on purpose: an automatic export would land bot commits on branches
while you are working on them, and the staleness test already catches the
mistake in seconds. Tick *dry run* to see what would change without committing.

One wrinkle worth knowing: a commit pushed by that workflow uses `GITHUB_TOKEN`,
and GitHub does not start new workflow runs for those. The new head lands with
no checks against it, so re-run them from the Actions tab (or push anything
else) if your PR needs green checks to merge.

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
