# Entity naming scheme

This is the reference for how Power Insight names its sensors. New sensors must
follow it so the entity set stays predictable and self-explanatory. The
canonical list of shipped sensors lives in the
[Entity reference](../entities.md); this page is the *rule set* behind it.

## Name = device + entity

Every sensor sets `_attr_has_entity_name = True`, so Home Assistant builds the
friendly name as **`{device} {entity name}`**:

| Scope | Device name | Example entity name | Full name |
|---|---|---|---|
| Hub (whole home) | `PowerInsight` | `Combined cost rate` | *PowerInsight Combined cost rate* |
| Per adapter | `PowerInsight {device}` | `Export power` | *PowerInsight Rooftop Export power* |

Consequences for the `name=` string on a `PowerInsightSensorDescription`:

- **Never repeat the device or adapter** in the entity name — it is already the
  prefix (write `Export power`, not `PV export power`).
- **Whole-home aggregates carry the `Combined` prefix** (`Combined cost rate`).
  The hub device is just `PowerInsight`, so the prefix is what distinguishes an
  aggregate from a same-named per-device sensor at a glance.
- Sentence-case the name (`Export compensation rate`), matching Home Assistant
  conventions.

## `key` vs. `name`

- **`name`** is the display string (above). Changing it is cosmetic.
- **`key`** feeds the `unique_id` (`{entry}_{key}` for the hub,
  `{entry}_{uid}_{key}` per adapter) and therefore the **`entity_id`**. Changing
  a `key` changes the entity id and **breaks history** for existing installs, so
  keep `key` a stable, lower_snake_case echo of the `name`.

When you rename a `key`, also update: the `_SENSOR_OPTION_GATE` map (or the
sensor silently loses its option gating), `COMBINED_LEDGER_ADAPTER_KEYS` /
`LEVELIZED_TOTAL_KEYS` if it is a levelized total, any hard-coded entity-id
assertions in `tests/`, and the doc tables under `docs/`.

## Vocabulary

Pick the noun that matches the quantity — do not invent synonyms.

| Suffix | Unit | Meaning |
|---|---|---|
| `… power` | W | An instantaneous power value. |
| `… ratio` | % | A flow as a fraction of the **scope's own power** — a device's own production/throughput, or gross power for the whole home. |
| `… share` | % | This device's slice of a **home-wide total** for that flow. |
| `… rate` | currency/h | A per-hour money (or CO₂) flow. |
| `Total …` | currency | A `TOTAL` sensor accumulating a `… rate` over time. |
| `… from {source}` | % | A dynamic per-source attribution sensor (one per source). |

`ratio` and `share` are **not interchangeable** — see
[Power distribution](../concepts.md#the-four-channels) for the precise
denominators. Prose that describes a `ratio` as "share of total home power" (or
vice versa) is a bug.

## Cross-device consistency rules

- **Grid money is symmetric** around the two sides of the meter:
  `Import power` · `Import cost rate` · `Total import cost` mirror
  `Export power` · `Export compensation rate` · `Total export compensation`.
  The grid's own cost is an *import* cost — it is distinct from a producer's
  *operating* cost, which is why it does not share that name.
- **Producers** (PV, battery) report running electricity cost as
  `Operating cost rate` / `Total operating cost`, with `Levelized …` variants.
- **Per-source attribution** sensors read **`{Category} share from {source}`** —
  `Charging share from Grid` (battery), `Power share from PV` (consumer). Both
  answer "how much of *this device's* {charging|power} comes from that source?".

## Config-flow labels track entity names

The option that creates a sensor should use the same words the entity uses
(`strings.json` / `translations/*.json`). For example the toggle that creates
`Total export compensation` is labelled *Total export compensation*, not
*Accumulated export compensation*.
