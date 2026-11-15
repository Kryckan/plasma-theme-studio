# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What the desktop has is read in a worker for every page, never on the window's thread."""

import threading

import pytest

PAGES = ["overview", "themes", "colors", "fonts", "plasma_style", "icons", "pointers", "splash", "app_style"]


@pytest.fixture
def window(app, home, desktop_runner, pickers_in_background, monkeypatch):
    from plasma_theme_studio.ui.main_window import MainWindow

    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(desktop_runner)
    window.show()
    yield window
    window.close_without_asking()


def watch(runner, monkeypatch):
    """Record on which thread each command the runner runs is started (`which` is only a PATH lookup)."""
    threads = []
    for name in ("run",):
        real = getattr(runner, name)

        def watching(*args, _real=real, **kwargs):
            threads.append(threading.current_thread() is threading.main_thread())
            return _real(*args, **kwargs)

        monkeypatch.setattr(runner, name, watching)
    return threads


@pytest.mark.parametrize("key", PAGES)
def test_a_page_reads_the_desktop_off_the_window_thread(window, desktop_runner, monkeypatch, key):
    window.settle()
    threads = watch(desktop_runner, monkeypatch)
    window.show_page(key)
    assert True not in threads, f"{key} asked the desktop on the window's thread"
    window.settle()
    page = window.page(key)
    if hasattr(page, "wait_items"):
        page.wait_items()
    page.wait_desktop()
    assert True not in threads


def test_the_answer_of_a_worker_is_shown(window):
    window.show_page("fonts")
    window.page("fonts").wait_desktop()
    page = window.page("fonts")
    assert page.present  # the fonts of the desktop reached the rows


def test_a_read_that_fails_shows_nothing_instead_of_breaking_the_page(window, monkeypatch):
    page = window.page("fonts")

    def broken():
        raise OSError("no desktop")

    monkeypatch.setattr(page, "read_desktop_state", broken)
    page.ensure_built()
    page.read_desktop()
    page.wait_desktop()
    assert all(spec is None for spec in page.present.values())
