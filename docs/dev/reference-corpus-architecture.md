# The reference cases as the centre of the test suite

A design proposal. The reference cases in `docs/spec/cases/` are already the
specification of record for the engine's modelling choices. This describes what
has to change for them to also be the *input* to the engine tests and to a
future end-to-end tier — one case description, several projections — and what
deliberately should not move into them.

## Where we are

The corpus is nine cases, 648 slots, none derived yet
(`docs/spec/cases/index.json`). Four things describe a Power Insight topology
today, and only one of them is the corpus:

| Description | Lives in | Consumed by |
| --- | --- | --- |
| `CASES` (Python literals) | `tools/gen_cases.py` | writes the corpus JSON |
| Reference-case JSON | `docs/spec/cases/*.json` | the docs site; `tests/engine/test_reference_corpus.py` |
| `Adapter` / `Topology` / `State` | `tests/engine/scenario_framework.py` | every engine-tier test |
| Subentry builders | `tests/integration/conftest.py` | every integration test |
| `Grid` / `Pv` / `Battery` / `Consumer` | `tools/mock_power_insight.py` | `tools/playground.py` |

Three observations follow from that table.

**The corpus reaches exactly one test file, and that file is skipped.**
`test_reference_corpus.py` asserts every derived slot and there are none, so the
corpus currently constrains nothing. Everything actually tested about engine
values is hand-written in `tests/engine/`, against topologies that have no
counterpart in the corpus. Two specifications of the same engine, neither aware
of the other.

**The dependency direction is backwards.** `tools/gen_cases.py` and
`tools/certify.py` both `sys.path`-insert the repo root to import
`tests.engine.scenario_framework`. The generator of the published
specification depends on the test suite. Anything else that wants to read a case
— a docs script, an e2e tier, a future validator — inherits that.

**The corpus cannot express an HA-level question.** A case knows adapter uids,
kinds, engine config, watt readings and a price. It does not know entity ids,
subentry ids, adapter *type* strings (`pv` vs. HA's `pv_system`), option keys, or
which sensor publishes which property. All of that is exactly what an end-to-end
test is about.

## What "central" should mean

One case, several projections:

```
                      docs/spec/cases/*.json          ← the question + hand-derived answers
                               │
                    ┌──────────┼───────────┬─────────────────┐
                    ▼          ▼           ▼                 ▼
              CaseDiagram   engine      HA config        worksheet /
              (website)     builder     builder          certify
                               │           │
                               ▼           ▼
                   engine-tier value    e2e-tier sensor
                   assertions           assertions
```

The rule that keeps this from turning into a second config system: **the corpus
stays layer-neutral and the projections carry the layer knowledge.** A case says
`{"uid": "pv1", "kind": "pv", "config": {"lcoe": "1/10"}}`. It never says
`sensor.pv1_power`, never says `pv_system`, never says which option key has to be
enabled for a sensor to exist. The HA builder knows all four, because that
mapping *is* the thing an e2e test exists to check, and a corpus that already
encoded it could not catch it being wrong.

The corollary is the important half: an e2e test derived from a case must not
need any new hand-derived value. The derived value is a property of the model,
and the HA layer's job is to publish it unchanged. So e2e asserts the *same*
numbers through a longer pipe, and the only genuinely new expectations are the
ones the engine has no property for — availability, units, naming, option gating.

## The shape

A package the tests, the tools and the docs pipeline all depend on, rather than
one that depends on the tests:

```
corpus/
  __init__.py            load(), case(id), snapshot(case_id, state_id)
  model.py               Case, Snapshot, AdapterSpec, Expectation  (frozen dataclasses)
  definitions.py         the CASES literals, moved out of tools/gen_cases.py
  schema/
    reference-case.schema.json     ← currently referenced by every case, does not exist
  builders/
    engine.py            AdapterSpec → PowerInsight        (no HA, no pytest)
    ha.py                Case → ConfigEntry + subentries   (imports HA)
```

`corpus/builders/engine.py` absorbs `engine_from_corpus` and the `Adapter.build`
half of the scenario framework; `corpus/model.py` absorbs `Adapter`, `Topology`
and `State`. `tests/engine/scenario_framework.py` keeps what is genuinely about
pytest — the `@topology` / `@state` decorators, source-order binding, `Cell`,
`expect_attribute` — and imports the rest. `tools/*` import `corpus` and stop
reaching into `tests`. Splitting the two builders into separate modules keeps the
engine tier's no-Home-Assistant guarantee: importing `corpus.builders.engine`
pulls in nothing but `power_insight.py`.

Whether the case *definitions* stay Python literals (`corpus/definitions.py`,
JSON generated) or the JSON becomes hand-authored is a real fork; see
[Decisions](#decisions-i-would-want-made) below. Either way the JSON keeps its
current dual role — generated question, certified answer merged forward by
`asks` fingerprint — because the answers only ever exist there.

## Step 1 — give the corpus a home, a schema and a drift check

Cheap, no behaviour change, and everything else builds on it.

* Extract the `corpus/` package as above; leave the JSON exactly as it is.
* Write `corpus/schema/reference-case.schema.json`. Every case file already
  points at `../reference-case.schema.json` and the file does not exist, so the
  `$schema` line is currently decorative. The wellformedness rules in
  `test_reference_corpus.py::test_derivation_status_is_wellformed` are the first
  draft of its content; a real schema also pins the shape of `topology[].config`
  per kind, which is what a projection needs in order to be total.
* Add `gen_cases.py --check`: regenerate into a temp dir, diff against the
  committed corpus, fail on drift. Today an edit to `CASES` that is never
  regenerated leaves the docs and the tests describing different snapshots, and
  nothing notices.
* Add a loader-level guard that the corpus is non-empty and that only
  `docs/spec/cases/` is read — `website/versioned_docs/version-*/spec/anchors/`
  holds frozen copies of an older corpus, and no test should ever pick those up.

## Step 2 — the engine projection

Mostly exists; the work is making it the default rather than a side channel.

**Values.** `test_reference_corpus.py` stays as-is. It is already the right test:
parametrized per slot, three statuses, comparison by unit tolerance.

**Wirings.** Give the scenario framework a way to take its block from the corpus:

```python
class TestCaptiveBattery(EngineScenario):
    @topology
    def wiring(self):
        return corpus.case("captive-battery").topology

    @state
    def captive_depletes_first(self):
        return corpus.snapshot("captive-battery", "captive_depletes_first").state

    def test_rows_sum_to_one(self, power_insight): ...
```

or, sugar for the common case, a single `@from_case("captive-battery",
"captive_depletes_first")` that supplies both. The existing safety rail (a state
must name exactly its topology's uids) still applies and is free here, since both
came from the same case.

**What stays hand-written, and why.** Not everything a test asserts is a per-property
value, and the things that are not should never go through the certification
workflow:

* *Invariants* — cost conservation, savings additivity, avoided-cost duality,
  source balance, "provenance rows sum to one" (`test_full_topology.py`,
  `test_source_shares_invariants.py`). These need no derived number; they are
  relations that must hold for *every* topology, and they are the cheapest real
  bug detector in the suite.
* *Guards and error paths* — zero-gross division, `None` propagation, the
  framework's own validation (`test_scenario_framework.py`).
* *Wirings the ladder must not have* — `test_full_topology.py` deliberately runs
  a grid + 2 PV + 3 batteries + 2 consumers house, which violates the corpus's
  minimality rule ("a case earns its place only if it settles a decision no lower
  rung can express"). It is a stress topology, not a rung.

The duplicated part is the third one: per-property expected values in
`test_full_topology.py` for wirings the corpus also covers. Those can retire as
the corresponding slots get certified — but only per (property, snapshot), and
only where the wiring genuinely matches. Worth a lint that lists scenario
topologies with no corpus twin, so the overlap is visible rather than guessed at.

## Step 3 — the HA projection

The new piece. `corpus/builders/ha.py` turns a `Case` into everything a
`MockConfigEntry` needs, and a `Snapshot` into a set of source-entity states.

```python
built = build_entry(case, options=FULL_OPTIONS)
built.entry            # MockConfigEntry data + subentries
built.subentry_id      # {"pv1": "01PV...", "bat1": "01BAT..."}
built.power_entity     # {"pv1": "sensor.pv1_power"}
built.price_entity     # "sensor.grid_price" or None

feed(hass, built, snapshot)     # sets every power entity + the price, in W
```

Four mappings live in this module and nowhere else:

1. **uid → subentry_id.** Deterministic (a ULID-shaped hash of the uid) so a
   failure names the same id twice in a row. This matters more than it looks:
   at HA level `charge_from_adapters` and `power_from_adapters` hold *subentry
   ids*, and the engine keys every dict-valued property by adapter `unique_id`,
   which is the subentry id. Every dict expectation in the corpus is keyed by
   uid, so the comparison translates through this map.
2. **kind → adapter_type.** `pv` → `pv_system`; the other three are identity.
3. **engine config key → `CONF_*` key.** `lcoe` → `CONF_INITIAL_LCOE`, `lcos` →
   `CONF_INITIAL_LCOS`, and so on (`adapter_models.py`).
4. **property → sensor.** New, and the interesting one.

### The property → sensor mapping

`docs/spec/properties.json` documents 27 properties;
`custom_components/power_insight/sensor.py` declares the sensors that publish
them through `value_fn`. Nothing connects the two, so nothing can currently
notice a property that no sensor exposes, or a sensor whose `value_fn` drifted
onto a different property. Add the link to the catalog:

```json
"gross_power": {
  "unit": "W",
  "sensor": {"scope": "combined", "key": "available_power",
             "option": "enable_distribution_power"}
},
"sink_adapters_source_shares": {
  "unit": "share",
  "sensor": {"scope": "adapter", "key": "power_source_shares", "per": "sink"}
},
"combined_lcoe_rate": {
  "sensor": null,
  "sensor_note": "published only in its corrected form"
}
```

That single field earns three things:

* **e2e becomes generated.** For each snapshot with derived slots: build the
  entry with every option enabled, feed the readings, and assert each mapped
  sensor's state equals the derived value. No new hand-derived numbers.
* **A completeness test.** Every `sensor` entry must name a key that exists in
  `SENSOR_DESCRIPTIONS`, and every non-debug description must be reachable from
  some property or be explicitly listed as unpublished. Runs in the integration
  tier, needs no corpus values, and can land before any slot is certified.
* **The docs can say where a value is enforced.** The coverage table already
  reports derived-vs-slots; it can also report whether a property is checked at
  the engine layer only, or end to end.

### What e2e asserts that the engine tier cannot

* The subentry config actually round-trips into the adapter the case describes
  (`from_subentry` → `create_adapter`), including the restriction lists that go
  through the id translation.
* `EventHandler` normalisation: feed the *same* snapshot in W and in kW and
  require identical sensor states. The corpus stores watts; the unit is a
  parametrization of the feed, not case data.
* Availability: a `null` reading must render `unavailable`/`unknown` rather than
  a stale number, and a `null` derived value must do the same. This is a
  documented rule applied uniformly, not a per-slot expectation.
* Option gating: a property whose option is off has no entity at all.
* The coalesced event → `async_write_ha_state` path, which is where a value can
  silently be one snapshot stale (`_settle()` in `test_end_to_end.py` exists
  because of it).

### What stays out of e2e

Accumulation over time (`BaseEventIntegrationSensorEntity`, the removal ledger,
restore-across-restart) is a second dimension the corpus has no vocabulary for —
a case is one instant. Those stay hand-written in `tests/integration/`, driven by
`freeze_time` as today. Adding a time axis to the corpus would double the
derivation cost for the layer that needs it least.

## Step 4 — the docs projection

Unchanged in mechanism: the website imports the JSON through
`docs/spec/cases/all.ts` and passes it into `CaseDiagram`. Two additions worth
making once the above exists:

* the coverage table gains an "enforced at" column, from the `sensor` mapping;
* the "How a value gets here" section on `docs/spec/index.mdx` gains the last
  hop — a certified value is asserted against the engine *and* against the
  rendered sensor, which is a stronger claim than the page currently makes.

## Bootstrapping

Everything above collects zero tests today, because the corpus is 0/648. The
machinery is only real once a case is derived, so the first slice should end with
one: **grid-only, 81 slots, one adapter** — the cheapest rung, and enough to turn
on the engine projection and the e2e projection at once. Until then the generated
e2e module should guard on *cases loaded*, not on slots found, so an empty corpus
is visibly zero coverage rather than a silently passing suite.

## Enforcement

| Check | Tier | Exists? |
| --- | --- | --- |
| Corpus validates against the JSON schema | engine | no — schema missing |
| Certification records are wellformed | engine | yes |
| Every slot names a catalogued property | engine | yes |
| `gen_cases.py --check` finds no drift | engine | no |
| Engine matches every `verified` slot | engine | yes (skipped, empty) |
| Engine still contradicts every `disputed` slot | engine | yes (skipped, empty) |
| Every catalogued property maps to a real sensor key | integration | no |
| Every published sensor is reachable from a property | integration | no |
| Rendered sensor state equals the derived value | e2e | no |
| Readings in W and kW render identically | e2e | no |

## Decisions I would want made

1. **Where the case definitions live.** Keeping them as Python literals in
   `corpus/definitions.py` preserves today's authoring ergonomics and the
   `Adapter.pv(...)` factories. Making the JSON hand-authored removes a
   generation step and the drift risk entirely, at the cost of writing
   topologies as JSON. I lean to keeping Python plus the `--check` gate: the
   corpus is edited rarely and read constantly.
2. **Does the full-topology wiring become a rung?** It is the richest engine
   test we have and it duplicates corpus ground. Promoting it makes the corpus
   the single source of engine expectations, but breaks the minimality rule and
   makes hand-derivation there an afternoon per property. I lean to keeping it
   test-only and explicitly labelling it a stress topology, not a specification.
3. **How much e2e per case.** Every mapped property on every snapshot is the
   thorough reading and will be a few thousand assertions once the corpus fills;
   one snapshot per case is the fast reading. Since the numbers are shared with
   the engine tier, e2e is really testing the *pipe*, and one snapshot per case
   plus every degenerate snapshot (`null` readings, zero gross) probably buys the
   same confidence for a fraction of the runtime.
4. **Do dict-valued expectations stay keyed by uid?** Yes, in my view — the
   corpus should not learn subentry ids — but it means the e2e comparison always
   translates, and a translation bug could mask a real mismatch. Worth a
   dedicated test of the translation itself.

## Suggested order

1. `corpus/` package + schema + `--check` in CI. No behaviour change.
2. Property → sensor mapping + the two completeness tests. Lands before any
   value is derived and immediately covers a real gap.
3. Scenario blocks sourced from the corpus; lint for topologies with no twin.
4. `corpus/builders/ha.py` + the generated e2e module, guarded on cases loaded.
5. Derive `grid-only` end to end, which switches steps 1–4 from scaffolding to
   coverage.
