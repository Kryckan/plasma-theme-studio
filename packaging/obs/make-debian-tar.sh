#!/bin/sh
# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Packs packaging/obs/debian into debian.tar.xz, the form in which the Open
# Build Service takes the debian/ folder next to the source tarball.
#   packaging/obs/make-debian-tar.sh [OUTPUT_DIR]
set -eu
here=$(dirname "$(readlink -f "$0")")
out=${1:-.}
# Fixed owner, order and time so that the same files give the same archive.
tar --sort=name --owner=0 --group=0 --numeric-owner --mtime='2026-01-01 00:00:00 UTC' \
    -C "$here" -cJf "$out/debian.tar.xz" debian
echo "wrote $out/debian.tar.xz"
