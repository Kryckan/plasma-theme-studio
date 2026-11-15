# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The names of the values of the window frame extras, Icons and Toolbars and Launch Feedback.

`labels.py` imports this module last, so that its tables hold these entries too."""

from ..messages import translate
from . import labels

YES_NO = {True: translate("fields", "Yes"), False: translate("fields", "No")}

TOOLBAR_STYLE_NAMES = {
    "NoText": translate("fields", "None"),
    "TextOnly": translate("fields", "Text only"),
    "TextBesideIcon": translate("fields", "Beside icons"),
    "TextUnderIcon": translate("fields", "Below icon"),
}
FEEDBACK_NAMES = {
    "none": translate("fields", "None"),
    "static": translate("fields", "Static"),
    "blinking": translate("fields", "Blinking"),
    "bouncing": translate("fields", "Bouncing"),
}

labels.SECTION_TITLES["toolbars"] = translate("fields", "Icons and toolbars")
labels.SECTION_TITLES["feedback"] = translate("fields", "Launch feedback")
labels.SECTION_ICONS["toolbars"] = "configure-toolbars"
labels.SECTION_ICONS["feedback"] = "preferences-desktop-notification"

labels.FIELD_LABELS.update(
    {
        ("window", "title_height"): translate("fields", "Title bar height"),
        ("window", "button_size"): translate("fields", "Button size"),
        ("window", "button_spacing"): translate("fields", "Space between buttons"),
        ("shadow", "offset_x"): translate("fields", "Shadow offset sideways"),
        ("shadow", "offset_y"): translate("fields", "Shadow offset downwards"),
        ("toolbars", "main_style"): translate("fields", "Main toolbar label"),
        ("toolbars", "other_style"): translate("fields", "Secondary toolbar label"),
        ("toolbars", "icons_on_buttons"): translate("fields", "Icons on buttons"),
        ("toolbars", "icons_in_menus"): translate("fields", "Icons in menus"),
        ("feedback", "cursor"): translate("fields", "Cursor feedback"),
        ("feedback", "cursor_timeout"): translate("fields", "Stop cursor feedback after"),
        ("feedback", "taskbar"): translate("fields", "Task Manager feedback"),
        ("feedback", "taskbar_timeout"): translate("fields", "Stop Task Manager feedback after"),
    }
)
labels.CHOICE_LABELS.update(
    {
        ("toolbars", "main_style"): TOOLBAR_STYLE_NAMES,
        ("toolbars", "other_style"): TOOLBAR_STYLE_NAMES,
        ("toolbars", "icons_on_buttons"): YES_NO,
        ("toolbars", "icons_in_menus"): YES_NO,
        ("feedback", "cursor"): FEEDBACK_NAMES,
        ("feedback", "taskbar"): YES_NO,
    }
)
