"""Utility helpers for the PowerInsight integration."""

import logging
import re

from homeassistant.core import (
    State,
)

from .power_insight import UNIT_PREFIXES


_LOGGER = logging.getLogger(__name__)

#: A power unit and nothing else: an optional SI prefix followed by ``W``.
#: Matched against the *whole* unit string so that only genuine power readings
#: are rescaled — a price in ``GBP/kWh`` or ``kr/kWh`` and a carbon intensity in
#: ``kgCO2eq/kWh`` merely happen to start with a prefix letter, and must be
#: taken at face value.
_POWER_UNIT = re.compile(rf"^(?P<prefix>[{''.join(p for p in UNIT_PREFIXES if p)}])?W$")


def get_value(key: str, d: dict, multiply=None, divide=None):

    # _LOGGER.debug(f"get_value: key: {key}, dict: {d}")
    if d is None:
        return None

    value = d.get(key)
    if value is not None:
        if multiply:
            value = value * multiply
        if divide:
            value = value / divide

    return value


#: A price per unit of energy: a currency (or its subunit) over a prefixed Wh.
_PRICE_UNIT = re.compile(r"^\s*(?P<money>[^/\s]+)\s*/\s*(?P<energy>[kMG]?Wh)\s*$")

#: How many of each energy unit make a kWh.
_PER_KWH = {"Wh": 1000.0, "kWh": 1.0, "MWh": 0.001, "GWh": 0.000001}

#: Hundredth-of-a-currency units, however an integration spells them.
_SUBUNITS = {"ct", "c", "cent", "cents", "Cent", "Cents", "p", "öre", "øre", "Rp"}

#: Currency symbols that name exactly one currency.
_SYMBOLS = {"€": "EUR", "£": "GBP"}


def parse_price_unit(unit: str | None) -> tuple[float, str | None] | None:
    """Return ``(factor to currency/kWh, currency code)`` for a price unit.

    ``EUR/kWh`` is ``(1, "EUR")``, ``ct/kWh`` ``(0.01, None)``, ``EUR/MWh``
    ``(0.001, "EUR")``. The code is ``None`` when the unit names no single
    currency (a subunit, or a symbol like ``$`` or ``kr`` that several share).
    ``None`` for a unit that is not a price per unit of energy at all — a
    missing unit included, since a bare number could be in any of them.
    """
    if not unit or not (match := _PRICE_UNIT.match(unit)):
        return None

    factor = _PER_KWH[match["energy"]]
    money = match["money"]
    if money in _SUBUNITS:
        return factor / 100, None
    if money in _SYMBOLS:
        return factor, _SYMBOLS[money]
    if len(money) == 3 and money.isalpha() and money.isupper():
        return factor, money
    if money.isalpha() or not money.isalnum():
        return factor, None  # a symbol or name shared by several currencies

    return None


def price_to_value(state_obj: State) -> float | None:
    """Return a price state as a float in currency per kWh.

    ``25 ct/kWh`` is stored as ``0.25`` and ``250 EUR/MWh`` as ``0.25``. A
    price in a unit that is not a price per unit of energy is ``None`` rather
    than a guess: taken at face value, a ``ct/kWh`` tariff would make every
    cost a hundred times too large.
    """
    try:
        value = float(state_obj.state)
    except (TypeError, ValueError):
        return None

    parsed = parse_price_unit(state_obj.attributes.get("unit_of_measurement"))
    if parsed is None:
        return None

    return value * parsed[0]


def state_to_value(state_obj: State) -> float | None:
    """Return the state of the given state object as float, normalised to Watts.

    Power readings are rescaled by their SI prefix, so ``2.5 kW`` is stored as
    ``2500``. Every other tracked entity — the grid price, a carbon intensity —
    is stored exactly as reported: its unit carries a currency or a mass, not a
    prefixed Watt, and rescaling it by whatever letter it happens to start with
    would silently multiply a ``GBP/kWh`` tariff by a billion.
    """
    try:
        value = float(state_obj.state)
    except (TypeError, ValueError):
        return None

    unit = state_obj.attributes.get("unit_of_measurement")
    if not unit or not (match := _POWER_UNIT.match(unit)):
        return value

    return value * UNIT_PREFIXES[match["prefix"]]
