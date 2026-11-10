"""Tests for adapter-model base-intensity backfill.

The adapter reads its base LCOE/LCOS/CO2-intensity from the stored
``default_lcoe`` / ``default_lcos`` / ``default_co2_intensity`` values, which are
only computed in the config (create) flow. When lifetime data is added later via
reconfigure, that base is never recomputed and stays ``None``, so the per-device
levelized sensors never register (``exists_fn: adapter.lcoe is not None``) and the
combined levelized sensors read "unknown". ``from_subentry`` backfills the base
from the stored lifetime values when it is absent.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.power_insight.adapter_models import (
    PvAdapterModel,
    BatteryAdapterModel,
)


def _subentry(adapter_type: str, config: dict, **top_level):
    """Build a minimal fake config subentry for from_subentry."""
    data = {
        "adapter": {
            "adapter_type": adapter_type,
            "key": adapter_type,
            "config": config,
        },
        **top_level,
    }
    return SimpleNamespace(
        subentry_id=f"{adapter_type}_1", title=adapter_type, data=data
    )


# --- PV base backfill ---


def test_pv_lcoe_backfilled_from_lifetime_when_base_absent() -> None:
    sub = _subentry(
        "pv_system",
        {"power_entity": "sensor.pv_power"},  # no default_lcoe
        lifetime_cost=2000.0,
        lifetime_production=10000.0,
    )
    model = PvAdapterModel.from_subentry(sub)
    assert model.lcoe == pytest.approx(0.2)
    assert model.create_adapter().lcoe == pytest.approx(0.2)


def test_pv_co2_intensity_backfilled_from_lifetime() -> None:
    sub = _subentry(
        "pv_system",
        {"power_entity": "sensor.pv_power"},  # no default_co2_intensity
        co2_footprint=500.0,
        lifetime_production=10000.0,
    )
    model = PvAdapterModel.from_subentry(sub)
    assert model.lco2_intensity == pytest.approx(500.0 / 10000.0 * 1000)


def test_pv_stored_base_is_used_verbatim() -> None:
    """When the base is already stored, the backfill is a no-op."""
    sub = _subentry(
        "pv_system",
        {"power_entity": "sensor.pv_power", "default_lcoe": 0.5},
        lifetime_cost=2000.0,
        lifetime_production=10000.0,  # would imply 0.2
    )
    assert PvAdapterModel.from_subentry(sub).lcoe == pytest.approx(0.5)


def test_pv_lcoe_none_without_base_or_lifetime() -> None:
    sub = _subentry("pv_system", {"power_entity": "sensor.pv_power"})
    assert PvAdapterModel.from_subentry(sub).lcoe is None


# --- Battery base backfill ---


def test_battery_lcos_backfilled_from_lifetime_when_base_absent() -> None:
    sub = _subentry(
        "battery",
        {"power_entity": "sensor.bat_power"},  # no default_lcos
        lifetime_cost=3000.0,
        lifetime_production=10000.0,
    )
    model = BatteryAdapterModel.from_subentry(sub)
    assert model.lcos == pytest.approx(0.3)
    assert model.create_adapter().lcoe == pytest.approx(
        0.3
    )  # battery.lcoe returns _lcos


def test_battery_stored_base_is_used_verbatim() -> None:
    sub = _subentry(
        "battery",
        {"power_entity": "sensor.bat_power", "default_lcos": 0.15},
        lifetime_cost=3000.0,
        lifetime_production=10000.0,  # would imply 0.3
    )
    assert BatteryAdapterModel.from_subentry(sub).lcos == pytest.approx(0.15)


def test_battery_lcos_none_without_base_or_lifetime() -> None:
    sub = _subentry("battery", {"power_entity": "sensor.bat_power"})
    assert BatteryAdapterModel.from_subentry(sub).lcos is None


# --- What prices stored energy: export limit and curtailment ---


def test_grid_export_limit_reaches_the_adapter() -> None:
    from custom_components.power_insight.adapter_models import GridAdapterModel

    sub = _subentry("grid", {"power_entity": "sensor.grid_power", "export_limit": 800})
    assert GridAdapterModel.from_subentry(sub).create_adapter().export_limit == 800


def test_grid_without_an_export_limit_has_none() -> None:
    """Entries made before the field existed read as having no limit."""
    from custom_components.power_insight.adapter_models import GridAdapterModel

    sub = _subentry("grid", {"power_entity": "sensor.grid_power"})
    assert GridAdapterModel.from_subentry(sub).create_adapter().export_limit is None


def test_pv_curtailment_reaches_the_adapter() -> None:
    sub = _subentry(
        "pv_system",
        {"power_entity": "sensor.pv_power", "curtails_at_negative_prices": True},
    )
    assert PvAdapterModel.from_subentry(sub).create_adapter().curtails_at_negative_prices


def test_pv_without_the_curtailment_field_is_not_curtailed() -> None:
    """Entries made before the field existed assume nothing curtails the PV."""
    sub = _subentry("pv_system", {"power_entity": "sensor.pv_power"})
    adapter = PvAdapterModel.from_subentry(sub).create_adapter()
    assert adapter.curtails_at_negative_prices is False
