"""The Axium Amplifier integration."""
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
        if DOMAIN not in config:
            return True

        conf = config[DOMAIN]
        serial_port = conf[CONF_SERIAL_PORT]
        zones = conf[CONF_ZONES]

        controller = AxiumController(serial_port)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["controller"] = controller
        hass.data[DOMAIN]["config"] = {
                "serial_port": serial_port,
                "zones": zones
            }

        # ========== ADDED SERVICE HANDLERS ========== #
        async def handle_set_bass(call):
            """Handle bass adjustments with validation and error logging."""
            try:
                zone_name = call.data["zone"]
                level = int(call.data["level"])
                if zone_name not in ZONES:
                    raise ValueError(f"Invalid zone: {zone_name}")
                if level < -12 or level > 12:
                    raise ValueError(f"Bass level out of range (-12 to 12): {level}")
                
                zone_id = ZONES[zone_name]
                await controller.set_bass(zone_id, level)
            except Exception as e:
                _LOGGER.error("Service axium.set_bass failed: %s", str(e), exc_info=True)
                raise

        async def handle_set_treble(call):
            """Handle treble level adjustment."""
            zone_name = call.data.get("zone")
            level = call.data.get("level")
            if zone_name not in ZONES:
                _LOGGER.error("Invalid zone: %s", zone_name)
                return
            await controller.set_treble(ZONES[zone_name], level)

        # Register services
        hass.services.async_register(DOMAIN, "set_bass", handle_set_bass)
        hass.services.async_register(DOMAIN, "set_treble", handle_set_treble)
        # ========== END OF ADDED CODE ========== #
        
        task = hass.async_create_task(
            hass.helpers.discovery.async_load_platform(
                Platform.MEDIA_PLAYER, DOMAIN, {}, config
            )
        )

        return True
    except Exception as e:
        _LOGGER.error("Exception in async_setup: %s", e)
        return False
