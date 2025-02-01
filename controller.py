"""Axium amplifier controller."""
import asyncio
import logging
import json
import os
from typing import Optional

import serial_asyncio

_LOGGER = logging.getLogger("custom_components.axium")

STATE_FILE = "axium_state.json"

class AxiumController:
    """Interface to communicate with the Axium amplifier."""

    def __init__(self, port: str, baudrate: int = 9600, config_dir: str = None):
        """Initialize the controller."""
        self._port = port
        self._baudrate = baudrate
        self._serial_reader = None
        self._serial_writer = None
        self._lock = asyncio.Lock()
        self._state_cache = {}
        self._connected = False
        self._config_dir = config_dir
        self._state_file_path = os.path.join(self._config_dir, STATE_FILE) if self._config_dir else None
        self._load_state()


    def _load_state(self):
        """Load the state from the json file."""
        if self._state_file_path and os.path.exists(self._state_file_path):
            try:
                with open(self._state_file_path, "r") as f:
                    self._state_cache = json.load(f)
                _LOGGER.debug("Loaded state from file: %s", self._state_cache)
            except (FileNotFoundError, json.JSONDecodeError):
                _LOGGER.warning("State file not found or invalid, starting with empty state.")
                self._state_cache = {}
        else:
             _LOGGER.debug("No state file found, starting with empty state.")
             self._state_cache = {}


    def _save_state(self):
        """Save the state to the json file."""
        if self._state_file_path:
            try:
                with open(self._state_file_path, "w") as f:
                    json.dump(self._state_cache, f, indent=2)
                _LOGGER.debug("Saved state to file: %s", self._state_cache)
            except Exception as e:
                _LOGGER.error("Error saving state: %s", e)
        else:
             _LOGGER.debug("No config directory, so not saving state.")


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
            self._save_state()
            return True
        return False

    async def set_mute(self, zone: int, state: bool) -> bool:
        """Set mute state for a zone."""
        command = bytes([0x02, zone, 0x00 if state else 0x01])
        if await self._send_command(command):
            self._state_cache.setdefault(zone, {})["mute"] = state
            self._save_state()
            return True
        return False

    async def set_volume(self, zone: int, volume: int) -> bool:
        """Set volume level for a zone."""
        axium_volume = min(max(int((volume / 100) * 160), 0), 160)
        command = bytes([0x04, zone, axium_volume])
        if await self._send_command(command):
            self._state_cache.setdefault(zone, {})["volume"] = volume
            self._save_state()
            return True
        return False

    async def set_source(self, zone: int, source: int) -> bool:
        """Set input source for a zone."""
        command = bytes([0x03, zone, source])
        if await self._send_command(command):
            self._state_cache.setdefault(zone, {})["source"] = source
            self._save_state()
            return True
        return False

    async def get_zone_state(self, zone: int) -> dict:
        """Get the cached state for a zone."""
        _LOGGER.debug("Getting state for zone: %s. State: %s", zone, self._state_cache.get(zone, {}))
        return self._state_cache.get(zone, {})
