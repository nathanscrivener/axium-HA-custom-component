# Axium Amplifier Integration for Home Assistant

This custom component integrates Axium multi-zone amplifiers with Home Assistant, allowing you to control and monitor your Axium amplifier system.

## Features

- **Zone Control**: Power on/off, volume adjustment, source selection, and mute control for each amplifier zone
- **Audio Settings**: Adjust bass and treble levels for each zone
- **Maximum Volume**: Set maximum volume limits for zones
- **Real-time Updates**: Continuous monitoring for changes made outside Home Assistant (via keypads, remotes, or directly on the amplifier)
- **Periodic Refresh**: Automatic state refresh every 15 minutes to ensure synchronization

## Requirements

- Home Assistant (Core or OS)
- Serial connection to Axium amplifier (direct or via IP-to-serial adapter)
- Properly configured Axium amplifier system

## Installation

### Method 1: HACS (recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance
2. Go to HACS → Integrations → Click the three dots in the top right corner → Custom repositories
3. Add this repository URL with category "Integration"
4. Click "Install" on the Axium integration card
5. Restart Home Assistant

### Method 2: Manual Installation

1. Download the source code from this repository
2. Copy the `axium` folder to your Home Assistant `config/custom_components` directory
3. Restart Home Assistant

## Configuration

This integration supports configuration through the Home Assistant UI (Config Flow).

### UI Configuration Steps

1. Go to **Settings** → **Devices & Services**
2. Click the **+ ADD INTEGRATION** button in the bottom right
3. Search for "Axium" and select it
4. Follow the configuration flow:
   - Select or enter your serial port
   - Choose the zones you want to control
   - Customize zone names (optional)

The integration will automatically detect available serial ports. If your port isn't detected, you can enter it manually.

### Configuration Options

| Option | Description |
|--------|-------------|
| Serial Port | Path to the serial device connecting to your Axium amplifier |
| Zones | Select which zones you want to control |
| Zone Names | Customize the names of each zone |

## Zone Mapping

Axium amplifiers have main zones (1-16) and corresponding pre-out zones (41-56). The relationship is:
- Pre-out zone ID = Main zone ID + 40
- For example, zone 1's pre-out is zone 41

## Service Calls

This integration provides several services:

### axium.set_bass
```yaml
service: axium.set_bass
data:
  entity_id: media_player.living_room
  bass: 5  # Range: -12 to +12
```

### axium.set_treble
```yaml
service: axium.set_treble
data:
  entity_id: media_player.kitchen
  treble: -2  # Range: -12 to +12
```

### axium.set_max_volume
```yaml
service: axium.set_max_volume
data:
  entity_id: media_player.patio
  max_volume: 80  # Range: 0 to 160 (Axium native scale)
```

### axium.refresh_state
```yaml
service: axium.refresh_state
data:
  entity_id: media_player.living_room  # Optional, refreshes all zones if omitted
```

## Real-time Monitoring

The integration continuously monitors the serial port for "echoes" - unsolicited state updates from the amplifier when changes are made via keypads, remotes, or directly on the amplifier. This allows Home Assistant to stay in sync with the physical state of the system in real-time.

## Troubleshooting

### Connection Issues
- Verify the serial port path is correct
- Ensure you have read/write permissions to the serial port
- Check the baud rate (should be 9600 for older Axium amplifiers using RS232)
- If using an IP-to-serial adapter, verify network connectivity

### State Updates Not Working
- Check Home Assistant logs for any error messages
- Verify the zone IDs are configured correctly
- Try restarting the integration or Home Assistant

### Logs
Add the following to your `configuration.yaml` to enable debug logging:

```yaml
logger:
  default: info
  logs:
    custom_components.axium: debug
```

## Legacy YAML Configuration

While UI configuration is recommended, this integration also supports YAML configuration for backward compatibility:

```yaml
axium:
  serial_port: /dev/ttyUSB0  # Adjust to your serial port path
  zones:
    - zone_id: 1  # Main zone 1
      name: "Living Room"
    - zone_id: 2
      name: "Kitchen"
    - zone_id: 41  # Pre-out for zone 1 (main zone ID + 40)
      name: "Patio"
    # Add more zones as needed
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 