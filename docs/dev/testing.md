# Engine testing strategy

How the `PowerInsight` calculation engine is tested, and what to do when you
change it. The engine tests live in `tests/engine/`. They are pure Python,
import `power_insight.py` directly via `importlib`, need no Home Assistant and
run in a few seconds. The layout of the whole suite, including the integration
tier, is described in `tests/README.md`.

## The idea

**Assume the engine is right.** Don't try to derive every output by hand.
Instead:

1. pin every **known** modelling decision by hand,
2. generalise with **formulas and laws** checked over random homes, and
3. **freeze** every output, so any other change shows up.

## Declarative homes

Every hand-written home is a class whose attributes are its devices, a bit like
a Django model. The attribute name is the device id, the first argument is the
reading in W (`None` means the sensor is unavailable), and the rest is the
device's static config:

```python
class TestTheGridGoesFirst(Home):
    grid = Grid(400, price=F(3, 10))
    pv1 = Pv(1000, exports=True)
    bat1 = Battery(-400, charge_from=(grid, pv1))
    plug = Consumer(-100, power_from=(pv1,))
```

The grid must be called `grid`. A miswired home (no grid, an unknown
restriction target, a bad keyword) fails as soon as the class is created.

Tests are plain methods. Either take the `power_insight` fixture, or use
`@expect("<property>")` on a method that returns the expected value. Returning
`None` asserts that the engine publishes nothing. An expected per-device map
only needs to list the devices it's about; every other device gets its idle
value (0, or `None` for a price).

## The four directories

| Directory | Question | Values written by hand |
| --- | --- | --- |
| `manual/` | Does each modelling decision we know about still hold? | a few per decision |
| `automatic/` | Does every property obey its formula and the model's laws, in any home? | none |
| `frozen/` | Did this change move any engine output at all? | none, recorded from the engine |
| `reference/` | What does the engine compute for these fixed homes? (docs showcase) | none, nothing is asserted |

### `manual/`: one class per decision

There is one module per question, following the sections of
[Engine calculation decisions](engine-calculations.md) (`test_flow_roles.py`,
`test_allocation_rules.py`, `test_restrictions.py`, `test_costs.py`, …). Each
decision gets **one `Home` class**, named after it
(`TestBrokenRestrictionIsReported`): the smallest home that tells the decision
apart from its alternatives. Its `@expect` claims are derived by hand and never
read back from the engine.

- The class docstring opens with `Decision: …` and names its note in the
  decision log.
- Each note in the log ends with `Pinned by TestX in …`, or with
  `Not pinned in the engine tier:` plus a reason.
- `manual/test_decisions.py` checks both directions, so there is never a class
  without a note or a note without its class.
- Every test method has a docstring saying what it checks and why that value is
  right.

### `automatic/`: laws over random homes

These are value-free checks over a few hundred seeded random homes
(`random_homes.py`):

- `test_identities.py`: one executable formula per catalogued property.
- `test_laws.py`: metamorphic laws, such as scaling power or price, renaming
  devices, adding idle devices, splitting a PV system, unavailability and
  conservation.
- `test_source_shares_invariants.py`: guarantees about where power comes from,
  checked against a max-flow feasibility oracle.

### `frozen/`: the change detector

`snapshots/reference.json` and `snapshots/generated.json` record every
catalogued output for every reference-case snapshot and for 60 fixed generated
homes. When anything moves, `test_frozen.py` fails with a table of every
output that changed. Values are stored to 12 significant digits and compared
at rel 1e-9, so float noise doesn't count as a change. These tests can't say
that an output is right, only that it moved.

### `reference/`: the docs showcase

Ten fixed homes, written as `ReferenceCase` classes with bare devices and a
few `Snapshot` readings each, are the source of the
[Reference cases](../spec/index.mdx) pages:

```text
tests/engine/reference/*.py   case definitions (devices, readings, prose)
        │
        ▼  uv run --group engine python tools/snapshot.py
docs/spec/cases/*.json        every catalogued property the engine computes
        │
        ▼
docs/spec/*.mdx               the pages render the JSON
```

- The pages show **what the engine currently computes**. Nothing is asserted
  here; correctness comes from the other three directories.
- The JSON is generated, so never edit it by hand. `reference/test_corpus.py`
  fails when the JSON is out of date.
- The prose comes from docstrings. The class docstring above its `Shows:` list
  is the page summary, a `Snapshot` docstring is its caption, and an
  `Open question:` paragraph becomes a callout.

## Changing the engine

1. Make the change and run `uv run --group engine pytest tests/engine`.
2. If `frozen/` fails, read the table. If nothing should have moved, that table
   is your bug report.
3. If the moves are intended, accept them. This re-freezes the snapshots and
   regenerates the docs JSON:

   ```bash
   uv run --group engine python tools/snapshot.py
   ```

   Commit the result together with the change.
4. If the change settles a modelling decision, add its note in
   [Engine calculation decisions](engine-calculations.md) and its `manual/`
   class together.

Never re-freeze just to make a move you can't explain go away.
