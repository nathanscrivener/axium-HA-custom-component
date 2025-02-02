"""Axium amplifier controller."""
import asyncio
import logging
from typing import Optional

import serial_asyncio

_LOGGER = logging.getLogger("custom_components.axium")

class AxiumController:
    """Interface to communicate with the Axium amplifier."""

    def __init__(self, port: str, baudrate: int = 9600):
        """Initialize the controller."""
        self._port = port
        self._baudrate = baudrate
        self._serial_reader = None
        self._serial_writer = None
        self._lock = asyncio.Lock()
        self._state_cache = {}
        self._connected = False
        self._reconnect_task = None

    async def connect(self) -> None:
        """Connect to the amplifier with retries."""
        try:
            self._serial_reader, self._serial_writer = await serial_asyncio.open_serial_connection(
                url=self._port,
                baudrate=self._baudrate,
                xonxoff=True
            )
            self._connected = True
            _LOGGER.info("Successfully connected to Axium amplifier")
            if self._reconnect_task:
                self._reconnect_task.cancel()
                self._reconnect_task = None
        except Exception as err:
            self._connected = False
            _LOGGER.warning("Failed to connect to Axium amplifier: %s. Retrying...", err)
            if not self._reconnect_task:
                self._reconnect_task = asyncio.create_task(self._reconnect())

    async def _reconnect(self) -> None:
        """Periodically attempt to reconnect."""
        while True:
            await asyncio.sleep(10)  # Wait 10 seconds between retries
            try:
                await self.connect()
                if self._connected:
                    return
            except Exception as err:
                _LOGGER.warning("Reconnect attempt failed: %s", err)

    async def _send_command(self, command_bytes: bytes) -> bool:
        """Send a command with detailed error logging."""
        try:
            if not self._connected:
                await self.connect()

            async with self._lock:
                encoded = ''.join(f"{b:02X}" for b in command_bytes) + '\n'
                self._serial_writer.write(encoded.encode('ascii'))
                return True
        except Exception as err:
            _LOGGER.error(
                "Failed to send command %s: %s",
                command_bytes, str(err), exc_info=True
            )
            self._connected = False
            return False

    # Rest of the methods remain unchanged below this line
    async def set_power(self, zone: int, state: bool) -> bool:
        """Set power state for a zone."""
        command = bytes([0x01, zone, 0x01 if state else 0x00])
        if await self._send_command(command):
            self._state_cache.setdefault(zone, {})["power"] = state
            return True
        return False

    async def set_mute(self, zone: int, state: bool) -> bool:
        """Set mute state for a zone."""
        command = bytes([0x02, zone, 0x00 if state else 0x01])
        if await self._send_command(command):
            self._state_cache.setdefault(zone, {})["mute"] = state
            return True
        return False

    async def set_volume(self, zone: int, volume: int) -> bool:
        """Set volume level for a zone."""
        axium_volume = min(max(int((volume / 100) * 160), 0), 160)
        command = bytes([0x04, zone, axium_volume])
        if await self._send_command(command):
            self._state_cache.setdefault(zone, {})["volume"] = volume
            return True
        return False

    async def set_source(self, zone: int, source: int) -> bool:
        """Set input source for a zone."""
        command = bytes([0x03, zone, source])
        if await self._send_command(command):
            self._state_cache.setdefault(zone, {})["source"] = source
            return True
        return False

    async def get_zone_state(self, zone: int) -> dict:
        """Get the cached state for a zone."""
        return self._state_cache.get(zone, {})

    async def set_bass(self, zone: int, level: int) -> bool:
        """Set bass level for a zone (-12 to +12)."""
        bass_level = min(max(level, -12), 12)
        bass_byte = bass_level & 0xFF  # Convert to unsigned byte (e.g., -5 → 0xFB)
        command = bytes([0x05, zone, bass_byte])
        success = await self._send_command(command)
        if success:
            self._state_cache.setdefault(zone, {})["bass"] = bass_level
        return success

    async def set_treble(self, zone: int, level: int) -> bool:
        """Set treble level for a zone (-12 to +12)."""
        treble_level = min(max(level, -12), 12)
        treble_byte = treble_level & 0xFF  # Convert to unsigned byte
        command = bytes([0x06, zone, treble_byte])
        success = await self._send_command(command)
        if success:
            self._state_cache.setdefault(zone, {})["treble"] = treble_level
        return success