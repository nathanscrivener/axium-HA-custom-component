"""Services for the Axium Amplifier integration."""
import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, ZONES
from .controller import AxiumController

_LOGGER = logging.getLogger(__name__)

# Define the service schema for HA to validate the bass and treble service calls
SERVICE_SCHEMA = vol.Schema({
    vol.Required("zone"): vol.In(list(ZONES.keys())),  # Convert to list
    vol.Required("level"): vol.All(int, vol.Range(min=-12, max=12))
})


async def async_setup_services(hass: HomeAssistant, controller: AxiumController) -> None:
    """Set up the services for the Axium integration."""

    async def handle_set_bass(call: ServiceCall) -> None:
        """Handle the set_bass service call."""
        zone_name = call.data.get("zone")
        level = call.data.get("level")
        zone_id = ZONES[zone_name]
        await controller.set_bass(zone_id, level)

    async def handle_set_treble(call: ServiceCall) -> None:
        """Handle the set_treble service call."""
        zone_name = call.data.get("zone")
        level = call.data.get("level")
        zone_id = ZONES[zone_name]
        await controller.set_treble(zone_id, level)

    _LOGGER.debug("Registering bass and treble services.")
    hass.services.async_register(
        DOMAIN, "set_bass", handle_set_bass, schema=SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "set_treble", handle_set_treble, schema=SERVICE_SCHEMA
    )