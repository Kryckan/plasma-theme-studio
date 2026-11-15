# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Export a theme as a KDE Global Theme that works without Plasma Theme Studio.

The bundle is a folder with a `share/` tree that mirrors the data home
(`~/.local/share`) and two small shell scripts. The Global Theme package is
only a list of settings, so the color scheme, the window frame and the Plasma
style it names are installed next to it. The files are the ones the app's own
generators plan, so an exported theme looks the same as an applied one.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from . import generators, paths
from .generators import plasmastyle
from .generators.base import MARKER
from .messages import translate
from .model.theme import Theme, write_atomic

PACKAGE_PREFIX = "io.github.kryckan.plasmathemestudio."
PACKAGE_DIR = "plasma/look-and-feel"
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PREVIEW_SIZE = (760, 520)


class ExportError(Exception):
    """A theme that cannot be exported. `message` says why."""

    def __init__(self, message):
        self.message = message
        super().__init__(str(message))


def package_id(theme: Theme) -> str:
    slug = theme.slug.lower()
    if not slug:
        raise ExportError(translate("core", "The theme needs a name that contains letters or digits."))
    if theme.has_both and theme.shown_variant != theme.main_variant:
        slug += f".{theme.shown_variant}"  # the second variant of a theme is a package of its own
    return PACKAGE_PREFIX + slug


def _under_data_home(planned) -> Path:
    """Where a planned file goes below `share/`."""
    try:
        relative = planned.path.relative_to(paths.data_home())
    except ValueError:
        raise ExportError(
            translate("core", "Cannot export {path}: it is outside the data folder.").format(
                path=str(planned.path)
            )
        ) from None
    if ".." in relative.parts or not relative.parts:
        raise ExportError(translate("core", "Cannot export {path}.").format(path=str(planned.path)))
    return relative


def _folder_below(files: dict[Path, str], *prefix: str) -> str | None:
    """The name of the one folder the files use below `prefix`, or None."""
    for relative in files:
        if relative.parts[: len(prefix)] == prefix and len(relative.parts) > len(prefix) + 1:
            name = relative.parts[len(prefix)]
            if not SAFE_NAME.match(name):
                raise ExportError(translate("core", "Cannot export {path}.").format(path=str(relative)))
            return name
    return None


def _plan(theme: Theme) -> dict[Path, str]:
    """The files of the theme's parts, by path below the data home."""
    own = theme.copy()
    own.set("colors", "scheme_id", None)  # a package carries its own scheme, not a link to an installed one
    planned = list(generators.ColorSchemeGenerator().files(own))
    if theme.get("window", "decoration") == "generated":
        planned += generators.WindowFrameGenerator().files(theme)
    style = generators.PlasmaStyleGenerator()
    if style.wanted(theme):
        planned += style.files(theme)
    return {_under_data_home(file): file.content for file in planned}


def _defaults(theme: Theme, files: dict[Path, str]) -> str:
    scheme = next((p.stem for p in files if p.parts[:1] == ("color-schemes",)), None)
    lines = [MARKER, ""]
    if scheme:
        lines += ["[kdeglobals][General]", f"ColorScheme={scheme}", ""]
    style = _folder_below(files, "plasma", "desktoptheme")
    if style:
        lines += ["[plasmarc][Theme]", f"name={style}", ""]
    mode = theme.get("window", "decoration")
    if mode == "generated":
        frame = _folder_below(files, "aurorae", "themes")
        if frame:
            lines += [
                "[kwinrc][org.kde.kdecoration2]",
                f"library={generators.windowframe.AURORAE_LIBRARY}",
                f"theme={generators.windowframe.AURORAE_THEME_PREFIX}{frame}",
                "",
            ]
    elif mode == "breeze":
        lines += [
            "[kwinrc][org.kde.kdecoration2]",
            f"library={generators.windowframe.BREEZE_LIBRARY}",
            f"theme={generators.windowframe.BREEZE_THEME}",
            "",
        ]
    # Applying a package always writes the splash screen setting and this one has no splash,
    # so it names the one that means "no splash screen" instead of a broken one. The export
    # message and the docs say that applying the package turns the splash screen off.
    lines += ["[ksplashrc][KSplash]", "Theme=None", ""]
    return "\n".join(lines)


def _metadata(theme: Theme, pid: str) -> str:
    author = str(theme.get("meta", "author")).strip() or "Plasma Theme Studio"
    data = {
        "X-Generated-By": "Plasma Theme Studio",  # first key: the marker that made_here() looks for
        "KPackageStructure": "Plasma/LookAndFeel",
        "KPlugin": {
            "Authors": [{"Name": author}],
            "Description": str(
                translate("core", "{name}, made with Plasma Theme Studio").format(name=theme.name)
            ),
            "Id": pid,
            "License": "GPL-3.0-or-later",
            "Name": theme.scheme_title,
            "Version": "1.0",
        },
        "X-Plasma-APIVersion": "2",
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _preview(theme: Theme) -> bytes | None:
    """The theme's drawn preview as a PNG, or None when there is no Qt application to draw with."""
    try:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtWidgets import QApplication

        from .ui.preview import PreviewWidget
    except ImportError:
        return None
    if QApplication.instance() is None:
        return None
    widget = PreviewWidget(theme)
    widget.resize(*PREVIEW_SIZE)
    image = widget.grab().toImage()
    widget.deleteLater()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    ok = image.save(buffer, "PNG")
    buffer.close()
    return bytes(data.data()) if ok else None


def _quote(path: Path) -> str:
    return shlex.quote(path.as_posix())


def _directories(files: list[Path]) -> list[Path]:
    """The folders the install made or used, deepest first. Uninstall removes the ones
    that are empty by then; a folder with anything else in it stays."""
    found = {parent for relative in files for parent in relative.parents if parent.parts}
    return sorted(found, key=lambda p: (-len(p.parts), p.as_posix()))


# The marker test of the scripts: the first bytes of a file this app made carry one of these.
_IS_OURS = (
    "is_ours() {\n"
    "    head -c 300 -- \"$1\" 2>/dev/null | grep -aqF -e 'Generated by Plasma Theme Studio' \\\n"
    '        -e \'"X-Generated-By": "Plasma Theme Studio"\'\n'
    "}\n"
    "# A file that is ours: not a link, and marked. `$2` names the file that carries the mark\n"
    "# when `$1` cannot (a picture).\n"
    "owned() {\n"
    '    [ ! -L "$1" ] && [ -f "$1" ] && is_ours "${2:-$1}"\n'
    "}\n"
)


def _guard(relative: Path, package: Path) -> str:
    """The file that vouches for `relative`: the package's metadata for what cannot be marked."""
    if relative.suffix == ".png":
        return f' "$dest"/{_quote(package / "metadata.json")}'
    return ""


def _install_script(pid: str, files: list[Path]) -> str:
    package = Path(PACKAGE_DIR) / pid
    checks = "\n".join(
        f'path="$dest"/{_quote(f)}\n'
        f'if {{ [ -e "$path" ] || [ -L "$path" ]; }} && ! owned "$path"{_guard(f, package)}; then\n'
        '    echo "$skipped $path" >&2\n'
        "    clash=1\n"
        "fi"
        for f in files
    )
    copies = "\n".join(
        f'mkdir -p -- "$dest"/{_quote(f.parent)}\ncp -- "$here/share"/{_quote(f)} "$dest"/{_quote(f)}'
        for f in files
    )
    done = translate("core", "Installed. Apply it with: plasma-apply-lookandfeel -a {id}").format(id=pid)
    skipped = translate("core", "Nothing was installed. This file is not from Plasma Theme Studio:")
    purpose = translate("core", "Installs this Global Theme for the current user.")
    return (
        "#!/bin/sh\n"
        f"# {purpose}\n"
        "set -eu\n"
        'here=$(cd "$(dirname "$0")" && pwd)\n'
        'dest="${XDG_DATA_HOME:-$HOME/.local/share}"\n'
        f"{_IS_OURS}"
        f"skipped={shlex.quote(str(skipped))}\n"
        "clash=0\n"
        f"{checks}\n"
        '[ "$clash" = 0 ] || exit 1\n'
        f"{copies}\n"
        f"echo {shlex.quote(str(done))}\n"
    )


def _uninstall_script(pid: str, files: list[Path]) -> str:
    package = Path(PACKAGE_DIR) / pid
    # The package's metadata goes last: it vouches for the picture.
    ordered = sorted(files, key=lambda f: (f == package / "metadata.json", f.as_posix()))
    removes = "\n".join(
        f'path="$dest"/{_quote(f)}\n'
        f'if owned "$path"{_guard(f, package)}; then rm -f -- "$path"; '
        'elif [ -e "$path" ] || [ -L "$path" ]; then echo "$kept $path" >&2; fi'
        for f in ordered
    )
    folders = "\n".join(f'rmdir -- "$dest"/{_quote(d)} 2>/dev/null || true' for d in _directories(files))
    done = translate("core", "Removed the files of {id}.").format(id=pid)
    kept = translate("core", "Kept, because it is not from Plasma Theme Studio:")
    purpose = translate("core", "Removes what install.sh installed, and nothing else.")
    return (
        "#!/bin/sh\n"
        f"# {purpose}\n"
        "set -eu\n"
        'dest="${XDG_DATA_HOME:-$HOME/.local/share}"\n'
        f"{_IS_OURS}"
        f"kept={shlex.quote(str(kept))}\n"
        f"{removes}\n"
        f"{folders}\n"
        f"echo {shlex.quote(str(done))}\n"
    )


def export_global_theme(theme: Theme, folder: Path) -> list[Path]:
    """Write the bundle into `folder` (new or empty) and return the files written."""
    pid = package_id(theme)
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise ExportError(
            translate("core", "{path} already exists and is not empty.").format(path=str(folder))
        )
    plasmastyle.vet_artwork(theme)  # an own picture the draw child cannot draw is not put in the package
    files = _plan(theme)
    package = Path(PACKAGE_DIR) / pid
    colors = next((text for rel, text in files.items() if rel.parts[:1] == ("color-schemes",)), "")
    files[package / "metadata.json"] = _metadata(theme, pid)
    files[package / "contents/defaults"] = _defaults(theme, files)
    files[package / "contents/colors"] = colors
    contents: dict[Path, str | bytes] = dict(files)
    preview = _preview(theme)
    if preview is not None:
        contents[package / "contents/previews/preview.png"] = preview
    installed = sorted(contents)

    root = folder.resolve()
    written: list[Path] = []
    for relative, data in [(Path("share") / p, c) for p, c in contents.items()] + [
        (Path("install.sh"), _install_script(pid, installed)),
        (Path("uninstall.sh"), _uninstall_script(pid, installed)),
    ]:
        target = root / relative
        if root not in target.resolve().parents:
            raise ExportError(translate("core", "Cannot export {path}.").format(path=str(relative)))
        write_atomic(target, data)
        if relative.suffix == ".sh":
            target.chmod(0o755)
        written.append(folder / relative)
    return sorted(written)
