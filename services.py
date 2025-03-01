"""
This file is DEPRECATED - Service registration has been moved to __init__.py.

This file is kept for backwards compatibility but should not be used.
All service registration is now handled directly in __init__.py.
"""

"""Services for the Axium Amplifier integration."""
import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, ZONES
from .controller import AxiumController

_LOGGER = logging.getLogger(__name__)

# Define the service schema for HA to validate the bass and treble service calls
SERVICE_SCHEMA_BASS_TREBLE = vol.Schema({
    vol.Required("zone"): vol.In(list(ZONES.keys())),  # Convert to list
    vol.Required("level"): vol.All(int, vol.Range(min=-12, max=12))
})

# Define the service schema for HA to validate the max volume service call
SERVICE_SCHEMA_MAX_VOLUME = vol.Schema({
    vol.Required("zone"): vol.In(list(ZONES.keys())),
    vol.Required("level"): vol.All(int, vol.Range(min=0, max=160)) # Assuming max volume is 0-160
})

# Define the service schema for refreshing zone state
SERVICE_SCHEMA_REFRESH = vol.Schema({
    vol.Optional("zone"): vol.In(list(ZONES.keys())),  # Make zone optional; if not provided, refresh all zones
})

# List of service names for registration/unregistration
SERVICE_NAMES = ["set_bass", "set_treble", "set_max_volume", "refresh_state"]

async def async_setup_services(hass: HomeAssistant, controller: AxiumController) -> None:
    """Set up the services for the Axium integration."""
    # Store services data in hass.data to allow access across config entries
    hass.data.setdefault(DOMAIN, {})
    
    # If services are already registered, add this controller to controllers list and return
    if hass.data[DOMAIN].get("services_registered", False):
        if "controllers" not in hass.data[DOMAIN]:
            hass.data[DOMAIN]["controllers"] = []
        if controller not in hass.data[DOMAIN]["controllers"]:
            hass.data[DOMAIN]["controllers"].append(controller)
        return

    # Initialize controllers list if it doesn't exist
    if "controllers" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["controllers"] = []
    
    # Add controller to the list if not already there
    if controller not in hass.data[DOMAIN]["controllers"]:
        hass.data[DOMAIN]["controllers"].append(controller)

    # Set up service handlers
    async def handle_set_bass(call: ServiceCall) -> None:
        """Handle the set_bass service call."""
        zone_name = call.data.get("zone")
        level = call.data.get("level")
        zone_id = ZONES[zone_name]
        
        # Send command to all controllers
        for ctrl in hass.data[DOMAIN]["controllers"]:
            await ctrl.set_bass(zone_id, level)

    async def handle_set_treble(call: ServiceCall) -> None:
        """Handle the set_treble service call."""
        zone_name = call.data.get("zone")
        level = call.data.get("level")
        zone_id = ZONES[zone_name]
        
        # Send command to all controllers
        for ctrl in hass.data[DOMAIN]["controllers"]:
            await ctrl.set_treble(zone_id, level)

    async def handle_set_max_volume(call: ServiceCall) -> None:
        """Handle the set_max_volume service call."""
        zone_name = call.data.get("zone")
        level = call.data.get("level")
        zone_id = ZONES[zone_name]
        
        # Send command to all controllers
        for ctrl in hass.data[DOMAIN]["controllers"]:
            await ctrl.set_max_volume(zone_id, level)
            
    async def handle_refresh_state(call: ServiceCall) -> None:
        """Handle the refresh_state service call."""
        zone_name = call.data.get("zone")
        
        # If a specific zone is specified, refresh just that zone
        if zone_name:
            zone_id = ZONES[zone_name]
            _LOGGER.info(f"Manually refreshing state for zone: {zone_name}")
            
            # Send refresh command to all controllers
            for ctrl in hass.data[DOMAIN]["controllers"]:
                await ctrl.refresh_zone_state(zone_id)
        else:
            # If no zone specified, refresh all zones
            _LOGGER.info("Manually refreshing state for all zones")
            
            # Send refresh command to all controllers
            for ctrl in hass.data[DOMAIN]["controllers"]:
                await ctrl.refresh_all_zones()

    _LOGGER.debug("Registering bass, treble, max_volume, and refresh_state services.")
    hass.services.async_register(
        DOMAIN, "set_bass", handle_set_bass, schema=SERVICE_SCHEMA_BASS_TREBLE
    )
    hass.services.async_register(
        DOMAIN, "set_treble", handle_set_treble, schema=SERVICE_SCHEMA_BASS_TREBLE
    )
    hass.services.async_register(
        DOMAIN, "set_max_volume", handle_set_max_volume, schema=SERVICE_SCHEMA_MAX_VOLUME
    )
    hass.services.async_register(
        DOMAIN, "refresh_state", handle_refresh_state, schema=SERVICE_SCHEMA_REFRESH
    )
    
    # Mark services as registered
    hass.data[DOMAIN]["services_registered"] = True

async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister Axium services."""
    # If there are still controllers remaining, don't unregister services
    if "controllers" in hass.data[DOMAIN] and hass.data[DOMAIN]["controllers"]:
        return
    
    # Otherwise, unregister all services
    for service in SERVICE_NAMES:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
    
    # Mark services as unregistered
    if "services_registered" in hass.data[DOMAIN]:
        hass.data[DOMAIN]["services_registered"] = False 