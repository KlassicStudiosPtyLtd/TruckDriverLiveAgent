"""Rest Stop recommendation card.

Generated when Betty suggests a driver pull over at a rest area.
Shows rest area name, distance, facilities, and a warm message.

Background image pipeline:
1. Gemini Flash + Google Search grounding describes what the real location looks like
2. Imagen 4 generates a scenic image from that description
3. Falls back to a generic outback scene if search/generation fails
"""

import io
import logging
import os
import random
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter

from src.cards.renderer import (
    COLORS, FACILITY_LABELS, draw_gradient_overlay,
    draw_header, draw_badge, draw_text_wrapped, draw_divider,
    save_card, _get_font,
)
from src.data.mock_fleet import REST_AREAS

logger = logging.getLogger(__name__)

# Generic fallback prompts when we can't find the real location
_FALLBACK_PROMPTS = [
    "A peaceful Australian outback roadhouse at golden hour, red dirt road, eucalyptus trees, clear blue sky, warm light, wide angle landscape photo",
    "A serene truck rest area under a big Australian sky at sunset, gum trees casting long shadows, quiet and inviting, landscape photography",
    "A quiet roadside rest stop in the Western Australian bush, shady trees, picnic tables, a water tank, warm afternoon light, landscape photo",
    "An inviting country roadhouse in rural Australia, veranda with shade, fuel pumps, dusty road, dramatic cloud formations, golden hour photography",
    "A tranquil rest bay along an outback highway at dawn, pink sky, spinifex grass, distant hills, a lone boab tree, landscape photography",
    "A welcoming truck stop in the Australian bush, corrugated iron roof, shady parking area, red earth, blue sky with wispy clouds, photography",
]


def _describe_location(rest_area_name: str, api_key: str) -> Optional[str]:
    """Use Gemini + Google Search grounding to describe the real location."""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=(
                f"Describe what {rest_area_name} in Western Australia looks like "
                f"in 2-3 sentences. Focus on physical appearance: landscape, vegetation, "
                f"buildings, road surface, colours, sky, surroundings. Be specific and visual. "
                f"If you can't find this exact location, describe the general area and landscape."
            ),
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        description = response.text.strip()
        if description:
            logger.info("Location description for %s: %s", rest_area_name, description[:150])
            return description
    except Exception:
        logger.exception("Failed to describe location %s", rest_area_name)
    return None


def _generate_imagen_background(prompt: str, api_key: str) -> Optional[Image.Image]:
    """Generate a scenic background image via Imagen 4."""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        logger.info("Generating Imagen background...")
        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                output_mime_type="image/jpeg",
                aspect_ratio="16:9",
            ),
        )

        if response.generated_images:
            img_bytes = response.generated_images[0].image.image_bytes
            bg = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
            logger.info("Imagen background generated (%dx%d)", bg.width, bg.height)
            return bg

        logger.warning("Imagen returned no images")
    except Exception:
        logger.exception("Imagen background generation failed")
    return None


def _generate_background(rest_area_name: str) -> Optional[Image.Image]:
    """Full pipeline: search → describe → generate.

    1. Use Gemini + Google Search to describe the real location
    2. Feed that description to Imagen 4 to generate a scenic background
    3. Fall back to a generic outback prompt if search fails
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning("No GEMINI_API_KEY — skipping background generation")
        return None

    # Step 1: Try to get a real description of this location
    description = _describe_location(rest_area_name, api_key)

    if description:
        # Step 2: Generate from the real description
        imagen_prompt = (
            f"A beautiful landscape photograph of this location: {description} "
            f"Wide angle, golden hour light, peaceful and inviting. "
            f"No people, no text, no signs. Photorealistic."
        )
    else:
        # Fallback: generic outback scene
        imagen_prompt = random.choice(_FALLBACK_PROMPTS) + " No people, no text, no signs."

    # Step 3: Generate the image
    return _generate_imagen_background(imagen_prompt, api_key)


def _find_rest_area(name: str) -> Optional[dict]:
    """Find a rest area by name (fuzzy match)."""
    name_lower = name.lower()
    for ra in REST_AREAS:
        if name_lower in ra["name"].lower() or ra["name"].lower() in name_lower:
            return ra
    return None


def generate_rest_stop_card(
    driver_id: str,
    driver_name: str,
    rest_area_name: str,
    distance_km: float,
    message: str,
) -> str:
    """Generate a rest stop recommendation card.

    Returns the URL path to the saved image.
    """
    width, height = 800, 450

    # Try to generate an Imagen background based on the real location
    bg_img = _generate_background(rest_area_name)

    if bg_img:
        # Resize and crop to card dimensions
        bg_img = bg_img.resize((width, height), Image.LANCZOS)
        # Apply a slight blur for readability
        bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=2))
        img = bg_img
    else:
        # Fallback to solid colour
        img = Image.new("RGBA", (width, height), COLORS["bg_blue"] + (255,))

    # Dark overlay for text readability
    draw_gradient_overlay(img, start_alpha=120, end_alpha=200)
    draw = ImageDraw.Draw(img)

    # Header
    y = 30
    y = draw_header(draw, y, "Rest Stop Ahead", f"Recommendation for {driver_name}")

    # Rest area name + distance
    y += 5
    font_big = _get_font(32, bold=True)
    draw.text((40, y), rest_area_name, fill=COLORS["yellow"], font=font_big)
    y += 44

    # Distance badge
    dist_text = f"{distance_km:.0f} km ahead"
    draw_badge(draw, 40, y, dist_text, COLORS["bg_green"])
    y += 50

    # Facilities
    rest_area = _find_rest_area(rest_area_name)
    if rest_area and rest_area.get("facilities"):
        draw_divider(draw, y)
        y += 5
        font_label = _get_font(13)
        draw.text((40, y), "FACILITIES", fill=COLORS["white_60"], font=font_label)
        y += 22

        x = 40
        for facility in rest_area["facilities"]:
            label = FACILITY_LABELS.get(facility, facility.upper())
            w = draw_badge(draw, x, y, label, COLORS["bg_blue_light"])
            x += w + 8
        y += 45
    else:
        y += 10

    # Betty's message
    draw_divider(draw, y)
    y += 5
    font_msg = _get_font(18)
    msg_display = f'"{message}"'
    y = draw_text_wrapped(draw, 40, y, msg_display, font_msg,
                          COLORS["white"], max_width=720)
    y += 8
    font_sig = _get_font(14)
    draw.text((40, y), "— Betty", fill=COLORS["yellow"], font=font_sig)

    # Footer
    font_footer = _get_font(11)
    draw.text((40, 425), "Betty AI Companion • Drive Safe",
              fill=COLORS["white_60"], font=font_footer)

    return save_card(img, driver_id, "rest_stop")
