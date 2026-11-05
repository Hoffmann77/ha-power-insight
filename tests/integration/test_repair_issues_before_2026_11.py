"""The repair issues behave the same on Home Assistant before 2026.11.

Before 2026.11 an issue cannot be linked to its config entry and there is no
``ir.async_refresh_issues``; ``issues.py`` stands in for both. These tests run
with the newer API hidden: the refresh is then done by the integration, an
issue counts as the entry's by its id, and a removed entry's issues are deleted
in ``async_remove_entry``.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.power_insight import issues

from .conftest import make_grid_subentry_data, setup_integration
from .test_repair_issues import (  # noqa: F401  (re-run on the older API)
    _entry,
    _issue,
    _reload,
    _set,
    test_a_charge_source_issue_survives_the_reload_it_triggers,
    test_a_fixed_issue_is_deleted_at_the_next_setup,
    test_an_ignored_issue_stays_ignored_across_a_reload,
    test_an_issue_setup_cannot_judge_is_kept,
)


@pytest.fixture(autouse=True)
def _before_2026_11(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(issues, "NATIVE_REFRESH", False)
    monkeypatch.setattr(issues, "LINKS_ENTRY", False)


async def test_removing_the_entry_removes_its_issues(hass: HomeAssistant) -> None:
    """Without a link Home Assistant cannot do it, so the integration does."""
    entry = _entry()
    _set(hass, "grid_power", "100", "W")
    _set(hass, "grid_price", "30", "EUR")  # not a price per energy
    await setup_integration(hass, entry)

    issue_id = f"price_unit_{entry.entry_id}"
    assert _issue(hass, issue_id).config_entry_id is None

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert _issue(hass, issue_id) is None


async def test_one_entrys_setup_leaves_another_entrys_issues_alone(
    hass: HomeAssistant,
) -> None:
    """The refresh only decides on the issues named after its own entry.

    Every entry's setup matches the same issue kinds, so without that a second
    entry would delete the first one's issue.
    """
    first = _entry()
    _set(hass, "grid_power", "100", "W")
    _set(hass, "grid_price", "30", "EUR")
    await setup_integration(hass, first)

    second = _entry(
        make_grid_subentry_data(subentry_id="grid_two", power_entity="sensor.grid_two")
    )
    _set(hass, "grid_two", "100", "W")
    await setup_integration(hass, second)
    await _reload(hass, second)

    assert _issue(hass, f"price_unit_{first.entry_id}") is not None
