"""
Color extraction utilities for product images.

This module provides functions to extract dominant colors from product images
and map them to human-readable color names. This helps the agent correctly
identify product colors (e.g., "red package", "blue item") that may be
difficult to discern from the visual input alone.
"""

from PIL import Image
from collections import Counter
import colorsys
from typing import Optional
import math


# Named colors with their RGB values
# These are common colors that products are likely to be described as
NAMED_COLORS = {
    "red": (255, 0, 0),
    "dark red": (139, 0, 0),
    "orange": (255, 165, 0),
    "yellow": (255, 255, 0),
    "green": (0, 128, 0),
    "dark green": (0, 100, 0),
    "lime": (0, 255, 0),
    "blue": (0, 0, 255),
    "light blue": (135, 206, 235),
    "dark blue": (0, 0, 139),
    "navy": (0, 0, 128),
    "purple": (128, 0, 128),
    "pink": (255, 192, 203),
    "magenta": (255, 0, 255),
    "brown": (139, 69, 19),
    "tan": (210, 180, 140),
    "beige": (245, 245, 220),
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gray": (128, 128, 128),
    "light gray": (192, 192, 192),
    "dark gray": (64, 64, 64),
    "gold": (255, 215, 0),
    "silver": (192, 192, 192),
    "cyan": (0, 255, 255),
    "teal": (0, 128, 128),
}


def color_distance(c1: tuple, c2: tuple) -> float:
    """
    Calculate the Euclidean distance between two RGB colors.

    Args:
        c1: First color as (R, G, B) tuple
        c2: Second color as (R, G, B) tuple

    Returns:
        Euclidean distance between the colors
    """
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def get_color_name(rgb: tuple) -> str:
    """
    Map an RGB value to the closest named color.

    Args:
        rgb: Color as (R, G, B) tuple

    Returns:
        Human-readable color name (e.g., "red", "dark blue")
    """
    min_distance = float("inf")
    closest_color = "unknown"

    for name, named_rgb in NAMED_COLORS.items():
        distance = color_distance(rgb, named_rgb)
        if distance < min_distance:
            min_distance = distance
            closest_color = name

    return closest_color


def extract_dominant_color(image: Image.Image, sample_size: int = 100) -> dict:
    """
    Extract the dominant color from an image.

    Uses color quantization to find the most common colors in the image,
    excluding near-white and near-black backgrounds.

    Args:
        image: PIL Image object
        sample_size: Number of pixels to sample (for performance)

    Returns:
        Dictionary with:
        - 'rgb': Dominant color as (R, G, B) tuple
        - 'name': Human-readable color name
        - 'confidence': Confidence score (0.0-1.0)
    """
    try:
        # Convert to RGB if necessary
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Resize for faster processing
        image = image.resize((sample_size, sample_size), Image.Resampling.LANCZOS)

        # Get all pixels
        pixels = list(image.getdata())

        # Filter out near-white and near-black pixels (background/borders)
        def is_interesting_color(rgb):
            r, g, b = rgb
            # Skip very dark (likely black/border)
            if r < 30 and g < 30 and b < 30:
                return False
            # Skip very light (likely white/background)
            if r > 230 and g > 230 and b > 230:
                return False
            # Skip gray tones (often not the main product color)
            if abs(r - g) < 15 and abs(g - b) < 15 and abs(r - b) < 15:
                if 50 < r < 200:  # Skip mid-grays
                    return False
            return True

        interesting_pixels = [p for p in pixels if is_interesting_color(p)]

        # If no interesting pixels found, use all pixels
        if not interesting_pixels:
            interesting_pixels = pixels

        # Quantize colors to reduce variety (group similar colors)
        def quantize_color(rgb, levels=8):
            factor = 256 // levels
            return tuple((c // factor) * factor + factor // 2 for c in rgb)

        quantized = [quantize_color(p) for p in interesting_pixels]

        # Find most common color
        color_counts = Counter(quantized)
        most_common = color_counts.most_common(3)  # Get top 3 colors

        if not most_common:
            return {"rgb": (128, 128, 128), "name": "unknown", "confidence": 0.0}

        dominant_rgb = most_common[0][0]
        total_pixels = len(quantized)
        dominant_count = most_common[0][1]

        # Calculate confidence based on how dominant the color is
        confidence = dominant_count / total_pixels

        return {
            "rgb": dominant_rgb,
            "name": get_color_name(dominant_rgb),
            "confidence": round(confidence, 2),
        }

    except Exception as e:
        # Return a safe default on error
        return {
            "rgb": (128, 128, 128),
            "name": "unknown",
            "confidence": 0.0,
            "error": str(e),
        }


def extract_colors_from_image(image: Image.Image, top_n: int = 3) -> list[dict]:
    """
    Extract the top N dominant colors from an image.

    Args:
        image: PIL Image object
        top_n: Number of top colors to return

    Returns:
        List of dictionaries with color information
    """
    try:
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Resize for faster processing
        image = image.resize((100, 100), Image.Resampling.LANCZOS)

        pixels = list(image.getdata())

        # Quantize colors
        def quantize_color(rgb, levels=8):
            factor = 256 // levels
            return tuple((c // factor) * factor + factor // 2 for c in rgb)

        quantized = [quantize_color(p) for p in pixels]
        color_counts = Counter(quantized)
        most_common = color_counts.most_common(top_n)

        total = len(quantized)
        results = []
        for rgb, count in most_common:
            results.append(
                {
                    "rgb": rgb,
                    "name": get_color_name(rgb),
                    "percentage": round(count / total * 100, 1),
                }
            )

        return results

    except Exception as e:
        return []
