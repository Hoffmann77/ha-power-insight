"""Engine tests for the levelized-cost correction factor and the B4 bug fix.

These import ``power_insight.py`` directly via importlib (HA-free), mirroring
``test_power_insight_calculations.py``.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

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
BatteryAdapter = _mod.BatteryAdapter
ConsumerAdapter = _mod.ConsumerAdapter


GRID_POWER = "sensor.grid_power"
GRID_PRICE = "sensor.grid_price"
PV1_POWER = "sensor.pv1_power"
CONS_POWER = "sensor.cons_power"


def _build(pv_correction_factor: float = 1.0):
    """Grid (import) + one producing PV + one consumer."""
    pi = PowerInsight()
    pi.register_adapter(
        GridAdapter(
            unique_id="grid",
            verbose_name="Grid",
            power_entity=GRID_POWER,
            price_entity=GRID_PRICE,
        )
    )
    pi.register_adapter(
        PvAdapter(
            unique_id="pv1",
            verbose_name="PV-1",
            power_entity=PV1_POWER,
            power_entity_inverted=False,
            lcoe=0.10,
            lco2_intensity=35.0,
            exports_power=True,
            export_compensation=0.08,
            correction_factor=pv_correction_factor,
        )
    )
    pi.register_adapter(
        ConsumerAdapter(
            unique_id="cons",
            verbose_name="Consumer",
            power_entity=CONS_POWER,
        )
    )
    pi.set_value(GRID_POWER, 1000.0)
    pi.set_value(GRID_PRICE, 0.30)
    pi.set_value(PV1_POWER, 2000.0)
    pi.set_value(CONS_POWER, 800.0)
    return pi


# ---------------------------------------------------------------------------
# C1 — correction factor
# ---------------------------------------------------------------------------

def test_pv_adapter_lcoe_is_base_value() -> None:
    """The adapter's lcoe stays the immutable base; the factor is separate."""
    pi = _build(pv_correction_factor=1.5)
    pv = pi.get_adapter_by_uid("pv1")
    assert pv.lcoe == 0.10
    assert pv.correction_factor == 1.5
    # lcoe_rate uses the base value: (2000 / 1000) * 0.10 = 0.20
    assert pv.lcoe_rate == pytest.approx(0.20)


def test_grid_correction_factor_defaults_to_one() -> None:
    """Adapters without an editable lifetime cost have a unit factor."""
    pi = _build()
    assert pi.get_adapter_by_uid("grid").correction_factor == 1.0


def test_combined_lcoe_rate_corrected_scales_each_term() -> None:
    """Corrected combined rate = sum of factor_i * base_rate_i."""
    pi = _build(pv_correction_factor=1.5)
    # grid: (1000/1000)*0.30 = 0.30 (factor 1.0); pv: 0.20 * 1.5 = 0.30
    assert pi.combined_lcoe_rate == pytest.approx(0.30 + 0.20)
    assert pi.combined_lcoe_rate_corrected == pytest.approx(0.30 + 0.30)


def test_combined_corrected_equals_base_when_factor_is_one() -> None:
    """With a unit factor the corrected variant matches the base."""
    pi = _build(pv_correction_factor=1.0)
    assert pi.combined_lcoe_rate_corrected == pytest.approx(pi.combined_lcoe_rate)
    assert (
        pi.combined_levelized_saving_rate_corrected
        == pytest.approx(pi.combined_levelized_saving_rate)
    )


def test_levelized_correction_factors_mapping() -> None:
    """Only prod adapters with an LCOE appear, keyed by uid."""
    pi = _build(pv_correction_factor=1.5)
    assert pi.levelized_correction_factors == {"pv1": 1.5}


# ---------------------------------------------------------------------------
# B4 — levelized cost saving rates no longer return None
# ---------------------------------------------------------------------------

def test_prod_levelized_cost_saving_rates_not_none() -> None:
    """Regression: the property used to `return` bare None."""
    pi = _build()
    rates = pi.prod_adapters_levelized_cost_saving_rates
    assert isinstance(rates, dict)
    assert "pv1" in rates
    assert rates["pv1"] is not None


def test_combined_levelized_saving_rate_is_sum_of_dict() -> None:
    """Combined equals the sum of the per-adapter dict values."""
    pi = _build()
    rates = pi.prod_adapters_levelized_cost_saving_rates
    assert pi.combined_levelized_saving_rate == pytest.approx(sum(rates.values()))


def test_combined_levelized_saving_rate_corrected_scales() -> None:
    """Corrected combined savings = sum of factor_i * per-adapter savings."""
    pi = _build(pv_correction_factor=2.0)
    rates = pi.prod_adapters_levelized_cost_saving_rates
    expected = sum(v * 2.0 for v in rates.values())
    assert pi.combined_levelized_saving_rate_corrected == pytest.approx(expected)
