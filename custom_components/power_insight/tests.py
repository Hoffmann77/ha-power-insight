"""Tests module."""


from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypedDict




VALUE = "value"



class Test(TypedDict):
    
    VALUE: str
    

x = Test(VALUE="myvalue")


print(x)




