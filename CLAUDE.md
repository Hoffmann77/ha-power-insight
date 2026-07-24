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
uv run pytest tests/engine/test_source_shares.py

# Run a single test method
uv run pytest tests/engine/test_source_shares.py::TestSourceShares::test_priority_battery_takes_all_pv

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

`EventHandler` (`event_handler.py`) is the single bridge between the HA event bus and the `PowerInsight` calculation engine. It normalises all power values to Watts using SI prefixes before storing them.

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
        "key": "<slugified name>",
        "config": { <adapter-specific fields> },
    },
    # Optional top-level raw inputs (pv/battery only):
    "lifetime_production": ...,
    "lifetime_cost": ...,
    "co2_footprint": ...,
}
```

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

Per-adapter sensors (`PowerInsightAdapterSensor`) additionally call `get_value(adapter.uid, dict_result)` since adapter-level properties return `dict[uid → value]`.

Integration sensors (`BaseEventIntegrationSensorEntity`) accumulate rate values (EUR/h) over time using a left-Riemann method, restoring state across HA restarts.

### Testing

Engine-tier tests in `tests/engine/` import `power_insight.py` directly via `importlib.util` to bypass all HA dependencies, and all use the **source-order scenario framework** (`tests/engine/scenario_framework.py`, wired via `conftest.py`).

**Source-order scenario framework**: a scenario is a class subclassing `EngineScenario` that concentrates on one aspect of the engine. Inside it, methods appear in repeating **blocks** — a `@topology` method (which adapters exist + their static config), a `@state` method (the `uid → power` readings plus grid `price`), then `test_` methods. Each `test_` method binds to the `@topology` and `@state` declared closest **above** it, located by source line (`__code__.co_firstlineno`), so a block reads top to bottom as *wiring → readings → assertions*; a comment line separates blocks. Reusing one topology across two reading sets is just two `@state`/`test_` runs under it.

Adapters are declared with the `Adapter.grid()/pv()/battery()/consumer()` factories, config inline at the call site (`Adapter.pv("pv1", lcoe=0.10, exports=True)`, `Adapter.battery("bat1", charge_from=("pv1",))`, `Adapter.consumer("plug", power_from=("pv1",))`). A `@state` is `State(grid=1000, pv1=-500, price=0.30)`; `None` power models an unavailable sensor. A safety rail requires a state to name *exactly* its topology's uids. Each test receives a freshly built engine via the `power_insight` fixture (or `state` / `topology` for the raw block objects), and asserts hand-written expected values derived from first principles — not read back from the engine — so a regression flips the test red. Property families the engine has not implemented yet get skipped-stub scenarios (`test_engine_stubs.py`) with a ready topology/state to fill in.
