## What this changes

<!-- What and why, in a few lines. -->

## Engine outputs

<!--
Only if this touches custom_components/power_insight/power_insight.py.
See tests/README.md → "Changing the engine".
-->

- [ ] No frozen engine output moved (`tests/engine/frozen` passes unchanged).
- [ ] Outputs moved, and that is intended. I re-froze with
      `uv run --group engine python tools/snapshot.py` and explain below which
      moved and why.
- [ ] This settles a modelling decision, and I added its class to
      `tests/engine/manual/` and its note to `docs/dev/engine-calculations.md`.

<!-- Which outputs moved, and why that is right: -->
