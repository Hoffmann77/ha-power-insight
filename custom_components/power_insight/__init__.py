"""Set up the PowerInsight integration."""

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CHARGE_FROM_ADAPTERS,
    CONF_POWER_ENTITY,
    CONF_POWER_FROM_ADAPTERS,
    DOMAIN,
    PLATFORMS,
)
from .power_insight import PowerInsight
from .event_handler import EventHandler
from .adapter_models import ADAPTER_MODELS
from .utils import parse_price_unit


_LOGGER = logging.getLogger(__name__)


type MyConfigEntry = ConfigEntry[MyData]


@dataclass
class MyData:
    """Runtime data definition."""

    power_insight: PowerInsight
    event_handler: EventHandler


async def async_setup_entry(hass: HomeAssistant, entry: MyConfigEntry) -> bool:
    """Init the Mygrid instance from the config entry."""
    power_insight = PowerInsight()

    for subentry in entry.subentries.values():
        adapter_type = subentry.data["adapter"].get("adapter_type")
        if not adapter_type:
            continue

        model_cls = ADAPTER_MODELS.get(adapter_type)
        if model_cls is None:
            _LOGGER.warning("Unknown adapter type %r in subentry %s — skipping.", adapter_type, subentry.subentry_id)
            continue

        model = model_cls.from_subentry(subentry)
        power_insight.register_adapter(model.create_adapter())
    
    # The pre-1.0 issue id was shared by every entry; it is per entry now.
    ir.async_delete_issue(hass, DOMAIN, "no_grid_configured")
    no_grid_issue = f"no_grid_configured_{entry.entry_id}"
    _delete_issues_of_removed_devices(hass)

    if power_insight.grid_adapter is None:
        # Without a grid connection nothing can be calculated; raise a repair
        # issue and set up with no tracked entities. The shared tail below still
        # runs so the platform (and its empty sensor set) loads cleanly.
        ir.async_create_issue(
            hass,
            DOMAIN,
            no_grid_issue,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="no_grid_configured",
            translation_placeholders={"entry_title": entry.title},
        )
        source_entities: list[str] = []
    else:
        # Grid is present — dismiss any previously raised issue.
        ir.async_delete_issue(hass, DOMAIN, no_grid_issue)
        _check_source_restrictions(hass, entry)

        source_entities = power_insight.source_entities
        _check_price_entity(hass, entry, power_insight)
        _check_shared_power_entities(hass, entry)

    # --- Shared setup tail (runs for both the grid and no-grid paths) ---
    event_handler = EventHandler(hass, entry.entry_id, power_insight)
    event_handler.track_entities(source_entities)
    entry.runtime_data = MyData(power_insight, event_handler)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    # The ``set_value`` service is registered as a platform entity service in
    # sensor.py (async_setup_entry), so HA handles entity-target resolution.

    return True


#: The restriction field and repair issue of each device kind that has one.
_RESTRICTIONS = {
    "battery": (CONF_CHARGE_FROM_ADAPTERS, "reconfigure_battery_", "reconfigure_battery_adapters"),
    "consumer": (CONF_POWER_FROM_ADAPTERS, "reconfigure_consumer_", "reconfigure_consumer_sources"),
}


def _check_source_restrictions(hass: HomeAssistant, entry: MyConfigEntry) -> None:
    """Raise a repair issue for a device restricted to a device that is gone.

    A battery's ``charge_from`` and a consumer's ``power_from`` name devices by
    subentry id; once one of those is removed, the restriction silently
    narrows. (The engine copes — see "a broken restriction is reported, not
    hidden" — but the user should decide.) The issue is dismissed when the
    device is reconfigured or removed.
    """
    valid_source_ids = {
        sub.subentry_id
        for sub in entry.subentries.values()
        if sub.data.get("adapter", {}).get("adapter_type") in ("grid", "pv_system")
    }
    for subentry in entry.subentries.values():
        adapter = subentry.data.get("adapter", {})
        restriction = _RESTRICTIONS.get(adapter.get("adapter_type"))
        if restriction is None:
            continue
        field, prefix, translation_key = restriction
        sources = adapter.get("config", {}).get(field) or []
        if any(source_id not in valid_source_ids for source_id in sources):
            ir.async_create_issue(
                hass,
                DOMAIN,
                f"{prefix}{subentry.subentry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=translation_key,
                translation_placeholders={
                    "battery_name": subentry.title,
                    "device_name": subentry.title,
                },
            )


def _delete_issues_of_removed_devices(hass: HomeAssistant) -> None:
    """Dismiss every per-device repair issue whose device no longer exists."""
    existing = {
        subentry_id
        for config_entry in hass.config_entries.async_entries(DOMAIN)
        for subentry_id in config_entry.subentries
    }
    prefixes = tuple(prefix for _, prefix, _ in _RESTRICTIONS.values())
    for domain, issue_id in list(ir.async_get(hass).issues):
        if domain != DOMAIN or not issue_id.startswith(prefixes):
            continue
        if issue_id.split("_", 2)[2] not in existing:
            ir.async_delete_issue(hass, DOMAIN, issue_id)


def _check_shared_power_entities(hass: HomeAssistant, entry: MyConfigEntry) -> None:
    """Raise a repair issue while two devices read the same power sensor.

    The config flow refuses it, but an entry configured before that check can
    still have one: its watts would be counted twice, and one of the devices
    would never update.
    """
    issue_id = f"shared_power_entity_{entry.entry_id}"
    devices_by_entity: dict[str, list[str]] = {}
    for subentry in entry.subentries.values():
        entity_id = subentry.data.get("adapter", {}).get("config", {}).get(
            CONF_POWER_ENTITY
        )
        if entity_id:
            devices_by_entity.setdefault(entity_id, []).append(subentry.title)

    shared = {e: names for e, names in devices_by_entity.items() if len(names) > 1}
    if not shared:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    entity_id, names = next(iter(shared.items()))
    ir.async_create_issue(
        hass, DOMAIN, issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="shared_power_entity",
        translation_placeholders={
            "entry_title": entry.title,
            "entity_id": entity_id,
            "devices": ", ".join(sorted(names)),
        },
    )


def _check_price_entity(
    hass: HomeAssistant, entry: MyConfigEntry, power_insight: PowerInsight,
) -> None:
    """Raise a repair issue when the grid price cannot be used as it is.

    A price in a unit that is not a price per energy is ignored (every cost
    that needs it reads unknown), and one in another currency than Home
    Assistant's is used but not converted — both need the user. Nothing is
    decided while the price entity has no state yet.
    """
    unit_issue = f"price_unit_{entry.entry_id}"
    currency_issue = f"price_currency_{entry.entry_id}"
    for entity_id in power_insight.source_entities_price:
        state = hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return
        unit = state.attributes.get("unit_of_measurement")
        parsed = parse_price_unit(unit)
        if parsed is None:
            ir.async_create_issue(
                hass, DOMAIN, unit_issue,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="price_unit",
                translation_placeholders={
                    "entry_title": entry.title,
                    "entity_id": entity_id,
                    "unit": unit or "—",
                },
            )
        else:
            ir.async_delete_issue(hass, DOMAIN, unit_issue)

        currency = parsed[1] if parsed else None
        if currency is not None and currency != hass.config.currency:
            ir.async_create_issue(
                hass, DOMAIN, currency_issue,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="price_currency",
                translation_placeholders={
                    "entry_title": entry.title,
                    "entity_id": entity_id,
                    "currency": currency,
                    "configured": hass.config.currency,
                },
            )
        else:
            ir.async_delete_issue(hass, DOMAIN, currency_issue)


async def async_update_listener(
    hass: HomeAssistant, entry: MyConfigEntry
) -> None:
    """Handle config_entry updates."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: MyConfigEntry
) -> bool:
    """Unload the config entries."""
    unload = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    data = entry.runtime_data
    event_handler = data.event_handler
    event_handler.untrack_entities()

    return unload


async def async_migrate_entry(
    hass: HomeAssistant, entry: MyConfigEntry,
) -> bool:
    """Migrate the config entry to a newer version.

    Version 1.4 is the 1.0 baseline: every change to what is stored after it
    needs a migration step here. An entry written by a newer major version
    is refused rather than loaded — a downgrade cannot know what changed.
    """
    if entry.version > 1:
        _LOGGER.error(
            "Config entry %s was written by a newer version of Power Insight "
            "(version %s); downgrading is not supported",
            entry.title, entry.version,
        )
        return False

    if entry.minor_version < 2:
        _migrate_options_to_scopes(hass, entry)
    if entry.minor_version < 3:
        _migrate_drop_battery_efficiency(hass, entry)
    if entry.minor_version < 4:
        await _migrate_share_unique_ids(hass, entry)

    return True


async def _migrate_share_unique_ids(hass: HomeAssistant, entry: MyConfigEntry) -> None:
    """Key the source-share sensors by the source's subentry id, not its name.

    ``charging_share_from_{name}`` / ``power_share_from_{name}`` used the
    source device's display name, so renaming a device would orphan the
    sensor's history. The registry entries are renamed in place, so the
    history carries over.
    """
    by_name = {
        subentry.title: subentry.subentry_id
        for subentry in entry.subentries.values()
        if subentry.data.get("adapter", {}).get("adapter_type")
        in ("grid", "pv_system", "battery")
    }

    def rekey(entity_entry: er.RegistryEntry) -> dict[str, str] | None:
        for kind in ("charging_share_from_", "power_share_from_"):
            head, sep, name = entity_entry.unique_id.partition(f"_{kind}")
            if sep and name in by_name:
                return {"new_unique_id": f"{head}_{kind}{by_name[name]}"}
        return None

    await er.async_migrate_entries(hass, entry.entry_id, rekey)
    hass.config_entries.async_update_entry(entry, minor_version=4)


def _migrate_drop_battery_efficiency(hass: HomeAssistant, entry: MyConfigEntry) -> None:
    """Drop the stored round-trip efficiency from every battery subentry.

    Nothing ever read it. Savings work from the metered readings, and a
    battery's LCOS divides its lifetime cost by the energy it *discharges*, so
    the losses are already netted out of that figure — see
    docs/dev/engine-calculations.md. Leaving the key behind would keep
    suggesting it feeds a calculation somewhere.
    """
    for subentry in entry.subentries.values():
        adapter = subentry.data.get("adapter", {})
        config = adapter.get("config", {})
        if "battery_efficiency" not in config:
            continue

        new_config = {k: v for k, v in config.items() if k != "battery_efficiency"}
        hass.config_entries.async_update_subentry(
            entry,
            subentry,
            data={**subentry.data, "adapter": {**adapter, "config": new_config}},
        )

    hass.config_entries.async_update_entry(entry, minor_version=3)


def _migrate_options_to_scopes(hass: HomeAssistant, entry: MyConfigEntry) -> None:
    """Convert the old flat options to the v2 per-scope schema.

    Pre-release, so history is not preserved — only behaviour is roughly kept:
    the old global selection is distributed into each scope, intersected with
    what that scope supports. See docs/options-flow-redesign.md.
    """
    # Imported here to avoid a circular import at module load.
    from .const import SCOPES, SCOPE_SUPPORTED_OPTIONS

    old = entry.options or {}

    # Already in the v2 per-scope shape (e.g. created by the current flow): just
    # stamp the version, never rewrite the user's selection.
    if "scopes" in old:
        if entry.minor_version != 2:
            hass.config_entries.async_update_entry(entry, minor_version=2)
        return

    leaves = set(
        old.get("calculate_instantaneous_rates", [])
        + old.get("calculate_instantaneous_saving_rates", [])
        + old.get("calculate_accumulated_entities", [])
    )
    if old.get("enable_power_shares"):
        leaves |= {
            "enable_distribution_ratios",
            "enable_distribution_shares",
            "enable_charging_source_shares",
            "enable_power_source_shares",
        }
    # Watt sensors were always-on before the redesign — keep them.
    leaves.add("enable_distribution_power")
    # Export compensation used to ride on the cost-rate keys.
    if "calculate_cost_rates" in leaves:
        leaves.add("enable_export_compensation_rate")
    if "accumulate_cost_rates" in leaves:
        leaves.add("accumulate_export_compensation")

    new_options = {
        "schema": 2,
        "scopes": {
            scope: sorted(leaves & SCOPE_SUPPORTED_OPTIONS[scope])
            for scope in SCOPES
        },
        "debug_power_entities": bool(old.get("debug_power_entities", False)),
    }
    hass.config_entries.async_update_entry(
        entry, options=new_options, minor_version=2
    )
