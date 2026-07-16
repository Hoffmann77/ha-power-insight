"""Top-level pytest configuration.

Tests are split into two tiers, one directory per dependency group:

* ``engine/``      — pure Python, no Home Assistant, no network. Imports
                     ``power_insight.py`` directly via ``importlib``.
* ``integration/`` — requires ``pytest-homeassistant-custom-component``.

The engine tier must stay runnable without the Home Assistant test harness
installed. If that harness is absent we drop the integration tier from
collection instead of failing at import time, so a minimal ``pytest`` +
engine environment still exercises the calculation engine.
"""
from __future__ import annotations

collect_ignore_glob: list[str] = []

try:
    import pytest_homeassistant_custom_component  # noqa: F401
except ImportError:
    collect_ignore_glob.append("integration/*")
