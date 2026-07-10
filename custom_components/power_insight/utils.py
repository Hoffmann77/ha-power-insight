"""Utility helpers for the PowerInsight integration."""

import logging

from homeassistant.core import (
    State,
)

from .power_insight import UNIT_PREFIXES


_LOGGER = logging.getLogger(__name__)


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
    """Return the state of the given state object as float."""
    try:
        value = float(state_obj.state)
    except ValueError:
        return None

    if unit := state_obj.attributes.get("unit_of_measurement"):
        unit = unit[0]

    return value * UNIT_PREFIXES.get(unit, 1.0)
