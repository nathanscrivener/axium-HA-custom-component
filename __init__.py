"""The Axium Amplifier integration."""
import logging
from .const import DOMAIN, CONF_SERIAL_PORT, CONF_ZONES, ZONES
from typing import Any

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.discovery import async_load_platform


from .controller import AxiumController

_LOGGER = logging.getLogger(__name__)

# Log a message when the module is imported
_LOGGER.info("Axium integration module imported.")

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
    _LOGGER.info("Axium integration setup started.")
    if DOMAIN not in config:
        _LOGGER.debug("Axium integration not in config, skipping setup.")
        return True

    conf = config[DOMAIN]
    serial_port = conf.get(CONF_SERIAL_PORT)
    zones = conf.get(CONF_ZONES)

    if not serial_port or not zones:
        _LOGGER.error("Missing required configuration: serial_port or zones.")
        return False

    try:
        # Initialize the controller
        _LOGGER.debug("Initializing Axium controller.")
        controller = AxiumController(serial_port)
        await controller.connect()  # Attempt to connect

        # Ensure the controller is properly initialized
        if not controller:
            _LOGGER.error("Failed to initialize Axium controller.")
            return False

        # Store controller and config in hass.data
        _LOGGER.debug("Storing controller and config in hass.data.")
        hass.data[DOMAIN] = {
            "controller": controller,
            "config": {
                "serial_port": serial_port,
                "zones": zones
            }
        }

        # Register services
        
        _LOGGER.debug("Registering services.")
        async def handle_set_bass(call):
            #Handle bass adjustments.
            zone_name = call.data.get("zone")
            level = call.data.get("level")
            if not zone_name or not level:
                _LOGGER.error("Missing zone or level in service call.")
                return
            if zone_name not in ZONES:
                _LOGGER.error(f"Invalid zone: {zone_name}")
                return
            try:
                level = int(level)
                if not (-12 <= level <= 12):
                    _LOGGER.error(f"Bass level out of range (-12 to 12): {level}")
                    return
                zone_id = ZONES[zone_name]
                await controller.set_bass(zone_id, level)
            except ValueError as e:
                _LOGGER.error(f"Invalid level value: {e}")

        async def handle_set_treble(call):
            #Handle treble adjustments.
            zone_name = call.data.get("zone")
            level = call.data.get("level")
            if not zone_name or not level:
                _LOGGER.error("Missing zone or level in service call.")
                return
            if zone_name not in ZONES:
                _LOGGER.error(f"Invalid zone: {zone_name}")
                return
            try:
                level = int(level)
                if not (-12 <= level <= 12):
                    _LOGGER.error(f"Treble level out of range (-12 to 12): {level}")
                    return
                zone_id = ZONES[zone_name]
                await controller.set_treble(zone_id, level)
            except ValueError as e:
                _LOGGER.error(f"Invalid level value: {e}")


    
        # Register services
        _LOGGER.debug("Register bass and treble services.")
        
        # Define the service schema
        service_schema = vol.Schema({
            vol.Required("zone"): vol.In(list(ZONES.keys())),  # Convert to list
            vol.Required("level"): vol.All(int, vol.Range(min=-12, max=12))
        })
        
        hass.services.async_register(DOMAIN, "set_bass", handle_set_bass, schema=service_schema)
        hass.services.async_register(DOMAIN, "set_treble", handle_set_treble, schema=service_schema)

        # Load the media_player platform
        _LOGGER.debug("Loading Axium media_player platform.")
        hass.async_create_task(
            async_load_platform(
                hass, Platform.MEDIA_PLAYER, DOMAIN, {}, config
            )
        )
        
        _LOGGER.info("Axium integration setup completed successfully.")
        return True

    except Exception as e:
        _LOGGER.error(f"Failed to set up Axium integration: {e}", exc_info=True)
        return False