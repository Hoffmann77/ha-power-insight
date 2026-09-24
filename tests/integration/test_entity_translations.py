"""Every sensor's name comes from strings.json, so every key must be there."""

from __future__ import annotations

import json
import re
from pathlib import Path

COMPONENT = Path(__file__).parents[2] / "custom_components" / "power_insight"


def test_every_sensor_translation_key_has_a_name() -> None:
    """A translation key with no name would leave the sensor with none at all."""
    used = set(re.findall(r'translation_key="([a-z0-9_]+)"', (COMPONENT / "sensor.py").read_text()))
    strings = json.loads((COMPONENT / "strings.json").read_text())
    named = set(strings["entity"]["sensor"])
    exceptions = set(strings["exceptions"])
    missing = used - named - exceptions
    assert not missing, f"no name in strings.json for {sorted(missing)}"


def test_no_sensor_name_is_hardcoded() -> None:
    """Names are translated; a hardcoded one would bypass strings.json."""
    source = (COMPONENT / "sensor.py").read_text()
    descriptions = re.findall(r"SensorDescription\((.*?)\n    \)", source, re.S)
    assert descriptions
    assert not [d for d in descriptions if re.search(r"^\s+name=", d, re.M)]
