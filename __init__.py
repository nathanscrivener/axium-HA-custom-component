"""The Axium Amplifier integration."""
import logging
import voluptuous as vol
from typing import Any

from .const import DOMAIN, CONF_SERIAL_PORT, CONF_ZONES, CONF_ZONE_NAMES, ZONES

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.config_entries import ConfigEntry

from .controller import AxiumController
# Import services only when needed to avoid circular imports

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

# YAML config setup
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Axium integration from YAML."""
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    
    # Initialize domain data
    hass.data.setdefault(DOMAIN, {})
    
    # Forward the config to be handled by async_setup_entry
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "import"},
            data={
                CONF_SERIAL_PORT: conf[CONF_SERIAL_PORT],
                CONF_ZONES: conf[CONF_ZONES],
                CONF_ZONE_NAMES: {zone: zone.replace("_", " ").title() for zone in conf[CONF_ZONES]},
            },
        )
    )
    
    return True

# Config entry setup
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Axium integration from a config entry."""
    _LOGGER.info("Axium integration setup started from config entry.")

    serial_port = entry.data.get(CONF_SERIAL_PORT)
    zones = entry.data.get(CONF_ZONES)
    zone_names = entry.data.get(CONF_ZONE_NAMES, {})

    if not serial_port or not zones:
        _LOGGER.error("Missing required configuration: serial_port or zones.")
        return False

    try:
        # Initialize domain data
        hass.data.setdefault(DOMAIN, {})
        
        # Initialize the controller
        _LOGGER.debug("Initializing Axium controller.")
        controller = AxiumController(serial_port)
        # Attempt to connect
        if not await controller.connect():
            _LOGGER.error("Failed to connect to Axium controller during setup.")
            return False  # Exit early if the initial connection fails.

        # Store controller and config in hass.data
        _LOGGER.debug("Storing controller and config in hass.data.")
        hass.data[DOMAIN][entry.entry_id] = {
            "controller": controller,
            "config": {
                "serial_port": serial_port,
                "zones": zones,
                "zone_names": zone_names
            },
            "entry": entry,
        }

        # Register services from services.py
        try:
            from .services import async_setup_services
            await async_setup_services(hass, controller)
        except Exception as service_err:
            _LOGGER.error(f"Failed to register Axium services: {service_err}", exc_info=True)
            # Continue setup even if service registration fails

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        _LOGGER.info("Axium integration setup completed successfully.")
        return True  # Indicate successful setup

    except Exception as e:
        _LOGGER.error(f"Failed to set up Axium integration: {e}", exc_info=True)
        return False  # Indicate setup failure

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle unloading of the Axium integration."""
    _LOGGER.info("Unloading Axium integration")

    # Unload the platform (media_player)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        # Get controller before removing the data
        controller = hass.data[DOMAIN][entry.entry_id]["controller"]
        
        # Close the serial connection
        await controller.disconnect()
        
        # Remove this controller from the list of controllers if it exists
        if "controllers" in hass.data[DOMAIN] and controller in hass.data[DOMAIN]["controllers"]:
            hass.data[DOMAIN]["controllers"].remove(controller)
        
        # Remove data for this entry
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # If no more config entries for this domain, clean up completely
        entries = hass.config_entries.async_entries(DOMAIN)
        if len(entries) == 0:
            try:
                # Unregister services
                from .services import async_unregister_services
                await async_unregister_services(hass)
            except Exception as service_err:
                _LOGGER.error(f"Failed to unregister Axium services: {service_err}", exc_info=True)
                
            # Remove domain data if it exists
            if DOMAIN in hass.data:
                hass.data.pop(DOMAIN)

    return unload_ok
