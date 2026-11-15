# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generates a Rofi theme (.rasi) from the theme and makes it Rofi's theme.

Rofi reads its theme files every time it starts, so there is nothing to reload.
Which theme it uses is the last `@theme` statement of ~/.config/rofi/config.rasi.
That file is the setting of this target: it is kept whole in the snapshot, and
an undo writes it back byte for byte.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .. import kconfig, paths
from ..apply import desktop
from ..messages import Msg, translate
from ..model.color import BLACK, WHITE, Color, contrast, readable_on
from ..model.theme import Theme, write_atomic
from .base import CSS_MARKER, ApplyError, Generator, PlannedFile

DEFAULT_FONT = "Noto Sans 10"
AA = 4.5  # WCAG contrast for text

OUR_TAG = "// plasma-theme-studio"
PREV_TAG = "// plasma-theme-studio previous: "
_STATEMENT = re.compile(r'@theme\s+"[^"\n]*"[ \t]*')
_PARSE_FAILURE = "Failed to parse"


def themes_dir() -> Path:
    return paths.config_home() / "rofi" / "themes"


def config_path() -> Path:
    return paths.config_home() / "rofi" / "config.rasi"


def theme_path(theme: Theme) -> Path:
    return themes_dir() / f"{theme.slug}.rasi"


def pango_font(kde_font: str | None, default: str = DEFAULT_FONT) -> str:
    """A KDE font setting ("Noto Sans,10,-1,5,400,...") as a Pango string
    ("Noto Sans 10"). Only the family and the point size are used."""
    if not kde_font:
        return default
    parts = kde_font.split(",")
    family = parts[0].replace('"', "").strip()
    if not family:
        return default
    try:
        size = float(parts[1])
    except (IndexError, ValueError):
        size = 10.0
    if size <= 0:
        size = 10.0
    return f"{family} {size:g}"


def desktop_font() -> str:
    """The desktop's general font, read from kdeglobals, as a Pango string."""
    value = kconfig.user_value("kdeglobals", ["General"], "font")
    if value is None:
        value = kconfig.default_value("kdeglobals", ["General"], "font")
    return pango_font(value)


def font_of(theme: Theme) -> str:
    """The font the Rofi theme names. Text that is empty counts as not set; then it is the general
    font the theme sets (the apply puts it on the desktop first), else the one the desktop has."""
    chosen = (theme.get("rofi", "font") or "").strip()
    if chosen:
        return chosen
    general = theme.get("fonts", "general")
    return pango_font(general) if general else desktop_font()


def _string(text: str) -> str:
    text = "".join(ch for ch in text if ch.isprintable())
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _comment(text: str) -> str:
    return "".join(ch for ch in text if ch.isprintable() and ch not in "*/")


def _hex(color: Color, alpha: float = 1.0) -> str:
    """#rrggbb, or #rrggbbaa when translucent."""
    return color.hex if alpha >= 0.999 else f"{color.hex}{int(alpha * 255 + 0.5):02x}"


def ensure_contrast(color: Color, backgrounds: list[Color], minimum: float = AA) -> Color:
    """Move `color` toward white or black, in steps of 1 percent, until it reaches
    `minimum` against every background. A color that already does is returned as it is."""

    def worst(candidate: Color) -> float:
        return min(contrast(candidate, background) for background in backgrounds)

    if worst(color) >= minimum:
        return color
    mean = sum(background.luminance for background in backgrounds) / len(backgrounds)
    target, other = (WHITE, BLACK) if mean < 0.18 else (BLACK, WHITE)
    for step in range(1, 101):
        candidate = color.mix(target, step / 100)
        if worst(candidate) >= minimum:
            return candidate
    if worst(other) > worst(target):  # backgrounds of middle brightness
        for step in range(1, 101):
            candidate = color.mix(other, step / 100)
            if worst(candidate) >= minimum:
                return candidate
        return other
    return target


def _look(theme: Theme) -> tuple[int, int, float]:
    return (
        int(theme.resolved("rofi", "radius")),
        int(theme.resolved("rofi", "border_width")),
        float(theme.get("rofi", "opacity")),
    )


def rasi_text(theme: Theme, font: str | None = None) -> str:
    """The complete Rofi theme for the theme's colors and shape."""
    radius, border_width, opacity = _look(theme)
    font = font_of(theme) if font is None else font
    window, view, button = theme.color("window"), theme.color("view"), theme.color("button")
    text, muted, accent = theme.color("text"), theme.color("text_muted"), theme.color("accent")
    negative, positive = theme.color("negative"), theme.color("positive")
    alt = view.mix(text, 0.06)  # alternate rows: a faint tint toward the text color
    # Text is moved to AA contrast on every background it is drawn on.
    text = ensure_contrast(text, [window, view, alt, button])
    muted = ensure_contrast(muted, [window, view])
    prompt = ensure_contrast(accent, [view])
    active = ensure_contrast(positive, [window, alt])
    urgent = ensure_contrast(negative, [window, alt])
    on_accent = ensure_contrast(readable_on(accent), [accent])
    on_negative = ensure_contrast(readable_on(negative), [negative])
    border = accent if border_width else window
    inner = max(0, radius - border_width) if radius else 0
    states = "\n".join(
        f"element {row}.{kind} {{ background-color: @{prefix}{kind}-background; "
        f"text-color: @{prefix}{kind}-foreground; }}"
        for row, prefix in (("normal", ""), ("selected", "selected-"), ("alternate", "alternate-"))
        for kind in ("normal", "urgent", "active")
    )
    return f"""{CSS_MARKER}
/* Theme: {_comment(theme.name)} */

* {{
    bg:        {_hex(window, opacity)};
    bg-view:   {_hex(view)};
    bg-button: {_hex(button)};
    bg-alt:    {_hex(alt)};
    fg:        {text.hex};
    fg-muted:  {muted.hex};
    accent:    {accent.hex};
    prompt-col: {prompt.hex};
    on-accent: {on_accent.hex};
    on-urgent: {on_negative.hex};
    urgent:    {urgent.hex};
    urgent-bg: {negative.hex};
    active:    {active.hex};
    border-col: {border.hex};

    background-color: transparent;
    text-color:       @fg;
    font:             {_string(font)};
    spacing:          8px;

    background:                  @bg;
    foreground:                  @fg;
    border-color:                @border-col;
    separatorcolor:              @fg-muted;
    normal-background:           transparent;
    normal-foreground:           @fg;
    alternate-normal-background: @bg-alt;
    alternate-normal-foreground: @fg;
    selected-normal-background:  @accent;
    selected-normal-foreground:  @on-accent;
    active-background:           transparent;
    active-foreground:           @active;
    alternate-active-background: @bg-alt;
    alternate-active-foreground: @active;
    selected-active-background:  @accent;
    selected-active-foreground:  @on-accent;
    urgent-background:           transparent;
    urgent-foreground:           @urgent;
    alternate-urgent-background: @bg-alt;
    alternate-urgent-foreground: @urgent;
    selected-urgent-background:  @urgent-bg;
    selected-urgent-foreground:  @on-urgent;
}}

window {{
    location:         center;
    anchor:           center;
    width:            640px;
    transparency:     "real";
    padding:          12px;
    border:           {border_width}px;
    border-color:     @border-col;
    border-radius:    {radius}px;
    background-color: @bg;
}}

mainbox {{
    spacing:  10px;
    padding:  0;
    border:   0;
    children: [ "inputbar", "message", "listview", "mode-switcher" ];
}}

inputbar {{
    spacing:          8px;
    padding:          8px 10px;
    border:           0;
    border-radius:    {inner}px;
    background-color: @bg-view;
    text-color:       @fg;
    children:         [ "prompt", "entry" ];
}}

prompt {{
    text-color: @prompt-col;
}}

textbox-prompt-colon {{
    str:        "";
    expand:     false;
}}

entry {{
    text-color:        @fg;
    placeholder:       "Search";
    placeholder-color: @fg-muted;
    cursor:            text;
}}

num-filtered-rows, num-rows, textbox-num-sep {{
    text-color: @fg-muted;
}}

case-indicator {{
    text-color: @fg-muted;
}}

message {{
    padding:          8px 10px;
    border:           0;
    border-radius:    {inner}px;
    background-color: @bg-view;
}}

textbox {{
    text-color:       @fg;
    background-color: transparent;
}}

listview {{
    lines:        8;
    columns:      1;
    fixed-height: false;
    scrollbar:    true;
    spacing:      2px;
    padding:      0;
    border:       0;
    background-color: transparent;
}}

scrollbar {{
    width:        4px;
    padding:      0;
    handle-width: 6px;
    handle-color: @fg-muted;
    border:       0;
    border-radius: {min(radius, 3)}px;
}}

element {{
    padding:       6px 8px;
    spacing:       10px;
    border:        0;
    border-radius: {inner}px;
    cursor:        pointer;
}}

{states}

element-icon {{
    size:             24px;
    background-color: transparent;
    text-color:       inherit;
}}

element-text {{
    background-color: transparent;
    text-color:       inherit;
    highlight:        bold underline;
    vertical-align:   0.5;
}}

mode-switcher {{
    spacing:          6px;
    background-color: transparent;
}}

button {{
    padding:          6px 10px;
    border-radius:    {inner}px;
    background-color: @bg-button;
    text-color:       @fg;
    cursor:           pointer;
}}

button selected {{
    background-color: @accent;
    text-color:       @on-accent;
}}
"""


def _code_mask(text: str) -> list[bool]:
    """True for every character that is Rasi code: not inside a comment or a string.
    An `@theme` in a block comment must not be taken for the real one."""
    mask = [True] * len(text)
    i, n = 0, len(text)
    while i < n:
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
        elif text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
        elif text[i] == '"':
            end = i + 1
            while end < n and text[end] not in '"\n':
                end += 2 if text[end] == "\\" else 1
            i = min(end + 1, n)
            continue
        else:
            i += 1
            continue
        for k in range(i, end):
            mask[k] = False
        i = end
    return mask


def theme_statements(text: str) -> list[re.Match]:
    """The real `@theme "..."` statements of a config.rasi, in order."""
    mask = _code_mask(text)
    return [m for m in _STATEMENT.finditer(text) if mask[m.start()]]


def _line_of(text: str, match: re.Match) -> tuple[int, int]:
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    return start, len(text) if end < 0 else end


def _our_line(text: str) -> re.Match | None:
    found = theme_statements(text)
    if found and text[found[-1].end() : _line_of(text, found[-1])[1]].strip() == OUR_TAG:
        return found[-1]
    return None


def restored_config(current: str, saved: str) -> str:
    """What config.rasi should hold after an undo, given its text now and the text captured
    before the apply (`desktop.ABSENT` for no file). A file that is still exactly what the
    apply wrote goes back as it was (a file the apply made is removed). One the user has
    changed since keeps the changes: only our @theme line goes, and the user's own line that
    it replaced is switched back on. Without a line of ours the file is left as it is."""
    if current == desktop.ABSENT:
        return current
    ours = _our_line(current)
    if ours is None:
        return current
    name = ours.group(0).split('"')[1]
    if current == set_theme_line("" if saved == desktop.ABSENT else saved, name):
        return saved
    start, end = _line_of(current, ours)
    lines = current[:start].splitlines(keepends=True)
    # The line above ours may be the user's own, kept as a comment.
    for index in range(len(lines) - 1, max(len(lines) - 3, -1), -1):
        if lines[index].startswith(PREV_TAG):
            lines[index] = lines[index][len(PREV_TAG) :]
            break
    rest = "".join(lines) + current[end + 1 :]
    return desktop.ABSENT if saved == desktop.ABSENT and not rest.strip() else rest


def effective_theme(text: str) -> tuple[str, bool] | None:
    """The theme the last statement names, and whether the line is ours."""
    found = theme_statements(text)
    if not found:
        return None
    last = found[-1]
    _start, end = _line_of(text, last)
    name = last.group(0).split('"')[1]
    return name, text[last.end() : end].strip() == OUR_TAG


def set_theme_line(text: str, name: str) -> str:
    """Make `@theme "name"` the theme Rofi uses, touching nothing else.

    Rofi uses the last @theme, so that statement is replaced where it stands; the
    user's own line stays above it as a comment. Without one, our line goes to the
    top: a block before an @theme is discarded by it, one after it stays."""
    ours = f'@theme "{name}" {OUR_TAG}'
    found = theme_statements(text)
    if not found:
        eol = "\r\n" if "\r\n" in text else "\n"
        return ours + eol + text
    last = found[-1]
    start, end = _line_of(text, last)
    raw = text[start:end]
    line = raw.rstrip("\r")
    eol = raw[len(line) :]
    before = text[start : last.start()]
    after = text[last.end() : end].rstrip("\r")
    if after.strip() == OUR_TAG:  # our own line from an earlier apply
        return text[: last.start()] + ours + eol + text[end:]
    lines = [PREV_TAG + line.strip()]
    if before.strip():
        lines.append(before.rstrip())
    lines.append(ours)
    if after.strip() and not after.strip().startswith("//"):
        lines.append(after.strip())
    return text[:start] + (eol + "\n").join(lines) + text[start + len(line) :]


class RofiGenerator(Generator):
    id = "rofi"
    title = translate("core", "Rofi")
    sections = ("rofi",)

    def wanted(self, theme: Theme) -> bool:
        return theme.get("rofi", "style") == "generated"

    def notes(self, theme: Theme) -> list[Msg]:
        if not self.wanted(theme):
            return [
                translate(
                    "core",
                    "Rofi keeps the theme it uses now. The Rofi values here only show in the preview.",
                )
            ]
        return [
            translate("core", "Rofi reads the theme when it starts. A window that is open keeps its look."),
            translate(
                "core",
                "The window mode of Rofi does not work on KWin, so the theme is not made for it.",
            ),
        ]

    def unavailable_reason(self, runner) -> Msg | None:
        if not runner.which("rofi"):
            return translate("core", "Rofi was not found. Install it to use a Rofi theme.")
        return None

    def files(self, theme: Theme) -> list[PlannedFile]:
        return [PlannedFile(theme_path(theme), rasi_text(theme), CSS_MARKER)]

    def check_output(self, file: PlannedFile) -> list[Msg]:
        problems = []
        if file.content.count("{") != file.content.count("}"):
            problems.append(translate("core", "The generated Rofi theme has unbalanced braces."))
        if any(line.lstrip().startswith("#") for line in file.content.splitlines()):
            problems.append(
                translate("core", "The generated Rofi theme has a comment that Rofi cannot read.")
            )
        return problems

    def problems(self, theme: Theme) -> list[Msg]:
        try:
            desktop.capture_file(config_path())
        except OSError as error:
            return [
                translate("core", "Rofi's configuration cannot be read: {detail}").format(detail=str(error))
            ]
        return []

    def _parse_error(self, runner, path: Path) -> Msg | None:
        """What Rofi says about a theme file, asked without opening a window."""
        result = runner.run(["rofi", "-no-config", "-theme", str(path), "-dump-theme"])
        if _PARSE_FAILURE in result.stderr:
            line = next((ln for ln in result.stderr.splitlines() if _PARSE_FAILURE in ln), "")
            return translate("core", "Rofi cannot read the generated theme. {detail}").format(
                detail=line[:200]
            )
        return None

    def warnings(self, theme: Theme, runner) -> list[Msg]:
        notes: list[Msg] = []
        try:
            text = desktop.capture_file(config_path())
        except OSError:
            text = desktop.ABSENT
        current = effective_theme(text) if text != desktop.ABSENT else None
        if current and not current[1]:
            notes.append(
                translate(
                    "core",
                    "Your Rofi configuration names the theme {name}. The theme line is replaced; "
                    "the old line stays in the file as a comment.",
                ).format(name=current[0])
            )
        if runner.which("rofi"):
            with tempfile.TemporaryDirectory(prefix="pts-rofi-") as folder:
                probe = Path(folder) / f"{theme.slug}.rasi"
                probe.write_text(rasi_text(theme), encoding="utf-8")
                error = self._parse_error(runner, probe)
            if error:
                notes.append(error)
        return notes

    def is_active(self, theme: Theme, runner) -> bool:
        try:
            text = desktop.capture_file(config_path())
            current = effective_theme(text) if text != desktop.ABSENT else None
            planned = rasi_text(theme)
            return bool(
                current
                and current == (theme.slug, True)
                and desktop.capture_file(theme_path(theme)) == planned
            )
        except OSError:
            return False

    def reload_command(self, theme: Theme) -> str:
        return f"rofi -no-config -theme {theme.slug}.rasi -dump-theme"

    def changed_settings(self, theme: Theme) -> list[Msg]:
        return [translate("core", "which theme Rofi uses (the @theme line of rofi/config.rasi)")]

    def capture_settings(self, runner) -> dict:
        return {"config": desktop.capture_file(config_path())}

    def reload(self, theme: Theme, runner) -> None:
        path = config_path()
        try:
            text = desktop.capture_file(path)
        except OSError as error:
            raise ApplyError(
                translate("core", "Rofi's configuration cannot be read: {detail}").format(detail=str(error))
            ) from error
        old = "" if text == desktop.ABSENT else text
        current = effective_theme(old)
        if current != (theme.slug, True) or text == desktop.ABSENT:
            try:
                write_atomic(path, set_theme_line(old, theme.slug))
            except OSError as error:
                raise ApplyError(
                    translate("core", "Could not write the Rofi configuration: {detail}").format(
                        detail=str(error)
                    )
                ) from error
        if runner.which("rofi"):
            error = self._parse_error(runner, theme_path(theme))
            if error:
                raise ApplyError(error)

    def restore_settings(self, settings: dict, runner) -> None:
        saved = settings.get("config")
        if isinstance(saved, str):
            desktop.restore_file(config_path(), restored_config(desktop.capture_file(config_path()), saved))
