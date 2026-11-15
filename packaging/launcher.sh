#!/bin/sh
# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The installed launcher (/usr/bin/plasma-theme-studio). The program lives in
# /usr/share/plasma-theme-studio, outside Python's site-packages, so a Python
# upgrade does not break it. The system Python is used on purpose: the
# distribution's PySide6 is the one that loads the real KDE widget styles.
# packaging/install.sh puts the real prefix in when it is not /usr.
PYTHONPATH="/usr/share/plasma-theme-studio${PYTHONPATH:+:$PYTHONPATH}" exec /usr/bin/python3 -m plasma_theme_studio "$@"
