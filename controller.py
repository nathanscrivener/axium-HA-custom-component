"""Axium amplifier controller."""
import asyncio
import logging
from typing import Optional

import serial_asyncio
from .const import REQUIRED_BAUDRATE, ZONES

_LOGGER = logging.getLogger("custom_components.axium")

class AxiumController:
    """Interface to communicate with the Axium amplifier."""

    def __init__(self, port: str, baudrate: int = REQUIRED_BAUDRATE):
        """Initialize the controller."""
        self._port = port
        self._baudrate = baudrate
        self._serial_reader = None
        self._serial_writer = None
        self._lock = asyncio.Lock()  # Protects against concurrent serial access
        self._state_cache = {}  # Cache of zone states
        self._connected = False
        self._reconnect_task = None
        self._last_attempt = 0  # Time of the last connection attempt

        # Mapping of main zones to pre-out zones (and vice-versa)
        self._zone_mapping = {}
        for zone_name, zone_id in ZONES.items():
            if zone_id <= 0x0F: #Main zones
                self._zone_mapping[zone_id] = zone_id + 0x40
                self._zone_mapping[zone_id + 0x40] = zone_id

    async def connect(self) -> bool:
        """Connect to the amplifier with retries and rate limiting."""
        now = asyncio.get_event_loop().time()
        if now - self._last_attempt < 5:  # Prevent immediate retries
            _LOGGER.debug("Connection attempt too soon, skipping.")
            return False
        self._last_attempt = now

        # Explicitly close the connection if it exists
        await self.disconnect()

        try:
            self._serial_reader, self._serial_writer = await serial_asyncio.open_serial_connection(
                url=self._port,
                baudrate=self._baudrate,
                xonxoff=True  # Enable XON/XOFF flow control
            )
            self._connected = True
            _LOGGER.info("Successfully connected to Axium amplifier")
            if self._reconnect_task:
                self._reconnect_task.cancel()  # Cancel any existing reconnect task
                self._reconnect_task = None
            return True  # Indicate successful connection
        except Exception as err:
            self._connected = False
            _LOGGER.warning("Failed to connect to Axium amplifier: %s.", err)
            if not self._reconnect_task:
                self._reconnect_task = asyncio.create_task(self._reconnect())
            return False  # Indicate connection failure

    async def disconnect(self) -> None:
        """Explicitly disconnect from the amplifier."""
        if self._serial_writer:
            try:
                self._serial_writer.close()
                await self._serial_writer.wait_closed()
            except Exception as e:
                _LOGGER.error(f"Error closing serial writer: {e}")
            self._serial_writer = None
        if self._serial_reader:
            try:
                self._serial_reader.close()
            except Exception as e:
                _LOGGER.error(f"Error closing serial reader: {e}")

            self._serial_reader = None
        self._connected = False

    async def _reconnect(self) -> None:
        """Periodically attempt to reconnect."""
        while True:
            await asyncio.sleep(10)  # Wait 10 seconds between retries
            _LOGGER.debug("Attempting to reconnect to Axium amplifier...")
            await self.connect()  # No try-except here; let connect() handle it

    async def _send_command(self, command_bytes: bytes) -> bool:
        """Send a command to the amplifier, handling connection and errors."""
        if not self._connected:
            if not await self.connect():  # Try to reconnect, but check the result
                _LOGGER.error("Not connected and failed to reconnect.")
                return False  # Return False if not connected and reconnection fails

        try:
            async with self._lock:  # Acquire lock for thread safety
                encoded = ''.join(f"{b:02X}" for b in command_bytes) + '\n'
                self._serial_writer.write(encoded.encode('ascii'))
                await self._serial_writer.drain()  # Ensure data is sent
                return True  # Indicate success
        except Exception as err:
            _LOGGER.error(
                "Failed to send command %s: %s",
                command_bytes, str(err), exc_info=True
            )
            await self.disconnect() #Disconnect on failure.
            #self._connected = False  # Mark as disconnected on any send error #Redundant
            if not self._reconnect_task: #Initiate reconnection attempts
                self._reconnect_task = asyncio.create_task(self._reconnect())
            return False  # Indicate failure

    @property
    def connected(self) -> bool:
        """Return the connection status."""
        return self._connected

    async def set_power(self, zone: int, state: bool) -> bool:
        """Set power state for a zone."""
        command = bytes([0x01, zone, 0x01 if state else 0x00])
        if await self._send_command(command):  # Only update cache if command sent
            self._state_cache.setdefault(zone, {})["power"] = state
            return True
        return False

    async def set_mute(self, zone: int, state: bool) -> bool:
        """Set mute state for a zone."""
        command = bytes([0x02, zone, 0x00 if state else 0x01])
        if await self._send_command(command):  # Only update cache if command sent
            self._state_cache.setdefault(zone, {})["mute"] = state
            return True
        return False

    async def set_volume(self, zone: int, volume: int) -> bool:
        """Set volume level for a zone."""
        axium_volume = min(max(int((volume / 100) * 160), 0), 160)
        command = bytes([0x04, zone, axium_volume])
        if await self._send_command(command):  # Only update cache if command sent
            self._state_cache.setdefault(zone, {})["volume"] = volume
            return True
        return False

    async def set_source(self, zone: int, source: int) -> bool:
        """Set input source for a zone, and update cache for paired zone."""
        command = bytes([0x03, zone, source])
        if await self._send_command(command):
            self._state_cache.setdefault(zone, {})["source"] = source

            # Update the paired zone's cache *without* sending a command
            paired_zone = self._zone_mapping.get(zone)
            if paired_zone:
                self._state_cache.setdefault(paired_zone, {})["source"] = source
            return True
        return False

    async def get_zone_state(self, zone: int) -> dict:
        """Get the cached state for a zone."""
        return self._state_cache.get(zone, {})

    async def set_bass(self, zone: int, level: int) -> bool:
        """Set bass level for a zone (-12 to +12)."""
        bass_level = min(max(level, -12), 12)
        bass_byte = bass_level & 0xFF  # Convert to unsigned byte
        command = bytes([0x05, zone, bass_byte])
        if await self._send_command(command):  # Only update cache if command sent
            self._state_cache.setdefault(zone, {})["bass"] = bass_level
            return True
        return False

    async def set_treble(self, zone: int, level: int) -> bool:
        """Set treble level for a zone (-12 to +12)."""
        treble_level = min(max(level, -12), 12)
        treble_byte = treble_level & 0xFF  # Convert to unsigned byte
        command = bytes([0x06, zone, treble_byte])
        if await self._send_command(command):  # Only update cache if command sent
            self._state_cache.setdefault(zone, {})["treble"] = treble_level
            return True
        return False