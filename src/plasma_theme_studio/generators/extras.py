# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The two small settings dialogs of System Settings as targets: "Configure Icons and Toolbars" of the
Application Style page (kdeglobals) and "Configure Launch Feedback" of the Cursors page (klaunchrc).

Both are optional values of the theme: a value that is not set leaves the desktop as it is. A target changes
the keys of the values that are set, tells the programs that read them (as the KCM does), and hands back
exactly what undo needs: the user's own value of each key, whether the key hid a default, and which files
were not there.
"""

from __future__ import annotations

from .. import kconfig
from ..messages import Msg, translate
from ..model.theme import Theme
from .base import ApplyError, Generator, PlannedFile

# name -> (file, groups, key, default as the KCM has it), the keys of each dialog.
TOOLBAR_KEYS = {
    "main_style": ("kdeglobals", ["Toolbar style"], "ToolButtonStyle", "TextBesideIcon"),
    "other_style": ("kdeglobals", ["Toolbar style"], "ToolButtonStyleOtherToolbars", "TextBesideIcon"),
    "icons_on_buttons": ("kdeglobals", ["KDE"], "ShowIconsOnPushButtons", "true"),
    "icons_in_menus": ("kdeglobals", ["KDE"], "ShowIconsInMenuItems", "true"),
}
FEEDBACK_KEYS = {
    "busy_cursor": ("klaunchrc", ["FeedbackStyle"], "BusyCursor", "true"),
    "blinking": ("klaunchrc", ["BusyCursorSettings"], "Blinking", "false"),
    "bouncing": ("klaunchrc", ["BusyCursorSettings"], "Bouncing", "true"),
    "cursor_timeout": ("klaunchrc", ["BusyCursorSettings"], "Timeout", "5"),
    "taskbar": ("klaunchrc", ["FeedbackStyle"], "TaskbarButton", "true"),
    "taskbar_timeout": ("klaunchrc", ["TaskbarButtonSettings"], "Timeout", "5"),
}

# KGlobalSettings.notifyChange kinds the KCM sends.
SETTINGS_CHANGED, TOOLBAR_STYLE_CHANGED, SETTINGS_STYLE = 3, 6, 7


def _bool(value) -> str:
    return "true" if value else "false"


def _emit(runner, path: str, interface: str, member: str, *integers: int) -> None:
    # desktopparts imports the generators, so it cannot be imported when they are.
    from ..desktopparts import _emit as emit

    emit(runner, path, interface, member, *integers)


class _Extra(Generator):
    """A group of keys that are set when the theme gives their values."""

    keys: dict = {}

    def values(self, theme: Theme) -> dict[str, str]:
        """The text to write for each key the theme sets (a key that is left alone is not in it)."""
        raise NotImplementedError

    def wanted(self, theme: Theme) -> bool:
        return bool(self.values(theme))

    def files(self, theme: Theme) -> list[PlannedFile]:
        return []  # the desktop's settings are changed, no file is made

    def describe(self, theme: Theme) -> list[Msg]:
        raise NotImplementedError

    def changed_settings(self, theme: Theme) -> list[Msg]:
        return self.describe(theme) if self.wanted(theme) else []

    def unavailable_reason(self, runner) -> Msg | None:
        for tool in ("kreadconfig6", "kwriteconfig6"):
            if not runner.which(tool):
                return translate("core", "{tool} is not installed.").format(tool=tool)
        return None

    def current(self, runner, name: str) -> str:
        file, groups, key, default = self.keys[name]
        return kconfig.effective_value(runner, file, groups, key, default).strip().lower()

    def is_active(self, theme: Theme, runner) -> bool:
        return all(self.current(runner, name) == text.lower() for name, text in self.values(theme).items())

    def capture_settings(self, runner) -> dict:
        return {
            "values": {name: kconfig.user_value(*key[:3]) for name, key in self.keys.items()},
            "masked": [name for name, key in self.keys.items() if kconfig.masked(*key[:3])],
            "absent": sorted({key[0] for key in self.keys.values() if not kconfig.file_exists(key[0])}),
        }

    def reload(self, theme: Theme, runner) -> None:
        failure = None
        for name, text in self.values(theme).items():
            try:
                kconfig.write_value(runner, *self.keys[name][:3], text, notify=True)
            except ApplyError as error:
                failure = failure or error
        self.tell(runner)
        if failure:
            raise failure

    def restore_settings(self, settings: dict, runner) -> None:
        values, masked = settings.get("values") or {}, settings.get("masked") or ()
        failure = None
        for name, key in self.keys.items():
            if name not in values:
                continue
            try:
                kconfig.write_value(runner, *key[:3], values[name], masked=name in masked, notify=True)
            except ApplyError as error:
                failure = failure or error
        for file in settings.get("absent") or ():
            if file in {key[0] for key in self.keys.values()}:
                kconfig.drop_if_empty(file)
        self.tell(runner)
        if failure:
            raise failure

    def tell(self, runner) -> None:
        """Tell the programs that read these keys that they changed."""


class ToolbarsTarget(_Extra):
    id = "toolbars"
    title = translate("core", "Icons and toolbars")
    sections = ("toolbars",)
    keys = TOOLBAR_KEYS

    def values(self, theme: Theme) -> dict[str, str]:
        found = {}
        for name in ("main_style", "other_style"):
            value = theme.get("toolbars", name)
            if value is not None:
                found[name] = str(value)
        for name in ("icons_on_buttons", "icons_in_menus"):
            value = theme.get("toolbars", name)
            if value is not None:
                found[name] = _bool(value)
        return found

    def describe(self, theme: Theme) -> list[Msg]:
        return [translate("core", "the icon and toolbar settings of applications (kdeglobals)")]

    def tell(self, runner) -> None:
        # What the KCM sends: the toolbars of running programs read their style again, and the programs
        # that show icons on buttons and in menus read the style settings.
        _emit(runner, "/KToolBar", "org.kde.KToolBar", "styleChanged")
        _emit(runner, "/KGlobalSettings", "org.kde.KGlobalSettings", "notifyChange", TOOLBAR_STYLE_CHANGED, 0)
        _emit(
            runner,
            "/KGlobalSettings",
            "org.kde.KGlobalSettings",
            "notifyChange",
            SETTINGS_CHANGED,
            SETTINGS_STYLE,
        )


class LaunchFeedbackTarget(_Extra):
    id = "launch_feedback"
    title = translate("core", "Launch feedback")
    sections = ("feedback",)
    keys = FEEDBACK_KEYS

    def values(self, theme: Theme) -> dict[str, str]:
        found = {}
        cursor = theme.get("feedback", "cursor")
        if cursor is not None:
            found["busy_cursor"] = _bool(cursor != "none")
            found["blinking"] = _bool(cursor == "blinking")
            found["bouncing"] = _bool(cursor == "bouncing")
        timeout = theme.get("feedback", "cursor_timeout")
        if timeout is not None:
            found["cursor_timeout"] = str(int(timeout))
        taskbar = theme.get("feedback", "taskbar")
        if taskbar is not None:
            found["taskbar"] = _bool(taskbar)
        timeout = theme.get("feedback", "taskbar_timeout")
        if timeout is not None:
            found["taskbar_timeout"] = str(int(timeout))
        return found

    def describe(self, theme: Theme) -> list[Msg]:
        return [translate("core", "the launch feedback of applications (klaunchrc)")]

    def tell(self, runner) -> None:
        _emit(runner, "/KLauncher", "org.kde.KLauncher", "reparseConfiguration")


# ---- words for the Overview

_STYLE_WORDS = {
    "notext": translate("core", "icons only"),
    "textonly": translate("core", "text only"),
    "textbesideicon": translate("core", "text beside icons"),
    "textundericon": translate("core", "text below icons"),
}
_CURSOR_WORDS = {
    "none": translate("core", "none"),
    "static": translate("core", "static"),
    "blinking": translate("core", "blinking"),
    "bouncing": translate("core", "bouncing"),
}


def _yes(text: str) -> str:
    return str(translate("core", "yes") if text == "true" else translate("core", "no"))


def _f(message, **args) -> str:
    return str(message.format(**args))


def summary(target: _Extra, values: dict[str, str]) -> str:
    """The given key values (`target.values` or the desktop's) in a line."""
    parts = []
    if isinstance(target, ToolbarsTarget):
        for name, message in (
            ("main_style", translate("core", "main toolbar: {style}")),
            ("other_style", translate("core", "other toolbars: {style}")),
        ):
            if name in values:
                word = _STYLE_WORDS.get(values[name].lower(), values[name])
                parts.append(_f(message, style=word))
        if "icons_on_buttons" in values:
            parts.append(_f(translate("core", "icons on buttons: {on}"), on=_yes(values["icons_on_buttons"])))
        if "icons_in_menus" in values:
            parts.append(_f(translate("core", "icons in menus: {on}"), on=_yes(values["icons_in_menus"])))
    else:
        if "busy_cursor" in values:
            if values["busy_cursor"] != "true":
                kind = "none"
            elif values.get("blinking") == "true":
                kind = "blinking"
            elif values.get("bouncing") == "true":
                kind = "bouncing"
            else:
                kind = "static"
            parts.append(_f(translate("core", "cursor: {kind}"), kind=_CURSOR_WORDS[kind]))
        if "cursor_timeout" in values:
            parts.append(
                _f(translate("core", "cursor stops after {seconds} s"), seconds=values["cursor_timeout"])
            )
        if "taskbar" in values:
            parts.append(_f(translate("core", "Task Manager: {on}"), on=_yes(values["taskbar"])))
        if "taskbar_timeout" in values:
            parts.append(
                _f(
                    translate("core", "Task Manager stops after {seconds} s"),
                    seconds=values["taskbar_timeout"],
                )
            )
    return ", ".join(parts)


def status_texts(target: _Extra, theme: Theme, runner) -> tuple[str, str]:
    """(what the desktop has for the keys the theme sets, what the theme sets) for the Overview."""
    wanted = target.values(theme)
    if target.keys is FEEDBACK_KEYS and "busy_cursor" in wanted:  # the kind is read from three keys
        wanted_all = {**wanted}
        desktop = {name: target.current(runner, name) for name in target.keys}
    else:
        desktop = {name: target.current(runner, name) for name in wanted}
        wanted_all = wanted
    return summary(target, desktop), summary(target, wanted_all)
