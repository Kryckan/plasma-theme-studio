# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The names shown for theme sections and fields."""

from ..messages import translate

SECTION_TITLES = {
    "meta": translate("fields", "Theme"),
    "colors": translate("fields", "Colors"),
    "shape": translate("fields", "Shapes"),
    "shadow": translate("fields", "Shadows"),
    "panel": translate("fields", "Panel"),
}

SECTION_ICONS = {
    "meta": "document-properties",
    "colors": "preferences-desktop-color",
    "shape": "draw-rectangle",
    "shadow": "blurfx",
    "panel": "preferences-desktop-plasma",
}

# Sections that no target reads yet. They are stored in the theme file and
# shown in the preview.
PREVIEW_ONLY_SECTIONS = ("shape", "shadow", "panel")

FIELD_LABELS = {
    ("meta", "name"): translate("fields", "Name"),
    ("meta", "author"): translate("fields", "Author"),
    ("colors", "accent"): translate("fields", "Accent"),
    ("colors", "window"): translate("fields", "Window background"),
    ("colors", "view"): translate("fields", "View background"),
    ("colors", "button"): translate("fields", "Button background"),
    ("colors", "header"): translate("fields", "Header and title bar"),
    ("colors", "text"): translate("fields", "Text"),
    ("colors", "text_muted"): translate("fields", "Secondary text"),
    ("colors", "link"): translate("fields", "Link"),
    ("colors", "visited"): translate("fields", "Visited link"),
    ("colors", "negative"): translate("fields", "Negative"),
    ("colors", "neutral"): translate("fields", "Neutral"),
    ("colors", "positive"): translate("fields", "Positive"),
    ("shape", "radius"): translate("fields", "Corner radius"),
    ("shape", "border_width"): translate("fields", "Border width"),
    ("shadow", "size"): translate("fields", "Size"),
    ("shadow", "strength"): translate("fields", "Strength"),
    ("panel", "opacity"): translate("fields", "Opacity"),
}

PRESET_TITLES = {
    "breeze-light": translate("fields", "Breeze Light"),
    "breeze-dark": translate("fields", "Breeze Dark"),
}
