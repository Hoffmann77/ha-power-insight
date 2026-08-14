# Handoff: interactive reference-case diagram

A design brief for an interactive power-flow graphic to embed in these docs.

## Context

Power Insight is a Home Assistant integration that answers questions like
*"where did the power my battery just charged with actually come from?"* and
*"what did that save me?"*. The hard part is a pure-Python calculation engine
that, every snapshot, splits the house's power between grid, PV strings,
batteries, consumers and the unmetered base load — honouring per-device rules
like *"this battery may only charge from solar"*.

Several answers the engine gives are **modelling choices, not arithmetic**: more
than one result is defensible. So we are building a set of **reference cases** — a
handful of small, deliberately-chosen wirings whose every value is derived by
hand and published here as the engine's specification of record. The engine is
then validated against them in CI.

The goal is that a user who thinks the engine is wrong can argue with the
*documented model* instead of reading Python. That only works if the reference
cases are legible, which is where this graphic comes in: a wall of JSON and
fractions is not something anyone will argue with.

There are 4 reference cases and 10 snapshots today, in `docs/spec/cases/`.

## What to build

An interactive diagram that renders one reference case, embedded in a docs page.

**v1 — the scope of this brief**

- A **topology graphic**: the devices of one reference case and the power flowing
  between them. Flow direction and magnitude both matter; edge width should
  carry watts.
- A **snapshot navbar above the graphic** to switch between the case's
  snapshots. Switching keeps the wiring and changes the flows.
- **Click a device** → it highlights, and a panel shows that device's values:
  its configuration, its role this snapshot, its reading, and either where its
  output went (if it is a source) or where its power came from (if it is a
  sink). Keyboard-selectable too, please, not click-only.

**v2 — since built**

A second navbar selecting which **value category** is displayed. It landed as
the engine's own four layers, taken from `docs/spec/properties.json`: the
readings and totals, source provenance, the channel split, and the monetary
model. Each re-labels the same topology and lists every value the engine
published for that snapshot underneath — because the graph can only ever
re-label its nodes, and most of what the integration computes has nowhere to
live on the picture.

## The one thing that will bite you

**A device's role changes between states.** The engine classifies every adapter
each snapshot from the *sign* of its power reading:

| reading | grid | PV | battery | consumer |
| --- | --- | --- | --- | --- |
| positive | importing → **source** | producing → **source** | discharging → **source** | (never a source) |
| negative | exporting → **sink** | standby draw → **sink** | charging → **sink** | load → **sink** |
| exactly 0 | idle — in neither group | idle | idle | idle |

So in `pv-export/export_surplus` the grid is a **sink** being fed by the house,
while in `pv-self-consumption/sunny_partial` the same grid is the largest
**source**.
A layout that hard-codes "grid on the left, loads on the right" will break on
half the cases. The sides have to be derived from the data.

There is also a **virtual node**: the *home base load* is everything consumed
without a sensor on it. It is a sink, it competes for power like any other, and
it has no device — it appears in `home_base_load_power` and
`home_base_load_source_shares` rather than in the adapter list. It should be
drawn, and visibly distinguished from real devices.

## Data contract

One JSON file per case in `docs/spec/cases/`, plus `index.json` listing them in
ladder order and `coverage.json` recording which rungs each property is settled
by. The diagram component needs neither of the latter two — they drive the
tables on the section index — but `index.json` is the authority on case order.

Read `group-captivity.json` and `mixed-export-house.json` first — between them
they exercise every shape. `grid-only.json` is the other end of the range: one
adapter, and still a value for every property.

```jsonc
{
  "id": "group-captivity",
  "title": "Group captivity",
  "summary": "…prose for the page…",
  "decides": ["…the modelling choices this case pins…"],

  "topology": [
    { "uid": "grid",  "kind": "grid",    "config": { "has_price_entity": true } },
    { "uid": "east",  "kind": "pv",      "config": { "lcoe": "1/10", "exports_power": true } },
    { "uid": "bat_a", "kind": "battery", "config": { "lcos": "3/20",
                                                     "charge_from_adapters": ["east", "west"] } }
  ],

  "states": [
    {
      "id": "hall_tight_pair",
      "note": "…one line on what makes this snapshot interesting…",
      "readings": { "grid": "200", "east": "100", "bat_a": "-100" },
      "price": "3/10",
      "expectations": [
        { "property": "gross_power", "value": "400",
          "derivation": [], "certification": { "status": "unverified" } },
        { "property": "sink_adapters_source_shares",
          "value": { "bat_a": { "grid": "0", "east": "1/2", "west": "1/2" } },
          "derivation": [], "certification": { "status": "unverified" } }
      ]
    }
  ]
}
```

Four things to know about it:

**Every number is an exact-rational string.** `"1/2"`, `"-600"`, `"3/20"`,
`"400"`. Never a JSON float — the whole point is that these values are exact and
comparable by hand. Parse by splitting on `/`. Display should probably show both
forms (`1/2` and `50%`, or `8/15` and `0.533`), since the fraction is what a
reader checks and the decimal is what they intuit.

**Edge flows are derived, not stored.** There is one source of truth — the
share matrix — and watts come from multiplying it out:

```
flow(source → sink) = sink_adapters_source_shares[sink][source] × |readings[sink]|
flow(source → home) = home_base_load_source_shares[source]      × home_base_load_power
```

**`derivation` is empty and `certification.status` is `"unverified"` today.**
Values are currently engine-generated placeholders; the maintainer certifies
them by hand over the coming weeks, filling in `derivation` (a list of
`{text, detail?, math?, result?}` steps) and flipping status to `"verified"`.
The design should surface that distinction honestly — a reader deserves to know
which numbers a human has checked. A small badge is enough; please don't let it
dominate.

**Don't assume a fixed property list.** Every state publishes the whole
catalog today, but a property the engine cannot answer for a snapshot is left
out rather than written as null — so render what is present.

## Embedding — as built

The site moved from MkDocs Material to **Docusaurus 3** while this component was
being designed, so the constraints below are the ones that actually applied. The
implementation lives in `website/src/components/CaseDiagram/`.

- **Build-time JSON imports, never `fetch`.** A page imports its case data and
  passes it in as a prop. That removes the base-path problem entirely (the site
  is served under `/ha-power-insight/`, so any absolute fetch would 404), makes a
  missing or malformed case a *build* failure rather than a runtime one, and lets
  the whole diagram server-render into the static HTML.
- **Data is passed in, not imported by the component.** `docs/` is what
  Docusaurus snapshots when a version is cut; `website/src/` is shared across
  every version. Keeping the case data on the `docs/` side and threading it
  through a prop is what stops an old version's page from rendering with today's
  numbers.
- **Server-rendering, so no `window` at render time.** State comes from props
  and `useState`; the URL is read in a mount effect, never during render, so the
  server markup and the first client render agree. `<BrowserOnly>` is
  deliberately *not* used — it would opt out of the SSR that makes the diagram
  visible without JavaScript.
- **Theming is pure CSS.** Colours are custom properties on the component root,
  redefined under `:global([data-theme='dark'])`. No JavaScript reads the theme,
  so the Docusaurus toggle just works and there is nothing to hydrate.
- **Inline SVG**, one `viewBox`, `width: 100%` — crisp at any zoom, themeable
  through the same variables, and focusable per node in a way canvas is not.
- **Deep links.** The selected snapshot is mirrored into the query string
  (`?state=hall_tight_pair`), so an issue report can point at exactly the
  snapshot it means. The case is not in the query: each case has its own page,
  so the path already names it.
- These docs get read on phones: the state cards wrap, the detail panel collapses
  to one column, and the SVG scales with its container.

## Out of scope

- **Live recalculation.** The engine is Python; the browser only ever displays
  stored case values. A user-driven playground with arbitrary inputs is planned
  separately and is not this component.
- **Editing.** Read-only. Certification happens offline, on paper.

## Two open modelling questions

Both are unresolved and both live in this data. Don't design around either
answer — just don't let the diagram imply one is settled.

1. In `group-captivity/unsatisfiable_overlap`, captive demand (300 W) exceeds local supply
   (200 W), so some restriction must be broken. The engine currently serves
   `bat_c` in full and pushes a 50 W deficit onto each of `bat_a` and `bat_b`.
   Whether that is the intended priority is undecided.
2. In `captive-battery/source_in_standby`, `home_base_load_power` includes the 400 W that
   `bat_1` drew but could not legally be attributed — so the "unmetered" load
   includes a device that very much has a meter on it.
