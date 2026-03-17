# -*- coding: utf-8 -*-
"""
Created on Sat Aug 24 17:13:43 2024

@author: Bobby
"""
import logging

from homeassistant.core import (
    State,
)


_LOGGER = logging.getLogger(__name__)

UNIT_PREFIXES = {None: 1, "k": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}


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


def division_zero(a, b):
    result = b and a / b or 0

    return result


def state_to_value(state_obj: State) -> float | None:
    """Return the state of the given state object as float."""
    try:
        value = float(state_obj.state)
    except ValueError:
        return None

    if unit := state_obj.attributes.get("unit_of_measurement"):
        unit = unit[0]

    return value * UNIT_PREFIXES.get(unit, 1.0)
