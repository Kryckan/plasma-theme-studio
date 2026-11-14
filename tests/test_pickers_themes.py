# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Global Theme, Colors, Plasma Style, Splash Screen and System Sounds pickers."""

import gzip
import json

import pytest

pytest.importorskip("PySide6.QtSvg")

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage

from plasma_theme_studio import pickers
from plasma_theme_studio.pickers import globalthemes, plasmastyles

SIZE = QSize(176, 110)


@pytest.fixture(autouse=True)
def qt(app):
    return app


def share(home, *sub):
    folder = home / "system/share"
    folder = folder.joinpath(*sub)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def user_share(home, *sub):
    folder = (home / ".local/share").joinpath(*sub)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def png(path, color="#ff0000", size=(64, 40)):
    image = QImage(*size, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    path.parent.mkdir(parents=True, exist_ok=True)
    assert image.save(str(path))


def pixel(image, fx, fy):
    return QColor.fromRgba(image.pixel(int(image.width() * fx), int(image.height() * fy)))


# Global themes -------------------------------------------------------------


def make_theme(root, name, meta=True, previews=(), defaults=None, splash=False):
    folder = root / name
    (folder / "contents").mkdir(parents=True)
    if meta:
        (folder / "metadata.json").write_text(json.dumps({"KPlugin": {"Name": name.upper(), "Id": name}}))
    for preview in previews:
        png(folder / "contents/previews" / preview, "#00ff00", (160, 90))
    if defaults is not None:
        (folder / "contents/defaults").write_text(defaults)
    if splash:
        (folder / "contents/splash").mkdir()
    return folder


DEFAULTS = """[kdeglobals][General]
ColorScheme=Nord
font=Noto Sans,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1
Unknown=1

[kdeglobals][KDE]
widgetStyle=kvantum

[kdeglobals][Icons]
Theme=breeze

[plasmarc][Theme]
name=Nord

[kwinrc][org.kde.kdecoration2]
library=org.kde.kwin.aurorae
theme=__aurorae__svg__Nord

[kcminputrc][Mouse]
cursorTheme=Nordic
cursorSize=32

[ksplashrc][KSplash]
Theme=Nord

[Wallpaper]
Image=Next
"""


def test_global_themes_list_and_defaults(home):
    root = share(home, "plasma/look-and-feel")
    make_theme(root, "b.theme", previews=["preview.png"], defaults=DEFAULTS)
    make_theme(root, "nometa", meta=False)
    (root / "nocontents").mkdir()
    (root / "nocontents/metadata.json").write_text("{}")
    broken = make_theme(root, "broken")
    (broken / "metadata.json").write_text("{not json")
    legacy = make_theme(root, "legacy", meta=False)
    (legacy / "metadata.desktop").write_text("[Desktop Entry]\nName=Old one\nComment=Legacy\n")
    make_theme(user_share(home, "plasma/look-and-feel"), "b.theme")
    kind = pickers.kind("global_theme")
    items = kind.items()
    assert [i.id for i in items] == [
        "b.theme",
        "legacy",
    ]  # home copy of b.theme wins, broken ones are skipped
    assert items[0].user and items[0].name == "B.THEME"
    assert items[1].name == "Old one" and items[1].description == "Legacy"
    # The home copy has no defaults; the system one does.
    assert globalthemes.defaults(items[0]) == {}
    system = globalthemes.package_items()  # same list
    assert system == items
    item = globalthemes.Item("x", "x", path=root / "b.theme")
    assert globalthemes.defaults(item) == {
        "color_scheme": "Nord",
        "app_style": "kvantum",
        "plasma_style": "Nord",
        "decoration": "org.kde.kwin.aurorae:__aurorae__svg__Nord",
        "icons": "breeze",
        "cursors": "Nordic",
        "cursor_size": 32,
        "fonts": {"general": "Noto Sans,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1"},
        "splash": "Nord",
    }


def test_global_theme_defaults_edge_cases(home):
    root = share(home, "plasma/look-and-feel")
    folder = make_theme(
        root,
        "t",
        defaults="[kwinrc][org.kde.kdecoration2]\nlibrary=org.kde.breeze\n[kcminputrc][Mouse]\ncursorSize=big\n",
    )
    item = globalthemes.Item("t", "t", path=folder)
    assert globalthemes.defaults(item) == {"decoration": "org.kde.breeze:Breeze"}
    assert globalthemes.defaults(globalthemes.Item("n", "n")) == {}


def test_global_theme_decoration_without_a_theme_name(home):
    root = share(home, "plasma/look-and-feel")
    for library, expected in (
        ("org.kde.oxygen", {"decoration": "org.kde.oxygen:Oxygen"}),
        ("org.kde.unknown", {}),  # no name to give: nothing, not "org.kde.unknown:"
    ):
        folder = make_theme(root, library, defaults=f"[kwinrc][org.kde.kdecoration2]\nlibrary={library}\n")
        assert globalthemes.defaults(globalthemes.Item("t", "t", path=folder)) == expected


def test_resolve_finds_the_installed_item_for_a_loose_value():
    Item = globalthemes.Item
    items = [
        Item("Oxygen", "Oxygen"),
        Item("NordicDarker", "Nordic-Darker"),
        Item("org.kde.kwin.aurorae.v2:__aurorae__svg__Nordic", "Nordic"),
    ]
    assert globalthemes.resolve("oxygen", items) is items[0]
    assert globalthemes.resolve("Nordic-Darker", items) is items[1]
    assert globalthemes.resolve("org.kde.kwin.aurorae:__aurorae__svg__Nordic", items) is items[2]
    assert globalthemes.resolve("candy", items) is None


def test_color_schemes_skip_pipes_and_device_links(home):
    import os

    from plasma_theme_studio.pickers import colorschemes

    folder = home / ".local/share/color-schemes"
    folder.mkdir(parents=True, exist_ok=True)
    os.mkfifo(folder / "Fifo.colors")
    (folder / "Zero.colors").symlink_to("/dev/zero")
    (folder / "Test.colors").write_text(SCHEME)
    assert [item.id for item in colorschemes.ColorSchemes().items()] == ["Test"]


def test_global_theme_thumbnail(home):
    root = share(home, "plasma/look-and-feel")
    make_theme(root, "a", previews=["preview.png"])
    make_theme(root, "b", previews=["fullscreenpreview.jpg"])
    make_theme(root, "c")
    kind = pickers.kind("global_theme")
    images = {i.id: kind.thumbnail(i, SIZE, 2.0, None) for i in kind.items()}
    for image in images.values():
        assert (image.width(), image.height()) == (352, 220)
        assert image.devicePixelRatio() == 2.0
    assert pixel(images["a"], 0.5, 0.5) == QColor("#00ff00")
    assert pixel(images["b"], 0.5, 0.5).green() > 250  # a JPEG is not exact
    assert pixel(images["c"], 0.5, 0.5).alpha() < 255  # a placeholder, not a picture
    unreadable = globalthemes.Item("z", "z", path=root / "missing")
    assert not kind.thumbnail(unreadable, SIZE, 1.0, None).isNull()


# Colors ---------------------------------------------------------------------

SCHEME = """[General]
Name=Test Scheme
Name[sv]=Provschema

[Colors:Window]
BackgroundNormal=10,20,30
ForegroundNormal=250,250,250

[Colors:View]
BackgroundNormal=#102030
ForegroundNormal=1,2,3

[Colors:Selection]
BackgroundNormal=200,0,0
ForegroundNormal=0,255,0

[Colors:Button]
BackgroundNormal=0,0,200
ForegroundNormal=255,255,255

[WM]
activeBackground=0,100,0
activeForeground=255,255,255
"""


def test_color_scheme_items(home):
    folder = share(home, "color-schemes")
    (folder / "Test.colors").write_text(SCHEME)
    (folder / "Broken.colors").write_text("not a scheme")
    user_share(home, "color-schemes")
    (home / ".local/share/color-schemes/Test.colors").write_text(SCHEME.replace("Test Scheme", "Mine"))
    items = pickers.kind("color_scheme").items()
    assert [(i.id, i.name, i.user) for i in items] == [("Test", "Mine", True)]
    assert items[0].extra["colors"]["window"] == "#0a141e"


def test_color_scheme_card_uses_file_colors(home):
    folder = share(home, "color-schemes")
    (folder / "Test.colors").write_text(SCHEME)
    (folder / "Bare.colors").write_text("[Colors:Window]\nBackgroundNormal=1,1,1\nForegroundNormal=2,2,2\n")
    kind = pickers.kind("color_scheme")
    items = {i.id: i for i in kind.items()}
    image = kind.thumbnail(items["Test"], SIZE, 1.0, None)
    assert (image.width(), image.height()) == (176, 110)
    assert pixel(image, 0.65, 0.05) == QColor(0, 100, 0)  # title bar
    assert pixel(image, 0.55, 0.28) == QColor(10, 20, 30)  # window area
    assert pixel(image, 0.9, 0.55) == QColor(0x10, 0x20, 0x30)  # inside the view, right of the rows' text
    colors = {pixel(image, x / 100, 0.70).name() for x in range(10, 90)}
    assert "#c80000" in colors  # the highlighted row
    assert "#0000c8" not in colors
    assert QColor(0, 0, 200).name() in {pixel(image, x / 100, 0.9).name() for x in range(62, 95)}
    bare = kind.thumbnail(items["Bare"], SIZE, 2.0, None)  # missing keys: Breeze values
    assert not bare.isNull() and bare.width() == 352
    assert pixel(bare, 0.65, 0.05) == QColor(227, 229, 231)  # Breeze Light title bar
    assert pixel(bare, 0.55, 0.28) == QColor(1, 1, 1)


# Plasma styles ---------------------------------------------------------------

CLOCK = """<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
<style id="current-color-scheme" type="text/css">.ColorScheme-Text {color:#000000;}</style>
<circle id="ClockFace" cx="100" cy="100" r="90" class="ColorScheme-Text" style="fill:currentColor"/>
</svg>"""

FRAME = """<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">
<style id="current-color-scheme" type="text/css">.ColorScheme-Background {color:#000000;}</style>
<g class="ColorScheme-Background" style="fill:currentColor">
<rect id="topleft" x="0" y="0" width="10" height="10"/>
<rect id="topright" x="30" y="0" width="10" height="10"/>
<rect id="bottomleft" x="0" y="30" width="10" height="10"/>
<rect id="bottomright" x="30" y="30" width="10" height="10"/>
<rect id="top" x="10" y="0" width="20" height="10"/><rect id="bottom" x="10" y="30" width="20" height="10"/>
<rect id="left" x="0" y="10" width="10" height="20"/><rect id="right" x="30" y="10" width="10" height="20"/>
<rect id="center" x="10" y="10" width="20" height="20"/></g></svg>"""


def make_style(root, name, colors=None, frame=True, svgz=False, meta=True):
    folder = root / name
    folder.mkdir(parents=True)
    if meta:
        (folder / "metadata.json").write_text(
            json.dumps({"KPlugin": {"Name": name.title(), "Description": "d"}})
        )
    if colors:
        (folder / "colors").write_text(colors)
    if frame:
        (folder / "dialogs").mkdir()
        data = FRAME.encode()
        if svgz:
            (folder / "dialogs/background.svgz").write_bytes(gzip.compress(data))
        else:
            (folder / "dialogs/background.svg").write_bytes(data)
    return folder


def roles(window, accent="#3daee9"):
    return {"window": window, "accent": accent, "text": "#ffffff", "view": "#111111", "button": "#222222"}


def test_plasma_style_items(home):
    root = share(home, "plasma/desktoptheme")
    make_style(root, "default")
    make_style(root, "own", colors="[Colors:Window]\nBackgroundNormal=1,2,3\n")
    make_style(root, "nometa", meta=False)
    (root / "default/metadata.json").write_text("{broken")
    kind = pickers.kind("plasma_style")
    items = {i.id: i for i in kind.items()}
    assert set(items) == {"own"}  # broken and metadata-less styles are skipped
    (root / "default/metadata.json").write_text(json.dumps({"KPlugin": {"Name": "Breeze"}}))
    items = {i.id: i for i in kind.items()}
    assert items["default"].extra["follows_color_scheme"] is True
    assert items["default"].description == "Follows color scheme"
    assert items["own"].extra["follows_color_scheme"] is False
    assert items["own"].description == "d"
    assert kind.scheme_dependent


@pytest.mark.parametrize("svgz", [False, True])
def test_plasma_style_follows_given_colors(home, svgz):
    root = share(home, "plasma/desktoptheme")
    make_style(root, "default", frame=False)
    make_style(root, "mine", svgz=svgz)  # no colors file: follows the scheme
    kind = pickers.kind("plasma_style")
    item = next(i for i in kind.items() if i.id == "mine")
    one = kind.thumbnail(item, SIZE, 1.0, roles("#aa0000"))
    two = kind.thumbnail(item, SIZE, 1.0, roles("#0000bb"))
    assert pixel(one, 0.5, 0.5) == QColor("#aa0000")
    assert pixel(two, 0.5, 0.5) == QColor("#0000bb")


def test_plasma_style_with_own_colors_ignores_given_colors(home):
    root = share(home, "plasma/desktoptheme")
    make_style(root, "default", frame=False)
    make_style(
        root, "own", colors="[Colors:Window]\nBackgroundNormal=0,128,0\nForegroundNormal=255,255,255\n"
    )
    kind = pickers.kind("plasma_style")
    item = next(i for i in kind.items() if i.id == "own")
    image = kind.thumbnail(item, SIZE, 1.0, roles("#aa0000"))
    assert pixel(image, 0.5, 0.5) == QColor(0, 128, 0)


def test_plasma_style_clock_and_fallback_to_default(home):
    root = share(home, "plasma/desktoptheme")
    default = make_style(root, "default", frame=False)
    (default / "widgets").mkdir()
    (default / "widgets/clock.svg").write_text(CLOCK)
    make_style(root, "bare", frame=False)  # has nothing: everything comes from default
    kind = pickers.kind("plasma_style")
    item = next(i for i in kind.items() if i.id == "bare")
    image = kind.thumbnail(item, SIZE, 1.0, {"text": "#00aa00"})
    assert pixel(image, 0.5, 0.5) == QColor("#00aa00")  # the face, recolored
    assert pixel(image, 0.02, 0.02).alpha() == 0
    nothing = share(home, "plasma/desktoptheme") / "default"
    (nothing / "widgets/clock.svg").unlink()
    placeholder = kind.thumbnail(item, SIZE, 1.0, None)
    assert not placeholder.isNull()


def test_clock_hands_turn_around_their_center(home):
    from PySide6.QtGui import QPainter
    from PySide6.QtSvg import QSvgRenderer

    svg = QSvgRenderer(
        b"""<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
        <circle id="ClockFace" cx="100" cy="100" r="95" style="fill:#ffffff"/>
        <rect id="MinuteHand" x="95" y="100" width="10" height="80" style="fill:#ff0000"/>
        </svg>"""
    )
    # The minute hand is drawn pointing down; hands are rotated 180 degrees plus the time,
    # about the middle of their picture, so at minute 0 it points up from the center.
    from PySide6.QtCore import QRectF

    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    image.fill(QColor("black"))
    painter = QPainter(image)
    plasmastyles.draw_clock(painter, svg, QRectF(0, 0, 200, 200), hours=0, minutes=0)
    painter.end()
    assert QColor(image.pixel(100, 60)) != QColor("black")
    assert QColor(image.pixel(100, 140)) != QColor("black")  # the picture is centered on the pivot


# Splash screens -------------------------------------------------------------


def test_splash_items_and_thumbnails(home):
    root = share(home, "plasma/look-and-feel")
    make_theme(root, "withsplash", previews=["preview.png", "splash.png"], splash=True)
    png(root / "withsplash/contents/previews/splash.png", "#0000ff", (160, 90))
    make_theme(root, "fallback", previews=["preview.png"], splash=True)
    make_theme(root, "nosplash", previews=["preview.png"])
    kind = pickers.kind("splash")
    items = kind.items()
    assert [i.id for i in items] == ["None", "fallback", "withsplash"]
    assert items[0].name == "None"
    none = kind.thumbnail(items[0], SIZE, 1.0, None)
    assert not none.isNull()
    assert pixel(kind.thumbnail(items[2], SIZE, 1.0, None), 0.5, 0.5) == QColor("#0000ff")
    assert pixel(kind.thumbnail(items[1], SIZE, 1.0, None), 0.5, 0.5) == QColor("#00ff00")


# System sounds --------------------------------------------------------------


def test_sound_themes(home):
    root = share(home, "sounds")
    ocean = root / "ocean"
    (ocean / "stereo").mkdir(parents=True)
    (ocean / "index.theme").write_text(
        "[Sound Theme]\nName=Ocean\nName[sv]=Hav\nComment=Waves\nDirectories=stereo\nExample=demo\n"
    )
    (ocean / "stereo/other.ogg").write_text("")
    (ocean / "stereo/demo.oga").write_text("")
    plain = root / "plain"
    (plain / "stereo").mkdir(parents=True)
    (plain / "index.theme").write_text("[Sound Theme]\nName=Plain\nDirectories=stereo\n")
    (plain / "stereo/zzz.wav").write_text("")
    (plain / "stereo/aaa.wav").write_text("")
    hidden = root / "hidden"
    hidden.mkdir()
    (hidden / "index.theme").write_text("[Sound Theme]\nName=Hidden\nHidden=true\n")
    (root / "noindex").mkdir()
    (root / "icons-like").mkdir()
    (root / "icons-like/index.theme").write_text("[Icon Theme]\nName=Not sounds\n")
    loose = root / "loose.ogg"
    loose.write_text("")
    kind = pickers.kind("sounds")
    items = kind.items()
    assert [(i.id, i.name) for i in items] == [("ocean", "Ocean"), ("plain", "Plain")]
    assert items[0].description == "Waves"
    assert items[0].extra["sample"] == ocean / "stereo/demo.oga"
    assert items[1].extra["sample"] == plain / "stereo/aaa.wav"
    image = kind.thumbnail(items[0], SIZE, 2.0, None)
    assert (image.width(), image.height()) == (352, 220)
    assert not kind.gui_thread_only


def test_kinds_are_registered():
    keys = {k.key for k in pickers.kinds()}
    assert {"global_theme", "color_scheme", "plasma_style", "splash", "sounds"} <= keys
    assert all(k.title for k in pickers.kinds())
