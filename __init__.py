"""The Axium integration."""
import logging
from typing import Any

import voluptuous as vol

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, CONF_SERIAL_PORT, CONF_ZONES, ZONES
from .controller import AxiumController

_LOGGER = logging.getLogger("custom_components.axium")

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
    try:
        _LOGGER.debug("async_setup function called - START")
        if DOMAIN not in config:
            return True

        conf = config[DOMAIN]
        serial_port = conf[CONF_SERIAL_PORT]
        zones = conf[CONF_ZONES]

        controller = AxiumController(serial_port, config_dir=hass.config.path()) # Fixed this line
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["controller"] = controller
        hass.data[DOMAIN]["config"] = {
                "serial_port": serial_port,
                "zones": zones
            }

        _LOGGER.debug("Before async_load_platform call. DOMAIN is: %s", DOMAIN)
        task = hass.async_create_task(
            hass.helpers.discovery.async_load_platform(
                Platform.MEDIA_PLAYER, DOMAIN, {}, config
            )
        )
        _LOGGER.debug("After async_load_platform call. Task is: %s", task)
        _LOGGER.debug("async_setup function called - END")
        return True
    except Exception as e:
        _LOGGER.error("Exception in async_setup: %s", e)
        return False
