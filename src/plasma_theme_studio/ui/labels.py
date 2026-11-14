# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The names shown for theme sections and fields."""

from ..messages import translate
from ..model.parts import BORDER_SIZES

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
    "desktop": translate("fields", "Icons, pointers and sounds"),
    "fonts": translate("fields", "Fonts"),
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
    "desktop": "preferences-desktop-icons",
    "fonts": "preferences-desktop-font",
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
    ("colors", "accent_from_wallpaper"): translate("fields", "Accent color from the wallpaper"),
    ("colors", "window"): translate("fields", "Window background"),
    ("colors", "view"): translate("fields", "View background"),
    ("colors", "button"): translate("fields", "Button background"),
    ("colors", "header"): translate("fields", "Header and title bar"),
    ("colors", "scheme_id"): translate("fields", "Installed color scheme"),
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
    ("apps", "style_id"): translate("fields", "Installed application style"),
    ("apps", "radius"): translate("fields", "Corner radius"),
    ("apps", "border_width"): translate("fields", "Border width"),
    ("window", "decoration"): translate("fields", "Window frame"),
    ("window", "radius"): translate("fields", "Corner radius"),
    ("window", "border_width"): translate("fields", "Border width"),
    ("window", "decoration_id"): translate("fields", "Installed window decoration"),
    ("window", "border_size"): translate("fields", "Border size"),
    ("window", "buttons_left"): translate("fields", "Title bar buttons on the left"),
    ("window", "buttons_right"): translate("fields", "Title bar buttons on the right"),
    ("shadow", "size"): translate("fields", "Size"),
    ("shadow", "strength"): translate("fields", "Strength"),
    ("panel", "style"): translate("fields", "Panel background"),
    ("panel", "style_id"): translate("fields", "Installed Plasma style"),
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
    ("desktop", "icons"): translate("fields", "Icons"),
    ("desktop", "cursors"): translate("fields", "Pointers"),
    ("desktop", "cursor_size"): translate("fields", "Pointer size"),
    ("desktop", "dark_at_night"): translate("fields", "Switch to Dark Mode at Night"),
    ("desktop", "splash"): translate("fields", "Splash screen"),
    ("desktop", "sounds"): translate("fields", "System sounds"),
    ("fonts", "general"): translate("fields", "General font"),
    ("fonts", "fixed"): translate("fields", "Fixed width font"),
    ("fonts", "small"): translate("fields", "Small font"),
    ("fonts", "toolbar"): translate("fields", "Toolbar font"),
    ("fonts", "menu"): translate("fields", "Menu font"),
    ("fonts", "window_title"): translate("fields", "Window title font"),
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
        "breeze": translate("fields", "Breeze with your changes"),
        "generated": translate("fields", "Made from this theme"),
        "installed": translate("fields", "An installed one"),
    },
    ("apps", "style"): {
        "unchanged": translate("fields", "Leave as it is"),
        "generated": translate("fields", "Made from this theme"),
        "installed": translate("fields", "An installed one"),
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
        "installed": translate("fields", "An installed one"),
    },
    ("colors", "accent_from_wallpaper"): {
        True: translate("fields", "Yes"),
        False: translate("fields", "No"),
    },
    ("window", "border_size"): dict(BORDER_SIZES),
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
