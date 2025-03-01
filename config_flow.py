"""Config flow for Axium Amplifier integration."""
import logging
import asyncio
import os
import serial.tools.list_ports
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, ZONES, CONF_SERIAL_PORT, CONF_ZONES, CONF_ZONE_NAMES
from .controller import AxiumController

_LOGGER = logging.getLogger(__name__)

class AxiumConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Axium Amplifier."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._serial_port: Optional[str] = None
        self._selected_zones: List[str] = []
        self._zone_names: Dict[str, str] = {}
        self._discovered_ports: List[str] = []

    async def async_step_import(self, import_data: Dict[str, Any]) -> FlowResult:
        """Import configuration from YAML."""
        _LOGGER.info("Importing configuration from YAML")
        
        # Check if we already have this device configured
        await self.async_set_unique_id(f"axium_{import_data[CONF_SERIAL_PORT]}")
        self._abort_if_unique_id_configured()
        
        # Test the connection to make sure it works
        if not await self._test_connection(import_data[CONF_SERIAL_PORT]):
            return self.async_abort(reason="cannot_connect")
        
        # Create entry from import data
        return self.async_create_entry(
            title=f"Axium Amplifier ({import_data[CONF_SERIAL_PORT]})",
            data=import_data,
        )

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        # Discover available serial ports
        self._discovered_ports = await self.hass.async_add_executor_job(
            self._get_serial_ports
        )
        
        if user_input is not None:
            self._serial_port = user_input[CONF_SERIAL_PORT]
            
            # Set a unique_id based on serial port
            await self.async_set_unique_id(f"axium_{self._serial_port}")
            self._abort_if_unique_id_configured()
            
            # Test the connection
            if not await self._test_connection(self._serial_port):
                errors["base"] = "cannot_connect"
            else:
                # Proceed to zone selection
                return await self.async_step_zones()

        # Build the schema with discovered ports
        schema = vol.Schema({
            vol.Required(CONF_SERIAL_PORT): vol.In(
                self._discovered_ports if self._discovered_ports else ["Enter Manually"]
            ),
        })

        # If no ports discovered or user selected "Enter Manually", allow manual entry
        if not self._discovered_ports or (
            user_input and user_input.get(CONF_SERIAL_PORT) == "Enter Manually"
        ):
            schema = vol.Schema({
                vol.Required(CONF_SERIAL_PORT): str,
            })

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_zones(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the zones selection step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Store selected zones
            self._selected_zones = user_input[CONF_ZONES]
            
            # Initialize zone names dictionary
            self._zone_names = {zone: zone.replace("_", " ").title() for zone in self._selected_zones}
            
            # Proceed to zone naming
            return await self.async_step_zone_names()

        # Build schema for zone selection
        schema = vol.Schema({
            vol.Required(CONF_ZONES, default=list(ZONES.keys())): cv.multi_select(list(ZONES.keys())),
        })

        return self.async_show_form(
            step_id="zones", data_schema=schema, errors=errors
        )

    async def async_step_zone_names(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the zone naming step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Store custom zone names
            self._zone_names = user_input
            
            # Create config entry
            data = {
                CONF_SERIAL_PORT: self._serial_port,
                CONF_ZONES: self._selected_zones,
                CONF_ZONE_NAMES: self._zone_names,
            }
            
            # Create entry
            return self.async_create_entry(
                title=f"Axium Amplifier ({self._serial_port})",
                data=data,
            )

        # Build schema for zone naming
        schema = {}
        for zone in self._selected_zones:
            schema[vol.Required(zone, default=zone.replace("_", " ").title())] = str
        
        return self.async_show_form(
            step_id="zone_names", data_schema=vol.Schema(schema), errors=errors
        )

    @staticmethod
    def _get_serial_ports() -> List[str]:
        """Get available serial ports."""
        ports = []
        try:
            for port in serial.tools.list_ports.comports():
                ports.append(port.device)
        except Exception as e:
            _LOGGER.error("Error listing serial ports: %s", e)
        
        # Add "Enter Manually" option if no ports found
        if not ports:
            ports.append("Enter Manually")
        
        return ports

    async def _test_connection(self, serial_port: str) -> bool:
        """Test if we can connect to the Axium amplifier."""
        try:
            controller = AxiumController(serial_port)
            connected = await controller.connect()
            
            # Ensure we disconnect properly after testing
            await controller.disconnect()
            
            return connected
        except Exception as e:
            _LOGGER.error("Error connecting to Axium amplifier: %s", e)
            return False

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return AxiumOptionsFlow(config_entry)


class AxiumOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Axium integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._selected_zones: List[str] = []
        self._zone_names: Dict[str, str] = {}

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage options."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Store selected zones
            self._selected_zones = user_input[CONF_ZONES]
            
            # Proceed to zone naming
            return await self.async_step_zone_names()

        # Get current selections
        current_zones = self.config_entry.data.get(CONF_ZONES, list(ZONES.keys()))
        
        # Build schema for zone selection
        schema = vol.Schema({
            vol.Required(CONF_ZONES, default=current_zones): cv.multi_select(list(ZONES.keys())),
        })

        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )

    async def async_step_zone_names(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle zone naming in options flow."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Store custom zone names
            self._zone_names = user_input
            
            # Update config data
            new_data = dict(self.config_entry.data)
            new_data[CONF_ZONES] = self._selected_zones
            new_data[CONF_ZONE_NAMES] = self._zone_names
            
            # Update entry
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            
            return self.async_create_entry(title="", data={})

        # Get current zone names
        current_zone_names = self.config_entry.data.get(CONF_ZONE_NAMES, {})
        
        # Build schema for zone naming
        schema = {}
        for zone in self._selected_zones:
            default_name = current_zone_names.get(zone, zone.replace("_", " ").title())
            schema[vol.Required(zone, default=default_name)] = str
        
        return self.async_show_form(
            step_id="zone_names", data_schema=vol.Schema(schema), errors=errors
        ) 