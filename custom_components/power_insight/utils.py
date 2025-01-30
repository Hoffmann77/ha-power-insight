# -*- coding: utf-8 -*-
"""
Created on Sat Aug 24 17:13:43 2024

@author: Bobby
"""


def get_value(key: str, d: dict, multiply=None, divide=None):
    
    value = d.get(key)
    if value is not None:
        if multiply:
            value = value * multiply
        if divide:
            value = value / divide
    
    return value