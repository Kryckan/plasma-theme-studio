# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The frame editor: own artwork for the frames of the Plasma style, its checking, the theme file,
the archive and the page. No test starts Inkscape; the runner is a fake that records what it was asked."""

import re
import zipfile

import pytest

from plasma_theme_studio import archive
from plasma_theme_studio.generators import artwork, plasmastyle
from plasma_theme_studio.model.theme import ARTWORK_KEYS, FIELD_BY_ID, Theme, artwork_folder

EXTRA = '<rect id="extra" width="1" height="1" fill="#ff0000"/>'


def base():
    return Theme.from_preset("breeze-dark")


def generated(theme, frame="panel"):
    return plasmastyle.frame_svg(theme, frame)


def required(frame="panel"):
    return plasmastyle.required_ids(frame)


def saved_with_artwork(tmp_path, text=None, frame="panel"):
    theme = base()
    theme.set("panel", "style", "generated")
    path = tmp_path / "mine.toml"
    folder = artwork_folder(path)
    folder.mkdir()
    (folder / f"{frame}.svg").write_text(text if text is not None else generated(theme, frame))
    theme.set("artwork", frame, f"{folder.name}/{frame}.svg")
    theme.save(path)
    return theme, path


# ---- checking a picture


def test_generated_frame_passes_the_check():
    text, problems = artwork.check(generated(base()).encode(), required())
    assert problems == [] and text


def test_missing_ids_are_listed_in_plain_words():
    raw = generated(base()).replace('id="center"', 'id="middle"').encode()
    text, problems = artwork.check(raw, required())
    assert text is None
    assert any("center" in str(p) and "lacks parts" in str(p) for p in problems)


@pytest.mark.parametrize(
    "extra",
    [
        "<script>alert(1)</script>",
        "<text x='0' y='0'>hi</text>",
        "<image href='file:///etc/passwd'/>",
        "<rect width='1' height='1' onclick='x()'/>",
        "<rect width='1' height='1' fill='url(http://example.com/x)'/>",
        "<style>@import 'http://example.com/x.css';</style>",
        "<use xlink:href='other.svg#a' xmlns:xlink='http://www.w3.org/1999/xlink'/>",
    ],
)
def test_dangerous_content_is_refused(extra):
    raw = generated(base()).replace("</svg>", extra + "</svg>").encode()
    text, problems = artwork.check(raw, required())
    assert text is None and problems


@pytest.mark.parametrize(
    "raw",
    [
        b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg"/>',
        b"<svg xmlns='http://www.w3.org/2000/svg'><?pi x?></svg>",
        b"not xml at all",
        b"\xff\xfe\x00",
        b"<html/>",
    ],
)
def test_not_a_clean_svg_is_refused(raw):
    text, problems = artwork.check(raw, frozenset())
    assert text is None and problems


def test_size_and_depth_limits():
    text, problems = artwork.check(b" " * (artwork.ARTWORK_LIMIT + 1), frozenset())
    assert text is None and problems
    deep = "<svg xmlns='http://www.w3.org/2000/svg'>" + "<g>" * 100 + "</g>" * 100 + "</svg>"
    assert artwork.check(deep.encode(), frozenset())[0] is None


def test_declared_size_decides_nothing():
    raw = re.sub(r'width="[^"]*"', 'width="99999999"', generated(base()), count=1).encode()
    text, problems = artwork.check(raw, required())
    assert problems == []  # accepted, and nothing was allocated for it


# ---- the generated style


def test_own_artwork_is_used_and_changes_the_style_id(tmp_path):
    theme, _path = saved_with_artwork(tmp_path)
    plain = base()
    plain.set("panel", "style", "generated")
    text = generated(theme).replace("</svg>", EXTRA + "</svg>")
    folder = artwork_folder(tmp_path / "mine.toml")
    (folder / "panel.svg").write_text(text)
    assert plasmastyle.style_id(theme) != plasmastyle.style_id(plain)
    files = {str(f.path): f.content for f in plasmastyle.PlasmaStyleGenerator().files(theme)}
    assert any("#ff0000" in str(c) and artwork.OWN_MARK in str(c) for c in files.values())
    assert "own artwork" in plasmastyle.status_words(theme)


def test_unusable_artwork_leaves_the_frame_generated(tmp_path, runner):
    theme, _path = saved_with_artwork(tmp_path, "<svg xmlns='http://www.w3.org/2000/svg'/>")
    plain = base()
    plain.set("panel", "style", "generated")
    assert plasmastyle.style_id(theme) == plasmastyle.style_id(plain)
    problems = plasmastyle.artwork_problems(theme)
    assert problems and "center" in " ".join(str(p) for p in problems)
    assert any("center" in str(w) for w in plasmastyle.PlasmaStyleGenerator().warnings(theme, runner))


def test_artwork_outside_the_folder_is_not_found(tmp_path):
    theme, _path = saved_with_artwork(tmp_path)
    (tmp_path / "x.svg").write_text(generated(theme))
    theme.base_dir = tmp_path
    theme._values[("artwork", "panel")] = "../x.svg"
    art = artwork.load(theme, "panel", required())
    assert not art.usable and art.problems


# ---- the theme file


@pytest.mark.parametrize(
    "name", ["../x.svg", "/etc/x.svg", "a\\b.svg", "a/../b.svg", "x.png", "", "x" * 300 + ".svg"]
)
def test_hostile_artwork_names_are_refused(name):
    problem = FIELD_BY_ID[("artwork", "panel")]
    from plasma_theme_studio.model import theme as model

    assert model._check_form(problem, name) is not None or name == ""


def test_artwork_is_optional_and_round_trips(tmp_path):
    theme, path = saved_with_artwork(tmp_path)
    again = Theme.load(path)
    assert again.get("artwork", "panel") == "mine-artwork/panel.svg"
    assert again.get("artwork", "popups") is None
    assert again.base_dir == tmp_path
    assert again.copy().base_dir == tmp_path


def test_save_in_another_folder_copies_the_artwork(tmp_path):
    theme, _path = saved_with_artwork(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    theme.save(other / "copy.toml")
    assert (other / "mine-artwork" / "panel.svg").is_file()
    assert Theme.load(other / "copy.toml").get("artwork", "panel") == "mine-artwork/panel.svg"


# ---- the archive


def test_archive_holds_the_artwork_and_import_puts_it_back(tmp_path):
    theme, _path = saved_with_artwork(tmp_path)
    file = tmp_path / "out.zip"
    archive.export_theme(theme, file)
    with zipfile.ZipFile(file) as z:
        assert "assets/panel.svg" in z.namelist()
    imported = archive.import_theme(file)
    target = tmp_path / "elsewhere" / "got.toml"
    target.parent.mkdir()
    imported.save(target)
    assert (target.parent / "got-artwork" / "panel.svg").read_text() == generated(theme)
    assert Theme.load(target).get("artwork", "panel") == "got-artwork/panel.svg"


def test_archive_artwork_that_is_not_usable_is_dropped(tmp_path):
    theme, _path = saved_with_artwork(tmp_path)
    file = tmp_path / "out.zip"
    archive.export_theme(theme, file)
    with zipfile.ZipFile(file) as z:
        members = {n: z.read(n) for n in z.namelist()}
    members["assets/panel.svg"] = b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>"
    with zipfile.ZipFile(file, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    imported = archive.import_theme(file)
    imported.save(tmp_path / "bad.toml")
    assert not (tmp_path / "bad-artwork").exists()
    assert Theme.load(tmp_path / "bad.toml").get("artwork", "panel") is None


@pytest.mark.parametrize(
    "name", ["../panel.svg", "/panel.svg", "assets/../panel.svg", "assets/x/y.svg", "assets/panel.svg\\x"]
)
def test_hostile_archive_member_names_are_refused(tmp_path, name):
    theme, _path = saved_with_artwork(tmp_path)
    file = tmp_path / "out.zip"
    archive.export_theme(theme, file)
    with zipfile.ZipFile(file, "a") as z:
        z.writestr(name, b"<svg/>")
    with pytest.raises(archive.ArchiveError):
        archive.import_theme(file)


def test_oversized_artwork_member_is_refused(tmp_path):
    theme, _path = saved_with_artwork(tmp_path)
    file = tmp_path / "out.zip"
    archive.export_theme(theme, file)
    with zipfile.ZipFile(file, "a", zipfile.ZIP_DEFLATED) as z:
        z.writestr("assets/popups.svg", b"x" * (archive.MAX_ASSET + 1))
    with pytest.raises(archive.ArchiveError):
        archive.import_theme(file)


# ---- the page


@pytest.fixture
def window(app, home, desktop_runner, monkeypatch):
    from plasma_theme_studio.ui.main_window import MainWindow

    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(desktop_runner)
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


def editor(window):
    window.edit(FIELD_BY_ID[("panel", "style")], "generated")
    window.show_page("plasma_style")
    window.refresh()
    return window.page("plasma_style").frame_editor


def test_four_cards_and_values(window):
    fe = editor(window)
    assert [c for c in fe.sources] == list(ARTWORK_KEYS)
    fe.choose("popups")
    assert "px" in fe.value_labels["radius"].text()
    assert not fe.thumbnail("tooltips").isNull()


def test_nine_slice_switch(window):
    fe = editor(window)
    fe.guides.setChecked(True)
    assert fe.view.guides is True
    fe.view.grab()  # draws with the guides
    fe.guides.setChecked(False)
    assert fe.view.guides is False


def test_inkscape_missing_turns_the_button_off_with_a_sentence(window):
    window.runner.missing.add("inkscape")
    fe = editor(window)
    assert not fe.open_button.isEnabled()
    assert "Inkscape" in fe.why.text() and fe.why.text().endswith(".")
    assert window.runner.launched == []


def test_unsaved_theme_asks_to_save_first(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    fe = editor(window)
    asked = []
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.No
    )
    assert fe.open_in_inkscape() is False
    assert asked and window.runner.launched == []


def test_open_writes_the_file_and_launches_the_fake(window, tmp_path):
    window.theme.save(tmp_path / "t.toml")
    window.path = tmp_path / "t.toml"
    fe = editor(window)
    assert fe.open_in_inkscape() is True
    target = tmp_path / "t-artwork" / "panel.svg"
    assert target.is_file()
    assert window.runner.launched[-1] == ["inkscape", str(target)]


def test_saving_in_inkscape_makes_it_own_artwork_and_back_forgets_it(window, tmp_path):
    window.theme.save(tmp_path / "t.toml")
    window.path = tmp_path / "t.toml"
    fe = editor(window)
    fe.open_in_inkscape()
    target = tmp_path / "t-artwork" / "panel.svg"
    target.write_text(target.read_text().replace("</svg>", EXTRA + "</svg>"))
    fe.stamps["panel"] = (0, 0)
    fe.check_files()
    assert window.theme.get("artwork", "panel") == "t-artwork/panel.svg"
    assert fe.sources["panel"][2].usable
    fe.back_to_generated()
    assert window.theme.get("artwork", "panel") is None
    assert target.is_file() and str(target) in fe.source_note.text()
    window.undo_stack.undo()
    assert window.theme.get("artwork", "panel") == "t-artwork/panel.svg"


def test_bad_artwork_is_explained_on_the_page(window, tmp_path):
    window.theme.save(tmp_path / "t.toml")
    window.path = tmp_path / "t.toml"
    folder = artwork_folder(window.path)
    folder.mkdir()
    (folder / "panel.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    window.edit(FIELD_BY_ID[("artwork", "panel")], "t-artwork/panel.svg")
    fe = editor(window)
    assert not fe.problems.isHidden()
    assert fe.back_button.isVisibleTo(fe)


def test_open_in_inkscape_after_back_keeps_the_picture_on_disk(window, tmp_path):
    window.theme.save(tmp_path / "t.toml")
    window.path = tmp_path / "t.toml"
    fe = editor(window)
    fe.open_in_inkscape()
    target = tmp_path / "t-artwork" / "panel.svg"
    target.write_text(target.read_text().replace("</svg>", EXTRA + "</svg>"))
    fe.stamps["panel"] = (0, 0)
    fe.check_files()
    fe.back_to_generated()
    drawn = target.read_text()
    assert fe.open_in_inkscape() is True
    assert target.read_text() == drawn and EXTRA in drawn
    assert window.theme.get("artwork", "panel") == "t-artwork/panel.svg"
