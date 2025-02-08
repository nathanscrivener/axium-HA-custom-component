# volume_scaling.py
import math

# Define POWER_FACTOR and VOLUME_OFFSET as constants
POWER_FACTOR = 2.5
VOLUME_OFFSET = 0.05

"""Scale linear volume (0.0-1.0) to perceptual volume (0.0-1.0) - BOOST LOW VOLUMES.

    Args:
        linear_volume (float): The linear volume level from Home Assistant UI (0.0-1.0).
        power_factor (float):  Exponent for the power function (adjust to control curve steepness). Values 2.0 to 3.0
            are good starting points for this inverted scaling.
        volume_offset (float): Offset applied to linear volume *before* scaling (UI 0.0-1.0 scale).
                                A small positive offset (e.g., 0.05) can be a good starting point
                                to lift the lower end of the volume curve and make very quiet
                                settings more audible. Experiment with values from 0.0 to 0.1.
"""

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