"""The Axium Amplifier integration."""
import logging
import voluptuous as vol
from typing import Any

from .const import DOMAIN, CONF_SERIAL_PORT, CONF_ZONES, ZONES

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.discovery import async_load_platform
# No need for async_remove_entity

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

# HA looks for the following function and calls it to set up the integration
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Axium integration."""

    _LOGGER.info("Axium integration setup started.")

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
        # Attempt to connect.  The connect() method now returns True/False and initializes state.
        if not await controller.connect():
            _LOGGER.error("Failed to connect to Axium controller during setup.")
            return False  # Exit early if the initial connection fails.

        # Store controller and config in hass.data
        _LOGGER.debug("Storing controller and config in hass.data.")
        hass.data[DOMAIN] = {
            "controller": controller,
            "config": {
                "serial_port": serial_port,
                "zones": zones
            },
            "entry": None,  # Placeholder for the config entry
        }

        # Define bass and treble service functions
        async def handle_set_bass(call):
            """Handle the set_bass service call."""
            zone_name = call.data.get("zone")
            level = call.data.get("level")
            zone_id = ZONES[zone_name]
            await controller.set_bass(zone_id, level)

        async def handle_set_treble(call):
            """Handle the set_treble service call."""
            zone_name = call.data.get("zone")
            level = call.data.get("level")
            zone_id = ZONES[zone_name]
            await controller.set_treble(zone_id, level)

        # Define the service schema for HA to validate the bass and treble service calls
        service_schema = vol.Schema({
            vol.Required("zone"): vol.In(list(ZONES.keys())),  # Convert to list
            vol.Required("level"): vol.All(int, vol.Range(min=-12, max=12))
        })

        _LOGGER.debug("Registering bass and treble services.")
        hass.services.async_register(DOMAIN, "set_bass", handle_set_bass, schema=service_schema)
        hass.services.async_register(DOMAIN, "set_treble", handle_set_treble, schema=service_schema)

        # Load the media_player platform
        _LOGGER.debug("Loading Axium media_player platform.")
        # Store the config entry
        hass.data[DOMAIN]['entry'] = config.get('config_entry') #Get config entry from passed in config
        #The line above replaces the need for passing in the entry, and storing it in async_setup_entry
        task = hass.async_create_task(
            async_load_platform(
                hass, Platform.MEDIA_PLAYER, DOMAIN, {}, config
            )
        )

        if hass.data[DOMAIN]['entry']: #Check if the entry exists
            hass.data[DOMAIN]['entry'].async_on_unload(task)  #Simplified unload

        _LOGGER.info("Axium integration setup completed successfully.")
        return True  # Indicate successful setup

    except Exception as e:
        _LOGGER.error(f"Failed to set up Axium integration: {e}", exc_info=True)
        return False  # Indicate setup failure

async def async_unload_entry(hass: HomeAssistant, entry: ConfigType) -> bool:
    """Handle unloading of the Axium integration."""
    _LOGGER.info("Unloading Axium integration")

    # Close the serial connection
    controller = hass.data[DOMAIN]["controller"]
    await controller.disconnect()

    # Unload the platform (media_player)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove data
    if unload_ok:
        hass.data.pop(DOMAIN)

    return unload_ok