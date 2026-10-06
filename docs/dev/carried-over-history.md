# Carried-over history

Users adopt Power Insight years after their PV system or battery went in.
The device's app knows what happened since; the device forms' **Already
accumulated** section carries it into the running totals, as kWh, as
amounts, or both.

This page was the plan. It is implemented: the decisions are recorded in
[Engine calculation decisions](engine-calculations.md#history-carried-over-from-a-devices-app),
the user's side is [Carried-over history](../history.md), and this page keeps
a map of the code and what is still open.

## The decisions

Four notes under *The monetary model*, each covered by integration tests:

- history is added when a total is reported, never accumulated;
- history is split by the engine's allocator, on period totals (no grid
  import as a source, no battery charging another, own export
  pre-assigned), solved on save and then frozen;
- entered amounts are the truth; only their cost of energy follows
  corrections, and a total missing a term carries nothing;
- a removed device keeps its history, at its last price.

## Where it lives

| Piece | What it does |
| --- | --- |
| `history.py` | Pure Python. `solve` splits a period's kWh with `allocate` and deals out home-level amounts, or returns the refusals; `history_totals` prices one device's record at the current corrected LCOE / LCOS. |
| `history_store.py` | The Home Assistant side. Re-solves at setup whenever the entered figures changed, stores the result in the config entry, prices it once per setup for the sensors, and checks a form's figures with everyone else's (`check_view`). |
| `config_flow.py` | The two *Already accumulated* sections, one per route, energy (kWh) and amounts (`HISTORY_SECTIONS`, `history_section`), merged into one stored history (`entered_history`), and the check on save (`history_errors`). |
| `sensor.py` | `history_key` on a total's description; `native_value` adds the carried-over part, the attributes split it from the counted one. |
| `__init__.py` | Migration 1.4 → 1.5 (`counting_since` from the entity registry), and `async_sync_history` at setup. |

### Storage

| Where | What |
| --- | --- |
| Device subentry `counting_since` | When Power Insight started counting the device: the cutoff for its history. Set when the subentry is created. |
| Device subentry `history` | The figures as entered. The grid's are the whole home's (`home_fed_in`, `average_tariff`, `home_savings`, `home_export_compensation`). |
| Entry `data["history"]` | `records` (one solved record per device), `last_price` (each device's levelized price at the last setup), and the last solve's `entered`, `home` and `inputs`. A removed device's stay. |

Entered figures may disagree by the larger of 1 kWh and 1 % before they are
refused (`SLACK_KWH`, `SLACK_SHARE` in `history.py`).

Devices whose `counting_since` is within 24 hours of the grid's share one
period and are split together; a device added later stands alone and
supplies its own tariff and export.

### Tests

| File | Covers |
| --- | --- |
| `tests/integration/test_history.py` | The solve and the pricing, against hand-derived worked examples, and every refusal. Randomized: figures read off a real flow (rounded, meters 0.5 % apart) are always accepted, and whatever is accepted balances within the tolerance and keeps every restriction. |
| `tests/integration/test_history_store.py` | Solving at setup, staying frozen, removed devices, standalone devices, live prices. |
| `tests/integration/test_history_sensors.py` | Totals and attributes, whole-home totals, a reload adding nothing twice, corrections. |
| `tests/integration/test_history_flow.py` | The section in the forms, saving, refusals, and that every field and refusal has text. |

## Still open

- **A total switched on later** starts counting later than its device, and
  the time in between is in neither the carried-over nor the counted part. A
  date per sensor would close it; not worth its complexity until users ask.
- **A standalone battery with several PV systems** splits its local charging
  evenly between them: there are no shared totals to weigh by. It only
  decides which PV's LCOE prices its levelized charging.
- **Not carried over:** consumer totals (*avoided cost*, *consumption cost*)
  and PV standby cost. No app reports them per device.
- **Attribute values are codes** (`carried_over_missing: no_tariff`), not
  translated text, so they stay stable for automations.
- **Release notes:** a total seeded with the retired `set_value` service
  restores as before, at face value. Users who seeded one should subtract
  that seed before entering the history, or the two add up.
- **Found while building, not specific to history:** the combined levelized
  totals sum the per-device totals as they stood at the last *changed*
  reading, so they lag one reading behind. Harmless with live readings, which
  change constantly.
