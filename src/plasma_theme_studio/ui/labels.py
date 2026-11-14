# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The names shown for theme sections and fields."""

from ..messages import translate

SECTION_TITLES = {
    "meta": translate("fields", "Theme"),
    "colors": translate("fields", "Colors"),
    "shape": translate("fields", "Shapes"),
    "apps": translate("fields", "Applications"),
    "window": translate("fields", "Windows"),
    "shadow": translate("fields", "Shadows"),
    "panel": translate("fields", "Panel"),
    "popup": translate("fields", "Popups and tooltips"),
    "panel_layout": translate("fields", "Panel position"),
    "gtk": translate("fields", "GTK applications"),
    "rofi": translate("fields", "Rofi"),
}

SECTION_ICONS = {
    "meta": "document-properties",
    "colors": "preferences-desktop-color",
    "shape": "draw-rectangle",
    "apps": "preferences-desktop-theme-applications",
    "window": "window",
    "shadow": "blurfx",
    "panel": "preferences-desktop-plasma",
    "popup": "preferences-desktop-notification-bell",
    "panel_layout": "align-vertical-bottom",
    "gtk": "preferences-gtk-config",
    "rofi": "system-run",
}

# What a page says about its values whatever the targets are. No target reads the
# Shapes page: its values are what the pages of the parts follow until they are set.
SECTION_NOTES = {
    "shape": translate(
        "fields",
        "These values are the starting point for Applications, Windows, Panel, Popups and tooltips, "
        "GTK applications and Rofi: each follows them until it gets values of its own. They reach "
        "the desktop through those pages, for every part that is not left as it is.",
    ),
}

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
    ("apps", "style"): translate("fields", "Application style"),
    ("apps", "radius"): translate("fields", "Corner radius"),
    ("apps", "border_width"): translate("fields", "Border width"),
    ("window", "decoration"): translate("fields", "Window frame"),
    ("window", "radius"): translate("fields", "Corner radius"),
    ("window", "border_width"): translate("fields", "Border width"),
    ("shadow", "size"): translate("fields", "Size"),
    ("shadow", "strength"): translate("fields", "Strength"),
    ("panel", "style"): translate("fields", "Panel background"),
    ("panel", "radius"): translate("fields", "Corner radius"),
    ("panel", "border_width"): translate("fields", "Border width"),
    ("panel", "opacity"): translate("fields", "Opacity"),
    ("popup", "radius"): translate("fields", "Corner radius"),
    ("popup", "border_width"): translate("fields", "Border width"),
    ("popup", "opacity"): translate("fields", "Opacity"),
    ("gtk", "style"): translate("fields", "GTK style"),
    ("gtk", "radius"): translate("fields", "Corner radius"),
    ("gtk", "border_width"): translate("fields", "Border width"),
    ("gtk", "window_radius"): translate("fields", "Window corner radius"),
    ("rofi", "style"): translate("fields", "Rofi theme"),
    ("rofi", "radius"): translate("fields", "Corner radius"),
    ("rofi", "border_width"): translate("fields", "Border width"),
    ("rofi", "opacity"): translate("fields", "Opacity"),
    ("rofi", "font"): translate("fields", "Font"),
    ("panel_layout", "location"): translate("fields", "Screen edge"),
    ("panel_layout", "height"): translate("fields", "Thickness"),
    ("panel_layout", "alignment"): translate("fields", "Alignment"),
    ("panel_layout", "length_mode"): translate("fields", "Length"),
    ("panel_layout", "floating"): translate("fields", "Floating"),
    ("panel_layout", "visibility"): translate("fields", "Visibility"),
    ("panel_layout", "opacity_mode"): translate("fields", "Opacity"),
}

# The names of the values a field offers.
CHOICE_LABELS = {
    ("window", "decoration"): {
        "unchanged": translate("fields", "Leave as it is"),
        "breeze": translate("fields", "Breeze, adjusted"),
        "generated": translate("fields", "Made from this theme"),
    },
    ("apps", "style"): {
        "unchanged": translate("fields", "Leave as it is"),
        "generated": translate("fields", "Made from this theme"),
    },
    ("gtk", "style"): {
        "unchanged": translate("fields", "Leave as it is"),
        "generated": translate("fields", "Made from this theme"),
    },
    ("rofi", "style"): {
        "unchanged": translate("fields", "Leave as it is"),
        "generated": translate("fields", "Made from this theme"),
    },
    ("panel", "style"): {
        "unchanged": translate("fields", "Leave as it is"),
        "generated": translate("fields", "Made from this theme"),
    },
    ("panel_layout", "location"): {
        "top": translate("fields", "Top"),
        "bottom": translate("fields", "Bottom"),
        "left": translate("fields", "Left"),
        "right": translate("fields", "Right"),
    },
    ("panel_layout", "alignment"): {
        "left": translate("fields", "Left or top"),
        "center": translate("fields", "Center"),
        "right": translate("fields", "Right or bottom"),
    },
    ("panel_layout", "length_mode"): {
        "fill": translate("fields", "Fill the whole edge"),
        "fit": translate("fields", "Fit the content"),
    },
    ("panel_layout", "floating"): {
        True: translate("fields", "Yes"),
        False: translate("fields", "No"),
    },
    ("panel_layout", "visibility"): {
        "none": translate("fields", "Always visible"),
        "autohide": translate("fields", "Auto hide"),
        "dodgewindows": translate("fields", "Dodge windows"),
        "windowsgobelow": translate("fields", "Windows go below"),
    },
    ("panel_layout", "opacity_mode"): {
        "adaptive": translate("fields", "Adaptive"),
        "opaque": translate("fields", "Opaque"),
        "translucent": translate("fields", "Translucent"),
    },
}

PRESET_TITLES = {
    "breeze-light": translate("fields", "Breeze Light"),
    "breeze-dark": translate("fields", "Breeze Dark"),
}
