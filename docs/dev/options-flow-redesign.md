# Options flow redesign — final spec

Status: **implemented** (step 1: grid import/export sensors; step 2: per-scope
options flow, gating, migration).

Refinements made during implementation (the code is the source of truth):
- The single `enable_power_shares` toggle was split into the categories
  **Power distribution (W)** (`enable_distribution_power`), **Power
  distribution ratios** (`enable_distribution_ratios`), **Power distribution
  shares** (`enable_distribution_shares`), **Charging source shares**
  (`enable_charging_source_shares`, battery) and **Power source shares**
  (`enable_power_source_shares`, consumer).
- **Export compensation** became its own category
  (`enable_export_compensation_rate`, `accumulate_export_compensation`), and the
  accumulated category was split into **Accumulated costs** and **Accumulated
  cost savings**.
- The grid gained **Import power** alongside Export power.
- The options flow is a **menu** with one step per scope (no defaults/inherit).
- Each section is **saved immediately on submit** (no separate "save" step);
  an under-configured selection routes through a confirm step ("save anyway").

This spec reorganises the integration's options so that *which sensors are
created* is configured **per device type**, in human‑readable categories, from a
single central options flow. It folds in the related decisions to move the grid
import/export sensors onto the grid device and to keep one grid per config
entry.

It builds on the gating work already merged (`_SENSOR_OPTION_GATE` +
`_sync_entity_enabled_state` in `sensor.py`): every sensor is gated by an option
and toggling an option disables (keeps history) / re‑enables its entities. This
redesign only changes *how options are grouped and stored* and *which option
gates which sensor* — the gating/enable machinery is reused unchanged.

---

## 1. Goals

- One central options flow, **sectioned by device type** (no per‑subentry flows,
  no global "defaults/inherit" bucket).
- Each section shows **only the categories that device type supports**, with
  friendly names.
- The grid device owns **both sides of the meter**: import (cost) and export
  (compensation + power).
- **One grid per config entry** — the correct domain model, not a limitation
  (two grid connections → two config entries).
- Pre‑release: **no history‑preserving migration** required; entities may be
  recreated.

---

## 2. Scope model

Six configurable scopes. A scope is shown in the flow only if it applies (the
device type has at least one subentry; `combined`/`diagnostics` always shown).

| Scope | Meaning |
|---|---|
| `combined` | Whole‑home aggregate (hub) sensors |
| `grid` | The single grid connection (import + export) |
| `pv_system` | Applies to all PV system devices |
| `battery` | Applies to all battery devices |
| `consumer` | Applies to all consumer devices |
| `diagnostics` | Global troubleshooting toggles |

"Per device type" means a choice applies to **all** instances of that type, not
per instance.

---

## 3. Category taxonomy & option keys

Categories are the user‑facing groupings; each maps to one or more leaf option
keys (the values actually stored and checked).

!!! note "Post-implementation addition"
    Four financial-return option keys were added to `combined`, `pv_system`, and
    `battery` scopes after this spec was written:
    `calculate_financial_return_rate`, `calculate_levelized_financial_return_rate`,
    `accumulate_financial_return`, `accumulate_levelized_financial_return`.
    The `self_consumption_cost_savings_*` sensor family was removed (cost savings
    now means avoided import only; financial return = cost savings + export
    compensation). The sensor-key tables in section 5 reflect the current state.

### Money categories

| Category (label) | Leaf option key(s) | Choice labels |
|---|---|---|
| Cost rates (€/h) | `calculate_cost_rates`, `calculate_levelized_cost_rates` | Cost, Levelized cost |
| Cost savings rates (€/h) | `calculate_cost_saving_rates`, `calculate_levelized_cost_saving_rates` | Cost savings, Levelized cost savings |
| Export compensation | `enable_export_compensation_rate`, `accumulate_export_compensation` | Rate (€/h), Accumulated total (€) |
| Accumulated costs (€) | `accumulate_cost_rates`, `accumulate_levelized_cost_rates` | Cost, Levelized cost |
| Accumulated cost savings (€) | `accumulate_cost_saving_rates`, `accumulate_levelized_cost_saving_rates` | Cost savings, Levelized cost savings |

### Power categories

| Category (label) | Leaf option key | Notes |
|---|---|---|
| Power distribution (W) | `enable_distribution_power` | absolute watt split |
| Power distribution ratios | `enable_distribution_ratios` | `*_ratio` % (own power split) |
| Power distribution shares | `enable_distribution_shares` | `*_share` % (share of combined) |
| Charging source shares | `enable_charging_source_shares` | battery only |
| Power source shares | `enable_power_source_shares` | consumer only |

### Diagnostics

| Category (label) | Leaf option key |
|---|---|
| Enable debug power entities | `debug_power_entities` |

### Key changes vs today

- **Added:** `enable_export_compensation_rate`, `accumulate_export_compensation`,
  `enable_distribution_power`, `enable_distribution_ratios`,
  `enable_distribution_shares`, `enable_charging_source_shares`,
  `enable_power_source_shares`.
- **Removed:** `enable_power_shares` (split into the four power categories), and
  the three *container* keys `calculate_instantaneous_rates`,
  `calculate_instantaneous_saving_rates`, `calculate_accumulated_entities`
  (the flow now groups leaf keys by category directly).
- **Repurposed:** export compensation is pulled **out** of `calculate_cost_rates`
  / `accumulate_cost_rates` into its own two keys, so "Cost rates" and
  "Accumulated costs" now mean strictly operating cost.

### Which categories each scope offers (`SCOPE_SUPPORTED_OPTIONS`)

| Scope | Categories |
|---|---|
| combined | Cost rates · Cost savings rates · Accumulated costs · Accumulated cost savings · Power distribution (W) · Power distribution ratios |
| grid | Cost rates (Cost only) · Accumulated costs (Cost only) · Export compensation · Power distribution (W) · Power distribution ratios · Power distribution shares |
| pv_system | Cost rates · Cost savings rates · Export compensation · Accumulated costs · Accumulated cost savings · Power distribution (W) · Power distribution ratios · Power distribution shares |
| battery | same as pv_system **+ Charging source shares** |
| consumer | Cost rates · Power source shares |
| diagnostics | Enable debug power entities |

---

## 4. Per‑scope sections (exact fields shown)

### Whole‑home (combined)
- Cost rates (€/h): `Cost`, `Levelized cost`
- Cost savings rates (€/h): `Cost savings`, `Levelized cost savings`
- Accumulated costs (€): `Cost`, `Levelized cost`
- Accumulated cost savings (€): `Cost savings`, `Levelized cost savings`
- Power distribution (W) *(toggle)* — self‑consumption / charging / standby power
- Power distribution ratios *(toggle)* — export / self‑consumption / charging / standby ratio
- *(electricity‑price sensors stay always‑on — core readings)*

### Grid
- Power distribution (W) *(toggle)* — **import power, export power**
- Cost rates (€/h): `Cost`
- Accumulated costs (€): `Cost`
- Export compensation: `Rate (€/h)`, `Accumulated total (€)`
- Power distribution ratios *(toggle)* — consumption ratio
- Power distribution shares *(toggle)* — consumption share

### PV systems
- Power distribution (W) *(toggle)* — export power, self‑consumption power
- Cost rates (€/h): `Cost`, `Levelized cost`
- Cost savings rates (€/h): `Cost savings`, `Levelized cost savings`
- Export compensation: `Rate (€/h)`, `Accumulated total (€)`
- Accumulated costs (€): `Cost`, `Levelized cost`
- Accumulated cost savings (€): `Cost savings`, `Levelized cost savings`
- Power distribution ratios *(toggle)* — export ratio, self‑consumption ratio
- Power distribution shares *(toggle)* — export share, self‑consumption share

### Batteries
- Same as PV systems, plus:
- Charging source shares *(toggle)* — charging share from each selected source
- *(Export compensation shown only when the battery exports)*

### Consumers
- Cost rates (€/h): `Cost`, `Levelized cost`
- Power source shares *(toggle)* — per‑source `Power share from <source>`

### Diagnostics
- Enable debug power entities *(toggle)* — global

---

## 5. Sensor → scope → category map

Capability gates (`exports_power`, `lcoe is not None`) still apply **in addition**
to the option gate.

### Combined (hub device)
| Sensor key | Option key |
|---|---|
| combined_self_consumption_power | enable_distribution_power |
| combined_charging_power | enable_distribution_power |
| combined_standby_power | enable_distribution_power |
| combined_export_ratio | enable_distribution_ratios |
| combined_self_consumption_ratio | enable_distribution_ratios |
| combined_charging_ratio | enable_distribution_ratios |
| combined_standby_ratio | enable_distribution_ratios |
| combined_cost_rate | calculate_cost_rates |
| combined_operating_cost_rate | calculate_cost_rates |
| combined_levelized_cost_rate | calculate_levelized_cost_rates |
| combined_levelized_operating_cost_rate | calculate_levelized_cost_rates |
| combined_cost_savings_rate | calculate_cost_saving_rates |
| combined_levelized_cost_savings_rate | calculate_levelized_cost_saving_rates |
| combined_financial_return_rate | calculate_financial_return_rate |
| combined_levelized_financial_return_rate | calculate_levelized_financial_return_rate |
| combined_total_operating_costs | accumulate_cost_rates |
| combined_total_levelized_operating_costs | accumulate_levelized_cost_rates |
| combined_total_cost_savings | accumulate_cost_saving_rates |
| combined_total_levelized_cost_savings | accumulate_levelized_cost_saving_rates |
| combined_total_financial_return | accumulate_financial_return |
| combined_total_levelized_financial_return | accumulate_levelized_financial_return |
| combined_price_of_electricity | *(always on)* |
| combined_levelized_price_of_electricity | *(always on)* |

`combined_export_compensation_rate` and `combined_total_export_compensation`
**move to the grid device** (see below) and are removed from the combined scope.
`combined_export_ratio` stays at combined.

### Grid device
| Sensor key | Option key | Source property |
|---|---|---|
| import_power *(new)* | enable_distribution_power | `grid_adapters_import_power` |
| export_power *(new)* | enable_distribution_power | `grid_adapters_export_power` |
| import_cost_rate | calculate_cost_rates | `grid_adapters_coe_rate` |
| total_import_cost | accumulate_cost_rates | (integration of import_cost_rate) |
| export_compensation_rate *(moved)* | enable_export_compensation_rate | `grid_adapters_export_compensation_rate` *(new wrapper)* |
| total_export_compensation *(moved)* | accumulate_export_compensation | (integration of export_compensation_rate) |
| consumption_ratio | enable_distribution_ratios | `grid_adapters_consumption_ratios` |
| consumption_share | enable_distribution_shares | `grid_adapters_consumption_shares` |

### PV system / Battery device (per instance)
| Sensor key | Option key | Capability |
|---|---|---|
| export_power | enable_distribution_power | exports_power |
| self_consumption_power | enable_distribution_power | — |
| export_compensation_rate | enable_export_compensation_rate | exports_power |
| total_export_compensation | accumulate_export_compensation | exports_power |
| operating_cost_rate | calculate_cost_rates | — |
| levelized_operating_cost_rate | calculate_levelized_cost_rates | lcoe |
| cost_savings_rate | calculate_cost_saving_rates | — |
| levelized_cost_savings_rate | calculate_levelized_cost_saving_rates | lcoe |
| financial_return_rate | calculate_financial_return_rate | exports_power |
| levelized_financial_return_rate | calculate_levelized_financial_return_rate | lcoe · exports_power |
| total_operating_costs | accumulate_cost_rates | — |
| total_levelized_operating_costs | accumulate_levelized_cost_rates | lcoe |
| total_cost_savings | accumulate_cost_saving_rates | — |
| total_levelized_cost_savings | accumulate_levelized_cost_saving_rates | lcoe |
| total_financial_return | accumulate_financial_return | exports_power |
| total_levelized_financial_return | accumulate_levelized_financial_return | lcoe · exports_power |
| export_ratio | enable_distribution_ratios | exports_power |
| self_consumption_ratio | enable_distribution_ratios | — |
| export_share | enable_distribution_shares | exports_power |
| self_consumption_share | enable_distribution_shares | — |
| charging_share_from_&lt;source&gt; *(battery)* | enable_charging_source_shares | — |

### Consumer device (per instance)
| Sensor key | Option key |
|---|---|
| operating_cost_rate | calculate_cost_rates |
| levelized_operating_cost_rate | calculate_levelized_cost_rates |
| power_share_from_&lt;source&gt; | enable_power_source_shares |

### Diagnostics
| Sensor key | Option key |
|---|---|
| available_power | debug_power_entities |

---

## 6. Option storage schema

Flat per‑scope leaf‑key lists; independent, no inheritance.

```python
entry.options = {
    "schema": 2,
    "scopes": {
        "combined":  [...leaf keys...],
        "grid":      [...],
        "pv_system": [...],
        "battery":   [...],
        "consumer":  [...],
    },
    "debug_power_entities": False,   # global
}
```

Resolution (single source of truth):

```python
def resolve_scope(options: dict, scope: str) -> set[str]:
    return set(options.get("scopes", {}).get(scope, []))
```

---

## 7. Read side — scope‑aware gating (`sensor.py`)

`OptionsWrapper` becomes scope‑aware; `_SENSOR_OPTION_GATE` keeps its shape but
points at the new keys; `_option_gated_out` takes a scope.

```python
class OptionsWrapper:
    def __init__(self, options: dict) -> None:
        self._options = options
        self._by_scope = {
            s: resolve_scope(options, s)
            for s in ("combined", "grid", "pv_system", "battery", "consumer")
        }

    def check(self, key: str, scope: str = "combined") -> bool:
        if key == CONF_ENABLE_DEBUG_ENTITIES:
            return bool(self._options.get(key, False))
        return key in self._by_scope.get(scope, set())


def _option_gated_out(description, options, scope) -> bool:
    gate = _SENSOR_OPTION_GATE.get(description.key)
    return gate is not None and not options.check(gate, scope)
```

Each setup loop passes its scope: hub → `"combined"`, grid → `"grid"`, PV →
`"pv_system"`, battery → `"battery"`, consumer → `"consumer"`. Dynamic sensors
pass their owner's scope. `_sync_entity_enabled_state` is unchanged — it already
disables/re‑enables based on the resolved "wanted" set.

---

## 8. Options flow (`config_flow.py`)

**Single form**, with one collapsible **section** per shown scope plus a
diagnostics section, and one Submit button (HA `data_entry_flow.section`).

```
async_step_init → async_show_form(step_id="init", schema = {
   section("combined")     (always)
   section("grid")         (if grid subentry exists)
   section("pv_system")    (if ≥1 PV)
   section("battery")      (if ≥1 battery)
   section("consumer")     (if ≥1 consumer)
   section("diagnostics")  (always; debug toggle)
})
on submit → feasibility check
            → ok:       async_create_entry(data=new_options)   # one reload
            → problems: re-show the form with errors["base"] = reconfigure_adapters_first
```

Each section's schema is `build_scope_schema(scope, current)` (categories from
`SCOPE_SUPPORTED_OPTIONS[scope]`, pre‑filled). Section fields arrive nested under
the section key; `collect_scope_selection` turns each back into a leaf list.
Scopes whose device type is absent keep their stored value. The under‑configured
case **blocks** (re‑shows the form with an error) rather than saving.

No "use default selection" toggle; each scope is edited directly and
independently.

---

## 9. Initial config flow seeding (`async_step_user`)

Name‑only step, seeding sensible per‑scope defaults (intersected with each
scope's supported set):

```python
DEFAULT_SELECTION = {
    "calculate_cost_saving_rates",
    "accumulate_cost_saving_rates",
    "enable_distribution_power",
    "enable_distribution_ratios",
    "enable_distribution_shares",
    "enable_charging_source_shares",
    "enable_power_source_shares",
    "enable_export_compensation_rate",
    "accumulate_export_compensation",
}
options = {
    "schema": 2,
    "scopes": {
        s: sorted(DEFAULT_SELECTION & SCOPE_SUPPORTED_OPTIONS[s])
        for s in ("combined", "grid", "pv_system", "battery", "consumer")
    },
    "debug_power_entities": False,
}
```

(Defaults are a starting point — tune before implementation if desired.)

---

## 10. Migration (`MINOR_VERSION` 1 → 2)

Pre‑release, so **history is not preserved** — entities are recreated. Migration
only needs to leave the entry in the new schema with behaviour roughly matching
the old global selection. Best‑effort mapping:

```python
async def async_migrate_entry(hass, entry):
    if entry.minor_version < 2:
        old = entry.options
        old_leaves = set(
            old.get("calculate_instantaneous_rates", [])
            + old.get("calculate_instantaneous_saving_rates", [])
            + old.get("calculate_accumulated_entities", [])
        )
        if old.get("enable_power_shares"):
            old_leaves |= {
                "enable_distribution_ratios",
                "enable_distribution_shares",
                "enable_charging_source_shares",
                "enable_power_source_shares",
            }
        # watt sensors were always-on before → keep them
        old_leaves.add("enable_distribution_power")
        # export compensation used to ride on the cost-rate keys
        if "calculate_cost_rates" in old_leaves:
            old_leaves.add("enable_export_compensation_rate")
        if "accumulate_cost_rates" in old_leaves:
            old_leaves.add("accumulate_export_compensation")

        scopes = {
            s: sorted(old_leaves & SCOPE_SUPPORTED_OPTIONS[s])
            for s in ("combined", "grid", "pv_system", "battery", "consumer")
        }
        hass.config_entries.async_update_entry(
            entry,
            options={
                "schema": 2,
                "scopes": scopes,
                "debug_power_entities": bool(old.get("debug_power_entities", False)),
            },
            minor_version=2,
        )
    return True
```

Bump `MINOR_VERSION = 2` in `PowerInsightConfigFlow`.

---

## 11. Engine additions (`power_insight.py`)

Mostly already present:

- `grid_adapters_import_power` → `{grid_uid: combined_grid_import}` ✅ exists
- `grid_adapters_export_power` → `{grid_uid: combined_grid_export}` ✅ exists
- **New:** `grid_adapters_export_compensation_rate` →
  `{grid_uid: combined_export_compensation_rate}` (uid‑keyed wrapper so the grid
  device can use the standard adapter/integration sensor classes).

No change to the calculation logic — the moved sensors read the same combined
properties, just attached to the grid device. Add a short comment at the
`grid_adapter` slot documenting that **one grid per entry is intentional**, and
keep the `grid_already_configured` config‑flow guard.

---

## 12. Sensor platform changes (`sensor.py`)

- Add grid `import_power` / `export_power` descriptions to
  `POWER_INSIGHT_GRID_ADAPTER_SENSORS` (value_fn → the uid‑keyed grid power
  props; standard `PowerInsightAdapterSensor`).
- Move `export_compensation_rate` (rate) into
  `POWER_INSIGHT_GRID_ADAPTER_SENSORS` and `total_export_compensation` into
  `POWER_INSIGHT_GRID_ADAPTER_INTEGRATION_SENSORS`; remove the two combined
  export descriptions from the hub tuples.
- Update `_SENSOR_OPTION_GATE` to the new keys (section 5).
- Pass the scope into `_option_gated_out` / `OptionsWrapper.check` in each loop;
  gate the dynamic battery (`enable_charging_source_shares`) and consumer
  (`enable_power_source_shares`) sensors accordingly.
- `_sync_entity_enabled_state`, `_add` accumulation: unchanged.

---

## 13. Feasibility check (per scope)

`check_options_feasibility` evaluates each subentry against **its scope's**
resolved options: e.g. enabling levelized categories for `pv_system` requires
each PV's lifetime values; enabling cost rates for `grid` requires a price
entity on the grid. Errors name the specific device type + missing data.

---

## 14. Translations (`en.json`)

Add under `options.step`:
- `init` — menu title + `menu_options` (combined, grid, pv_system, battery,
  consumer, diagnostics, save).
- one step per scope with `data` / `data_description` for the categories it
  shows.
- `save` step (confirmation).

Add `data` labels/descriptions for all new category keys. Remove obsolete
`enable_power_shares` strings.

---

## 15. Testing plan

- **Migration:** old flat options → new `scopes` shape; `minor_version == 2`.
- **Resolution:** `resolve_scope` returns the right set; absent scope → empty.
- **Per‑type gating:** a PV override enabling levelized creates PV levelized
  sensors; battery (not enabled) does not. Grid gets import/export power +
  export compensation; combined no longer has export compensation.
- **Disable/re‑enable** across a per‑scope options change (extend the existing
  `test_disabling_option_disables_entity_but_keeps_it`).
- **Feasibility:** levelized enabled for `pv_system` with a PV missing lifetime
  values flags that PV only.
- **Flow:** menu lists only present device types; each scope step round‑trips.
- Update `tests/conftest.py` `BASE_OPTIONS` / `FULL_OPTIONS` to the new schema.

---

## 16. Out of scope / future

- **CO₂ track.** `calculate_co2_*` / `accumulate_co2_*` constants exist but are
  unwired. This taxonomy has room for a parallel "CO₂ rates / savings / totals"
  set of categories per scope when the engine side is ready.
- **Multiple grids in one entry.** Not supported and not planned — two grid
  connections are modelled as two config entries.

---

## 17. Implementation checklist (file by file)

- `const.py` — new option keys; `SCOPE_SUPPORTED_OPTIONS`; remove
  `enable_power_shares` + container keys; note CO₂ keys remain dormant.
- `power_insight.py` — `grid_adapters_export_compensation_rate` wrapper; comment
  on single‑grid intent.
- `sensor.py` — grid import/export power + moved export‑compensation sensors;
  `_SENSOR_OPTION_GATE` remap; scope‑aware `OptionsWrapper`/`_option_gated_out`;
  dynamic‑sensor scope gating.
- `config_flow.py` — menu options flow with per‑scope steps; scope‑filtered
  selectors; per‑scope feasibility; `MINOR_VERSION = 2`; updated initial seeding.
- `__init__.py` — `async_migrate_entry` implementation.
- `translations/en.json` — menu + per‑scope steps + new category strings.
- `tests/` — conftest option fixtures; migration, per‑scope gating, flow tests.
