"""Support for Axium amplifier zones."""
from __future__ import annotations

import logging
_LOGGER = logging.getLogger("custom_components.axium")

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, ZONES, SOURCES
from .controller import AxiumController

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Axium media player platform."""
    _LOGGER.info("Setting up Axium media player platform.")

    if DOMAIN not in hass.data:
        _LOGGER.error("DOMAIN not in hass.data, exiting async_setup_platform")
        return

    controller = hass.data[DOMAIN]["controller"]
    zones = hass.data[DOMAIN]["config"]["zones"]

    entities = []
    for zone_name in zones:
        if zone_name in ZONES:
            
            zone_id = ZONES[zone_name]
            
            # Initialize the controller's cache for this zone
            controller._state_cache.setdefault(zone_id, {
                "power": False,      # Default: Zone is OFF
                "volume": 50,        # Default: 50% volume
                "mute": False,       # Default: Not muted
                "source": SOURCES["aux"]["id"],      # Default: Roon Source
            #    "bass": 0,           # Default: Bass level 0
            #    "treble": 0          # Default: Treble level 0
            })
                        
            entities.append(AxiumZone(controller, zone_name, zone_id))
        else:
            _LOGGER.warning(f"Zone {zone_name} not found in ZONES mapping.")

    if not entities:
        _LOGGER.error("No entities created for Axium media player platform.")
        return

    _LOGGER.info(f"Adding {len(entities)} Axium media player entities.")
    async_add_entities(entities)

class AxiumZone(MediaPlayerEntity, RestoreEntity):
    """Representation of an Axium amplifier zone."""

    _attr_has_entity_name = True

    def __init__(self, controller: AxiumController, name: str, zone_id: int) -> None:
        """Initialize the zone."""
        self._controller = controller
        self._attr_name = f"Axium {name.replace('_', ' ').title()}"
        self._attr_unique_id = f"axium_{name}"
        self._zone_id = zone_id
        self.entity_id = f"media_player.axium_{name}"  # Explicit entity ID
        
    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Flag media player features that are supported."""
        features = (
            MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
        )
        return features

    @property
    def source_list(self) -> list[str]:
        """List of available input sources."""
        return [source["name"] for source in SOURCES.values()]

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        last_state = await self.async_get_last_state()
        if last_state:
            self._attr_state = last_state.state
            self._attr_volume_level = last_state.attributes.get("volume_level", 0.5)
            self._attr_is_volume_muted = last_state.attributes.get("is_volume_muted", False)
            self._attr_source = last_state.attributes.get("source")
            
            # Update controller's state_cache with restored values
            power = self._attr_state == STATE_ON
            volume = int(self._attr_volume_level * 100)
            mute = self._attr_is_volume_muted
            source_id = None
            if self._attr_source:
                for src in SOURCES.values():
                    if src["name"] == self._attr_source:
                        source_id = src["id"]
                        break
            
            self._controller._state_cache[self._zone_id] = {
                "power": power,
                "volume": volume,
                "mute": mute,
                "source": source_id
            }
        
        await self.async_update()
    async def async_update(self) -> None:
        """Retrieve latest state."""
        state = await self._controller.get_zone_state(self._zone_id)
        if state:
            if self._attr_state != (STATE_ON if state.get("power") else STATE_OFF):
               self._attr_state = STATE_ON if state.get("power") else STATE_OFF
            if self._attr_volume_level != state.get("volume", 0) / 100.0:
               self._attr_volume_level = state.get("volume", 0) / 100.0
            if self._attr_is_volume_muted != state.get("mute", False):
               self._attr_is_volume_muted = state.get("mute", False)
            
            source_id = state.get("source")
            if source_id is not None:
                for source_info in SOURCES.values():
                    if source_info["id"] == source_id:
                        if self._attr_source != source_info["name"]:
                            self._attr_source = source_info["name"]
                        break
            self._attr_extra_state_attributes = {
                "bass": state.get("bass", 0),
                "treble": state.get("treble", 0) }

    async def async_turn_on(self) -> None:
        """Turn the zone on."""
        await self._controller.set_power(self._zone_id, True)
        self._attr_state = STATE_ON

    async def async_turn_off(self) -> None:
        """Turn the zone off."""
        await self._controller.set_power(self._zone_id, False)
        self._attr_state = STATE_OFF

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        await self._controller.set_mute(self._zone_id, mute)
        self._attr_is_volume_muted = mute

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        await self._controller.set_volume(self._zone_id, int(volume * 100))
        self._attr_volume_level = volume

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        for source_info in SOURCES.values():
            if source_info["name"] == source:
                await self._controller.set_source(self._zone_id, source_info["id"])
                self._attr_source = source
                break