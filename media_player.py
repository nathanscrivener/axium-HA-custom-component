"""Support for Axium amplifier zones."""
from __future__ import annotations

import logging
_LOGGER = logging.getLogger("custom_components.axium")
_LOGGER.debug("media_player.py file loaded")

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

from .const import DOMAIN, ZONES, SOURCES
from .controller import AxiumController

_LOGGER = logging.getLogger("custom_components.axium")

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Axium media player platform."""
    _LOGGER.debug("async_setup_platform function called")
    if DOMAIN not in hass.data:
        _LOGGER.debug("DOMAIN not in hass.data, exiting async_setup_platform")
        return

    controller = hass.data[DOMAIN]["controller"]
    zones = hass.data[DOMAIN]["config"]["zones"]

    entities = []
    for zone_name in zones:
        if zone_name in ZONES:
            zone_id = ZONES[zone_name]
            _LOGGER.debug("Creating AxiumZone entity for zone: %s, id: %s", zone_name, zone_id)
            entities.append(AxiumZone(controller, zone_name, zone_id))
    async_add_entities(entities)
    _LOGGER.debug("async_add_entities called with %s entities", len(entities))

class AxiumZone(MediaPlayerEntity):
    """Representation of an Axium amplifier zone."""

    _attr_has_entity_name = True

    def __init__(self, controller: AxiumController, name: str, zone_id: int) -> None:
        """Initialize the zone."""
        self._controller = controller
        self._attr_name = f"Axium {name.replace('_', ' ').title()}"
        self._attr_unique_id = f"axium_{name}"
        self._zone_id = zone_id
        
        # Attempt to get last known state, default to STATE_OFF
        last_state = self._controller._state_cache.get(zone_id, {})
        self._attr_state = STATE_ON if last_state.get("power") else STATE_OFF
        self._attr_volume_level = last_state.get("volume", 0) / 100.0 if last_state.get("volume") else 0.5
        self._attr_source = None
        self._attr_is_volume_muted = last_state.get("mute", False) if last_state.get("mute") is not None else False

        self._initial_state_retrieved = False

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
        _LOGGER.debug("supported_features called for %s. Features: %s", self._attr_name, features)
        return features

    @property
    def source_list(self) -> list[str]:
        """List of available input sources."""
        return [source["name"] for source in SOURCES.values()]

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass called for %s", self._attr_name)
        await super().async_added_to_hass()
        await self.async_update()

    async def async_update(self) -> None:
        """Retrieve latest state."""
        _LOGGER.debug("Updating state for zone: %s", self._attr_name)
        state = await self._controller.get_zone_state(self._zone_id)
        _LOGGER.debug("State received for zone %s: %s", self._attr_name, state)
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

    async def async_turn_on(self) -> None:
        """Turn the zone on."""
        _LOGGER.debug("async_turn_on called for: %s", self._attr_name)
        await self._controller.set_power(self._zone_id, True)
        self._attr_state = STATE_ON

    async def async_turn_off(self) -> None:
        """Turn the zone off."""
        _LOGGER.debug("async_turn_off called for: %s", self._attr_name)
        await self._controller.set_power(self._zone_id, False)
        self._attr_state = STATE_OFF

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        _LOGGER.debug("async_mute_volume called for: %s. Mute: %s", self._attr_name, mute)
        await self._controller.set_mute(self._zone_id, mute)
        self._attr_is_volume_muted = mute

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        _LOGGER.debug("async_set_volume_level called for: %s. Volume: %s", self._attr_name, volume)
        await self._controller.set_volume(self._zone_id, int(volume * 100))
        self._attr_volume_level = volume

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        _LOGGER.debug("async_select_source called for: %s. Source: %s", self._attr_name, source)
        for source_info in SOURCES.values():
            if source_info["name"] == source:
                await self._controller.set_source(self._zone_id, source_info["id"])
                self._attr_source = source
                break
