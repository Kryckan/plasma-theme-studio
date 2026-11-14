# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import struct

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage  # noqa: E402

from plasma_theme_studio.pickers import cursors, icons, xcursor  # noqa: E402

SIZE = QSize(176, 110)
SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" fill="{}"/></svg>'
)


@pytest.fixture(autouse=True)
def fresh(app):
    icons.clear_caches()
    yield
    icons.clear_caches()


def theme(home, name, body="", dirs="", extra=""):
    folder = home / ".local/share/icons" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.theme").write_text(f"[Icon Theme]\nName={name}\n{extra}\nDirectories={dirs}\n{body}\n")
    return folder


def png(path, color, side=32):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(side, side, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    assert image.save(str(path))


def centre(image):
    return QColor(image.pixelColor(image.width() // 2, image.height() // 2))


# icons -------------------------------------------------------------------


def test_icon_list_rules(home, app):
    theme(home, "Good", "[places/32]\nSize=32\nType=Fixed\n", "places/32")
    theme(home, "Gone", dirs="places/32", extra="Hidden=true")
    theme(home, "hicolor", dirs="places/32")
    theme(home, "Adwaita", dirs="places/32")
    cursor_only = home / ".local/share/icons/OnlyCursors"
    (cursor_only / "cursors").mkdir(parents=True)
    (cursor_only / "index.theme").write_text("[Icon Theme]\nName=Cursors\n")
    items = icons.IconThemes().items()
    assert [i.id for i in items] == ["Good"]
    assert items[0].user and items[0].path.name == "Good"


def test_home_theme_beats_system_theme(home, app):
    theme(home, "Same", extra="Comment=home", dirs="a")
    system = home / "system/share/icons/Same"
    system.mkdir(parents=True)
    (system / "index.theme").write_text("[Icon Theme]\nName=Same\nDirectories=a\nComment=system\n")
    (items,) = icons.IconThemes().items()
    assert items.user and items.description == "home"


def test_inherited_icon_and_hicolor(home, app):
    child = theme(home, "Child", "[a/32]\nSize=32\nType=Fixed\n", "a/32", "Inherits=Parent")
    parent = theme(home, "Parent", "[b/32]\nSize=32\nType=Fixed\n", "b/32")
    hicolor = theme(home, "hicolor", "[c/32]\nSize=32\nType=Fixed\n", "c/32")
    png(parent / "b/32/folder.png", "#ff0000")
    png(hicolor / "c/32/configure.png", "#00ff00")
    png(child / "a/32/user-trash.png", "#0000ff")
    finder = icons.Finder()
    assert finder.find(child, ["folder"], 32) == parent / "b/32/folder.png"
    assert finder.find(child, ["configure"], 32) == hicolor / "c/32/configure.png"
    assert finder.find(child, ["user-trash"], 32) == child / "a/32/user-trash.png"
    assert finder.find(child, ["nothing"], 32) is None


def test_size_matching_and_odd_values(home, app):
    body = (
        "[a/16]\nSize=12px\nType=Fixed\n[a/48]\nSize=48\nType=Fixed\n[a/96@2]\nSize=48\nScale=2\nType=Fixed\n"
    )
    folder = theme(home, "Sizes", body, "a/16,a/48,a/96@2")
    for sub in ("a/16", "a/48", "a/96@2"):
        png(folder / sub / "folder.png", "#ffffff")
    finder = icons.Finder()
    assert finder.find(folder, ["folder"], 44) == folder / "a/48/folder.png"
    assert finder.find(folder, ["folder"], 10) == folder / "a/16/folder.png"  # "12px" reads as 12
    assert finder.find(folder, ["folder"], 96, 2) == folder / "a/96@2/folder.png"
    assert finder.find(folder, ["folder"], 48, 1) == folder / "a/48/folder.png"  # not a 2x directory


def test_svg_and_png_thumbnail_pixels(home, app):
    body = "[a/32]\nSize=32\nType=Fixed\n[s]\nSize=32\nType=Scalable\nMinSize=8\nMaxSize=256\n"
    folder = theme(home, "Mixed", body, "a/32,s")
    png(folder / "a/32/folder.png", "#ff0000")
    (folder / "s").mkdir()
    (folder / "s/user-trash.svg").write_text(SVG.format("#0000ff"))
    item = icons.IconThemes().items()[0]
    image = icons.IconThemes().thumbnail(item, SIZE, 1.0, None)
    assert (image.width(), image.height()) == (176, 110)
    cell_w, cell_h = 176 / 3, 110 / 2
    # slot 1 is the folder (png), slot 3 the trash (svg); empty slots stay transparent
    assert image.pixelColor(int(cell_w * 1.5), int(cell_h * 0.5)) == QColor("#ff0000")
    assert image.pixelColor(int(cell_w * 0.5), int(cell_h * 1.5)) == QColor("#0000ff")
    assert image.pixelColor(int(cell_w * 0.5), int(cell_h * 0.5)).alpha() == 0
    big = icons.IconThemes().thumbnail(item, SIZE, 2.0, None)
    assert (big.width(), big.height(), big.devicePixelRatio()) == (352, 220, 2.0)


def test_recolor_follows_the_scheme(home, app):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><defs>'
        '<style type="text/css" id="current-color-scheme">.ColorScheme-Text{color:#000000;}</style></defs>'
        '<rect width="32" height="32" style="fill:currentColor" class="ColorScheme-Text"/></svg>'
    )
    folder = theme(home, "Mono", "[s]\nSize=32\nType=Scalable\nMinSize=8\nMaxSize=64\n", "s")
    (folder / "s").mkdir()
    (folder / "s/folder.svg").write_text(svg)
    item = icons.IconThemes().items()[0]
    kind = icons.IconThemes()
    image = kind.thumbnail(item, SIZE, 1.0, {"text": "#fcfcfc", "accent": "#3daee9"})
    assert image.pixelColor(int(176 / 3 * 1.5), int(110 / 4)) == QColor("#fcfcfc")
    assert b"#fcfcfc" in icons.recolor(svg.encode(), {"text": "#fcfcfc"})
    assert icons.recolor(svg.encode(), None) == svg.encode()


def test_icon_theme_without_icons_or_folder(home, app):
    folder = theme(home, "Empty", "[a/32]\nSize=32\nType=Fixed\n", "a/32")
    item = icons.IconThemes().items()[0]
    assert icons.IconThemes().thumbnail(item, SIZE, 1.0, None).isNull()
    gone = item.__class__("x", "x", path=home / "nowhere")
    assert icons.IconThemes().thumbnail(gone, SIZE, 1.0, None).isNull()
    assert folder.is_dir()


def test_icon_links_cannot_leave_the_icon_folders(home, app):
    folder = theme(home, "Link", "[a/32]\nSize=32\nType=Fixed\n", "a/32")
    outside = home / "elsewhere/folder.png"
    png(outside, "#ff0000")
    (folder / "a/32").mkdir(parents=True)
    (folder / "a/32/folder.png").symlink_to(outside)
    assert icons.Finder().find(folder, ["folder"], 32) is None


def test_directory_listings_are_kept(home, app, monkeypatch):
    folder = theme(home, "Kept", "[a/32]\nSize=32\nType=Fixed\n", "a/32")
    png(folder / "a/32/folder.png", "#ff0000")
    finder = icons.Finder()
    assert finder.find(folder, ["folder"], 32)
    calls = []
    monkeypatch.setattr(icons.os, "scandir", lambda *a: calls.append(a) or [])
    assert finder.find(folder, ["folder"], 32)
    assert not calls


# xcursor -----------------------------------------------------------------


def encode(images, ntoc_extra=0):
    """images: (nominal, width, height, xhot, yhot, ARGB int) one chunk each, in order."""
    count = len(images)
    head = struct.pack("<4sIII", b"Xcur", 16, 0x10000, count)
    position = 16 + 12 * count
    toc, chunks = b"", b""
    for nominal, w, h, xh, yh, argb in images:
        toc += struct.pack("<III", 0xFFFD0002, nominal, position + len(chunks))
        chunks += struct.pack("<IIIIIIIII", 36, 0xFFFD0002, nominal, 1, w, h, xh, yh, 50)
        chunks += struct.pack("<I", argb) * (w * h)
    return head + toc + chunks


def test_xcursor_reads_the_nearest_size_and_first_frame(tmp_path):
    path = tmp_path / "left_ptr"
    path.write_bytes(
        encode(
            [
                (24, 4, 4, 1, 2, 0xFFFF0000),
                (24, 4, 4, 0, 0, 0xFF00FF00),  # second frame of an animation
                (48, 8, 8, 3, 3, 0xFF0000FF),
            ]
        )
    )
    assert xcursor.nominal_sizes(path) == [24, 48]
    near = xcursor.read_image(path, 30)
    assert (near.nominal, near.width, near.xhot, near.yhot) == (24, 4, 1, 2)
    image = near.to_qimage()
    assert image.pixelColor(0, 0) == QColor("#ff0000")
    assert xcursor.read_image(path, 40).nominal == 48


def test_xcursor_premultiplied_pixels(tmp_path, app):
    path = tmp_path / "c"
    path.write_bytes(encode([(24, 2, 2, 0, 0, 0x80800000)]))  # half transparent premultiplied red
    color = xcursor.read_image(path, 24).to_qimage().pixelColor(0, 0)
    assert color.alpha() == 128 and color.red() == 255


@pytest.mark.parametrize("cut", [0, 3, 15, 20, 40, 60])
def test_xcursor_truncated_file_is_refused(tmp_path, cut):
    data = encode([(24, 4, 4, 1, 1, 0xFFFFFFFF)])
    path = tmp_path / "c"
    path.write_bytes(data[:cut])
    assert xcursor.read_image(path, 24) is None


def test_xcursor_hostile_files(tmp_path):
    path = tmp_path / "c"
    path.write_bytes(b"Xcur" + struct.pack("<III", 16, 0x10000, 0xFFFFFFFF))
    assert xcursor.read_image(path, 24) is None and xcursor.nominal_sizes(path) == []
    huge = struct.pack("<4sIII", b"Xcur", 16, 0x10000, 1) + struct.pack("<III", 0xFFFD0002, 24, 28)
    huge += struct.pack("<IIIIIIIII", 36, 0xFFFD0002, 24, 1, 60000, 60000, 0, 0, 50) + b"\0" * 64
    path.write_bytes(huge)
    assert xcursor.read_image(path, 24) is None
    path.write_bytes(b"not a cursor at all, really")
    assert xcursor.read_image(path, 24) is None
    assert xcursor.read_image(tmp_path / "missing", 24) is None
    assert xcursor.read_image(tmp_path, 24) is None  # a folder


# cursors -----------------------------------------------------------------


def cursor_theme(home, name, files, extra=""):
    folder = home / ".local/share/icons" / name
    (folder / "cursors").mkdir(parents=True, exist_ok=True)
    (folder / "index.theme").write_text(f"[Icon Theme]\nName[sv]=Svensk\nName=Nice {name}\n{extra}\n")
    for file, data in files.items():
        (folder / "cursors" / file).write_bytes(data)
    return folder


def test_cursor_list_and_sizes(home, app):
    red = encode([(24, 4, 4, 0, 0, 0xFFFF0000), (36, 6, 6, 0, 0, 0xFFFF0000)])
    cursor_theme(home, "Plain", {"left_ptr": red})
    cursor_theme(home, "Hid", {"left_ptr": red}, "Hidden=true")
    (home / ".local/share/icons/NoCursors").mkdir()
    (items,) = [i for i in cursors.CursorThemes().items()]
    assert items.id == "Plain" and items.name in ("Nice Plain", "Svensk")
    assert items.extra["sizes"] == [24, 36]


def test_symlinked_names_and_aliases_and_pixels(home, app):
    blue = encode([(24, 24, 24, 0, 0, 0xFF0000FF)])
    folder = cursor_theme(home, "Links", {"default": blue})
    (folder / "cursors/left_ptr_link").symlink_to("default")
    kind = cursors.CursorThemes()
    (item,) = kind.items()
    assert item.extra["sizes"] == [24]  # "left_ptr" is not there: the alias "default" is
    image = kind.thumbnail(item, SIZE, 1.0, None)
    assert (image.width(), image.height()) == (176, 110)
    assert image.pixelColor(22, 27) == QColor("#0000ff")  # first cell, centre
    assert image.pixelColor(66, 27).alpha() == 0  # no pointer hand in this theme
    big = kind.thumbnail(item, SIZE, 2.0, None)
    assert (big.width(), big.height()) == (352, 220)
    assert big.pixelColor(44, 54) == QColor("#0000ff")


def test_cursor_inherits_and_link_out_of_the_folders(home, app):
    green = encode([(24, 8, 8, 0, 0, 0xFF00FF00)])
    cursor_theme(home, "Parent", {"left_ptr": green})
    child = cursor_theme(home, "Child", {}, "Inherits=Parent")
    outside = home / "outside"
    outside.write_bytes(green)
    (child / "cursors/pointer").symlink_to(outside)
    finder = cursors.Finder()
    assert finder.find(child, ["left_ptr"])[1].parent.parent.name == "Parent"
    assert finder.find(child, ["pointer"]) is None


def test_truncated_cursor_file_gives_no_picture(home, app):
    data = encode([(24, 4, 4, 0, 0, 0xFFFFFFFF)])
    cursor_theme(home, "Broken", {"left_ptr": data[:50]})
    kind = cursors.CursorThemes()
    (item,) = kind.items()
    assert kind.thumbnail(item, SIZE, 1.0, None).isNull()


def test_svg_cursor_theme(home, app):
    folder = home / ".local/share/icons/Vector"
    sub = folder / "cursors_scalable/left_ptr"
    sub.mkdir(parents=True)
    (folder / "index.theme").write_text("[Icon Theme]\nName=Vector\n")
    (sub / "left_ptr.svg").write_text(SVG.format("#ff00ff"))
    (sub / "metadata.json").write_text(
        '[{"filename": "left_ptr.svg", "hotspot_x": 1, "hotspot_y": 1, "nominal_size": 24}]'
    )
    kind = cursors.CursorThemes()
    (item,) = kind.items()
    assert item.extra["sizes"] == list(cursors.SCALABLE_SIZES) and item.extra["scalable"]
    image = kind.thumbnail(item, SIZE, 1.0, None)
    assert image.pixelColor(22, 27) == QColor("#ff00ff")
    (sub / "metadata.json").write_text("[]")
    assert kind.thumbnail(item, SIZE, 1.0, None).isNull()


def test_kinds_are_found_by_the_framework(app):
    from plasma_theme_studio import pickers

    assert pickers.kind("icons").scheme_dependent
    assert pickers.kind("cursors") is not None
    assert str(pickers.kind("cursors").title) == "Pointers"
    assert QGuiApplication.instance() is not None
