# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Application Style and Window Decorations pickers."""

import importlib
import shutil
import subprocess
import sys
import tempfile

import pytest

pytest.importorskip("PySide6.QtSvg")

from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, QImage
from PySide6.QtWidgets import QApplication, QStyleFactory

from plasma_theme_studio.generators.base import MARKER
from plasma_theme_studio.pickers import _process, appstyles, decorations

SIZE = QSize(176, 110)


@pytest.fixture(autouse=True)
def qt(app):
    return app


class FakeProcess:
    """A stand-in for the helper's Popen: `code` is what wait() gives, or an exception."""

    killed = []

    def __init__(self, argv, code=0, run=None, **kwargs):
        self.argv, self.kwargs, self.code, self.pid = argv, kwargs, code, 4242
        self.waited = None
        if run is not None:
            run(argv, kwargs)

    def wait(self, timeout=None):
        if self.waited is None:
            self.waited = timeout
            if isinstance(self.code, BaseException):
                raise self.code
        return self.code


def fake_helper(monkeypatch, code=0, run=None, seen=None):
    """Replace the helper's Popen; `seen` collects the processes."""
    FakeProcess.killed = []
    monkeypatch.setattr(_process.os, "killpg", lambda pid, sig: FakeProcess.killed.append(pid))

    def make(argv, **kwargs):
        process = FakeProcess(argv, code, run, **kwargs)
        if seen is not None:
            seen.append(process)
        return process

    monkeypatch.setattr(_process.subprocess, "Popen", make)


def share(home, *sub):
    folder = (home / "system/share").joinpath(*sub)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def user_share(home, *sub):
    folder = (home / ".local/share").joinpath(*sub)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def themerc(folder, name, style, title, comment="", hidden=False):
    text = f"[KDE]\nWidgetStyle={style}\n\n[Misc]\nName={title}\nComment={comment}\n"
    if hidden:
        text += "\n[Desktop Entry]\nHidden=true\n"
    (folder / name).write_text(text, "utf-8")


def test_modules_import_without_application():
    for name in ("appstyles", "decorations", "_helper", "_process", "_colors"):
        importlib.import_module(f"plasma_theme_studio.pickers.{name}")


# Application Style -----------------------------------------------------------


def test_style_listing_rules(home, monkeypatch):
    monkeypatch.setattr(appstyles, "style_keys", lambda: ["Breeze", "Fusion", "Union", "kvantum", "Mystery"])
    themes = share(home, "kstyle", "themes")
    themerc(themes, "breeze.themerc", "breeze", "Breeze", "Plasma's default")
    themerc(themes, "union.themerc", "union", "Union", hidden=True)
    themerc(themes, "ghost.themerc", "notinstalled", "Ghost")
    user = user_share(home, "kstyle", "themes")
    themerc(user, "fusion.themerc", "fusion", "My Fusion", "Mine")
    items = {item.id: item for item in appstyles.list_styles()}
    assert set(items) == {"Breeze", "Fusion", "kvantum", "Mystery"}
    assert items["Breeze"].name == "Breeze"
    assert items["Breeze"].description == "Plasma's default"
    assert items["Breeze"].extra["in_process"] is True
    assert items["Fusion"].name == "My Fusion" and items["Fusion"].user is True
    assert items["Mystery"].name == "Mystery" and items["Mystery"].extra["in_process"] is False
    assert items["kvantum"].path.name == "kvantum.kvconfig"
    assert items["kvantum"].extra["in_process"] is False


def test_style_listing_has_every_factory_key(home):
    ids = {item.id for item in appstyles.list_styles()}
    assert ids == {key for key in QStyleFactory.keys() if key != "kvantum-dark"}


def test_union_is_never_drawn_in_this_process():
    # A widget with the Union style crashes the process when Union's data is not in XDG_DATA_DIRS.
    assert "union" not in appstyles.IN_PROCESS


def test_union_styles_are_listed_as_union_slash_name(home, monkeypatch):
    monkeypatch.setattr(appstyles, "style_keys", lambda: ["Breeze", "Union"])
    for name in ("breeze", "breeze-mobile"):
        share(home, "union", "styles", name)
    items = {item.id: item for item in appstyles.list_styles()}
    assert items["union/breeze"].name == "Breeze (Union)"
    assert items["union/breeze-mobile"].name == "Breeze Mobile (Union)"
    assert items["union/breeze"].extra["in_process"] is False
    assert appstyles.AppStyles().thumbnail(items["union/breeze-mobile"], SIZE, 1.0, None).isNull()
    monkeypatch.setattr(appstyles, "style_keys", lambda: ["Breeze"])
    assert not [i for i in appstyles.list_styles() if i.id.startswith("union/")]


def test_style_thumbnail_leaves_the_host_alone(home):
    app = QApplication.instance()
    style_before = app.style().objectName()
    palette_before = app.palette().window().color().name()
    font_before = app.font().toString()
    colors = {"window": "#102030", "base": "#203040", "text": "#f0f0f0", "highlight": "#ff0066"}
    drawn = 0
    for key in QStyleFactory.keys():
        if key.casefold() in appstyles.IN_PROCESS:
            image = appstyles.render_panel(key, SIZE, 2.0, colors, appstyles.labels())
            assert image.size() == SIZE * 2
            assert image.pixelColor(2, 2).name() == "#102030"
            drawn += 1
    assert drawn
    assert app.style().objectName() == style_before
    assert app.palette().window().color().name() == palette_before
    assert app.font().toString() == font_before
    assert app.font() == QFont(font_before) or app.font().toString() == font_before


def test_unknown_style_is_a_null_image(home):
    assert appstyles.render_panel("NoSuchStyle", SIZE, 1.0, None, appstyles.labels()).isNull()


def test_style_thumbnail_uses_the_helper_for_unknown_styles(home, monkeypatch):
    monkeypatch.setattr(appstyles, "style_keys", lambda: ["Fusion", "kvantum"])

    def draw(argv, kwargs):
        out = next(part for part in argv if part.endswith("/out"))
        image = QImage(176 * 2, 110 * 2, QImage.Format.Format_ARGB32)
        image.fill(0xFF00FF00)
        image.save(f"{out}/0.png")

    processes = []
    fake_helper(monkeypatch, 0, draw, processes)
    kind = appstyles.AppStyles()
    items = {item.id: item for item in kind.items()}
    image = kind.thumbnail(items["kvantum"], SIZE, 2.0, None)
    assert not image.isNull() and image.devicePixelRatio() == 2.0
    assert len(processes) == 1
    kind.thumbnail(items["kvantum"], SIZE, 2.0, None)
    assert len(processes) == 1  # the batch is kept
    argv, kwargs = processes[0].argv, processes[0].kwargs
    assert "styles" in argv and argv[argv.index("-m") + 1] == "plasma_theme_studio.pickers._helper"
    assert kwargs["env"]["QT_QPA_PLATFORM"] == "offscreen"
    # Fusion is drawn here, so only kvantum is in the job.
    assert kind.thumbnail(items["Fusion"], SIZE, 2.0, None).size() == SIZE * 2


def test_failing_style_helper_gives_null(home, monkeypatch):
    monkeypatch.setattr(appstyles, "style_keys", lambda: ["kvantum"])
    fake_helper(monkeypatch, 1)
    kind = appstyles.AppStyles()
    assert kind.thumbnail(kind.items()[0], SIZE, 1.0, None).isNull()


# Window Decorations ----------------------------------------------------------


def aurorae(home, name, marker=False):
    folder = user_share(home, "aurorae", "themes") / name
    folder.mkdir(parents=True)
    (folder / f"{name}rc").write_text("[General]\nTitleAlignment=Center\n")
    (folder / "decoration.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
        '<rect id="decoration-top" width="64" height="24" fill="#334455"/></svg>'
    )
    head = f"{MARKER}\n" if marker else ""
    (folder / "metadata.desktop").write_text(f"{head}[Desktop Entry]\nName={name} theme\nComment=Test\n")
    return folder


def test_decoration_listing_rules(home, monkeypatch):
    plugins = home / "plugins"
    plugins.mkdir()
    for name in ("breeze", "aurorae", "broken", "klassy"):
        (plugins / f"org.kde.{name}.so").write_bytes(b"")
    metadata = {
        "org.kde.breeze.so": {"KPlugin": {"Name": "Breeze", "Description": "Default"}},
        "org.kde.aurorae.so": {"KPlugin": {"Name": "Aurorae"}, "org.kde.kdecoration3": {"themes": True}},
        "org.kde.broken.so": {},
    }
    monkeypatch.setattr(decorations, "plugin_folders", lambda: [plugins])
    monkeypatch.setattr(decorations, "plugin_metadata", lambda path: metadata.get(path.name, {}))
    aurorae(home, "Plain")
    aurorae(home, "PlasmaThemeStudio-nord-1234abcd", marker=True)
    aurorae(home, "PlasmaThemeStudio-foreign", marker=False)
    source = user_share(home, "aurorae", "themes") / "klassy-src"
    source.mkdir()
    (source / "decoration.svg").write_text("<svg/>")  # a source tree: no rc file
    qml = share(home, "kwin", "decorations", "kwin4_decoration_qml_plastik")
    (qml / "contents/ui").mkdir(parents=True)
    (qml / "contents/ui/main.qml").write_text("import QtQuick\nItem {}\n")
    (qml / "metadata.desktop").write_text("[Desktop Entry]\nName=Plastik\nComment=Old\n")

    items = {item.id: item for item in decorations.list_decorations()}
    assert set(items) == {
        "org.kde.breeze:Breeze",
        "org.kde.kwin.aurorae.v2:__aurorae__svg__Plain",
        "org.kde.kwin.aurorae.v2:__aurorae__svg__PlasmaThemeStudio-nord-1234abcd",
        "org.kde.kwin.aurorae.v2:__aurorae__svg__PlasmaThemeStudio-foreign",
        "org.kde.kwin.aurorae:kwin4_decoration_qml_plastik",
    }
    assert items["org.kde.breeze:Breeze"].extra["kind"] == "plugin"
    assert items["org.kde.breeze:Breeze"].description == "Default"
    plain = items["org.kde.kwin.aurorae.v2:__aurorae__svg__Plain"]
    assert plain.name == "Plain theme" and plain.user is True and plain.extra["made_here"] is False
    made = items["org.kde.kwin.aurorae.v2:__aurorae__svg__PlasmaThemeStudio-nord-1234abcd"]
    assert made.extra["made_here"] is True
    assert (
        items["org.kde.kwin.aurorae.v2:__aurorae__svg__PlasmaThemeStudio-foreign"].extra["made_here"] is False
    )
    assert items["org.kde.kwin.aurorae:kwin4_decoration_qml_plastik"].extra["kind"] == "qml"


@pytest.fixture
def listed(home, monkeypatch):
    monkeypatch.setattr(decorations, "plugin_folders", lambda: [])
    aurorae(home, "Plain")
    qml = share(home, "kwin", "decorations", "kwin4_decoration_qml_plastik")
    (qml / "contents/ui").mkdir(parents=True)
    (qml / "contents/ui/main.qml").write_text("import QtQuick\nItem {}\n")
    (qml / "metadata.desktop").write_text("[Desktop Entry]\nName=Plastik\n")
    return decorations.Decorations()


def test_helper_command_and_environment(listed, monkeypatch):
    seen = []
    fake_helper(monkeypatch, 0, None, seen)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    listed.thumbnail(listed.items()[0], SIZE, 2.0, {"window": "#112233"})
    assert len(seen) == 1
    argv, kwargs = seen[0].argv, seen[0].kwargs
    if shutil.which("prlimit"):
        assert argv[:3] == [shutil.which("prlimit"), "--core=0:0", "--"]
    assert sys.executable in argv
    assert argv[argv.index("-m") + 1] == "plasma_theme_studio.pickers._helper"
    assert "decorations" in argv
    env = kwargs["env"]
    assert env["QT_QPA_PLATFORM"] == "offscreen"
    assert env["QT_QUICK_BACKEND"] == "software"
    assert "DISPLAY" not in env and "WAYLAND_DISPLAY" not in env
    assert env["XDG_CACHE_HOME"].startswith(tempfile.gettempdir())
    assert seen[0].waited == _process.TIMEOUT <= 15
    assert env["DBUS_SESSION_BUS_ADDRESS"].endswith("pts-no-bus")  # not the user's session
    assert kwargs["stdin"] == subprocess.DEVNULL


def test_failing_helper_gives_the_fallback(listed, monkeypatch):
    fake_helper(monkeypatch, 139)
    for item in listed.items():
        image = listed.thumbnail(item, SIZE, 2.0, None)
        assert image.size() == SIZE * 2 and image.devicePixelRatio() == 2.0


def test_hanging_helper_gives_the_fallback(listed, monkeypatch):
    fake_helper(monkeypatch, subprocess.TimeoutExpired("helper", 1))
    image = listed.thumbnail(listed.items()[0], SIZE, 1.0, None)
    assert image.size() == SIZE and not image.isNull()
    assert FakeProcess.killed == [4242]  # the hung helper and its group are killed


def test_terminate_all_kills_the_running_helpers(monkeypatch):
    killed = []
    monkeypatch.setattr(_process.os, "killpg", lambda pid, sig: killed.append(pid))
    process = FakeProcess(["x"])
    _process._LIVE.add(process)
    try:
        _process.terminate_all()
    finally:
        _process._LIVE.discard(process)
    assert killed == [4242]


def test_missing_interpreter_gives_the_fallback(listed, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(_process.subprocess, "Popen", missing)
    assert not listed.thumbnail(listed.items()[0], SIZE, 1.0, None).isNull()


def test_failed_run_is_not_repeated_at_once(listed, monkeypatch):
    calls = []
    fake_helper(monkeypatch, 1, None, calls)
    for item in listed.items():
        listed.thumbnail(item, SIZE, 1.0, None)
    assert len(calls) == 1


def test_svg_fallback_draws_the_theme(home):
    folder = aurorae(home, "Plain")
    image = decorations.compose_svg(folder, QSize(116, 75), 1.0, True, None, "Window")
    assert not image.isNull()
    plain = decorations.plain_window(QSize(116, 75), 2.0, False, None, "Window")
    assert not plain.isNull() and plain.devicePixelRatio() == 2.0


@pytest.mark.skipif(not decorations.plugin_folders(), reason="no KWin decoration plugins here")
def test_real_decorations_render(home):
    kind = decorations.Decorations()
    items = [item for item in kind.items() if item.extra["kind"] == "plugin"]
    if not items:
        pytest.skip("no decoration plugin")
    probe = _process.run("decorations", {}, None)
    with probe as (out, _code):
        if out is None:
            pytest.skip("helper cannot start")
    image = kind.thumbnail(items[0], SIZE, 1.0, None)
    assert image.size() == SIZE and not image.isNull()
