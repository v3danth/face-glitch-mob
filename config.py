"""
Config module for glass_effect project.

This module loads all configurable parameters from the .env file and provides
a Config class for easy access throughout the project.

Each variable is documented with its purpose and expected type.
"""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """
    Configuration class for glass_effect project.
    Loads values from .env file or uses defaults.
    """

    # Face detection
    FACE_CASCADE_PATH: str = os.getenv(
        "FACE_CASCADE_PATH", "haarcascade_frontalface_default.xml"
    )
    """Path to Haar cascade XML for face detection (str)"""

    FACE_SCALE_FACTOR: float = float(os.getenv("FACE_SCALE_FACTOR", 0.5))
    """Scaling factor for resizing input image before detection (float)"""

    FACE_DETECT_SCALE: float = float(os.getenv("FACE_DETECT_SCALE", 1.1))
    """Scale factor for face detection (float)"""

    FACE_DETECT_MIN_NEIGHBORS: int = int(os.getenv("FACE_DETECT_MIN_NEIGHBORS", 5))
    """Minimum neighbors for face detection (int)"""

    FACE_DETECT_WEIGHT_THRESHOLD: float = float(
        os.getenv("FACE_DETECT_WEIGHT_THRESHOLD", 5)
    )
    """Threshold for face detection weight (float)"""

    # Glass effect
    GRID_SIZE: int = int(os.getenv("GRID_SIZE", 8))
    """Grid size for glass tiling (int)"""

    FEATHER_EDGES: bool = os.getenv("FEATHER_EDGES", "True").lower() == "true"
    """Whether to use smooth/feathered edge blending for tiles by default (bool)"""

    # Distortion
    DISTORTION_STRENGTH_MIN: float = float(os.getenv("DISTORTION_STRENGTH_MIN", 5))
    """Minimum distortion strength (float)"""

    DISTORTION_STRENGTH_MAX: float = float(os.getenv("DISTORTION_STRENGTH_MAX", 12))
    """Maximum distortion strength (float)"""

    NOISE_FACTOR: float = float(os.getenv("NOISE_FACTOR", 2))
    """Noise factor for distortion (float)"""

    # Frosted material
    FROSTED_KERNEL_CHOICES: list = [
        int(x) for x in os.getenv("FROSTED_KERNEL_CHOICES", "15,27,31").split(",")
    ]
    """Kernel sizes for frosted blur (list of int)"""

    # Clear material
    CLEAR_BLUR_KERNEL: int = int(os.getenv("CLEAR_BLUR_KERNEL", 7))
    """Kernel size for clear blur (int)"""

    # Glossy material
    GLOSSY_BLUR_KERNEL: int = int(os.getenv("GLOSSY_BLUR_KERNEL", 9))
    """Kernel size for glossy blur (int)"""

    HIGHLIGHT_BLUR_KERNEL: int = int(os.getenv("HIGHLIGHT_BLUR_KERNEL", 15))
    """Kernel size for highlight blur (int)"""

    HIGHLIGHT_LINE_COLOR: tuple = tuple(
        int(x) for x in os.getenv("HIGHLIGHT_LINE_COLOR", "255,255,255").split(",")
    )
    """Color of highlight line (tuple of int, RGB)"""

    HIGHLIGHT_LINE_THICKNESS: int = int(os.getenv("HIGHLIGHT_LINE_THICKNESS", 1))
    """Thickness of highlight line (int)"""

    HIGHLIGHT_LINE_POSITION: float = float(os.getenv("HIGHLIGHT_LINE_POSITION", 0.5))
    """Relative vertical position of highlight line (float, 0-1)"""

    GLOSSY_WEIGHT: float = float(os.getenv("GLOSSY_WEIGHT", 0.85))
    """Weight for glossy blur in blending (float)"""

    HIGHLIGHT_WEIGHT: float = float(os.getenv("HIGHLIGHT_WEIGHT", 0.15))
    """Weight for highlight in blending (float)"""

    # Output
    OUTPUT_PATH: str = os.getenv("OUTPUT_PATH", "output/output_with_faces.jpg")
    """Path to save output image (str)"""

    INPUT_IMAGE: str = os.getenv("INPUT_IMAGE", "input.jpg")
    """Path to input image (str)"""
