"""Constants for the Axium integration."""
from typing import Final

DOMAIN: Final = "axium"

CONF_SERIAL_PORT: Final = "serial_port"
CONF_ZONES: Final = "zones"

# Define your zones and their hex values
ZONES = {
    "family_room": 0x01,
    "kitchen": 0x02,
    "outside": 0x03,
    "master_bedroom": 0x04,
    "garage": 0x43,
    "ensuite": 0x44
}

""" Define your sources and their hex values
Default amp sources area below
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
    "aux": {"id": 0x03, "name": "Roon"},
    #"utility": {"id": 0x04, "name": "Utility"},
    #"sat": {"id": 0x05, "name": "SAT"},
    #"dvd": {"id": 0x06, "name": "DVD"},
    #"video": {"id": 0x07, "name": "Video"}
}
