"""Regression tests for release-readiness bug fixes.

- A1: ``power_entity_inverted`` must actually invert the stored power value.
- A2: ratio properties must not raise ``ZeroDivisionError`` on degenerate
      states (pure grid export with no production → ``gross_power == 0``).

Imports ``power_insight.py`` directly via importlib to bypass HA deps, matching
the other engine tests.
"""

from __future__ import annotations

import importlib.util
import os

_MODULE_PATH = os.path.join(
    os.path.dirname(__file__),
    os.pardir,
    "custom_components",
    "power_insight",
    "power_insight.py",
)
_spec = importlib.util.spec_from_file_location("power_insight", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

PowerInsight = _mod.PowerInsight
GridAdapter = _mod.GridAdapter
PvAdapter = _mod.PvAdapter


# ---------------------------------------------------------------------------
# A1 — power_entity_inverted
# ---------------------------------------------------------------------------

def test_invert_flag_negates_power():
    """An inverted grid sensor flips sign; a non-inverted one does not."""
    inverted = GridAdapter(
        unique_id="grid",
        verbose_name="Grid",
        power_entity="sensor.grid_power",
        price_entity="sensor.grid_price",
        power_entity_inverted=True,
    )
    inverted.set_value("sensor.grid_power", 1000.0)
    # Raw sensor reads +1000 (export in its own convention); inverted → -1000
    # which is "export" in this integration's convention.
    assert inverted.power == -1000.0

    plain = GridAdapter(
        unique_id="grid2",
        verbose_name="Grid2",
        power_entity="sensor.grid2_power",
        price_entity="sensor.grid2_price",
        power_entity_inverted=False,
    )
    plain.set_value("sensor.grid2_power", 1000.0)
    assert plain.power == 1000.0


def test_invert_flag_none_stays_none():
    """Inversion must not turn an unavailable (None) reading into a value."""
    adapter = PvAdapter(
        unique_id="pv1",
        verbose_name="PV-1",
        power_entity="sensor.pv1_power",
        power_entity_inverted=True,
        lcoe=0.10,
        lco2_intensity=35.0,
        exports_power=False,
        export_compensation=0.0,
    )
    # No value set → None; inversion leaves it None (not -0.0 / crash).
    assert adapter.power is None


# ---------------------------------------------------------------------------
# A2 — division-by-zero guard
# ---------------------------------------------------------------------------

def test_export_only_ratio_no_zero_division():
    """Pure grid export with no production: gross_power == 0, export > 0.

    Before the fix, ``gross_power_export_ratio`` divided ``grid_export`` by
    ``gross_power`` (0.0) and raised ``ZeroDivisionError``.
    """
    pi = PowerInsight()
    pi.register_adapter(GridAdapter(
        unique_id="grid",
        verbose_name="Grid",
        power_entity="sensor.grid_power",
        price_entity="sensor.grid_price",
    ))
    pi.set_value("sensor.grid_power", -500.0)  # exporting 500 W, no PV/battery

    assert pi.gross_power == 0.0
    # Must return a finite value rather than raising.
    assert pi.gross_power_export_ratio == 0.0
