# Handoff: interactive anchor-case diagram

A design brief for an interactive power-flow graphic to embed in these docs.

## Context

Power Insight is a Home Assistant integration that answers questions like
*"where did the power my battery just charged with actually come from?"* and
*"what did that save me?"*. The hard part is a pure-Python calculation engine
that, every snapshot, splits the house's power between grid, PV strings,
batteries, consumers and the unmetered base load — honouring per-device rules
like *"this battery may only charge from solar"*.

Several answers the engine gives are **modelling choices, not arithmetic**: more
than one result is defensible. So we are building a set of **anchor cases** — a
handful of small, deliberately-chosen wirings whose every value is derived by
hand and published here as the engine's specification of record. The engine is
then validated against them in CI.

The goal is that a user who thinks the engine is wrong can argue with the
*documented model* instead of reading Python. That only works if the anchor
cases are legible, which is where this graphic comes in: a wall of JSON and
fractions is not something anyone will argue with.

There are 4 anchor cases and 10 states today, in `docs/spec/anchors/`.

## What to build

An interactive diagram that renders one anchor case, embedded in a docs page.

**v1 — the scope of this brief**

- A **topology graphic**: the devices of one anchor case and the power flowing
  between them. Flow direction and magnitude both matter; edge width should
  carry watts.
- A **case/state navbar above the graphic** to switch between the 10 states.
  Switching state keeps the wiring and changes the flows.
- **Click a device** → it highlights, and a panel shows that device's values:
  its configuration, its role this snapshot, its reading, and either where its
  output went (if it is a source) or where its power came from (if it is a
  sink). Keyboard-selectable too, please, not click-only.

**v2 — design for it, don't build it yet**

A second navbar selecting which **value category** is displayed: power (W),
shares (%), channels, prices and rates (EUR/kWh, EUR/h), restriction deficits.
The same topology, re-labelled. Please leave room for it in the layout so it
does not need a redesign later.

## The one thing that will bite you

**A device's role changes between states.** The engine classifies every adapter
each snapshot from the *sign* of its power reading:

| reading | grid | PV | battery | consumer |
| --- | --- | --- | --- | --- |
| positive | importing → **source** | producing → **source** | discharging → **source** | (never a source) |
| negative | exporting → **sink** | standby draw → **sink** | charging → **sink** | load → **sink** |
| exactly 0 | idle — in neither group | idle | idle | idle |

So in `A-004/export_non_exporting_battery` the grid is a **sink** being fed by
the house, while in `A-001/import_mix` the same grid is the largest **source**.
A layout that hard-codes "grid on the left, loads on the right" will break on
half the cases. The sides have to be derived from the data.

There is also a **virtual node**: the *home base load* is everything consumed
without a sensor on it. It is a sink, it competes for power like any other, and
it has no device — it appears in `home_base_load_power` and
`home_base_load_source_shares` rather than in the adapter list. It should be
drawn, and visibly distinguished from real devices.

## Data contract

One JSON file per case in `docs/spec/anchors/`, plus `index.json` listing them.
Read `A-003.json` (group captivity) and `A-004.json` (export) first — between
them they exercise every shape.

```jsonc
{
  "id": "A-003",
  "title": "Group captivity (Hall's condition)",
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

**Not every property appears in every state.** The set varies by what each
state is there to demonstrate. Render what is present; don't assume a fixed list.

## Embedding

MkDocs Material 9.5, versioned with `mike`, deployed to GitHub Pages. Some hard
constraints from that:

- **No build step and no npm.** The docs CI installs `mkdocs-material` and
  `mike`, nothing else. Ship vanilla JS + CSS as static assets under
  `docs/assets/`, wired up with `extra_javascript` / `extra_css` in
  `mkdocs.yml`. No bundler, no framework.
- **No CDN.** Everything self-contained; the site should work offline.
- **`navigation.instant` is enabled.** Pages swap via XHR with no full reload,
  so `DOMContentLoaded` fires once for the whole session and your component
  will silently fail on the second visit. Initialise inside Material's
  `document$.subscribe(...)` observable (globally available) and make setup
  idempotent — tear down any previous instance first.
- **Light and dark are both live**, with an in-page toggle (`default` /
  `slate`, primary colour light blue). Read Material's CSS custom properties
  (`--md-default-fg-color`, `--md-default-bg-color`, `--md-primary-fg-color`,
  `--md-accent-fg-color`, `--md-typeset-color`) rather than hard-coding
  anything. The toggle switches without a reload, so any JS that reads computed
  colours must re-read on change.
- **`mike` puts the site under a version prefix** (`/ha-power-insight/dev/…`).
  Do **not** fetch `/spec/anchors/A-003.json` from an absolute path — resolve it
  relative to the executing script's own URL, or it will 404 on every published
  version.
- `attr_list`, `md_in_html` and `pymdownx.superfences` are enabled, so a page
  can drop in `<div class="anchor-diagram" data-case="A-003"></div>` and let the
  script hydrate it.
- Inline **SVG** is almost certainly the right medium: crisp at any zoom,
  themeable through CSS variables, stylable per element, and accessible in a way
  canvas is not.
- These docs get read on phones. It needs to reflow, not just scale down.

## Out of scope

- **Live recalculation.** The engine is Python; the browser only ever displays
  stored case values. A user-driven playground with arbitrary inputs is planned
  separately and is not this component.
- **Editing.** Read-only. Certification happens offline, on paper.

## Two open modelling questions

Both are unresolved and both live in this data. Don't design around either
answer — just don't let the diagram imply one is settled.

1. In `A-003/unsatisfiable_overlap`, captive demand (300 W) exceeds local supply
   (200 W), so some restriction must be broken. The engine currently serves
   `bat_c` in full and pushes a 50 W deficit onto each of `bat_a` and `bat_b`.
   Whether that is the intended priority is undecided.
2. In `A-002/source_in_standby`, `home_base_load_power` includes the 400 W that
   `bat_1` drew but could not legally be attributed — so the "unmetered" load
   includes a device that very much has a meter on it.
