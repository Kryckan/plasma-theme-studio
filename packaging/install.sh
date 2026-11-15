#!/bin/sh
# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Installs Plasma Theme Studio into a staging root. Every package recipe
# (Arch, RPM, Debian) calls this one script, so they all install the same files.
#
#   packaging/install.sh DESTDIR [PREFIX]
#
# DESTDIR is the staging root ($pkgdir, %{buildroot}, debian/plasma-theme-studio).
# PREFIX defaults to /usr. LRELEASE names the Qt translation compiler; without
# it the script looks for the usual names. The license text is not installed
# here: each distribution has its own place for it.
set -eu

[ $# -ge 1 ] || { echo "usage: $0 DESTDIR [PREFIX]" >&2; exit 2; }
dest=$1
prefix=${2:-/usr}
root=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
id=io.github.kryckan.PlasmaThemeStudio
app="$dest$prefix/share/plasma-theme-studio"

find_lrelease() {
    if [ -n "${LRELEASE:-}" ]; then echo "$LRELEASE"; return; fi
    for tool in lrelease6 lrelease-qt6 /usr/lib/qt6/bin/lrelease /usr/lib64/qt6/bin/lrelease \
        /usr/lib/qt6/libexec/lrelease /usr/lib/x86_64-linux-gnu/qt6/bin/lrelease lrelease; do
        if command -v "$tool" >/dev/null 2>&1; then command -v "$tool"; return; fi
    done
    echo "lrelease (Qt 6 translation compiler) not found; set LRELEASE" >&2
    return 1
}
lrelease=$(find_lrelease)

# The program: a copy of the package, with compiled translations and no sources of them.
install -d "$app"
cp -r "$root/src/plasma_theme_studio" "$app/"
find "$app" -name '__pycache__' -type d -prune -exec rm -r {} +
for ts in "$app"/plasma_theme_studio/i18n/*.ts; do
    "$lrelease" -silent "$ts" -qm "${ts%.ts}.qm"
    rm -f "$ts"
done
python3 -m compileall -q -s "$dest" -p / "$app"

# The launcher.
install -d "$dest$prefix/bin"
sed "s|/usr/share/plasma-theme-studio|$prefix/share/plasma-theme-studio|" "$root/packaging/launcher.sh" \
    > "$dest$prefix/bin/plasma-theme-studio"
chmod 755 "$dest$prefix/bin/plasma-theme-studio"

# Desktop file, AppStream data and icons.
install -Dm644 "$root/data/$id.desktop" "$dest$prefix/share/applications/$id.desktop"
install -Dm644 "$root/data/$id.metainfo.xml" "$dest$prefix/share/metainfo/$id.metainfo.xml"
install -d "$dest$prefix/share/icons"
cp -r "$root/data/icons/hicolor" "$dest$prefix/share/icons/"
