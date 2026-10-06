"""Keep the carried-over history in the config entry.

The Home Assistant side of ``history.py``. Each device subentry holds its
history *as entered*; the config entry holds what it solved to, under
``data["history"]``:

* ``entered`` — the figures the last solve used, per device, to tell when
  they change.
* ``inputs`` / ``home`` — the solve's inputs. A removed device's stay, because
  its kWh are still part of the home's totals when the others are re-solved.
* ``records`` — one solved :class:`~.history.Record` per device. A removed
  device's record stays as it was: its history outlives its subentry.
* ``last_price`` — each device's levelized price at the last setup, so a
  battery's history keeps the price of a PV system that has since been removed.

The history is re-solved at setup whenever the entered figures differ from
the last solve. Saving a history reloads the entry, so that is "on save".
Removing a device or editing its configuration changes no entered figure, so
it moves nobody's past. The write happens before the update listener is
registered, so it triggers no reload of its own.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CHARGE_FROM_ADAPTERS,
    CONF_COUNTING_SINCE,
    CONF_EXPORT_COMPENSATION,
    CONF_EXPORTS_POWER,
    CONF_HISTORY,
    DOMAIN,
)
from .history import (
    BATTERY,
    MISSING_TARIFF,
    MISSING_WAITING,
    TOTAL_COST_SAVINGS,
    PV_SYSTEM,
    DeviceInputs,
    HomeInputs,
    Record,
    Solution,
    Totals,
    history_totals,
    shares_period,
    solve,
)
from .power_insight import PowerInsight

_LOGGER = logging.getLogger(__name__)

GRID = "grid"

_ENTERED = "entered"
_INPUTS = "inputs"
_HOME = "home"
_RECORDS = "records"
_LAST_PRICE = "last_price"

#: The history fields of each form, as stored in the subentry, and the solver
#: input each one is. The grid's are the whole home's, named apart from a
#: device's own because every device type shares one form and its labels.
HOME_FIELDS = {
    "home_fed_in": "fed_in",
    "average_tariff": "tariff",
    "home_savings": "savings",
    "home_export_compensation": "export_compensation",
}
DEVICE_FIELDS = {
    "produced": "produced",
    "charged": "charged",
    "grid_charged": "grid_charged",
    "discharged": "discharged",
    "fed_in": "fed_in",
    "into_batteries": "into_batteries",
    "average_tariff": "tariff",
    "feed_in_tariff": "feed_in_tariff",
    "savings": "savings",
    "export_compensation": "export_compensation",
    "levelized_savings": "levelized_savings",
}
#: Only asked of a device added later, which cannot share the home's figures.
#: (Every PV system and battery may give its own average tariff; one added
#: later must, one sharing the home's period falls back to the grid's.)
STANDALONE_FIELDS = ("into_batteries",)


@dataclass(frozen=True)
class DeviceView:
    """What the history needs to know of one subentry.

    A flow builds one for a device that is not saved yet, to check its figures
    together with everyone else's before saving them.
    """

    uid: str
    adapter_type: str
    config: dict
    entered: dict
    counting_since: str | None


def device_views(entry: ConfigEntry) -> list[DeviceView]:
    """Return a view of every subentry of ``entry``."""
    return [
        DeviceView(
            uid=subentry.subentry_id,
            adapter_type=subentry.data.get("adapter", {}).get("adapter_type", ""),
            config=subentry.data.get("adapter", {}).get("config", {}),
            entered=_present(subentry.data.get(CONF_HISTORY) or {}),
            counting_since=subentry.data.get(CONF_COUNTING_SINCE),
        )
        for subentry in entry.subentries.values()
    ]


def build_inputs(
    views: list[DeviceView],
) -> tuple[HomeInputs, list[DeviceInputs]] | None:
    """Turn the views into the solver's inputs; ``None`` without a grid.

    A device set up more than a day after the grid is standalone. Its
    feed-in tariff defaults to the export compensation it is configured with.
    """
    grid = next((v for v in views if v.adapter_type == GRID), None)
    if grid is None:
        return None

    home = HomeInputs(
        grid.uid, **{field: grid.entered.get(key) for key, field in HOME_FIELDS.items()}
    )
    grid_since = _parse(grid.counting_since)
    devices = []
    for view in views:
        if view.adapter_type not in (PV_SYSTEM, BATTERY):
            continue
        since = _parse(view.counting_since)
        fields = {field: view.entered.get(key) for key, field in DEVICE_FIELDS.items()}
        if fields["feed_in_tariff"] is None:
            fields["feed_in_tariff"] = view.config.get(CONF_EXPORT_COMPENSATION)
        devices.append(
            DeviceInputs(
                view.uid,
                view.adapter_type,
                exports=bool(view.config.get(CONF_EXPORTS_POWER)),
                charge_from=tuple(view.config.get(CONF_CHARGE_FROM_ADAPTERS) or ()),
                standalone=_standalone(grid_since, since),
                **fields,
            )
        )
    return home, devices


def is_standalone(entry: ConfigEntry, counting_since: str | None) -> bool:
    """Whether a device counted from ``counting_since`` stands alone.

    For a form: a device being added now, long after the grid, is asked for
    its own tariff instead of sharing the home's figures.
    """
    grid = next((v for v in device_views(entry) if v.adapter_type == GRID), None)
    if grid is None:
        return False
    return _standalone(_parse(grid.counting_since), _parse(counting_since))


def check_view(entry: ConfigEntry, view: DeviceView) -> Solution | None:
    """Solve the history as it would be with ``view`` saved.

    ``view`` replaces the subentry of the same uid, or joins as a new device,
    so a form's figures are checked together with every other device's.
    """
    views = [v for v in device_views(entry) if v.uid != view.uid]
    return solve_views(entry, [*views, view])


def solve_views(entry: ConfigEntry, views: list[DeviceView]) -> Solution | None:
    """Solve the history of ``views``, with the removed devices' kWh still in.

    ``None`` without a grid, when there is no history to solve.
    """
    built = build_inputs(views)
    if built is None:
        return None
    home, devices = built
    live = {v.uid for v in views}
    retired = [
        DeviceInputs.from_dict(data)
        for uid, data in _stored(entry).get(_INPUTS, {}).items()
        if uid not in live
    ]
    return solve(home, [*devices, *retired])


def async_sync_history(
    hass: HomeAssistant, entry: ConfigEntry, power_insight: PowerInsight
) -> None:
    """Re-solve the history if the entered figures changed, and note prices.

    Called at setup, after the adapters are registered and before the
    sensors read the records. Figures that cannot be solved keep the last
    solved history: the flows refuse them, so they only reach here when
    edited outside the flow.
    """
    stored = _stored(entry)
    views = device_views(entry)
    live = {v.uid for v in views}
    entered = {v.uid: v.entered for v in views if v.entered}
    last_entered = stored.get(_ENTERED, {})
    updated = dict(stored)

    if {u: e for u, e in last_entered.items() if u in live} != entered:
        solution = solve_views(entry, views)
        if solution is not None and solution.problems:
            _LOGGER.warning(
                "The history entered for %s does not balance (%s); keeping "
                "the history solved last",
                entry.title,
                ", ".join(p.code for p in solution.problems),
            )
        elif solution is not None:
            home, devices = build_inputs(views)

            def retired(key: str) -> dict:
                """The removed devices' part of ``key``, kept as it was."""
                return {u: d for u, d in stored.get(key, {}).items() if u not in live}

            updated[_ENTERED] = {**retired(_ENTERED), **entered}
            updated[_HOME] = home.to_dict()
            updated[_INPUTS] = {
                **retired(_INPUTS),
                **{d.uid: d.to_dict() for d in devices if d.uid in entered},
            }
            updated[_RECORDS] = {
                **retired(_RECORDS),
                **{
                    uid: record.to_dict()
                    for uid, record in solution.records.items()
                    if uid in live
                },
            }

    if updated.get(_RECORDS):
        prices = dict(updated.get(_LAST_PRICE, {}))
        for adapter in power_insight.prod_adapters:
            price = _price(adapter)
            if price is not None:
                prices[adapter.uid] = price
        updated[_LAST_PRICE] = prices

    if updated != stored:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_HISTORY: updated}
        )


def stored_records(entry: ConfigEntry) -> dict[str, Record]:
    """Return every stored history record, removed devices' included."""
    return {
        uid: Record.from_dict(data)
        for uid, data in _stored(entry).get(_RECORDS, {}).items()
    }


def price_lookup(
    entry: ConfigEntry, power_insight: PowerInsight
) -> Callable[[str], float | None]:
    """Return ``price(uid)``: a device's levelized price per kWh, as of now.

    A live device's is its LCOE / LCOS times its correction factor, so a
    lifetime cost edit restates its history. A removed device's is the last
    one it had: it can never be edited again, so that one cannot go stale.
    """
    last = _stored(entry).get(_LAST_PRICE, {})

    def price(uid: str) -> float | None:
        adapter = power_insight.get_adapter_by_uid(uid)
        if adapter is None:
            return last.get(uid)
        if adapter not in power_insight.prod_adapters:
            return None  # only PV systems and batteries have an LCOE / LCOS
        return _price(adapter)

    return price


# ---------------------------------------------------------------------------
# What the sensors add
# ---------------------------------------------------------------------------

#: State attributes of a total that carries history.
ATTR_CARRIED_OVER = "carried_over"
ATTR_CARRIED_OVER_UNTIL = "carried_over_until"
ATTR_CARRIED_OVER_MISSING = "carried_over_missing"
ATTR_CARRIED_OVER_WAITING_FOR = "carried_over_waiting_for"
ATTR_TRACKED = "tracked"


@dataclass(frozen=True)
class DeviceHistory:
    """One device's record, priced: what its totals carry over."""

    record: Record
    totals: Totals


def priced_history(
    entry: ConfigEntry, power_insight: PowerInsight
) -> dict[str, DeviceHistory]:
    """Price every stored record, removed devices' included.

    Done once per setup: the records only change at setup, and so do the
    prices, because a lifetime cost edit is a reconfigure, which reloads.
    """
    price = price_lookup(entry, power_insight)
    return {
        uid: DeviceHistory(record, history_totals(record, price))
        for uid, record in stored_records(entry).items()
    }


def device_carried_over(
    entry: ConfigEntry, history: dict[str, DeviceHistory], uid: str, key: str
) -> tuple[float | None, dict]:
    """What device ``uid``'s total ``key`` carries over, and its attributes.

    ``(None, {})`` when the device has no history for that total. A total
    missing a term carries nothing, and its attributes say why.
    """
    found = history.get(uid)
    if found is None or key not in found.totals.values:
        return None, {}

    value = found.totals.values[key]
    attributes: dict = {}
    if value is None:
        reason = found.totals.missing[key]
        attributes[ATTR_CARRIED_OVER_MISSING] = reason
        if reason == MISSING_WAITING:
            attributes[ATTR_CARRIED_OVER_WAITING_FOR] = [
                _name(entry, waited) for waited in found.record.waiting_for
            ]
    else:
        attributes[ATTR_CARRIED_OVER] = round(value, 2)
    if (subentry := entry.subentries.get(uid)) is not None:
        attributes[ATTR_CARRIED_OVER_UNTIL] = subentry.data.get(CONF_COUNTING_SINCE)
    return value, attributes


def summed_carried_over(
    entry: ConfigEntry, history: dict[str, DeviceHistory], key: str
) -> tuple[float | None, dict]:
    """What a whole-home total carries over: every device's, removed included.

    The sum of exactly what the per-device totals carry, so a combined total
    stays the sum of its devices; a device whose total carries nothing is
    left out and named. ``(None, {})`` when no device has history for ``key``.
    """
    relevant = {
        uid: found for uid, found in history.items() if key in found.totals.values
    }
    if not relevant:
        return None, {}

    total = 0.0
    missing: dict[str, str] = {}
    for uid, found in relevant.items():
        value = found.totals.values[key]
        if value is None:
            missing[_name(entry, uid)] = found.totals.missing[key]
        else:
            total += value
    attributes: dict = {ATTR_CARRIED_OVER: round(total, 2)}
    if missing:
        attributes[ATTR_CARRIED_OVER_MISSING] = missing
    return total, attributes


def async_check_tariff(
    hass: HomeAssistant, entry: ConfigEntry, history: dict[str, DeviceHistory]
) -> None:
    """Raise a repair issue while a device's savings wait for a tariff.

    A device's kWh history is valued at the average grid tariff: its own, or
    the grid's for every device without one. With neither, its savings carry
    nothing, which is easy to miss because the tariff usually lives on another
    device's form. The issue names the devices and says where to add it, and
    is dismissed at the setup that follows once every device has one.
    """
    issue_id = f"history_tariff_missing_{entry.entry_id}"
    devices = sorted(
        _name(entry, uid)
        for uid, found in history.items()
        if uid in entry.subentries
        and found.totals.missing.get(TOTAL_COST_SAVINGS) == MISSING_TARIFF
    )
    if not devices:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="history_tariff_missing",
        translation_placeholders={
            "entry_title": entry.title,
            "devices": ", ".join(devices),
        },
    )


def _name(entry: ConfigEntry, uid: str) -> str:
    """A device's name; a removed device's id, its name being gone with it."""
    subentry = entry.subentries.get(uid)
    return subentry.title if subentry is not None else uid


def _price(adapter) -> float | None:
    lcoe = adapter.lcoe
    if lcoe is None:
        return None
    return lcoe * adapter.correction_factor


def _stored(entry: ConfigEntry) -> dict:
    return entry.data.get(CONF_HISTORY) or {}


def _present(entered: dict) -> dict:
    """Drop the fields left empty, so an untouched form reads as no history."""
    return {k: v for k, v in entered.items() if v is not None}


def _standalone(grid_since: datetime | None, since: datetime | None) -> bool:
    return grid_since is not None and since is not None and not shares_period(
        grid_since, since
    )


def _parse(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None
