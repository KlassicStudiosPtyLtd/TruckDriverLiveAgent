"""Incident Snapshot card for fleet managers.

Generated when Betty escalates a driver concern to the fleet manager.
Shows trigger details, severity, Betty's assessment, and outcome.
"""

import logging
from datetime import datetime, timezone

from PIL import ImageDraw

from src.cards.renderer import (
    COLORS, create_card, draw_gradient_overlay, draw_header,
    draw_badge, draw_text_wrapped, draw_divider, save_card, _get_font,
)

logger = logging.getLogger(__name__)

URGENCY_COLORS = {
    "low": COLORS["yellow"],
    "medium": COLORS["orange"],
    "high": COLORS["red"],
}

URGENCY_BG = {
    "low": COLORS["bg_blue"],
    "medium": COLORS["bg_orange"],
    "high": COLORS["bg_red"],
}


def generate_incident_card(
    driver_id: str,
    driver_name: str,
    trigger_type: str,
    trigger_data: dict,
    urgency: str,
    reason: str,
    vehicle_rego: str = "",
    route: str = "",
) -> str:
    """Generate an incident snapshot card.

    Returns the URL path to the saved image.
    """
    bg = URGENCY_BG.get(urgency, COLORS["bg_orange"])
    img = create_card(800, 450, bg)
    draw_gradient_overlay(img, start_alpha=0, end_alpha=60)
    draw = ImageDraw.Draw(img)

    # Header with urgency badge
    y = 25
    font_title = _get_font(28, bold=True)
    draw.text((40, y), "Incident Report", fill=COLORS["white"], font=font_title)

    # Urgency badge
    badge_text = f"{urgency.upper()} URGENCY"
    badge_color = URGENCY_COLORS.get(urgency, COLORS["orange"])
    draw_badge(draw, 620, y + 5, badge_text, badge_color)
    y += 40

    # Timestamp
    font_sub = _get_font(14)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    draw.text((40, y), now, fill=COLORS["white_60"], font=font_sub)
    y += 28

    y = draw_divider(draw, y)

    # Driver info row
    font_label = _get_font(13)
    font_value = _get_font(16, bold=True)

    draw.text((40, y), "DRIVER", fill=COLORS["white_60"], font=font_label)
    draw.text((40, y + 18), driver_name, fill=COLORS["white"], font=font_value)

    if vehicle_rego:
        draw.text((250, y), "VEHICLE", fill=COLORS["white_60"], font=font_label)
        draw.text((250, y + 18), vehicle_rego, fill=COLORS["white"], font=font_value)

    draw.text((450, y), "DRIVER ID", fill=COLORS["white_60"], font=font_label)
    draw.text((450, y + 18), driver_id, fill=COLORS["white"], font=font_value)
    y += 50

    if route:
        draw.text((40, y), "ROUTE", fill=COLORS["white_60"], font=font_label)
        draw.text((40, y + 18), route, fill=COLORS["white"], font=font_value)
        y += 48

    y = draw_divider(draw, y + 5)

    # Trigger details
    draw.text((40, y), "TRIGGER", fill=COLORS["white_60"], font=font_label)
    y += 18

    trigger_display = trigger_type.replace("_", " ").title()
    draw.text((40, y), trigger_display, fill=COLORS["yellow"], font=font_value)

    # Sub-details
    details = []
    if trigger_data.get("fatigue_event_type"):
        details.append(f"Event: {trigger_data['fatigue_event_type'].replace('_', ' ').title()}")
    if trigger_data.get("severity"):
        details.append(f"Severity: {trigger_data['severity'].upper()}")
    if trigger_data.get("erratic_sub_type"):
        details.append(f"Type: {trigger_data['erratic_sub_type'].replace('_', ' ').title()}")
    if trigger_data.get("g_force"):
        details.append(f"G-force: {trigger_data['g_force']}g")

    if details:
        x = 40
        y += 28
        for detail in details:
            w = draw_badge(draw, x, y, detail, (0, 0, 0, 100))
            x += w + 8
        y += 38
    else:
        y += 30

    y = draw_divider(draw, y + 5)

    # Reason / Betty's assessment
    draw.text((40, y), "BETTY'S ASSESSMENT", fill=COLORS["white_60"], font=font_label)
    y += 20

    font_reason = _get_font(15)
    y = draw_text_wrapped(draw, 40, y, reason, font_reason,
                          COLORS["white"], max_width=720)

    # Footer
    font_footer = _get_font(11)
    draw.text((40, 425), "Betty AI Companion • Fleet Manager Alert",
              fill=COLORS["white_60"], font=font_footer)
    draw.text((550, 425), "ESCALATED TO FLEET MANAGER",
              fill=COLORS["red"], font=font_footer)

    return save_card(img, driver_id, "incident")
