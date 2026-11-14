# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Translatable messages for code that must not depend on Qt.

Core modules create messages with `translate("core", "English text {name}")`.
Qt's lupdate extracts those calls by name. The text is translated when the
message is turned into a string, through a hook the UI installs at startup.
"""

from __future__ import annotations

from collections.abc import Callable

_hook: Callable[[str, str], str] = lambda context, text: text


def set_hook(hook: Callable[[str, str], str]) -> None:
    global _hook
    _hook = hook


class Msg:
    """A message that is translated and formatted when converted to str."""

    def __init__(self, context: str, template: str, args: dict | None = None):
        self.context = context
        self.template = template
        self.args = args or {}

    def format(self, **args) -> Msg:
        return Msg(self.context, self.template, args)

    def __str__(self) -> str:
        return _hook(self.context, self.template).format(**self.args)

    def __repr__(self) -> str:
        return f"Msg({self.template!r}, {self.args!r})"

    def __eq__(self, other) -> bool:
        return isinstance(other, Msg) and (self.template, self.args) == (other.template, other.args)

    def __hash__(self) -> int:
        return hash(self.template)


def translate(context: str, text: str) -> Msg:
    return Msg(context, text)
