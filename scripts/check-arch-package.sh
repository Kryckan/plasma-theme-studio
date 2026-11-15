#!/bin/bash
# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Builds both Arch packages from the files of the working tree, committed or
# not (they are copied into a throwaway repository: the release package is
# built from a "git archive" of it, the -git one from a clone), lists their files, unpacks the release package and runs its
# launcher: --help and validate, in an empty home, without a display.
#
#   scripts/check-arch-package.sh [WORKDIR]
#
# Needs makepkg (not as root), git, qt6-tools and, to run the launcher, pyside6
# and python-jinja. Nothing is installed and the real home is not touched.
# Dependencies are not checked (makepkg --nodeps): the CI job installs them.
set -eu
root=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
work=${1:-$(mktemp -d /tmp/pts-arch-package.XXXXXX)}
mkdir -p "$work/git" "$work/release" "$work/home"
version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$root/src/plasma_theme_studio/__init__.py")

# The -git package: its source is a clone of this repository instead of GitHub.
mkdir -p "$work/tree"
git -C "$root" ls-files -z --cached --others --exclude-standard | while IFS= read -r -d '' f; do
    [ -f "$root/$f" ] && { mkdir -p "$work/tree/$(dirname "$f")"; cp -p "$root/$f" "$work/tree/$f"; }
done
git -C "$work/tree" init -q
git -C "$work/tree" add -A
git -C "$work/tree" -c user.name=ci -c user.email=ci@example.invalid commit -q -m "working tree"
git clone -q "$work/tree" "$work/clone"
sed "s|^source=.*|source=(\"\$pkgname::git+file://$work/clone\")|" "$root/packaging/arch/git/PKGBUILD" \
    > "$work/git/PKGBUILD"
# The release package: its source is the tag archive; here an archive of HEAD.
git -C "$work/tree" archive --prefix="plasma-theme-studio-$version/" -o "$work/release/plasma-theme-studio-$version.tar.gz" HEAD
sed "s|^source=.*|source=(\"\$pkgname-\$pkgver.tar.gz\")|" "$root/packaging/arch/release/PKGBUILD" \
    > "$work/release/PKGBUILD"

for kind in git release; do
    (cd "$work/$kind" && makepkg -f --nodeps --noconfirm 2>&1 | tail -3)
done
for pkg in "$work"/git/*.pkg.tar.zst "$work"/release/*.pkg.tar.zst; do
    echo "== $pkg"
    tar -tf "$pkg" | grep -v '/$' | grep -v '__pycache__' | grep -v '\.py$'
done

unpacked="$work/unpacked"
mkdir -p "$unpacked"
tar -xf "$work"/release/*.pkg.tar.zst -C "$unpacked"
app="$unpacked/usr/share/plasma-theme-studio"
env -i PATH=/usr/bin:/bin HOME="$work/home" XDG_CONFIG_HOME="$work/home/.config" \
    XDG_DATA_HOME="$work/home/.local/share" XDG_CACHE_HOME="$work/home/.cache" \
    QT_QPA_PLATFORM=offscreen KDE_DEBUG=1 PYTHONPATH="$app" LANG=C \
    /usr/bin/python3 -c "
from pathlib import Path
from plasma_theme_studio.model.theme import Theme
Theme().save(Path('$work/theme.toml'))"
run() {
    env -i PATH=/usr/bin:/bin HOME="$work/home" XDG_CONFIG_HOME="$work/home/.config" \
        XDG_DATA_HOME="$work/home/.local/share" XDG_CACHE_HOME="$work/home/.cache" \
        QT_QPA_PLATFORM=offscreen KDE_DEBUG=1 PYTHONPATH="$app" LANG=C \
        "$unpacked/usr/bin/plasma-theme-studio" "$@"
}
run --help | head -3
run validate "$work/theme.toml"
if run validate /nonexistent.toml 2>/dev/null; then
    echo "validate accepted a missing file" >&2
    exit 1
fi
echo "arch package ok: $work"
