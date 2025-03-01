"""Support for Axium amplifier bass and treble controls."""
import logging
from typing import Any, Callable, Dict, Optional
import asyncio

from homeassistant.components.number import (
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import DOMAIN, CONF_ZONES, CONF_ZONE_NAMES, ZONES
from .controller import AxiumController

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Axium number entities from a config entry."""
    _LOGGER.info("Setting up Axium number entities")
    
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        _LOGGER.error("Axium integration data not found")
        return
    
    data = hass.data[DOMAIN][entry.entry_id]
    controller: AxiumController = data["controller"]
    zones = data["config"]["zones"]
    zone_names = data["config"]["zone_names"]
    
    entities = []
    
    # Create bass and treble number entities for each zone
    for zone_id in zones:
        zone_name = zone_names.get(zone_id, zone_id.replace("_", " ").title())
        
        # Add bass number entity
        bass_entity = AxiumBassNumber(controller, zone_id, zone_name)
        entities.append(bass_entity)
        
        # Add treble number entity
        treble_entity = AxiumTrebleNumber(controller, zone_id, zone_name)
        entities.append(treble_entity)
    
    async_add_entities(entities)
    _LOGGER.info(f"Added {len(entities)} Axium number entities")


class AxiumBaseNumber(NumberEntity):
    """Base class for Axium bass and treble number entities."""
    
    _attr_has_entity_name = False
    _attr_native_min_value = -12
    _attr_native_max_value = 12
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    
    def __init__(
        self,
        controller: AxiumController,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the number entity."""
        self._controller = controller
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{zone_id}")},
            name=f"Axium {zone_name}",
            manufacturer="Axium",
            model="Amplifier Zone",
            via_device=(DOMAIN, "controller"),
        )
        
        # Register for callbacks
        controller.register_callback(self.async_update_callback, zone_id)
    
    async def async_added_to_hass(self) -> None:
        """Run when entity is added to Home Assistant."""
        await super().async_added_to_hass()
        
        # Wait for the controller's initial query to complete before updating
        await self._controller.initial_query_complete.wait()
        
        # Update initial state
        await self.async_update_native_value()
        
        # Force a state update to Home Assistant
        self.async_write_ha_state()
        
    async def async_update_callback(self) -> None:
        """Update the entity state when the controller reports a change."""
        # Wait a small delay to allow the state cache to be updated
        await asyncio.sleep(0.1)
        
        # Force a direct state update
        await self.async_update_native_value()
        self.async_write_ha_state()
        _LOGGER.info(f"Callback update completed for {self._attr_name} - zone {self._zone_id}, value: {self._attr_native_value}")
    
    async def async_update_native_value(self) -> None:
        """Update the native value from the controller state."""
        # This must be implemented by subclasses
        raise NotImplementedError
    
    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal from Home Assistant."""
        # Unregister callback
        self._controller.unregister_callback(self.async_update_callback, self._zone_id)


class AxiumBassNumber(AxiumBaseNumber):
    """Represents the bass level for an Axium zone."""
    
    _attr_translation_key = "bass"
    _attr_icon = "mdi:music-note"
    
    def __init__(
        self,
        controller: AxiumController,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the bass number entity."""
        super().__init__(controller, zone_id, zone_name)
        self._attr_unique_id = f"{zone_id}_bass"
        self._attr_name = f"{zone_name} Bass"
    
    async def async_update_native_value(self) -> None:
        """Update the native value from the controller state."""
        zone_state = self._controller.get_zone_state(self._zone_id)
        _LOGGER.info(f"Bass update - Zone {self._zone_id} state retrieved: {zone_state}")
        if zone_state and "bass" in zone_state:
            self._attr_native_value = zone_state["bass"]
            _LOGGER.info(f"Setting bass native value to {self._attr_native_value} for zone {self._zone_id}")
        else:
            self._attr_native_value = 0
            _LOGGER.warning(f"No bass value found in zone state for {self._zone_id}, defaulting to 0")
    
    async def async_set_native_value(self, value: float) -> None:
        """Set the bass level."""
        _LOGGER.debug(f"Setting bass to {value} for zone {self._zone_id}")
        # Convert zone_id from string to integer if needed
        try:
            if self._zone_id in ZONES:
                zone_int = ZONES[self._zone_id]
            else:
                zone_int = int(self._zone_id)
            await self._controller.set_bass(zone_int, int(value))
        except (ValueError, TypeError) as e:
            _LOGGER.error(f"Error setting bass: {e}. Zone ID: {self._zone_id}, Value: {value}")


class AxiumTrebleNumber(AxiumBaseNumber):
    """Represents the treble level for an Axium zone."""
    
    _attr_translation_key = "treble"
    _attr_icon = "mdi:music-note"
    
    def __init__(
        self,
        controller: AxiumController,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize the treble number entity."""
        super().__init__(controller, zone_id, zone_name)
        self._attr_unique_id = f"{zone_id}_treble"
        self._attr_name = f"{zone_name} Treble"
    
    async def async_update_native_value(self) -> None:
        """Update the native value from the controller state."""
        zone_state = self._controller.get_zone_state(self._zone_id)
        _LOGGER.info(f"Treble update - Zone {self._zone_id} state retrieved: {zone_state}")
        if zone_state and "treble" in zone_state:
            self._attr_native_value = zone_state["treble"]
            _LOGGER.info(f"Setting treble native value to {self._attr_native_value} for zone {self._zone_id}")
        else:
            self._attr_native_value = 0
            _LOGGER.warning(f"No treble value found in zone state for {self._zone_id}, defaulting to 0")
    
    async def async_set_native_value(self, value: float) -> None:
        """Set the treble level."""
        _LOGGER.debug(f"Setting treble to {value} for zone {self._zone_id}")
        # Convert zone_id from string to integer if needed
        try:
            if self._zone_id in ZONES:
                zone_int = ZONES[self._zone_id]
            else:
                zone_int = int(self._zone_id)
            await self._controller.set_treble(zone_int, int(value))
        except (ValueError, TypeError) as e:
            _LOGGER.error(f"Error setting treble: {e}. Zone ID: {self._zone_id}, Value: {value}") 