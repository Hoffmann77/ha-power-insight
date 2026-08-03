"""Every options form the code can build must have translations behind it.

``build_scope_form`` is data-driven: it grows a section as soon as a scope
supports the underlying option. That is what makes adding a capability a
one-line change to ``SCOPE_SUPPORTED_OPTIONS`` — and it is also why a section
can appear in the UI with nothing to render it, which no flow test notices
because flows are driven programmatically and never touch translations.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from custom_components.power_insight.config_flow import build_scope_form
from custom_components.power_insight.const import SCOPES

TRANSLATION_FILES = (
    "custom_components/power_insight/strings.json",
    "custom_components/power_insight/translations/en.json",
)


def _load(path: str) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _form_layout(scope: str) -> dict[str, list[str]]:
    """Return ``{section: [field, ...]}`` for the form of one scope."""
    layout: dict[str, list[str]] = {}
    for key, value in build_scope_form(scope, {}).schema.items():
        inner = getattr(value, "schema", None)
        layout[str(key)] = (
            [str(field) for field in inner.schema] if inner is not None else []
        )
    return layout


@pytest.mark.parametrize("path", TRANSLATION_FILES)
@pytest.mark.parametrize("scope", SCOPES)
def test_scope_form_sections_are_translated(scope: str, path: str) -> None:
    """Every section and field the form builds is named in the translations."""
    step = _load(path)["options"]["step"]
    assert scope in step, f"{scope} has no options step in {path}"
    sections = step[scope].get("sections", {})

    for name, fields in _form_layout(scope).items():
        assert name in sections, f"{scope}: section '{name}' has no translation"
        data = sections[name].get("data", {})
        for field in fields:
            assert field in data, (
                f"{scope}.{name}: field '{field}' has no translation"
            )


@pytest.mark.parametrize("path", TRANSLATION_FILES)
def test_no_orphan_section_translations(path: str) -> None:
    """And nothing is translated that the form can no longer build.

    Catches the other direction: a section left behind after the option that
    produced it was moved or removed.
    """
    step = _load(path)["options"]["step"]
    orphans = []
    for scope in SCOPES:
        built = set(_form_layout(scope))
        for name in step.get(scope, {}).get("sections", {}):
            if name not in built:
                orphans.append(f"{scope}.{name}")
    assert not orphans, f"translated but never built: {orphans}"
