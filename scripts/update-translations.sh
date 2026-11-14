#!/bin/sh
# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Updates every translation file with the strings currently in the code.
# To start a new language, pass its code: scripts/update-translations.sh de
set -eu
cd "$(dirname "$(readlink -f "$0")")/../src/plasma_theme_studio"
lupdate=$(command -v pyside6-lupdate || command -v lupdate6 || command -v lupdate-qt6 || echo /usr/lib/qt6/bin/lupdate)
[ $# -gt 0 ] && files="i18n/plasma_theme_studio_$1.ts" || files=$(ls i18n/*.ts)
# shellcheck disable=SC2046,SC2086
"$lupdate" $(find . -name '*.py' | sort) -ts $files -source-language en_US -no-obsolete -locations none
