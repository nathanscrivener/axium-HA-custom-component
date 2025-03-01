"""Constants for the Axium integration."""
from typing import Final

DOMAIN: Final = "axium"
CONF_SERIAL_PORT: Final = "serial_port"
CONF_ZONES: Final = "zones"
CONF_ZONE_NAMES: Final = "zone_names"
REQUIRED_BAUDRATE: Final = 9600


"""Scale linear volume (0.0-1.0) to perceptual volume (0.0-1.0) - BOOST LOW VOLUMES.

    Args:
        linear_volume (float): The linear volume level from Home Assistant UI (0.0-1.0).
        power_factor (float):  Exponent for the power function (adjust to control curve steepness). Values 1.5 to 2.0
            are good starting points for this inverted scaling.
        volume_offset (float): Offset applied to linear volume *before* scaling (UI 0.0-1.0 scale).
                                A small positive offset (e.g., 0.05) can be a good starting point
                                to lift the lower end of the volume curve and make very quiet
                                settings more audible. Experiment with values from 0.0 to 0.1.
"""


POWER_FACTOR: Final = 1.7   # Scaling factor for logarithmic volume
VOLUME_OFFSET: Final = 0.0  # Offset for logarithmic volume

# Define your zones and their hex values
ZONES = {
    "family_room": 0x01,
    "kitchen": 0x02,
    "outside": 0x03,
    "master_bedroom": 0x04,
    "garage": 0x43,
    "ensuite": 0x44
}

#Define your sources and their hex values
"""
Default amp sources below
SOURCES = {
    "cd": {"id": 0x00, "name": "CD"},
    "tape": {"id": 0x01, "name": "Tape"},
    "tuner": {"id": 0x02, "name": "Tuner"},
    "aux": {"id": 0x03, "name": "Aux"},
    "utility": {"id": 0x04, "name": "Utility"},
    "sat": {"id": 0x05, "name": "SAT"},
    "dvd": {"id": 0x06, "name": "DVD"},
    "video": {"id": 0x07, "name": "Video"}
}
"""
SOURCES = {
    #"cd": {"id": 0x00, "name": "CD"},
    "tape": {"id": 0x01, "name": "TV"},
    #"tuner": {"id": 0x02, "name": "Tuner"},
    "aux": {"id": 0x03, "name": "Roon"}
    #"utility": {"id": 0x04, "name": "Utility"},
    #"sat": {"id": 0x05, "name": "SAT"},
    #"dvd": {"id": 0x06, "name": "DVD"},
    #"video": {"id": 0x07, "name": "Video"}
}
