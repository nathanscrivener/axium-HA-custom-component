"""Axium amplifier controller."""
import asyncio
import logging
from typing import Optional, TYPE_CHECKING  # Import TYPE_CHECKING

import serial_asyncio
from .const import REQUIRED_BAUDRATE, ZONES, SOURCES

if TYPE_CHECKING:
    from .media_player import AxiumZone  # Import only during type checking

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
        self._response_timeout = 2 # seconds for response timeout
        self.initial_query_complete = asyncio.Event()  # Event to signal completion
        self._entity_map = {}  # {zone_id: entity_instance}

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

            # Initialize zone states after successful connection
            self.initial_query_complete.clear()  # Reset the event
            for zone_id in ZONES.values(): #Iterate through all defined zone IDs
                if zone_id <= 0x0F: #Query only main zones, pre-outs are included in response
                    await self.async_query_zone_state(zone_id)
            self.initial_query_complete.set()  # Signal completion

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
                _LOGGER.debug(f"Sent command: {encoded.strip()}") #Debug log sent command
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
        axium_volume = min(max(int(volume), 0), 160)  # Ensure 0 <= volume <= 160
        command = bytes([0x04, zone, axium_volume])
        if await self._send_command(command):
            self._state_cache.setdefault(zone, {})["volume"] = volume  # Store raw value
            return True
        return False

    async def set_source(self, zone: int, source: int) -> bool:
        """Set input source, update cache, and trigger immediate entity updates."""
        command = bytes([0x03, zone, source])
        if await self._send_command(command):
            self._state_cache.setdefault(zone, {})["source"] = source

            # Update the paired zone's cache *without* sending a command
            paired_zone = self._zone_mapping.get(zone)
            if paired_zone:
                self._state_cache.setdefault(paired_zone, {})["source"] = source

                # --- IMMEDIATE UPDATE SECTION ---
                if zone in self._entity_map:
                    await self._entity_map[zone].async_update_ha_state(True)
                if paired_zone in self._entity_map:
                    await self._entity_map[paired_zone].async_update_ha_state(True)
                # --- END IMMEDIATE UPDATE SECTION ---

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

    async def set_max_volume(self, zone: int, max_volume: int) -> bool:
        """Set maximum volume level for a zone (0-160)."""
        axium_max_volume = min(max(int(max_volume), 0), 160)  # Ensure 0 <= max_volume <= 160
        command = bytes([0x0D, zone, axium_max_volume]) #Command 0D for Max Volume
        if await self._send_command(command):
            self._state_cache.setdefault(zone, {})["max_volume"] = axium_max_volume # Update cache
            # --- IMMEDIATE UPDATE SECTION ---
            if zone in self._entity_map:
                await self._entity_map[zone].async_update_ha_state(True) # Force entity update
            # --- END IMMEDIATE UPDATE SECTION ---
            return True
        return False


    async def async_query_zone_state(self, zone_id: int) -> None:
        """Query all parameters for a zone and update state cache."""
        command = bytes([0x09, zone_id]) # Send All Parameters command
        _LOGGER.debug(f"Querying state for zone {zone_id}...")
        if not await self._send_command(command): #Send command and check success
            _LOGGER.warning(f"Failed to send state query command for zone {zone_id}.")
            return

        expected_responses = [ #List of expected command codes in response
            '01', '02', '03', '04', '05', '06', '07', '0C', '0D', '1C', '1D', '26', '29',
            '09', '1E', '0F', '0D' # Add expected but currently unused responses, and '0D' for max volume
        ]
        responses_received = {} # Changed to just responses_received, will be nested dict
        timeout_start = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - timeout_start) < self._response_timeout:
            try:
                response_bytes = await asyncio.wait_for(self._serial_reader.readline(), timeout=self._response_timeout) #Read line with timeout
                if not response_bytes: #Empty response (timeout or connection issue)
                    _LOGGER.debug(f"Empty response received for zone {zone_id} state query.")
                    break

                decoded_response = self._decode_response(response_bytes) # Decode response
                if not decoded_response:
                    _LOGGER.warning(f"Failed to decode response: {response_bytes.hex()}")
                    continue #Skip to next response

                if len(decoded_response) < 2: #Need at least command code and zone
                    _LOGGER.warning(f"Incomplete response received: {decoded_response}")
                    continue

                command_code = decoded_response[0]
                response_zone_hex = decoded_response[1]
                response_zone_id = int(response_zone_hex, 16) #Parse zone ID here

                if command_code in expected_responses: #Check if it's an expected response
                    if response_zone_id not in responses_received: #Create zone entry if not exists
                        responses_received[response_zone_id] = {}
                    responses_received[response_zone_id][command_code] = decoded_response #Store response by zone and command

                else:
                    _LOGGER.debug(f"Unexpected command code in response: {command_code}, full response: {decoded_response}")


            except asyncio.TimeoutError: #Catch timeout
                _LOGGER.debug(f"Timeout waiting for zone {zone_id} state response.")
                break
            except Exception as e: #Catch other errors during read
                _LOGGER.error(f"Error reading response during zone {zone_id} state query: {e}", exc_info=True)
                break #Exit loop on error

        if not responses_received:
            _LOGGER.warning(f"No valid state responses received for zone {zone_id}.")
            return

        _LOGGER.debug(f"Received responses for zone {zone_id}: {responses_received.keys()}")
        self._update_state_from_responses(zone_id, responses_received) # Process and update state from collected responses
        _LOGGER.info(f"Initial state query completed for zone {zone_id}.")


    def _decode_response(self, response_bytes):
        """Decodes a byte response to a readable string, showing the hex bytes."""
        if not response_bytes:
            return None
        try:
            # Decode the ASCII hex encoded values
            response_str = response_bytes.strip().decode('ascii', errors='ignore')
            decoded_bytes = [response_str[i:i+2] for i in range(0, len(response_str), 2)] #Keep as hex strings for parsing
            return decoded_bytes
        except ValueError:
            _LOGGER.warning(f"Invalid response encoding: {response_bytes}")
            return None # Indicate decoding failure

    def _update_state_from_responses(self, main_zone_id, responses): #responses is now nested dict
        """Update the zone state cache based on parsed responses."""
        # Now iterates through zones in responses, not just assuming main zone
        for response_zone_id, zone_responses in responses.items():
            zone_state = self._state_cache.setdefault(response_zone_id, {}) #Get or create zone state

            for command_code, response_hex_list in zone_responses.items():
                try:
                    if command_code == '01': #Power state
                        power_state_hex = response_hex_list[2]
                        power_state = power_state_hex == '01' # '01' is power on, '00' is standby
                        zone_state['power'] = power_state
                        _LOGGER.debug(f"Parsed command code 01 for zone {response_zone_id} - Response: {response_hex_list}")

                    elif command_code == '02': #Mute state
                        mute_state_hex = response_hex_list[2]
                        mute_state = mute_state_hex == '00' # '00' is unmuted, '01' is muted
                        zone_state['mute'] = mute_state
                        _LOGGER.debug(f"Parsed command code 02 for zone {response_zone_id} - Response: {response_hex_list}")

                    elif command_code == '03': #Source select
                        source_hex = response_hex_list[2]
                        #Find source name from ID, default to "unknown" if not found
                        source_name = next((name for name, src in SOURCES.items() if src["id"] == int(source_hex, 16)), "unknown")
                        source_id = int(source_hex, 16)
                        zone_state['source'] = source_id #Store ID not name in cache
                        _LOGGER.debug(f"Parsed command code 03 for zone {response_zone_id} - Response: {response_hex_list}")

                    elif command_code == '04': #Volume level
                        volume_hex = response_hex_list[2]
                        volume_level_axium = int(volume_hex, 16)
                        #volume_percent = int(round((volume_level_axium / 160) * 100)) #Convert to percentage #Removed
                        zone_state['volume'] = volume_level_axium #Store raw value
                        _LOGGER.debug(f"Parsed command code 04 for zone {response_zone_id} - Response: {response_hex_list}")

                    elif command_code == '05': #Bass level
                        bass_hex = response_hex_list[2]
                        bass_level = int.from_bytes(bytes.fromhex(bass_hex), byteorder='big', signed=True) #Handle signed byte
                        zone_state['bass'] = bass_level
                        _LOGGER.debug(f"Parsed command code 05 for zone {response_zone_id} - Response: {response_hex_list}")

                    elif command_code == '06': #Treble level
                        treble_hex = response_hex_list[2]
                        treble_level = int.from_bytes(bytes.fromhex(treble_hex), byteorder='big', signed=True) #Handle signed byte
                        zone_state['treble'] = treble_level
                        _LOGGER.debug(f"Parsed command code 06 for zone {response_zone_id} - Response: {response_hex_list}")

                    elif command_code == '0D': #Maximum Volume Level
                        max_volume_hex = response_hex_list[2]
                        max_volume = int(max_volume_hex, 16)
                        zone_state['max_volume'] = max_volume
                        _LOGGER.debug(f"Parsed command code 0D for zone {response_zone_id} - Response: {response_hex_list}, Max Volume: {max_volume}")

                    # Handle expected but currently unused responses
                    elif command_code in ['07', '0C', '1C', '1D', '26', '29', '09', '1E', '0F']: # Removed '0D' from ignored commands
                        _LOGGER.debug(f"Parsed and ignored command code {command_code} for zone {response_zone_id} - Response: {response_hex_list}")
                    elif command_code in ['07', '0C', '0D', '1C', '1D', '26', '29', '09', '1E', '0F']:
                        pass # no logging for these for now

                except Exception as e:
                    _LOGGER.warning(f"Error parsing response for command code {command_code}: {response_hex_list}. Error: {e}")
                    continue #Continue to next command code even if one fails

            _LOGGER.debug(f"Updated state cache for zone {response_zone_id}: {zone_state}") #Log for each zone updated

        _LOGGER.debug(f"State cache update complete after parsing responses for main zone {main_zone_id}.") #General log at the end

    def register_entity(self, zone_id: int, entity: "AxiumZone") -> None:
        """Register an entity with the controller."""
        self._entity_map[zone_id] = entity
        _LOGGER.debug(f"Registered entity for zone ID {zone_id}: {entity}")

    def unregister_entity(self, zone_id: int) -> None:
        """Unregister an entity."""
        if zone_id in self._entity_map:
            del self._entity_map[zone_id]
            _LOGGER.debug(f"Unregistered entity for zone ID {zone_id}")