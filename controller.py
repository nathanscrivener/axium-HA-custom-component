"""
Axium amplifier controller.

This module provides the AxiumController class, which handles communication with the Axium amplifier
via a serial connection. The controller supports:

1. Querying and setting the state of amplifier zones (power, volume, source, etc.)
2. Refreshing zone states on a periodic basis (every 15 minutes)
3. Continuous monitoring of the serial port for "echoes" - unsolicited state updates from the amplifier
   that occur when changes are made via keypads or directly on the amplifier

The continuous monitoring feature allows for real-time updates in Home Assistant when changes
are made outside of Home Assistant (e.g., via physical keypads or remotes).
"""
import asyncio
import logging
from typing import Optional, TYPE_CHECKING, List, Dict, Any, Union

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
        self._refresh_task = None  # Task for periodic refresh
        self._monitor_task = None  # Task for continuous monitoring
        self._monitoring = False  # Flag to indicate if monitoring is active
        self._last_command_time = None  # Time of last sent command
        self._read_lock = asyncio.Lock()  # Separate lock for reading, allows parallel read/write operations

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
            await self.refresh_all_zones()  # Use the new general refresh function
            self.initial_query_complete.set()  # Signal completion
            
            # Start periodic refresh task
            self._start_refresh_task()
            
            # Start continuous monitoring task
            self._start_monitor_task()

            return True  # Indicate successful connection
        except Exception as err:
            self._connected = False
            _LOGGER.warning("Failed to connect to Axium amplifier: %s.", err)
            if not self._reconnect_task:
                self._reconnect_task = asyncio.create_task(self._reconnect())
            return False  # Indicate connection failure

    async def disconnect(self) -> None:
        """Explicitly disconnect from the amplifier."""
        # Cancel the refresh task if it's running
        self._stop_refresh_task()
        
        # Stop the monitoring task if it's running
        self._stop_monitor_task()
        
        if self._serial_writer:
            try:
                self._serial_writer.close()
                await self._serial_writer.wait_closed()
            except Exception as e:
                _LOGGER.error(f"Error closing serial writer: {e}")
            self._serial_writer = None
            # The reader will be cleaned up automatically when the writer is closed
            self._serial_reader = None
        self._connected = False
        
    def _start_refresh_task(self) -> None:
        """Start the periodic refresh task if not already running."""
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._refresh_loop())
            _LOGGER.debug("Started periodic refresh task (every 15 minutes)")
            
    def _stop_refresh_task(self) -> None:
        """Stop the periodic refresh task if running."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            self._refresh_task = None
            _LOGGER.debug("Stopped periodic refresh task")
    
    def _start_monitor_task(self) -> None:
        """Start the continuous monitoring task if not already running."""
        if self._monitor_task is None or self._monitor_task.done():
            self._monitoring = True
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            _LOGGER.info("Started continuous amplifier state monitoring")
            
    def _stop_monitor_task(self) -> None:
        """Stop the continuous monitoring task if running."""
        self._monitoring = False
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            self._monitor_task = None
            _LOGGER.debug("Stopped continuous monitoring task")
            
    async def _monitor_loop(self) -> None:
        """
        Continuously monitor the serial port for spontaneous updates from the amplifier.
        
        This loop runs indefinitely in the background, processing any incoming data
        that is not a direct response to a command we sent. This allows us to detect
        changes made by keypads, remote controls, or directly on the amplifier.
        """
        try:
            while self._monitoring and self._connected:
                # Check if we're in the middle of sending a command
                # If we are, we'll skip monitoring for a short time to avoid
                # mixing up responses to our commands with spontaneous updates
                current_time = asyncio.get_event_loop().time()
                recently_sent_command = (
                    self._last_command_time is not None and 
                    current_time - self._last_command_time < 0.3  # Reduced to 300ms grace period
                )
                
                if not recently_sent_command:
                    # Only try to read if we're not expecting a response to a command
                    try:
                        # Use a very short timeout to make this non-blocking
                        async with self._read_lock:
                            response_bytes = await asyncio.wait_for(
                                self._serial_reader.readline(), 
                                timeout=0.05  # Reduced to 50ms timeout for faster response
                            )
                            
                            if response_bytes:
                                # Process the response
                                decoded_response = self._decode_response(response_bytes)
                                if decoded_response and len(decoded_response) >= 2:
                                    # This is a spontaneous update from the amplifier
                                    await self._process_spontaneous_update(decoded_response)
                    except asyncio.TimeoutError:
                        # This is expected, just continue the loop
                        pass
                    except Exception as e:
                        _LOGGER.warning(f"Error in monitor loop: {e}")
                
                # Small sleep to prevent CPU hogging
                await asyncio.sleep(0.01)  # Reduced to 10ms sleep for more responsive detection
                
        except asyncio.CancelledError:
            # Task was cancelled - this is normal during shutdown
            _LOGGER.debug("Monitoring task cancelled")
        except Exception as e:
            _LOGGER.error(f"Unexpected error in monitoring task: {e}", exc_info=True)
            # Attempt to restart the monitor task if it fails
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            
    async def _process_spontaneous_update(self, decoded_response: List[str]) -> None:
        """
        Process a spontaneous update from the amplifier (not in response to our command).
        
        Args:
            decoded_response: The decoded response from the amplifier as a list of hex strings
        """
        if len(decoded_response) < 2:
            return
            
        try:
            command_code = decoded_response[0]
            zone_hex = decoded_response[1]
            zone_id = int(zone_hex, 16)
            
            # Log the spontaneous update with more detail
            _LOGGER.debug(f"Processing spontaneous update: command={command_code}, zone={zone_id}, data={decoded_response}")
            
            # Create a dictionary structure like what refresh_zone_state uses
            responses = {zone_id: {command_code: decoded_response}}
            
            # Handle source switching specifically
            if command_code == '03' and len(decoded_response) >= 3:  # Source command with enough data
                source_id = int(decoded_response[2], 16)
                # Update state cache directly for both the zone and its paired zone
                self._state_cache.setdefault(zone_id, {})['source'] = source_id
                
                # If there's a paired zone, update it too
                paired_zone = self._zone_mapping.get(zone_id)
                if paired_zone:
                    self._state_cache.setdefault(paired_zone, {})['source'] = source_id
                    # Add the paired zone to the responses to ensure it gets processed
                    responses[paired_zone] = {command_code: decoded_response}
                    
                _LOGGER.info(f"Source change detected: zone={zone_id}, new source={source_id}")
            
            # Update state cache with this response
            self._update_state_from_responses(zone_id, responses)
            
            # Update all affected zones in Home Assistant
            for affected_zone_id in responses.keys():
                if affected_zone_id in self._entity_map:
                    _LOGGER.debug(f"Updating entity for zone {affected_zone_id} due to spontaneous update")
                    await self._entity_map[affected_zone_id].async_update_ha_state(True)
                
        except Exception as e:
            _LOGGER.warning(f"Error processing spontaneous update: {e}, response: {decoded_response}")
            
    async def _reconnect(self) -> None:
        """Periodically attempt to reconnect."""
        while True:
            await asyncio.sleep(10)  # Wait 10 seconds between retries
            _LOGGER.debug("Attempting to reconnect to Axium amplifier...")
            await self.connect()  # No try-except here; let connect() handle it
            
    async def _refresh_loop(self) -> None:
        """Periodically refresh all zones every 15 minutes."""
        try:
            while True:
                # Wait for 15 minutes (900 seconds)
                await asyncio.sleep(900)
                
                if not self._connected:
                    _LOGGER.debug("Periodic refresh skipped - not connected")
                    continue
                    
                try:
                    _LOGGER.debug("Performing periodic refresh of all zones")
                    await self.refresh_all_zones()
                except Exception as e:
                    _LOGGER.error(f"Error during periodic refresh: {e}")
        except asyncio.CancelledError:
            # Task was cancelled - this is normal during shutdown
            _LOGGER.debug("Periodic refresh task cancelled")
        except Exception as e:
            _LOGGER.error(f"Unexpected error in refresh task: {e}")

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
                
                # Record the time we sent this command
                self._last_command_time = asyncio.get_event_loop().time()
                
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

    async def refresh_zone_state(self, zone_id: int) -> bool:
        """
        Query the state of a specific zone and update the state cache.
        
        This is a general-purpose function that can be called at any time to 
        refresh the state of a zone, not just during initialization.
        
        Args:
            zone_id: The ID of the zone to refresh
            
        Returns:
            bool: True if the query was successful, False otherwise
        """
        if not self._connected and not await self.connect():
            _LOGGER.error(f"Cannot refresh zone {zone_id} - not connected and connection failed")
            return False
            
        command = bytes([0x09, zone_id]) # Send All Parameters command
        _LOGGER.debug(f"Refreshing state for zone {zone_id}...")
        if not await self._send_command(command): #Send command and check success
            _LOGGER.warning(f"Failed to send state query command for zone {zone_id}.")
            return False

        expected_responses = [ #List of expected command codes in response
            '01', '02', '03', '04', '05', '06', '07', '0C', '0D', '1C', '1D', '26', '29',
            '09', '1E', '0F', '0D' # Add expected but currently unused responses, and '0D' for max volume
        ]
        responses_received = {} # Changed to just responses_received, will be nested dict
        timeout_start = asyncio.get_event_loop().time()

        # Use the read lock to ensure exclusive access to the serial reader
        async with self._read_lock:
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
            return False

        _LOGGER.debug(f"Received responses for zone {zone_id}: {responses_received.keys()}")
        self._update_state_from_responses(zone_id, responses_received) # Process and update state from collected responses
        
        # Update entity if needed
        for zone_to_update in responses_received.keys():
            if zone_to_update in self._entity_map:
                await self._entity_map[zone_to_update].async_update_ha_state(True)
        
        _LOGGER.debug(f"State refresh completed for zone {zone_id}.")
        return True

    async def refresh_all_zones(self) -> bool:
        """
        Refresh the state of all main zones and their linked pre-out zones.
        
        Returns:
            bool: True if all queries were successful, False if any failed
        """
        success = True
        
        for zone_id in ZONES.values():
            if zone_id <= 0x0F:  # Query only main zones, pre-outs are included in response
                result = await self.refresh_zone_state(zone_id)
                success = success and result
                
        return success

    # Legacy method for backward compatibility
    async def async_query_zone_state(self, zone_id: int) -> None:
        """Query all parameters for a zone and update state cache. Use refresh_zone_state instead."""
        await self.refresh_zone_state(zone_id)

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