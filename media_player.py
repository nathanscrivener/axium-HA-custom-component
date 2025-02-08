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
    STATE_UNAVAILABLE
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, ZONES, SOURCES
from .controller import AxiumController
from .volume_scaling import linear_to_perceptual_volume, perceptual_to_linear_volume # Import scaling functions

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

            # Initialize the controller's cache for this zone (this is still needed)
            controller._state_cache.setdefault(zone_id, {
                "power": False,
                "volume": 50,
                "mute": False,
                "source": SOURCES["aux"]["id"],
                "max_volume": 160 # Default max volume if not reported - changed to 160
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
        self.entity_id = f"media_player.axium_{name}"
        self._controller.register_entity(self._zone_id, self) # Register!
        self._max_volume = 160 #Initialize default max volume - changed to 160

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
        """Run when entity is about to be added to hass."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state:
            # Restore state, but ONLY if we're connected.
            if not self._controller.connected:
                # If not connected, set state to unavailable.
                self._attr_state = STATE_UNAVAILABLE
        # No restoring of ANY attributes.

        # Wait for the initial query to complete before updating.
        await self._controller.initial_query_complete.wait() #Crucial addition
        await self.async_update() # Get the latest state

    async def async_update(self) -> None:
        """Retrieve latest state."""
        if not self._controller.connected:
            self._attr_state = STATE_UNAVAILABLE  # Set to unavailable if not connected
            return

        state = await self._controller.get_zone_state(self._zone_id)

        # Check if this is a pre-out zone.  If so, get source from main zone.
        if self._zone_id in self._controller._zone_mapping.values():
            main_zone_id = self._controller._zone_mapping.get(self._zone_id)
            if main_zone_id:
                main_zone_state = await self._controller.get_zone_state(main_zone_id)
                if main_zone_state:
                    state["source"] = main_zone_state.get("source")

        if state:
            # ALWAYS update ALL attributes from the cached state.
            self._attr_state = STATE_ON if state.get("power") else STATE_OFF
            current_volume = state.get("volume", 0) #Get raw axium volume
            max_volume = state.get("max_volume", 160) # Get max volume from state, default to 160

            # Re-scale volume from 0-160 (of max_volume) to 0-1.0 for HA
            if max_volume > 0:
                linear_volume = current_volume / max_volume # Linear scaling from 0-160 to 0-1
                self._attr_volume_level = perceptual_to_linear_volume(linear_volume) # Apply inverse perceptual scaling for display
            else:
                self._attr_volume_level = 0 # Fallback if max_volume is invalid

            self._attr_is_volume_muted = state.get("mute", False)
            source_id = state.get("source")
            if source_id is not None:
                for source_info in SOURCES.values():
                    if source_info["id"] == source_id:
                        self._attr_source = source_info["name"]
                        break
            self._attr_extra_state_attributes = { #Ensure bass/treble initialised
                "bass": state.get("bass", 0),
                "treble": state.get("treble", 0),
                "max_volume": max_volume, #Include max_volume in attributes
                "axium_volume": current_volume # OPTIONAL: For debugging
            }
            self._max_volume = max_volume # Update internal max_volume

    async def async_turn_on(self) -> None:
        """Turn the zone on."""
        if await self._controller.set_power(self._zone_id, True):
            self._attr_state = STATE_ON

    async def async_turn_off(self) -> None:
        """Turn the zone off."""
        if await self._controller.set_power(self._zone_id, False):
            self._attr_state = STATE_OFF

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        if await self._controller.set_mute(self._zone_id, mute):
            self._attr_is_volume_muted = mute

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        max_volume = self._max_volume
        perceptual_volume = linear_to_perceptual_volume(volume) # Apply perceptual scaling
        scaled_volume = int(perceptual_volume * max_volume)  # Scale to max volume
        if await self._controller.set_volume(self._zone_id, scaled_volume):
            self._attr_volume_level = volume  # Keep HA's 0.0-1.0 representation

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        for source_info in SOURCES.values():
            if source_info["name"] == source:
                if await self._controller.set_source(self._zone_id, source_info["id"]):
                    self._attr_source = source
                break

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        self._controller.unregister_entity(self._zone_id) #Unregister