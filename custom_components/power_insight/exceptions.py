"""Module for custom home-assistant exceptions."""

from homeassistant.exceptions import HomeAssistantError


def create_hass_exception(input_exception):
    """Create a hass exception."""
    name = input_exception.__class__.__name__
    return type(name, (HomeAssistantError,))
