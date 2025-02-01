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

    async def connect(self) -> None:
        """Connect to the amplifier."""
        _LOGGER.debug("Attempting to connect to Axium amplifier on port: %s", self._port)
        try:
            self._serial_reader, self._serial_writer = await serial_asyncio.open_serial_connection(
                url=self._port,
                baudrate=self._baudrate,
                xonxoff=True
            )
            self._connected = True
            _LOGGER.info("Successfully connected to Axium amplifier")
        except Exception as err:
            self._connected = False
            _LOGGER.error("Failed to connect to Axium amplifier: %s", err)
            raise

    async def _send_command(self, command_bytes: bytes) -> bool:
        """Send a command."""
        if not self._connected:
            try:
                await self.connect()
            except Exception as err:
                _LOGGER.error("Cannot send command - connection failed: %s", err)
                return False

        async with self._lock:
            try:
                encoded = ''.join('{:02X}'.format(b) for b in command_bytes) + '\n'
                _LOGGER.debug("Sending command: %s. Command Bytes: %s", encoded.strip(), command_bytes)
                self._serial_writer.write(encoded.encode('ascii'))
                return True

            except Exception as err:
                _LOGGER.error("Error sending command: %s", err)
                self._connected = False
                return False

    async def set_power(self, zone: int, state: bool) -> bool:
        """Set power state for a zone."""
        command = bytes([0x01, zone, 0x01 if state else 0x00])
        _LOGGER.debug("Setting power for zone %s to %s. Command bytes: %s", zone, state, command)
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
        _LOGGER.debug("Getting state for zone: %s. State: %s", zone, self._state_cache.get(zone, {}))
        return self._state_cache.get(zone, {})
