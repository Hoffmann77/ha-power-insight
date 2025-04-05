# -*- coding: utf-8 -*-
"""
Created on Sat Aug 24 17:13:43 2024

@author: Bobby
"""
import logging


_LOGGER = logging.getLogger(__name__)



def get_value(key: str, d: dict, multiply=None, divide=None):

    _LOGGER.debug(f"get_value: key: {key}, dict: {d}")
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
