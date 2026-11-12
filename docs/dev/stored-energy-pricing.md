# Stored-energy pricing

When a battery charges from a PV system, two devices share one result: the
PV produced the energy, the battery will later use it to replace grid power.
This page explains how the engine splits the saving between them: the
question it answers, the algorithm step by step, how the result is booked in
every savings family, and where it lives in the code.

The decision itself is recorded in
[Engine calculation decisions](engine-calculations.md#savings-are-booked-per-device-at-the-moment-they-are-realized)
("a battery pays for local energy what it was worth elsewhere"); the user's
side is
[What a battery pays for the solar energy it stores](../advanced/costs-and-savings.md#what-a-battery-pays-for-the-solar-energy-it-stores).

## The question

A device's saving is measured against **the home without that device**. For
a PV system that is easy: without it, the house would have imported what the
PV supplied. For a battery it needs one more step: without the battery, the
PV would still be there, and the energy the battery stored would have gone
somewhere else.

The engine used to treat that energy as free, its marginal price. That
credited the battery with whatever the PV gave up, typically its feed-in
income: battery savings came out too high and PV savings too low, by the same
amount. Now the battery **pays the source what the energy was worth
elsewhere**, and the source earns it.

"Elsewhere" is answered with one rule, the same for every device:

> Remove the battery, keep every other reading exactly as it is, and let the
> grid absorb the difference.

The engine does not imagine a better-run home. It cannot: what the optimal
home would have done depends on prices, production and consumption over time,
while the engine sees one reading at a time. And it should not: a saving says
what a device is worth in *this* home, not in an idealised one. The single
exception is a control decision the user tells the engine about,
[curtailment at negative prices](#step-3-the-price-per-source), which is a
fact about the home rather than an assumption.

## What goes in

Everything is per reading, from values the engine already has:

| Symbol | What it is | Where it comes from |
|---|---|---|
| `L_s` | Watts local source `s` (a PV system or a discharging battery) put into batteries | the provenance allocation, charging channel (`source_adapters_charging_power`) |
| `L` | `Σ L_s`, all local watts into batteries | |
| `G` | Grid watts into batteries | the same channel, grid column |
| `I` | Grid import, `0` while exporting | the grid reading, balanced |
| `E` | Grid export, `0` while importing | the grid reading, balanced |
| `cap` | The grid's export limit in W, `∞` when none is set | grid setting **Export limit** |
| `p` | Grid tariff | grid **Electricity price** |
| `f_s` | Source `s`'s feed-in rate | its **Export compensation per kWh** |
| exports `s` | Whether `s` may export at all | its **Exports to the grid** |
| curtailed `s` | Whether the home curtails `s` at negative prices (PV only) | its **Curtailed at negative prices** |

"Balanced" means after metering imbalance is resolved by meeting in the
middle, like every other derived value, so the watts here always add up with
the provenance rows.

## The algorithm

Without the batteries, the watts they took would have gone to the grid
instead. They go, in order, to three places, each with its own value.

### Step 1: covering the import

The batteries' own grid watts `G` are freed first: they simply would not have
been drawn. That leaves an import of `I − G` for the local watts to cover:

```
import room  R_i = max(0, I − G)
covered      a   = min(1, R_i / L)
```

A fraction `a` of every source's stored watts would have replaced import,
worth the tariff `p`.

`G` is subtracted because those watts are already priced at the tariff as the
battery's own grid draw. Counting the full import `I` as room would let the
same imported watt be avoided twice.

### Step 2: exporting up to the limit

The remaining `1 − a` would have been exported, but only by sources that may
export, and only up to the room left under the export limit:

```
to export    X = (1 − a) × Σ L_s over sources that may export
export room  R_e = max(0, cap − E)          (∞ without a limit)
exported     b = min(1, R_e / X)            (1 when X = 0)
```

The rest of an exporter's remainder, and all of a non-exporter's, would have
been curtailed, worth nothing. `max(0, …)` covers a meter that reads a little
above a configured limit: the room is empty, never negative.

### Step 3: the price per source

```
price_s = a × w(p)  +  (1 − a) × b × w(f_s)     if s may export
price_s = a × w(p)                              otherwise

w(x) = max(x, 0)   if the home curtails s at negative prices
w(x) = x           otherwise
```

`price_s` is in EUR/kWh; the battery pays `L_s × price_s`, and source `s`
earns exactly that.

`w` is the curtailment floor. With the field off, a negative tariff or feed-in
rate is passed through, so the battery is *paid* for taking the energy: it is
what kept the house importing or exporting at that price. With it on, the
home would have curtailed the PV instead, so the energy was worth nothing.
The floor only touches the counterfactual. What the PV actually did is still
valued as it happened: PV serving the house at a negative tariff still shows
that loss.

Steps 1 and 2 share each room **in proportion to watts**, across sources and
across batteries. That is what makes splitting one PV system into two
identical halves change nothing, which `test_laws.py` checks. It also means a
source that may not export gets no priority on the import room, although an
optimiser would give it some. That is a deliberate simplification, the same
proportional rule the provenance allocation uses.

### The matrix this produces

| Situation while the battery charges from PV | `a` | `b` | Battery pays per kWh |
|---|---|---|---|
| Home is exporting, below the limit | 0 | ≤ 1 | `b × f` |
| Home is already exporting at the limit | 0 | 0 | nothing |
| Home is importing more than the battery takes | 1 | – | `p` |
| Home is importing, but less than the battery takes | < 1 | ≤ 1 | `a × p + (1 − a) × b × f` |
| PV may not export | any | – | `a × p` |
| Negative `p` or `f`, curtailment off | any | any | that price, so the battery is paid |
| Negative `p` or `f`, curtailment on | any | any | the negative part counts as 0 |

## Booking it

The price is booked as a **transfer between two devices' savings**, in every
family of `adapters_*saving_rates` and through them in the financial returns:

| Device, role | Marginal saving | Levelized saving |
|---|---|---|
| Source, producing | `CON_s × p + L_s × price_s` | `CON_s × (p − LCOE_s) + L_s × (price_s − LCOE_s)` |
| Battery, charging | `−(G_b × p + Σ_s L_bs × price_s)` | the same |
| PV, in standby | `−(draw × its source mix)` | the same, levelized |

`CON_s` is what the source put into the house, `G_b` and `L_bs` are battery
`b`'s own grid and local watts. The marginal own price of local energy is 0,
so the first row's marginal form is the levelized one with `LCOE = 0`.

Four properties of this booking matter:

- **The battery's price never depends on a lifetime cost.** What the energy
  was worth elsewhere has nothing to do with what it cost to make. So the
  battery pays the same at the margin, levelized and corrected; the source
  carries its own `LCOE` on every watt it produced, the stored ones included.
  A feed-in rate below that `LCOE` is then the source's loss, where it
  belongs, not the battery's.
- **Corrections stay exact.** In `adapters_levelized_saving_rate_components`
  the battery's whole charge cost sits under the grid key, which never
  scales. The source's part splits into what it earned (grid key) and its own
  `LCOE` on everything it produced (its own key), so multiplying each part by
  its key's factor still gives the corrected saving.
- **Nothing combined moves.** The battery's saving drops by exactly what the
  sources' rise, so `combined_saving_rate`, the financial returns, the channel
  cost buckets and the cost-conservation invariant are untouched. The
  identity `combined_saving_rate = combined_avoided_cost_rate −
  combined_device_operating_cost_rate` still holds, because the transfer
  cancels inside it.
- **Operating cost keeps its meaning.** `source_adapters_coo_rates` /
  `lcoo_rates` stay at the cost of the mix: what running the hardware cost to
  produce, the ledger's view. Only the savings, which attribute a result
  between devices, use the price from elsewhere. While a battery charges from
  PV, its saving is therefore no longer simply minus its operating cost.

## Edge cases

- **Missing tariff.** The tariff is needed only for the covered part `a`.
  While the house exports, `a = 0`, and the price is the feed-in rate alone,
  known without a tariff. While it imports, the battery's and the source's
  savings go blank together, never one without the other. Pinned by
  `TestAMissingPriceBlanksOnlyWhatNeedsIt` and
  `TestStoredEnergyWhileExportingNeedsNoTariff`.
- **Unavailable meter.** Gross power is unknowable, so every savings map is
  `None` as a whole, as before.
- **Nothing stored from local sources.** No price is computed, and every
  saving is what it was before this rule existed.
- **A battery charging from another battery.** The discharging battery is a
  local source like any other, at its own feed-in rate if it may export.
- **No limit set.** `cap = ∞`, so everything not covering an import is
  exported (by sources that may).

## Worked example

Grid tariff 0.30 EUR/kWh, export limit 600 W. *Roof* (LCOE 0.10) may export
at 0.08; *Balcony* (LCOE 0.12) may not export. The battery may charge from
both. The readings: the grid imports 300 W, Roof makes 2000 W, Balcony 500 W,
the battery charges at 1500 W; the base load is the remaining 1300 W.

**Provenance** (the allocator, unchanged): the battery takes Roof 1200 W and
Balcony 300 W, in proportion to their output. The base load gets the 300 W
import, Roof 800 W and Balcony 200 W.

**Step 1.** `G = 0`, so `R_i = 300 W`. `L = 1500 W`, so `a = 300 / 1500 =
1/5`: a fifth of each source's stored watts would have covered the import.

**Step 2.** Roof's remainder is `4/5 × 1200 = 960 W`; Balcony's 240 W cannot
be exported. `R_e = 600 − 0 = 600 W`, so `b = 600 / 960 = 5/8`. The other
360 W of Roof, and Balcony's 240 W, would have been curtailed.

**Step 3.**

| Source | Price per kWh | Battery pays |
|---|---|---|
| Roof | `1/5 × 0.30 + 4/5 × 5/8 × 0.08 = 0.10` | `1.2 kW × 0.10 = 0.120` EUR/h |
| Balcony | `1/5 × 0.30 = 0.06` | `0.3 kW × 0.06 = 0.018` EUR/h |

**Savings** (EUR/h):

| Device | Marginal | Levelized | Before this rule (marginal / levelized) |
|---|---|---|---|
| Roof | `0.8 × 0.30 + 0.120 = 0.360` | `0.8 × 0.20 + 1.2 × (0.10 − 0.10) = 0.160` | 0.240 / 0.160 |
| Balcony | `0.2 × 0.30 + 0.018 = 0.078` | `0.2 × 0.18 + 0.3 × (0.06 − 0.12) = 0.018` | 0.060 / 0.036 |
| Battery | `−0.138` | `−0.138` | 0 / −0.156 |
| **Combined** | **0.300** | **0.040** | **0.300 / 0.040** |

The combined figures are unchanged. Balcony's levelized saving shows what its
stored energy really earns: 0.06 per kWh against an LCOE of 0.12, a loss
that used to be hidden in the battery as 0.12 per kWh. The battery's
operating cost is still 0 at the margin and `1.2 × 0.10 + 0.3 × 0.12 = 0.156`
levelized, the cost of making what it stored.

## Where it lives

| Piece | What it does |
|---|---|
| `PowerInsight._stored_energy_prices` (`power_insight.py`) | Steps 1–3: `{source uid: EUR/kWh}` for every local source that charged a battery this reading; cached per snapshot. |
| `_stored_energy_paid_rate` / `_stored_energy_sold_rate` | What one battery pays, and what one source is paid (EUR/h). |
| `_battery_charge_cost_rate` | A charging battery's cost in its saving: grid watts at the tariff plus what it paid. |
| `_source_saving_rate`, `_adapter_saving_rates`, `_adapter_levelized_components` | Book it in every savings family and in the correction components. |
| `GridAdapter.export_limit`, `PvAdapter.curtails_at_negative_prices` | The two settings, from `CONF_EXPORT_LIMIT` and `CONF_CURTAILS_AT_NEGATIVE_PRICES` via `adapter_models.py`; both optional, older entries read as no limit and not curtailed. |

How it is tested:

- `tests/engine/manual/test_battery_pricing.py` has one hand-derived class per
  row of the matrix (exporting, importing, export limit, negative tariff with
  curtailment off and on, battery to battery).
- `tests/engine/automatic/test_identities.py` restates steps 1–3 as
  `stored_energy_prices` and checks every savings family against it over the
  random homes, which include negative prices, export limits and curtailed PV
  systems.
- `test_laws.py` checks that it scales with power (the export limit scales
  too) and price, survives renaming and splitting a PV system, and that the
  components still add up before and after correction.

## Not covered

- **History carried over from a device's app** is booked the same way, at one
  price: period totals cannot tell whether the house was importing or
  exporting at the moment a battery charged, so a battery pays each PV system
  its feed-in rate (nothing if it may not export). A battery added later, or
  a pair where either device entered its own savings, keeps the rule from
  before. See [Carried-over history](carried-over-history.md).
- **CO₂** is not attributed this way, as no CO₂ sensor exists yet.
- **A battery source that may not export.** Without the receiving battery it
  would have kept its energy for later rather than curtail it. That later
  worth is unknowable from one reading, so its export part counts as nothing.
- **Fixed rates.** The feed-in rate and the export limit are fixed settings.
  Both fit the algorithm unchanged as live readings, should they become
  entities. A negative feed-in rate is already handled by the engine, but
  the setting does not accept one yet.
