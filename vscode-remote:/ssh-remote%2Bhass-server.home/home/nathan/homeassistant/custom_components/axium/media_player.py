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
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.components.media_player.const import (
    ATTR_MEDIA_VOLUME_MUTED,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_SOURCE,
)

from . import DOMAIN
from .const import SOURCES

import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
) -> None:
    """Set up the Axium media player platform."""
    if discovery_info is None:
        return

    controller = hass.data[DOMAIN]["controller"]
    entities = []
    
    for zone_id in range(1, 13):  # Zones 1-12
        entity = AxiumMediaPlayer(
            controller=controller,
            zone_id=zone_id,
            name=f"Zone {zone_id}",
        )
        entities.append(entity)

    async_add_entities(entities)

class AxiumMediaPlayer(MediaPlayerEntity, RestoreEntity):
    """Representation of an Axium media player."""

    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, controller, zone_id: int, name: str) -> None:
        """Initialize the media player."""
        self._controller = controller
        self._zone_id = zone_id
        self._attr_name = name
        self._attr_source_list = [source["name"] for source in SOURCES.values()]
        self._attr_state = STATE_OFF
        self._attr_volume_level = 0
        self._attr_is_volume_muted = False
        self._attr_source = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_state = last_state.state
            if last_state.attributes.get(ATTR_MEDIA_VOLUME_LEVEL):
                self._attr_volume_level = last_state.attributes[ATTR_MEDIA_VOLUME_LEVEL]
            if last_state.attributes.get(ATTR_MEDIA_VOLUME_MUTED):
                self._attr_is_volume_muted = last_state.attributes[ATTR_MEDIA_VOLUME_MUTED]
            if last_state.attributes.get(ATTR_SOURCE):
                self._attr_source = last_state.attributes[ATTR_SOURCE]

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        await self._controller.set_power(self._zone_id, True)
        self._attr_state = STATE_ON

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        await self._controller.set_power(self._zone_id, False)
        self._attr_state = STATE_OFF

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        await self._controller.set_mute(self._zone_id, mute)
        self._attr_is_volume_muted = mute

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        volume_pct = int(volume * 100)
        await self._controller.set_volume(self._zone_id, volume_pct)
        self._attr_volume_level = volume

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        for source_info in SOURCES.values():
            if source_info["name"] == source:
                await self._controller.set_source(self._zone_id, source_info["id"])
                self._attr_source = source
                break

    async def async_update(self) -> None:
        """Retrieve latest state."""
        _LOGGER.debug("Updating state for zone: %s", self._attr_name)
        state = await self._controller.get_zone_state(self._zone_id)
        _LOGGER.debug("State received for zone %s: %s", self._attr_name, state)
        if state:
            self._attr_state = STATE_ON if state.get("power") else STATE_OFF
            self._attr_volume_level = state.get("volume", 0) / 100.0
            self._attr_is_volume_muted = state.get("mute", False)
            
            source_id = state.get("source")
            if source_id is not None:
                for source_info in SOURCES.values():
                    if source_info["id"] == source_id:
                        self._attr_source = source_info["name"]
        