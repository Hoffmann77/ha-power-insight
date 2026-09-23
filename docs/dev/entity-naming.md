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
| Whole home | `{title} Combined` | `Cost rate` | *Home Combined Cost rate* |
| Per adapter | `{title} {device}` | `Import power` | *Home Grid Import power* |

Consequences for the `name=` string on a `PowerInsightSensorDescription`:

- **Never repeat the device or adapter** in the entity name — it is already the
  prefix (write `Production to grid`, not `PV production to grid`).
- **Whole-home aggregates live on the `{title} Combined` device** and do *not*
  carry a `Combined` prefix themselves — the device name supplies it.
- Sentence-case the name (`Export compensation rate`), matching Home Assistant
  conventions.

## `key` vs. `name`

- **`name`** is the display string (above). Changing it is cosmetic.
- **`key`** feeds the `unique_id` (`{entry}_{key}` for the hub,
  `{entry}_{uid}_{key}` per adapter). Changing a `key` orphans the registry
  entry and **breaks history** for existing installs, so keys stay stable even
  when the `name` changes — they need not echo it.
- The **`entity_id`** is generated from the full name once, when the entity is
  first registered, and is then kept by the entity registry. Renaming `name`
  therefore leaves existing installs' entity ids alone and only changes the
  slug new installs get.

When you rename a `key`, also update: the `_SENSOR_OPTION_GATE` map (or the
sensor silently loses its option gating), `COMBINED_LEDGER_ADAPTER_KEYS` /
`LEVELIZED_TOTAL_KEYS` if it is a levelized total, any hard-coded entity-id
assertions in `tests/`, and the doc tables under `docs/`.

## Vocabulary

Pick the noun that matches the quantity — do not invent synonyms.

| Pattern | Unit | Meaning |
|---|---|---|
| `… power` | W | An instantaneous power value of the scope itself. |
| `{Verb} to {destination}` | W | Where a provider's output goes (see below). |
| `… ratio` | % | A flow as a fraction of the **scope's own power** — a device's own production/throughput, or gross power for the whole home. |
| `Share of {channel}` | % | This device's slice of a **home-wide total** for that flow. |
| `… rate` | currency/h | A per-hour money (or CO₂) flow. |
| `Total …` | currency | A `TOTAL` sensor accumulating a `… rate` over time. |
| `… from {source}` | % | A dynamic per-source attribution sensor (one per source). |

`ratio` and `share` are **not interchangeable** — see
[Power distribution](../concepts.md#the-four-channels) for the precise
denominators. Prose that describes a `ratio` as "share of total home power" (or
vice versa) is a bug.

## Power distribution: name the direction

A provider's distribution sensors describe **where its output goes**, never
what the device consumes itself. A bare `Standby power` on a battery reads as
the battery's own idle draw, when it actually is battery discharge feeding a
PV inverter's night draw — so the name must carry the direction.

| Provider | Verb |
|---|---|
| Grid | `Import` |
| PV system | `Production` |
| Battery | `Discharge` |

| Channel | W | ratio % | share % |
|---|---|---|---|
| CON | `{Verb} to home consumption` | `{Verb} to home consumption ratio` | `Share of home consumption` |
| CHG | `{Verb} to batteries` | `{Verb} to batteries ratio` | `Share of battery charging` |
| STB | `{Verb} to system standby` | `{Verb} to system standby ratio` | `Share of system standby` |
| EXP | `{Verb} to grid` | `{Verb} to grid ratio` | `Share of grid export` |

- **home consumption** — household appliances (the CON channel). Not
  "self-consumption", which users read as the device consuming itself.
- **system standby** — the idle draw of the energy system's own equipment. The
  `system` is deliberate: appliances on standby are home consumption.
- The **Combined** device uses the channel noun without a verb:
  `Home consumption power`, `Battery charging power`, `System standby power`
  (+ `… ratio`).
- The grid's own meter sensors (`Import power`, `Export power`) keep their
  names — they describe the grid itself, not a destination.

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
*Total export compensation*.
