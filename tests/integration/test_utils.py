"""Tests for the HA-state translation helpers in ``utils``."""

from __future__ import annotations

import pytest
from homeassistant.core import State

from custom_components.power_insight.utils import (
    parse_price_unit,
    price_to_value,
    state_to_value,
)


def _state(value: str, unit: str | None = None) -> State:
    attributes = {"unit_of_measurement": unit} if unit is not None else {}
    return State("sensor.probe", value, attributes)


# ---------------------------------------------------------------------------
# Power units are normalised to Watts by their SI prefix.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("W", 2.5),
        ("kW", 2_500.0),
        ("MW", 2_500_000.0),
        ("GW", 2_500_000_000.0),
        ("TW", 2_500_000_000_000.0),
    ],
)
def test_power_units_scale_by_prefix(unit: str, expected: float) -> None:
    assert state_to_value(_state("2.5", unit)) == pytest.approx(expected)


def test_missing_unit_is_taken_as_watts() -> None:
    """A power sensor with no unit is the engine's own convention: Watts."""
    assert state_to_value(_state("2.5")) == pytest.approx(2.5)
    assert state_to_value(_state("2.5", "")) == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# Everything else is stored exactly as reported.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unit",
    [
        # Currencies whose first letter collides with an SI prefix. Before these
        # were matched as whole units, a GBP tariff was scaled by 10^9.
        "GBP/kWh",
        "MXN/kWh",
        "TRY/kWh",
        "kr/kWh",
        # ... and the ones that never collided, which must not regress.
        "EUR/kWh",
        "USD/kWh",
        "ct/kWh",
        # Carbon intensity.
        "gCO2eq/kWh",
        "kgCO2eq/kWh",
    ],
)
def test_non_power_units_are_not_rescaled(unit: str) -> None:
    assert state_to_value(_state("0.30", unit)) == pytest.approx(0.30)


def test_prefixed_energy_is_not_a_power_unit() -> None:
    """``kWh`` starts like ``kW`` but is energy — leave it alone."""
    assert state_to_value(_state("7", "kWh")) == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# Unparseable states.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["unavailable", "unknown", "", "n/a"])
def test_non_numeric_state_is_none(value: str) -> None:
    assert state_to_value(_state(value, "W")) is None


# ---------------------------------------------------------------------------
# Prices are normalised to currency per kWh — or refused.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        ("0.30", "EUR/kWh", 0.30),
        ("0.30", "€/kWh", 0.30),
        ("30", "ct/kWh", 0.30),
        ("30", "Cent/kWh", 0.30),
        ("300", "EUR/MWh", 0.30),
        ("0.0003", "EUR/Wh", 0.30),
        ("3", "SEK/kWh", 3.0),
        ("30", "öre/kWh", 0.30),
    ],
)
def test_prices_are_normalised_to_currency_per_kwh(
    value: str, unit: str, expected: float
) -> None:
    """A ct/kWh or EUR/MWh tariff taken at face value would be 100× or 1000× off."""
    assert price_to_value(_state(value, unit)) == pytest.approx(expected)


@pytest.mark.parametrize("unit", [None, "", "EUR", "EUR/kW", "W", "kWh", "%"])
def test_a_price_in_an_unknown_unit_is_refused(unit: str | None) -> None:
    """A price that is not per unit of energy is unknown, never a guess."""
    assert price_to_value(_state("0.30", unit)) is None


@pytest.mark.parametrize(
    ("unit", "currency"),
    [
        ("EUR/kWh", "EUR"),
        ("€/kWh", "EUR"),
        ("GBP/MWh", "GBP"),
        ("ct/kWh", None),
        ("kr/kWh", None),
        ("$/kWh", None),
    ],
)
def test_a_price_unit_names_its_currency_when_it_can(unit: str, currency) -> None:
    """Only a unit naming exactly one currency can be checked against HA's."""
    parsed = parse_price_unit(unit)
    assert parsed is not None
    assert parsed[1] == currency
