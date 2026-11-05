"""Repair issues on every supported Home Assistant version.

Home Assistant 2026.11 links a repair issue to its config entry
(``config_entry_id``) and refreshes a set of issues: the ones not raised or
kept again while the refresh runs are deleted when it finishes
(``async_refresh_issues`` / ``async_keep_issue``). Older versions have
neither, so this module stands in for them there: an issue cannot be linked,
and the refresh is done here, with an issue counted as the entry's when its id
ends in the entry's id or one of its devices' (subentry) ids, which is how
every issue of this integration is named.

Every issue of the integration is raised, kept and refreshed through here.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Iterable
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

#: Whether this Home Assistant refreshes issues itself (2026.11 and newer).
NATIVE_REFRESH = hasattr(ir, "async_refresh_issues") and hasattr(ir, "async_keep_issue")

#: Whether this Home Assistant links an issue to its config entry.
LINKS_ENTRY = "config_entry_id" in inspect.signature(ir.async_create_issue).parameters

_REFRESHES = f"{__name__}.refreshes"


def async_create_issue(
    hass: HomeAssistant,
    domain: str,
    issue_id: str,
    *,
    config_entry_id: str | None = None,
    **kwargs: Any,
) -> None:
    """Raise (or update) an issue, linked to its entry where supported."""
    if LINKS_ENTRY:
        kwargs["config_entry_id"] = config_entry_id
    ir.async_create_issue(hass, domain, issue_id, **kwargs)
    if not NATIVE_REFRESH:
        _touch(hass, domain, issue_id)


def async_keep_issue(hass: HomeAssistant, domain: str, issue_id: str) -> None:
    """Keep an issue in every running refresh without raising it again."""
    if NATIVE_REFRESH:
        ir.async_keep_issue(hass, domain, issue_id)
    else:
        _touch(hass, domain, issue_id)


def async_refresh_issues(
    hass: HomeAssistant,
    domain: str,
    *,
    issue_id_pattern: str | None = None,
    issue_ids: Iterable[str] | None = None,
    config_entry_id: str | None = None,
) -> Any:
    """Begin a refresh of a set of issues; a context manager."""
    if NATIVE_REFRESH:
        return ir.async_refresh_issues(
            hass,
            domain,
            issue_id_pattern=issue_id_pattern,
            issue_ids=issue_ids,
            config_entry_id=config_entry_id,
        )
    return _Refresh(hass, domain, issue_id_pattern, issue_ids, config_entry_id)


def issue_config_entry_id(issue: ir.IssueEntry) -> str | None:
    """Return the config entry an issue is linked to (never, before 2026.11)."""
    return getattr(issue, "config_entry_id", None)


def async_delete_entry_issues(hass: HomeAssistant, domain: str, entry_id: str) -> None:
    """Delete a removed entry's issues, which 2026.11 does by itself."""
    if LINKS_ENTRY:
        return
    suffixes = _entry_suffixes(hass, entry_id)
    for issue_domain, issue_id in list(ir.async_get(hass).issues):
        if issue_domain == domain and issue_id.endswith(suffixes):
            ir.async_delete_issue(hass, domain, issue_id)


def _entry_suffixes(hass: HomeAssistant, entry_id: str) -> tuple[str, ...]:
    entry = hass.config_entries.async_get_entry(entry_id)
    ids = [entry_id, *(entry.subentries if entry is not None else ())]
    return tuple(f"_{id_}" for id_ in ids)


def _touch(hass: HomeAssistant, domain: str, issue_id: str) -> None:
    for refresh in hass.data.get(_REFRESHES, ()):
        refresh.untouched.discard((domain, issue_id))


class _Refresh:
    """The refresh of Home Assistant 2026.11, for older versions."""

    def __init__(
        self,
        hass: HomeAssistant,
        domain: str,
        issue_id_pattern: str | None,
        issue_ids: Iterable[str] | None,
        config_entry_id: str | None,
    ) -> None:
        if issue_id_pattern is not None and issue_ids is not None:
            raise ValueError("At most one of issue_id_pattern and issue_ids is allowed")
        self._hass = hass
        keys = {key for key in ir.async_get(hass).issues if key[0] == domain}
        if issue_ids is not None:
            keys &= {(domain, issue_id) for issue_id in issue_ids}
        elif issue_id_pattern is not None:
            pattern = re.compile(issue_id_pattern)
            keys = {key for key in keys if pattern.match(key[1])}
        if config_entry_id is not None:
            suffixes = _entry_suffixes(hass, config_entry_id)
            keys = {key for key in keys if key[1].endswith(suffixes)}
        self.untouched = keys

    def __enter__(self) -> _Refresh:
        self._hass.data.setdefault(_REFRESHES, []).append(self)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._hass.data[_REFRESHES].remove(self)
        if exc_type is not None:
            return  # cancelled: every issue is left as it is
        for domain, issue_id in self.untouched:
            ir.async_delete_issue(self._hass, domain, issue_id)
