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
