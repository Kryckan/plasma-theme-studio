# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""For every part of the desktop that a theme can set: what the desktop uses now, what the theme
wants, and whether an apply would change it. The verdict is the one an apply gives: it comes from the
targets' own `is_active` and their plan, so the two cannot disagree."""

from __future__ import annotations

from dataclasses import dataclass

from ..messages import Msg, translate
from ..model.parts import BORDER_SIZES, FontSpec, describe_buttons
from ..model.theme import FONT_KEYS, Theme
from . import engine

CHANGE, SAME, LEAVE, BLOCKED = "change", "same", "leave", "blocked"

# The one vocabulary for the state of a part, in the Overview and wherever else a state is said.
STATE_WORDS = {
    CHANGE: translate("core", "Will change"),
    SAME: translate("core", "Already so"),
    LEAVE: translate("core", "Left as it is"),
    BLOCKED: translate("core", "Cannot be applied"),
}


def state_word(state: str) -> str:
    """The words for a state: "Will change", "Already so", "Left as it is" or "Cannot be applied"."""
    return str(STATE_WORDS.get(state, STATE_WORDS[SAME]))


@dataclass(frozen=True)
class PartStatus:
    key: str
    title: str
    desktop: str  # what the desktop uses now, as a person reads it
    theme: str  # what the theme asks for
    state: str  # CHANGE: an apply changes it, SAME: it is as the theme wants, LEAVE: the theme leaves it,
    # BLOCKED: an apply is refused because of it (`theme` then says why)


# key, title, the targets (by id) that make up the part
PARTS: tuple[tuple[str, Msg, tuple[str, ...]], ...] = (
    ("colors", translate("core", "Colors"), ("colors", "accent")),
    ("app_style", translate("core", "Application Style"), ("apps", "app_style", "toolbars")),
    ("plasma_style", translate("core", "Plasma Style"), ("panel", "plasma_style")),
    ("panel", translate("core", "Panel"), ("panel_layout",)),
    ("decoration", translate("core", "Window Decorations"), ("window", "decoration")),
    ("borders", translate("core", "Window Borders and Buttons"), ("border_size", "buttons")),
    ("icons", translate("core", "Icons"), ("icons",)),
    ("pointers", translate("core", "Pointers"), ("cursors", "cursor_size", "launch_feedback")),
    ("fonts", translate("core", "Fonts"), ("fonts",)),
    ("splash", translate("core", "Splash Screen"), ("splash",)),
    ("sounds", translate("core", "System Sounds"), ("sounds",)),
    ("night_mode", translate("core", "Dark mode at night"), ("night_mode", "night_variants")),
    ("gtk", translate("core", "GTK Apps"), ("gtk",)),
    ("rofi", translate("core", "Rofi"), ("rofi",)),
)

_FONT_NAMES = {
    "general": translate("core", "General"),
    "fixed": translate("core", "Fixed width"),
    "small": translate("core", "Small"),
    "toolbar": translate("core", "Toolbar"),
    "menu": translate("core", "Menu"),
    "window_title": translate("core", "Window title"),
}


def _leave() -> str:
    return str(translate("core", "Left as it is"))


def _not_checked() -> str:
    return str(translate("core", "Left as it is on your desktop"))


class _Names:
    """The display names of the installed things, as the pickers list them, read once per kind."""

    def __init__(self):
        self._kinds: dict[str, dict[str, str]] = {}

    def __call__(self, kind_key: str, value) -> str:
        if not value:
            return str(translate("core", "None"))
        if kind_key not in self._kinds:
            names: dict[str, str] = {}
            try:
                from ..pickers import kind

                picker = kind(kind_key)
                for item in picker.items() if picker else []:
                    names[item.id.casefold()] = item.name
            except Exception:  # noqa: S110 - without the pickers the ids are shown
                pass
            self._kinds[kind_key] = names
        return self._kinds[kind_key].get(str(value).casefold(), str(value))


class _Status:
    """The facts of one `parts_status` call: the theme, the runner and what was read already."""

    def __init__(self, theme: Theme, runner):
        from ..desktopparts import PARTS as desktop_parts

        self.theme, self.runner, self.parts = theme, runner, desktop_parts
        self.names = _Names()
        self.targets = {g.id: g for g in engine.generators.GENERATORS}
        self._plans: dict[str, object] = {}
        self._active: dict[str, bool] = {}
        self._current: dict[str, object] = {}

    def current(self, key: str):
        if key not in self._current:
            self._current[key] = self.parts[key].current(self.runner)
        return self._current[key]

    def plan(self, generator):
        """The plan of one target, made once per call."""
        if generator.id not in self._plans:
            self._plans[generator.id] = engine._plan_target(generator, self.theme, self.runner)
        return self._plans[generator.id]

    def is_active(self, generator) -> bool:
        if generator.id not in self._active:
            self._active[generator.id] = generator.is_active(self.theme, self.runner)
        return self._active[generator.id]

    def problem(self, ids: tuple[str, ...]) -> str | None:
        """The first reason why an apply would be refused because of these targets."""
        for i in ids:
            generator = self.targets[i]
            if generator.wanted(self.theme):
                try:
                    problems = self.plan(generator).problems
                except Exception:  # noqa: S112 - `state` counts a plan that fails as a change
                    continue
                if problems:
                    return str(problems[0])
        return None

    def made_here(self) -> str:
        return str(translate("core", "{name} (made from this theme)").format(name=self.theme.name))

    # ---- the verdict --------------------------------------------------------------------------
    def state(self, ids: tuple[str, ...]) -> str:
        wanted = [self.targets[i] for i in ids if self.targets[i].wanted(self.theme)]
        if not wanted:
            return LEAVE
        if self.problem(ids):
            return BLOCKED
        for generator in wanted:
            try:
                target = self.plan(generator)
                done = (
                    all(status.state == engine.UNCHANGED for status in target.files)
                    and not target.stale
                    and self.is_active(generator)
                )
            except Exception:
                done = False
            if not done:
                return CHANGE
        return SAME

    # ---- the two columns ----------------------------------------------------------------------
    def colors(self, wanted: bool) -> tuple[str, str]:
        from ..generators.colorscheme import current_scheme

        scheme = current_scheme(self.runner)
        desktop = self.names("color_scheme", scheme) if scheme else str(translate("core", "Breeze"))
        theme = self.theme.name
        if self.theme.has_both:
            from ..generators.colorscheme import scheme_name
            from ..generators.variants import of_variant

            dark = self.theme.shown_variant == "dark"
            theme = str(
                (
                    translate("core", "{name}, dark variant")
                    if dark
                    else translate("core", "{name}, light variant")
                ).format(name=self.theme.scheme_title)
            )
            for variant in self.theme.variants:
                if scheme and scheme == scheme_name(of_variant(self.theme, variant)):
                    desktop = str(
                        (
                            translate("core", "{name}, dark variant")
                            if variant == "dark"
                            else translate("core", "{name}, light variant")
                        ).format(name=desktop)
                    )
        if self.theme.get("colors", "accent_from_wallpaper"):
            theme = str(translate("core", "{name}, accent from the wallpaper").format(name=theme))
        return desktop, theme

    def named(self, key: str, kind: str, section: str, choice: str, wanted: bool) -> tuple[str, str]:
        desktop = self.names(kind, self.current(key))
        mode = self.theme.part_state(section, choice)
        if mode == "installed":
            return desktop, self.names(kind, self.theme.get(section, f"{choice}_id"))
        if mode == "generated":
            return desktop, self.made_here()
        return desktop, _leave()

    def decoration(self, wanted: bool) -> tuple[str, str]:
        desktop, theme = self.named("decoration", "decoration", "window", "decoration", wanted)
        mode = self.theme.part_state("window", "decoration")
        if mode == "breeze":
            theme = self.names("decoration", "org.kde.breeze:Breeze")
        elif mode == "unchanged" and wanted:
            theme = str(translate("core", "The frame in use, in the colors of the theme"))
        return desktop, theme

    def borders(self, wanted: bool) -> tuple[str, str]:
        """Border size and buttons: what the desktop has of the settings the theme names, or of both."""
        sizes = dict(BORDER_SIZES)
        size, buttons = self.current("border_size"), self.current("titlebar_buttons")
        wants_size = self.theme.get("window", "border_size")
        left, right = self.theme.get("window", "buttons_left"), self.theme.get("window", "buttons_right")
        wants_buttons = left is not None or right is not None
        desktop, theme = [], []
        if wants_size is not None or not wants_buttons:
            own = translate("core", "Size from the decoration")
            desktop.append(str(sizes.get(size, own)) if size else str(own))
        if wants_size is not None:
            theme.append(str(sizes[wants_size]))
        if wants_buttons or wants_size is None:
            desktop.append(_buttons_text(buttons["left"], buttons["right"]))
        if wants_buttons:
            theme.append(
                _buttons_text(
                    left if left is not None else buttons["left"],
                    right if right is not None else buttons["right"],
                )
            )
        return "; ".join(desktop), "; ".join(theme) if theme else _leave()

    def with_extra(self, base: tuple[str, str], target_id: str) -> tuple[str, str]:
        """`base` with the words of a small settings target (see `generators/extras.py`) added."""
        from ..generators import extras

        target = self.targets[target_id]
        if not target.wanted(self.theme):
            return base
        desktop, theme = extras.status_texts(target, self.theme, self.runner)
        desktop_text, theme_text = base
        return (
            f"{desktop_text}; {desktop}" if desktop_text else desktop,
            f"{theme_text}; {theme}" if theme_text != _leave() else theme,
        )

    def pointers(self, wanted: bool) -> tuple[str, str]:
        size = self.current("cursor_size")
        desktop = str(
            translate("core", "{name}, {size} px").format(
                name=self.names("cursors", self.current("cursor_theme")),
                size=size if size is not None else "?",
            )
        )
        theme = []
        if self.theme.get("desktop", "cursors") is not None:
            theme.append(self.names("cursors", self.theme.get("desktop", "cursors")))
        if self.theme.get("desktop", "cursor_size") is not None:
            theme.append(f"{self.theme.get('desktop', 'cursor_size')} px")
        return desktop, ", ".join(theme) if theme else _leave()

    def fonts(self, wanted: bool) -> tuple[str, str]:
        from ..generators.installed import FONT_ROLES

        current = self.current("fonts") or {}
        desktop, theme = [], []
        for name in FONT_KEYS:
            text = self.theme.get("fonts", name)
            if text is None:
                continue
            shown = FontSpec.parse(current.get(FONT_ROLES[name], ""))
            default = translate("core", "Default")
            desktop.append(f"{_FONT_NAMES[name]}: {shown.label() if shown else default}")
            spec = FontSpec.from_short(text)
            theme.append(f"{_FONT_NAMES[name]}: {spec.label() if spec else text}")
        if not theme:
            general = FontSpec.parse(current.get("font", ""))
            return (general.label() if general else str(translate("core", "Default"))), _leave()
        return "; ".join(desktop), "; ".join(theme)

    def night_mode(self) -> tuple[str, str]:
        def word(on) -> str:
            return str(translate("core", "On") if on else translate("core", "Off"))

        wanted = self.theme.get("desktop", "dark_at_night")
        return word(self.current("night_mode")), word(wanted) if wanted is not None else _leave()

    def simple(self, key: str, kind: str, section: str, field: str, extract=None) -> tuple[str, str]:
        current = self.current(key)
        if extract:
            current = extract(current)
        desktop = self.names(kind, current)
        value = self.theme.get(section, field)
        return desktop, self.names(kind, value) if value is not None else _leave()

    def generated(self, key: str, wanted: bool) -> tuple[str, str]:
        generator = self.targets[key]
        if not wanted:
            return _not_checked(), _leave()
        active = self.is_active(generator)
        desktop = translate("core", "This theme's own") if active else translate("core", "Something else")
        return str(desktop), self.made_here()

    def panel(self, wanted: bool) -> tuple[str, str]:
        from ..generators import panellayout

        if not wanted:  # reading the panel asks Plasma, so it is done only for a theme that names one
            return _not_checked(), _leave()
        return panellayout.status_texts(self.theme, self.runner)

    def texts(self, key: str, ids: tuple[str, ...]) -> tuple[str, str]:
        wanted = any(self.targets[i].wanted(self.theme) for i in ids)
        match key:
            case "colors":
                return self.colors(wanted)
            case "app_style":
                return self.with_extra(
                    self.named("app_style", "app_style", "apps", "style", wanted), "toolbars"
                )
            case "plasma_style":
                desktop, theme = self.named("plasma_style", "plasma_style", "panel", "style", wanted)
                if self.theme.part_state("panel", "style") == "generated":
                    from ..generators import plasmastyle

                    own = plasmastyle.status_words(self.theme)
                    theme = f"{theme}, {own}" if own else theme
                return desktop, theme
            case "panel":
                return self.panel(wanted)
            case "decoration":
                return self.decoration(wanted)
            case "borders":
                return self.borders(wanted)
            case "icons":
                return self.simple("icons", "icons", "desktop", "icons")
            case "pointers":
                return self.with_extra(self.pointers(wanted), "launch_feedback")
            case "fonts":
                return self.fonts(wanted)
            case "splash":
                return self.simple("splash", "splash", "desktop", "splash")
            case "night_mode":
                return self.night_mode()
            case "sounds":
                return self.simple("sounds", "sounds", "desktop", "sounds", lambda value: value["theme"])
            case _:
                return self.generated(key, wanted)


def _buttons_text(left: str | None, right: str | None) -> str:
    def side(text: str | None) -> str:
        return ", ".join(str(name) for name in describe_buttons(text or "")) or "-"

    return str(
        translate("core", "Buttons: left {left}; right {right}").format(left=side(left), right=side(right))
    )


def parts_status(theme: Theme, runner) -> list[PartStatus]:
    """One record for every part. It never raises: a part that cannot be read says so and
    counts as one an apply would change."""
    unreadable = str(translate("core", "Could not be read"))
    try:
        status = _Status(theme, runner)
    except Exception:
        return [PartStatus(key, str(title), unreadable, unreadable, CHANGE) for key, title, _ids in PARTS]
    records = []
    for key, title, ids in PARTS:
        try:
            state = status.state(ids)
        except Exception:
            state = CHANGE
        try:
            desktop, wanted = status.texts(key, ids)
        except Exception:
            desktop, wanted = unreadable, unreadable if state != LEAVE else _leave()
        if state == BLOCKED:
            wanted = status.problem(ids) or wanted
        records.append(PartStatus(key, str(title), desktop, wanted, state))
    return records
