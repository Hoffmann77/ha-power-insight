"""The repair issues setup raises belong to their config entry, and are refreshed.

Every issue is created with ``config_entry_id``, so Home Assistant deletes it
with the entry. Setup runs its checks inside ``ir.async_refresh_issues``: an
issue that no longer applies is deleted, one that still does is left alone,
so an issue the user ignored stays ignored across reloads.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant.common import MockConfigEntry

from .conftest import (
    BAT_SUB_ID,
    BASE_OPTIONS,
    DOMAIN,
    make_battery_subentry_data,
    make_grid_subentry_data,
    setup_integration,
)


def _grid_with_price() -> dict:
    grid = make_grid_subentry_data()
    grid["data"]["adapter"]["config"]["grid_electricity_price_entity"] = (
        "sensor.grid_price"
    )
    return grid


def _entry(*subentries: dict) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="My PowerInsight",
        options=BASE_OPTIONS,
        subentries_data=list(subentries) or [_grid_with_price()],
    )


def _set(hass: HomeAssistant, entity: str, value: str, unit: str) -> None:
    hass.states.async_set(f"sensor.{entity}", value, {"unit_of_measurement": unit})


async def _reload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


def _issue(hass: HomeAssistant, issue_id: str) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, issue_id)


async def test_an_issue_belongs_to_its_entry(hass: HomeAssistant) -> None:
    """Removing the entry removes its issues: nothing is left to point at."""
    entry = _entry()
    _set(hass, "grid_power", "100", "W")
    _set(hass, "grid_price", "30", "EUR")  # not a price per energy
    await setup_integration(hass, entry)

    issue_id = f"price_unit_{entry.entry_id}"
    assert _issue(hass, issue_id).config_entry_id == entry.entry_id

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert _issue(hass, issue_id) is None


async def test_an_ignored_issue_stays_ignored_across_a_reload(
    hass: HomeAssistant,
) -> None:
    """Still valid at the next setup, the issue is kept, not raised afresh.

    Deleting and creating it again would bring an issue the user ignored back.
    """
    entry = _entry()
    _set(hass, "grid_power", "100", "W")
    _set(hass, "grid_price", "30", "EUR")
    await setup_integration(hass, entry)

    issue_id = f"price_unit_{entry.entry_id}"
    ir.async_ignore_issue(hass, DOMAIN, issue_id, True)
    await _reload(hass, entry)

    assert _issue(hass, issue_id).dismissed_version is not None


async def test_a_fixed_issue_is_deleted_at_the_next_setup(hass: HomeAssistant) -> None:
    """Once the price is per kWh, the reload that follows drops the issue."""
    entry = _entry()
    _set(hass, "grid_power", "100", "W")
    _set(hass, "grid_price", "30", "EUR")
    await setup_integration(hass, entry)

    _set(hass, "grid_price", "30", "ct/kWh")
    await _reload(hass, entry)

    assert _issue(hass, f"price_unit_{entry.entry_id}") is None


async def test_an_issue_setup_cannot_judge_is_kept(hass: HomeAssistant) -> None:
    """While the price has no state, nothing is decided about it.

    The issue stays until the price is back and can be checked.
    """
    entry = _entry()
    _set(hass, "grid_power", "100", "W")
    _set(hass, "grid_price", "30", "EUR")
    await setup_integration(hass, entry)

    hass.states.async_set("sensor.grid_price", "unavailable")
    await _reload(hass, entry)

    assert _issue(hass, f"price_unit_{entry.entry_id}") is not None


async def test_a_charge_source_issue_survives_the_reload_it_triggers(
    hass: HomeAssistant,
) -> None:
    """The flow asks a battery to be reconfigured when a source is added.

    Setup cannot tell whether that was done, so the issue it cannot re-derive
    survives the reload; it goes once the battery is removed.
    """
    entry = _entry(make_grid_subentry_data(), make_battery_subentry_data())
    _set(hass, "grid_power", "100", "W")
    _set(hass, "battery_power", "0", "W")
    await setup_integration(hass, entry)

    issue_id = f"reconfigure_battery_{BAT_SUB_ID}"
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        config_entry_id=entry.entry_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="reconfigure_battery_adapters",
        translation_placeholders={"battery_name": "Battery"},
    )
    await _reload(hass, entry)
    assert _issue(hass, issue_id) is not None

    hass.config_entries.async_remove_subentry(entry, BAT_SUB_ID)
    await hass.async_block_till_done()
    assert _issue(hass, issue_id) is None


async def test_issues_from_before_they_had_an_entry_are_decided_again(
    hass: HomeAssistant,
) -> None:
    """An issue raised by an older release belongs to no entry.

    Setup still decides on it: one that no longer applies is deleted, one
    that still does is raised again and belongs to the entry from then on.
    """
    entry = _entry()
    entry.add_to_hass(hass)
    stale = f"shared_power_entity_{entry.entry_id}"
    valid = f"price_unit_{entry.entry_id}"
    for issue_id, key in ((stale, "shared_power_entity"), (valid, "price_unit")):
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=key,
        )

    _set(hass, "grid_power", "100", "W")
    _set(hass, "grid_price", "30", "EUR")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert _issue(hass, stale) is None
    assert _issue(hass, valid).config_entry_id == entry.entry_id
