"""The Axium Amplifier integration."""
import logging

from typing import Any

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.discovery import async_load_platform

from .const import DOMAIN, CONF_SERIAL_PORT, CONF_ZONES, ZONES
from .controller import AxiumController

_LOGGER = logging.getLogger(__name__) 

PLATFORMS = [Platform.MEDIA_PLAYER]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_SERIAL_PORT): cv.string,
                vol.Required(CONF_ZONES): vol.All(
                    cv.ensure_list, [vol.In(ZONES.keys())]
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Axium component."""
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    serial_port = conf[CONF_SERIAL_PORT]
    zones = conf[CONF_ZONES]

    try:
        # Initialize and connect to the controller
        controller = AxiumController(serial_port)
        await controller.connect()  # Ensure the controller is connected
    
    # Store controller and config in hass.data
        hass.data[DOMAIN] = {
            "controller": controller,
            "config": {
                "serial_port": serial_port,
                "zones": zones
            }
        }
        # Register services
        async def handle_set_bass(call):
            """Handle bass adjustments."""
            zone_name = call.data["zone"]
            level = int(call.data["level"])
            if zone_name not in ZONES:
                raise ValueError(f"Invalid zone: {zone_name}")
            if not (-12 <= level <= 12):
                raise ValueError(f"Bass level out of range (-12 to 12): {level}")
            zone_id = ZONES[zone_name]
            await controller.set_bass(zone_id, level)

        async def handle_set_treble(call):
            """Handle treble adjustments."""
            zone_name = call.data["zone"]
            level = int(call.data["level"])
            if zone_name not in ZONES:
                raise ValueError(f"Invalid zone: {zone_name}")
            if not (-12 <= level <= 12):
                raise ValueError(f"Treble level out of range (-12 to 12): {level}")
            zone_id = ZONES[zone_name]
            await controller.set_treble(zone_id, level)

        # Register services
        hass.services.async_register(DOMAIN, "set_bass", handle_set_bass)
        hass.services.async_register(DOMAIN, "set_treble", handle_set_treble)
        
        # Load the media_player platform
        hass.async_create_task(
            async_load_platform(
                hass, Platform.MEDIA_PLAYER, DOMAIN, {}, config
            )
        )

        return True
    except Exception as e:
        _LOGGER.error("Failed to set up Axium integration: %s", e, exc_info=True)
        return False