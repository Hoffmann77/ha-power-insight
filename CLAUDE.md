# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
uv run pytest

# Run a single tier (see tests/README.md)
uv run pytest tests/engine          # pure-Python engine, no HA needed
uv run pytest tests/integration     # Home Assistant layer

# Run a single test file
uv run pytest tests/engine/manual/test_allocation_rules.py

# Run a single test method
uv run pytest tests/engine/automatic/test_laws.py::test_the_books_balance

# Run one decision harness
uv run pytest tests/engine/manual/test_allocation_rules.py::TestTheGridGoesFirst

# Run a specific parametrized case by keyword
uv run pytest -k "import"
```

There is no build step — this is a Home Assistant custom component deployed by copying `custom_components/power_insight/` into a HA instance.

Tests are split into two tiers by dependency group: `tests/engine/` (pure Python, imports `power_insight.py` via `importlib`, no HA) and `tests/integration/` (needs `pytest-homeassistant-custom-component`). See `tests/README.md`.

## Architecture

### Data flow

```
HA state_changed/state_reported event
  → EventHandler._update_on_state_change()
      → PowerInsight.set_value(entity_id, value)   # stores raw W value
      → hass.bus.async_fire(custom_event)
          → BaseEventSensorEntity.async_write_ha_state()
              → sensor reads PowerInsight property (pure calculation)
```

`EventHandler` (`event_handler.py`) is the single bridge between the HA event bus and the `PowerInsight` calculation engine. It normalises all power values to Watts using SI prefixes, and the grid price to currency per kWh (`ct/kWh`, `EUR/MWh` … included; any other unit reads as an unknown price), before storing them.

### PowerInsight calculation engine (`power_insight.py`)

`PowerInsight` is a pure-Python class (no HA imports) that holds all adapters and exposes all derived quantities as `@property` chains. Calculation is lazy — nothing is computed until a property is accessed.

The engine contains one `GridAdapter` plus three `AdapterContainer` subclasses: `PvSystemAdapters`, `BatteryAdapters`, `ConsumerAdapters`. All result properties return `None` if any required input is `None`, propagating unavailability cleanly.

**Sign convention for raw power values stored by adapters:**
- Grid: positive = importing from grid, negative = exporting to grid
- PV/Battery: positive = producing/discharging, negative = consuming/charging (standby/charging)

**Adapter class hierarchy:**
```
AbstractBaseAdapter
└── BasePowerAdapter                (holds one power entity + _values dict)
    ├── BasePowerProvidingAdapter   (adds price + co2 source entities)
    │   ├── GridAdapter             (import/export split; holds price & co2 entities)
    │   └── BaseProductionAdapter   (production/consumption split; lcoe, export_compensation)
    │       ├── PvAdapter           (adds _lcoe)
    │       └── BatteryAdapter      (adds _lcos, charge_from_adapters)
    └── BaseConsumerAdapter
        └── ConsumerAdapter
```

### Config entry structure

The integration uses a **hub** pattern with one main `ConfigEntry` and multiple `ConfigSubentry` objects, one per adapter. Subentry data is structured as:

```python
{
    "adapter": {
        "adapter_type": "grid" | "pv_system" | "battery" | "consumer",
        "key": "<slugified name>",  # only keeps names unique
        "config": { <adapter-specific fields> },
    },
    # Optional top-level raw inputs (pv/battery only):
    "lifetime_production": ...,
    "lifetime_cost": ...,
    "co2_footprint": ...,
}
```

An adapter's `uid` — the key of every per-device map and part of every per-device `unique_id` — is its **subentry id**, not the slugified name, so renaming a device never orphans a sensor.

### Config flow (`config_flow.py`)

Field declarations use three dataclasses:
- `AdapterField` — a UI-visible field (holds selector, validators, `required_fn`, storage target flags)
- `EntryField` — a field on the main entry options (same idea, different flow visibility flags)
- `CalculatedAdapterField` — never shown; computed from other fields via `calculator` callable

`build_schema()` assembles a `voluptuous.Schema` from any of these collections, filtering by `flow_type` (`"config"` / `"reconfigure"` / `"options"`). `split_by_storage()` separates user input into `adapter_config` vs. top-level `data` based on `store_in_adapter_config` / `store_in_data` flags.

`ADAPTER_MODELS` dict (`adapter_models.py`) maps adapter type strings to model dataclasses via `@register_model`. Each model has `from_subentry()` and `create_adapter()`, decoupling HA config storage from the pure-Python adapter layer.

### Sensor platform (`sensor.py`)

Sensors are declared as `PowerInsightSensorDescription` / `PowerInsightIntegrationSensorDescription` tuples with:
- `value_fn(power_insight)` — reads a property from `PowerInsight`
- `entities_fn(power_insight)` — returns the source entity IDs this sensor cares about
- `exists_fn(options | adapter)` — gates registration based on user options or adapter config
- `transform_fn` — post-processing (e.g. `lambda val: val * 100` for percentages)
- `translation_key` — the name, which lives in `strings.json` (copied to `translations/en.json`) under `entity.sensor`; never a hardcoded `name=` (see `docs/dev/entity-naming.md`)

Per-adapter sensors (`PowerInsightAdapterSensor`) additionally call `get_value(adapter.uid, dict_result)` since adapter-level properties return `dict[uid → value]`.

Integration sensors (`BaseEventIntegrationSensorEntity`) accumulate rate values (EUR/h) over time using a left-Riemann method — each slice at the rate that held through it, up to the moment a rate becomes unavailable, then paused until it returns — restoring state across HA restarts and starting at setup once the engine has its readings.

### Testing

Engine-tier tests in `tests/engine/` import `power_insight.py` directly via `importlib.util` (in `tests/engine/home.py`) to bypass all HA dependencies. Every hand-written home is a **declarative home** (`tests/engine/home.py`); the generated homes and frozen snapshots use the plain data beneath it — `Adapter` / `Topology` / `State` / `Cell` — directly.

**Declarative homes**: a home is a class subclassing `Home` whose attributes are its devices, each with its reading, Django-model style — the attribute name is the uid, the first argument the power in W (`None` = unavailable sensor), the rest the static config with the `Adapter` factory keywords and defaults: `grid = Grid(400, price=F(3, 10))`, `pv1 = Pv(1000, exports=True)`, `bat1 = Battery(-400, charge_from=(grid, pv1))`, `plug = Consumer(-100, power_from=(pv1,))`. The grid must be called `grid`; a miswired home (no grid, unknown restriction target, bad keyword) fails at class creation. Tests are plain methods: take the `power_insight` fixture for an engine holding the readings, or use `@expect("<property>")` on a method that takes only `self` and *returns* the expected value; returning `None` asserts the engine publishes nothing at all. Every per-device map is keyed by a whole family of devices (the catalog's `keys`), but an expected map need only list the devices it is about — `@expect` gives every other one its idle value (0, or `None` for a price).

**Reference cases** use the same devices, declared *bare* (`grid = Grid()`, `pv1 = Pv(lcoe=0.10, exports=True)`), with one inner `Snapshot` class per set of readings: `class ExportSurplus(Snapshot)` with `grid = -400`, `pv1 = 900`, `price = F(1, 4)` as attributes. A snapshot must read *exactly* the case's devices, and publishes under its class name in snake_case (`export_surplus`).

The strategy: **assume the engine is right**, enforce every *known* decision by hand, generalise with formulas and laws, and detect any other change by freezing outputs. One directory each:

- **`tests/engine/automatic/`** — value-free checks over a few hundred seeded random homes (`random_homes.py`): `test_identities.py` (one executable formula per catalogued property over its published dependencies; provenance is the only root), `test_laws.py` (metamorphic laws — power/price scaling by catalog unit, renaming, idle devices, PV-system splitting, unavailability, every map keyed by its whole family, conservation), `test_source_shares_invariants.py` (provenance guarantees, with a max-flow feasibility oracle). No expected numbers.
- **`tests/engine/manual/`** — one hand-derived harness per **engine decision**: one module per question, following the sections of the decision log (`test_flow_roles.py`, `test_allocation_rules.py`, `test_feasibility.py`, `test_restrictions.py`, `test_costs.py`, `test_savings.py`, `test_battery_pricing.py`, `test_edge_readings.py`; expected provenance is written in watts via `provenance.rows`), one `Home` class per decision, named after it (`TestBrokenRestrictionIsReported`) and unique across the engine tier — the smallest home that tells the decision apart from its alternatives, then `@expect` claims with short names (`test_source_shares`, `test_restriction_deficit`) derived by hand, never read back from the engine. Every test method has a docstring a first-time reader can follow: what it checks and why that value is right. The class docstring opens with `Decision: …` and names its note in `docs/dev/engine-calculations.md`; each note ends with `Pinned by `TestX` in …` (the exact classes) or `Not pinned in the engine tier:` plus a reason, every class must be named in that log, and `manual/test_decisions.py` enforces both directions (plus the module paths, unique class names and test docstrings). Whenever an engine decision is made (or a bug turns into one), add its note, its class and the fix together.
- **`tests/engine/frozen/`** — the change detector: `snapshots/reference.json` and `snapshots/generated.json` record every catalogued output (plus the restriction deficit) for every reference-case snapshot and 60 fixed generated homes whose *inputs* are stored and replayed. `test_frozen.py` fails with a table of every output that moved. Values are stored to 12 significant digits and compared at rel 1e-9, so float noise is not a change.
- **`tests/engine/reference/`** — the docs showcase: ten fixed homes (`ReferenceCase` subclasses with `case_id` / `title`, bare devices, a few `Snapshot`s, prose in docstrings) that assert nothing; `docs/spec/cases/*.json` holds every catalogued property the engine computes for them (generated — never hand-edit), and `reference/test_corpus.py` fails when it is stale. Prose: the class docstring above its `Shows:` list is the page summary, a `Snapshot` docstring is its caption, and an `Open question:` paragraph becomes a callout. Older docs versions are not kept compatible with the shared `CaseDiagram` component: if the case JSON format changes, remove the broken old pages instead.

**Changing the engine**: run the engine tests; if `frozen/` lists moved outputs that are intended, run `uv run --group engine python tools/snapshot.py` (re-freezes the snapshots *and* re-publishes the docs JSON) and commit the result with the change; if the change settles a modelling decision, also add its `manual/` class and its note in `docs/dev/engine-calculations.md`. Never re-freeze to make an unexplained move go away.

Beside them: `test_flow_view.py` (grouping properties return adapter objects and `(vector, index)` pairs — no catalogable shape), `test_snapshot_cache.py` (memo invalidation across a reading change — a question about time), `test_home.py` (self-tests for the declarative homes and reference cases).
