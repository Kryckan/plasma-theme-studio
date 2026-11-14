# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The sample of real widgets drawn by the generated Kvantum theme."""

import os
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QStyleFactory  # noqa: E402

from plasma_theme_studio.model.theme import Theme  # noqa: E402
from plasma_theme_studio.ui import style_preview  # noqa: E402
from plasma_theme_studio.ui.style_preview import StylePreview  # noqa: E402

needs_kvantum = pytest.mark.skipif(
    not any(key.lower() == "kvantum" for key in QStyleFactory.keys()),
    reason="the Kvantum style plugin is not available to Qt",
)


def theme(radius=6, border=1, style="generated", **colors):
    values = {("apps", "style"): style, ("apps", "radius"): radius, ("apps", "border_width"): border}
    values.update({("colors", key): value for key, value in colors.items()})
    return Theme(values)


def picture(preview):
    preview.resize(420, 340)
    preview.show()
    QApplication.processEvents()
    return preview.grab().toImage()


def test_an_unchanged_style_shows_an_explanation(app):
    preview = StylePreview(theme(style="unchanged"))
    assert not preview.shows_sample
    assert "left as it is" in preview.message


def test_a_missing_plugin_shows_an_explanation(app, monkeypatch):
    monkeypatch.setattr(style_preview, "plugin_available", lambda: False)
    preview = StylePreview(theme())
    assert not preview.shows_sample
    assert "Kvantum is not installed" in preview.message


@needs_kvantum
def test_a_generated_style_shows_the_sample(app):
    preview = StylePreview(theme())
    assert preview.shows_sample
    assert preview.findChildren(QPushButton)


@needs_kvantum
def test_the_picture_follows_radius_border_and_colors(app):
    preview = StylePreview(theme(0, 0))
    flat = picture(preview)
    preview.set_theme(theme(12, 2))
    round_ = picture(preview)
    preview.set_theme(theme(12, 2, accent="#e53935"))
    red = picture(preview)
    assert flat != round_
    assert round_ != red
    assert picture(StylePreview(theme(0, 0))) == flat


@needs_kvantum
def test_switching_back_to_unchanged_shows_the_explanation_again(app):
    preview = StylePreview(theme())
    preview.set_theme(theme(style="unchanged"))
    assert not preview.shows_sample
    preview.set_theme(theme())
    assert preview.shows_sample


@needs_kvantum
def test_the_hosts_own_style_and_palette_are_not_changed(app):
    outside = QLabel("outside")
    style_name = app.style().objectName()
    palette = app.palette()
    outside_style = outside.style()
    outside_palette = outside.palette()
    config = os.environ.get("XDG_CONFIG_HOME")

    preview = StylePreview(theme(12, 2, window="#101010"))
    picture(preview)
    preview.set_theme(theme(3, 1))
    picture(preview)

    assert app.style().objectName() == style_name
    assert app.palette() == palette
    assert outside.style() is outside_style
    assert outside.palette() == outside_palette
    assert os.environ.get("XDG_CONFIG_HOME") == config
    for button in preview.findChildren(QPushButton):
        assert button.style().objectName() == "kvantum"


@needs_kvantum
def test_temporary_folders_are_removed(app):
    seen = []
    original = tempfile.TemporaryDirectory

    def recording(*args, **kwargs):
        folder = original(*args, **kwargs)
        seen.append(Path(folder.name))
        return folder

    style_preview.tempfile.TemporaryDirectory = recording
    try:
        preview = StylePreview(theme(4, 1))
        preview.set_theme(theme(8, 1))
        preview.set_theme(theme(10, 1))
        assert len(seen) == 3
        assert [p.exists() for p in seen] == [False, False, True]
        preview.set_theme(theme(style="unchanged"))
        assert not seen[2].exists()
        preview.set_theme(theme(5, 2))
        preview.close()
        assert not seen[3].exists()
    finally:
        style_preview.tempfile.TemporaryDirectory = original


@needs_kvantum
def test_folders_still_there_at_exit_are_removed(app):
    """closeEvent never reaches a tab, so the exit hook removes what is left."""
    preview = StylePreview(theme(4, 1))
    folder = Path(preview._rendering.folder.name)
    assert folder.exists() and preview._rendering in style_preview._LIVE
    style_preview._cleanup_all()
    assert not folder.exists() and not style_preview._LIVE
    preview.close()
