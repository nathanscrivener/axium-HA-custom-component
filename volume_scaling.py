# volume_scaling.py
import math

from .const import POWER_FACTOR, VOLUME_OFFSET

def linear_to_perceptual_volume(linear_volume, power_factor=POWER_FACTOR, volume_offset=VOLUME_OFFSET): # power_factor to 2.5, offset to 0.05
    """Scale linear volume (0.0-1.0) to perceptual volume (0.0-1.0) - BOOST LOW VOLUMES."""
    # Invert the linear volume:  1.0 becomes 0.0, 0.0 becomes 1.0
    inverted_linear_volume = 1.0 - linear_volume

    # Apply power function to the *inverted* volume
    scaled_inverted_volume = inverted_linear_volume ** power_factor

    # Invert the result back to the normal volume range
    perceptual_volume = 1.0 - scaled_inverted_volume

    # Apply offset (after scaling and inversion)
    adjusted_perceptual_volume = max(0.0, min(1.0, perceptual_volume + volume_offset))
    return adjusted_perceptual_volume


def perceptual_to_linear_volume(perceptual_volume, power_factor=POWER_FACTOR, volume_offset=VOLUME_OFFSET): # Match parameters
    """Scale perceptual volume (0.0-1.0) back to linear volume (0.0-1.0) - INVERSE of boosting."""
    # Reverse the offset first
    volume_without_offset = max(0.0, min(1.0, perceptual_volume - volume_offset))

    # Invert the perceptual volume
    inverted_perceptual_volume = 1.0 - volume_without_offset

    # Apply inverse power function to the *inverted* volume
    scaled_inverted_volume = inverted_perceptual_volume ** (1.0 / power_factor)

    # Invert back to the normal linear range
    linear_volume = 1.0 - scaled_inverted_volume
    return max(0.0, min(1.0, linear_volume))