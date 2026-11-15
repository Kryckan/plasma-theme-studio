# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The names of the own artwork values (the Frames block of the Plasma Style page).

`labels.py` imports this module last, so that its tables hold these entries too."""

from ..messages import translate
from . import labels

labels.SECTION_TITLES["artwork"] = translate("fields", "Own artwork")
labels.SECTION_ICONS["artwork"] = labels.SECTION_ICONS.get("panel", "preferences-desktop-theme")
labels.FIELD_LABELS.update(
    {
        ("artwork", "panel"): translate("fields", "Panel picture"),
        ("artwork", "popups"): translate("fields", "Popups picture"),
        ("artwork", "tooltips"): translate("fields", "Tooltips picture"),
        ("artwork", "widgets"): translate("fields", "Widget backgrounds picture"),
    }
)
