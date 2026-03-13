"""Shift Wellness Summary card.

Generated at the end of a shift simulation showing mood timeline,
events, hours driven, and a personalised message.
"""

import logging
from typing import Optional

from PIL import Image, ImageDraw

from src.cards.renderer import (
    COLORS, create_card, draw_gradient_overlay, draw_header,
    draw_badge, draw_text_wrapped, draw_divider, save_card, _get_font,
)

logger = logging.getLogger(__name__)

# Mood -> colour mapping for timeline dots
MOOD_COLORS = {
    "cheerful": (100, 220, 130),
    "neutral": (200, 210, 220),
    "grumpy": (255, 165, 60),
    "anxious": (255, 210, 70),
    "lonely": (150, 130, 200),
    "stressed": (255, 140, 100),
    "homesick": (150, 130, 200),
    "defiant": (255, 100, 100),
    "exhausted": (255, 80, 80),
    "shaken": (255, 120, 80),
    "tired": (255, 165, 60),
    "alert": (100, 220, 130),
    "mildly_tired": (255, 210, 70),
    "fatigued": (255, 140, 100),
    "dangerously_fatigued": (255, 80, 80),
}

# Trigger type -> short label
TRIGGER_LABELS = {
    "fatigue_camera": "FAT",
    "erratic_driving": "ERR",
    "break_limit": "BRK",
    "companion_check_in": "CHK",
    "driver_initiated": "DRV",
}

TRIGGER_COLORS = {
    "fatigue_camera": COLORS["orange"],
    "erratic_driving": COLORS["red"],
    "break_limit": COLORS["yellow"],
    "companion_check_in": COLORS["green"],
    "driver_initiated": (100, 180, 255),
}


def generate_wellness_card(
    driver_id: str,
    driver_name: str,
    shift_results: list[dict],
    total_duration_s: float,
    message: str = "",
) -> str:
    """Generate a shift wellness summary card.

    Args:
        driver_id: Driver identifier
        driver_name: Driver's first name
        shift_results: List of event results from shift simulator
        total_duration_s: Total real-time duration of the shift sim
        message: Personalised end-of-shift message

    Returns the URL path to the saved image.
    """
    img = create_card(800, 600, COLORS["bg_blue"])
    draw_gradient_overlay(img, start_alpha=0, end_alpha=80)
    draw = ImageDraw.Draw(img)

    # Header
    y = 25
    y = draw_header(draw, y, "Shift Wellness Summary", f"{driver_name}'s Shift Report")

    # Stats row
    y += 5
    total_events = len(shift_results)
    completed = sum(1 for r in shift_results if r.get("status") == "completed")
    max_hour = max((r.get("hour", 0) for r in shift_results), default=0)
    total_turns = sum(r.get("turns", 0) for r in shift_results)

    stats = [
        (f"{max_hour:.1f}h", "Shift Hours"),
        (str(total_events), "Events"),
        (str(total_turns), "Conversations"),
        (str(completed), "Completed"),
    ]

    font_stat_num = _get_font(28, bold=True)
    font_stat_label = _get_font(12)
    stat_width = 160
    stat_x = 40
    for value, label in stats:
        draw.text((stat_x, y), value, fill=COLORS["white"], font=font_stat_num)
        draw.text((stat_x, y + 34), label, fill=COLORS["white_60"], font=font_stat_label)
        stat_x += stat_width
    y += 65

    y = draw_divider(draw, y)

    # Event timeline
    font_label = _get_font(13)
    draw.text((40, y), "SHIFT TIMELINE", fill=COLORS["white_60"], font=font_label)
    y += 22

    # Draw timeline bar
    timeline_x = 60
    timeline_w = 680
    timeline_y = y + 12
    bar_h = 6

    # Background bar
    draw.rounded_rectangle(
        [timeline_x, timeline_y, timeline_x + timeline_w, timeline_y + bar_h],
        radius=3, fill=(255, 255, 255, 40),
    )

    # Plot events on timeline
    max_shift_hour = max(14.0, max_hour + 1)
    font_tiny = _get_font(10)
    for result in shift_results:
        hour = result.get("hour", 0)
        trigger = result.get("trigger", "")
        ex = timeline_x + int((hour / max_shift_hour) * timeline_w)

        dot_color = TRIGGER_COLORS.get(trigger, COLORS["white"])
        draw.ellipse([ex - 6, timeline_y - 3, ex + 6, timeline_y + bar_h + 3],
                     fill=dot_color)

        # Label below
        label = TRIGGER_LABELS.get(trigger, "?")
        draw.text((ex - 8, timeline_y + bar_h + 6), label,
                  fill=COLORS["white_60"], font=font_tiny)

    # Hour markers
    y = timeline_y + bar_h + 22
    for h in range(0, int(max_shift_hour) + 1, 2):
        hx = timeline_x + int((h / max_shift_hour) * timeline_w)
        draw.text((hx - 4, y), f"{h}h", fill=COLORS["white_60"], font=font_tiny)
    y += 20

    y = draw_divider(draw, y + 5)

    # Event breakdown
    draw.text((40, y), "EVENT BREAKDOWN", fill=COLORS["white_60"], font=font_label)
    y += 22

    font_event = _get_font(13)
    for i, result in enumerate(shift_results):
        if y > 490:
            draw.text((40, y), f"... and {len(shift_results) - i} more",
                      fill=COLORS["white_60"], font=font_event)
            y += 18
            break
        hour = result.get("hour", 0)
        trigger = result.get("trigger", "")
        turns = result.get("turns", 0)
        dur = result.get("duration", 0)

        dot_color = TRIGGER_COLORS.get(trigger, COLORS["white"])
        draw.ellipse([40, y + 3, 48, y + 11], fill=dot_color)

        line = f"{hour:.1f}h  {trigger.replace('_', ' ').title()}  —  {turns} turns, {dur:.0f}s"
        draw.text((55, y), line, fill=COLORS["white"], font=font_event)
        y += 20

    # Message
    if message:
        y = max(y + 5, 500)
        y = draw_divider(draw, y)
        font_msg = _get_font(16)
        y = draw_text_wrapped(draw, 40, y, f'"{message}"', font_msg,
                              COLORS["white"], max_width=720)
        font_sig = _get_font(13)
        draw.text((40, y + 4), "— Betty", fill=COLORS["yellow"], font=font_sig)

    # Footer
    font_footer = _get_font(11)
    draw.text((40, 575), "Betty AI Companion • Shift Wellness Report",
              fill=COLORS["white_60"], font=font_footer)

    return save_card(img, driver_id, "wellness")
