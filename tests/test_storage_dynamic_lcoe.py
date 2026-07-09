"""Regression tests for the battery dynamic (blended) coe/lcoe calculation.

Bug: ``storage_adapters_dynamic_coe`` / ``storage_adapters_dynamic_lcoe``
computed a blended value from each battery's charging sources but never stored
it in the returned dict, so the battery uid was absent from the result. Every
downstream battery operating-cost / cost-savings / levelized-cost-savings sensor
then read ``None`` ("unknown"). These tests inject a deterministic charging
source-share distribution to isolate the blend-and-store behaviour.
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


def _build() -> PowerInsight:
    """Grid + two PV sources (distinct LCOE) + one battery charging from them."""
    pi = PowerInsight()
    pi.register_adapter(
        GridAdapter(
            unique_id="grid",
            verbose_name="Grid",
            power_entity="sensor.grid_power",
            price_entity="sensor.grid_price",
        )
    )
    pi.register_adapter(
        PvAdapter(
            unique_id="pv1",
            verbose_name="PV-1",
            power_entity="sensor.pv1_power",
            power_entity_inverted=False,
            lcoe=0.10,
            lco2_intensity=35.0,
            exports_power=True,
            export_compensation=0.08,
        )
    )
    pi.register_adapter(
        PvAdapter(
            unique_id="pv2",
            verbose_name="PV-2",
            power_entity="sensor.pv2_power",
            power_entity_inverted=False,
            lcoe=0.20,
            lco2_intensity=40.0,
            exports_power=True,
            export_compensation=0.08,
        )
    )
    pi.register_adapter(
        BatteryAdapter(
            unique_id="bat1",
            verbose_name="Battery-1",
            power_entity="sensor.bat1_power",
            power_entity_inverted=False,
            lcos=0.30,
            lco2_intensity=50.0,
            exports_power=False,
            export_compensation=0.0,
            charge_from_grid=False,
            charge_from_adapters=["pv1", "pv2"],
        )
    )
    return pi


def _inject_sources(monkeypatch, pi: PowerInsight, shares: dict) -> None:
    """Override the (independently-computed) charging source shares."""
    monkeypatch.setattr(
        type(pi),
        "storage_adapters_charging_source_shares",
        property(lambda self: shares),
    )


def test_dynamic_lcoe_blends_and_stores(monkeypatch) -> None:
    pi = _build()
    _inject_sources(monkeypatch, pi, {"bat1": {"pv1": 0.25, "pv2": 0.75}})
    result = pi.storage_adapters_dynamic_lcoe
    # Pre-fix: {} (uid absent). Post-fix: weighted blend of the source LCOEs.
    assert result == {"bat1": pytest.approx(0.10 * 0.25 + 0.20 * 0.75)}


def test_dynamic_coe_stores_uid(monkeypatch) -> None:
    pi = _build()
    _inject_sources(monkeypatch, pi, {"bat1": {"pv1": 0.25, "pv2": 0.75}})
    result = pi.storage_adapters_dynamic_coe
    # Production adapters model coe as 0.0, so the blend is 0.0 — the regression
    # is that the battery uid is now present (pre-fix it was absent -> None).
    assert "bat1" in result
    assert result["bat1"] == pytest.approx(0.0)


def test_dynamic_lcoe_unknown_source_is_none(monkeypatch) -> None:
    pi = _build()
    _inject_sources(monkeypatch, pi, {"bat1": {"ghost": 1.0}})
    # An unresolvable source uid maps the battery to None (not absent, not blended).
    assert pi.storage_adapters_dynamic_lcoe == {"bat1": None}


def test_lcoo_rates_propagate_after_fix(monkeypatch) -> None:
    """With the blend stored, the battery's levelized operating-cost rate resolves."""
    pi = _build()
    pi.set_value("sensor.bat1_power", -800.0)  # charging -> consumption 800 W
    _inject_sources(monkeypatch, pi, {"bat1": {"pv1": 0.25, "pv2": 0.75}})
    lcoo = pi.storage_adapters_lcoo_rates
    blended = 0.10 * 0.25 + 0.20 * 0.75
    assert lcoo["bat1"] == pytest.approx((800.0 / 1000.0) * blended)
