"""Exceptions for the PowerInsight integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class PowerInsightError(HomeAssistantError):
    """Base class for PowerInsight errors."""


class BatteryChargeSourcesNotConfigured(PowerInsightError):
    """A battery adapter has no charge source configured.

    A battery with an empty ``charge_from_adapters`` cannot charge from any
    source, so leaving it unset is a misconfiguration rather than a shorthand
    for "the whole mix" — to draw from every source the user selects them
    explicitly. Raised during config-flow validation (to block the save) and at
    setup (to raise a repair issue). Carries the offending battery's name so the
    caller can build a user-facing message.
    """

    def __init__(self, battery_name: str) -> None:
        """Store the battery name and build the error message."""
        self.battery_name = battery_name
        super().__init__(
            f"Battery {battery_name!r} has no charge source configured; "
            "select at least one source it can charge from."
        )


def ensure_battery_charge_sources(battery_name: str, charge_from) -> None:
    """Raise :class:`BatteryChargeSourcesNotConfigured` if ``charge_from`` is empty.

    The single definition of "a battery is misconfigured" (no charge source),
    shared by the config flow (which blocks the save) and setup (which raises a
    repair issue).
    """
    if not charge_from:
        raise BatteryChargeSourcesNotConfigured(battery_name)
