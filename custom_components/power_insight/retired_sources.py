"""The ledger of removed sources of a consumer's per-source totals.

A consumer's "Energy from Roof PV" belongs to the consumer, not to Roof PV.
When Roof PV is removed the sensor is no longer created — its entity is
disabled with its history — but the energy it counted was really consumed, so
the consumer's per-source figures must not act as if Roof PV never existed.
Its final value is frozen here instead, per consumer:

    entry.data["retired_sources"] = [
        {
            "subentry_id": "<Roof PV's subentry id>",
            "title": "Roof PV",
            "totals": {"<consumer subentry id>": {"energy_from": 812.4}},
        },
    ]

The value is captured in the sensor's own teardown (see
``PowerInsightDynamicAdapterIntegrationSensor.async_will_remove_from_hass``),
like the retired-device ledger: Home Assistant offers no other reliable hook.
A total that was not running when its source was removed — its option off, or
the entity disabled — has no teardown with a value and is not captured.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_RETIRED_SOURCES


def retired_source_totals(
    entry: ConfigEntry, consumer_uid: str, key: str
) -> dict[str, tuple[str, float]]:
    """Return ``{source uid: (title, value)}`` frozen for one consumer's ``key``."""
    found: dict[str, tuple[str, float]] = {}
    for retired in entry.data.get(CONF_RETIRED_SOURCES, []):
        value = retired.get("totals", {}).get(consumer_uid, {}).get(key)
        if value is not None:
            found[retired["subentry_id"]] = (retired.get("title", ""), value)
    return found


def record_retired_source(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    source_uid: str,
    title: str,
    consumer_uid: str,
    key: str,
    value: float,
) -> None:
    """Freeze one consumer's total for a removed source; idempotent."""
    ledger = [dict(retired) for retired in entry.data.get(CONF_RETIRED_SOURCES, [])]
    retired = next((r for r in ledger if r.get("subentry_id") == source_uid), None)
    if retired is None:
        retired = {"subentry_id": source_uid, "title": title, "totals": {}}
        ledger.append(retired)

    totals = {uid: dict(keys) for uid, keys in retired.get("totals", {}).items()}
    if key in totals.get(consumer_uid, {}):
        return  # captured already, by an earlier teardown
    totals.setdefault(consumer_uid, {})[key] = value
    retired["totals"] = totals

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_RETIRED_SOURCES: ledger}
    )


def prune_retired_sources(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the frozen totals of consumers that no longer exist.

    A removed consumer takes its per-source sensors with it, so nothing reads
    its part of the ledger any more. Runs at setup, before the update listener
    is registered, so storing the result triggers no reload.
    """
    ledger = entry.data.get(CONF_RETIRED_SOURCES)
    if not ledger:
        return

    pruned = []
    for retired in ledger:
        totals = {
            uid: keys
            for uid, keys in retired.get("totals", {}).items()
            if uid in entry.subentries
        }
        if totals:
            pruned.append({**retired, "totals": totals})

    if pruned != ledger:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_RETIRED_SOURCES: pruned}
        )
