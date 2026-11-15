# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests for the repair of the third build: artwork names and files, hostile pictures,
what an undo puts back, the Rofi font, the notes and the banner."""

import os
import time
import zipfile

import pytest

from plasma_theme_studio import archive, paths
from plasma_theme_studio.apply import engine, sidefiles
from plasma_theme_studio.apply import snapshot as snapshots
from plasma_theme_studio.generators import artwork, panellayout, plasmastyle, rofi, windowframe
from plasma_theme_studio.model.theme import Theme, artwork_folder

# ---- artwork names


def with_artwork(tmp_path, stem):
    """A theme file called `stem`.toml whose theme came out of an archive with one own artwork."""
    source = Theme.from_preset("breeze-dark")
    source.set("panel", "style", "generated")
    folder = tmp_path / "src"
    folder.mkdir(exist_ok=True)
    (folder / "a-artwork").mkdir(exist_ok=True)
    (folder / "a-artwork/panel.svg").write_text(plasmastyle.frame_svg(source, "panel"))
    source.set("artwork", "panel", "a-artwork/panel.svg")
    source.save(folder / "a.toml")
    archive.export_theme(Theme.load(folder / "a.toml"), tmp_path / "x.ptstheme")
    imported = archive.import_theme(tmp_path / "x.ptstheme")
    target = tmp_path / "out"
    target.mkdir(exist_ok=True)
    return imported, target / f"{stem}.toml"


@pytest.mark.parametrize("stem", ["ok", "My theme (dark)", "it's", "a..b", "Tema åäö", "x" * 150, "---"])
def test_a_theme_saved_after_an_import_loads_again(tmp_path, stem):
    imported, file = with_artwork(tmp_path, stem)
    imported.save(file)
    loaded = Theme.load(file)
    assert loaded.get("artwork", "panel")
    assert plasmastyle.own_artwork(loaded, "panel").usable


def test_a_plain_folder_name_stays_as_it_was(tmp_path):
    assert artwork_folder(tmp_path / "my.toml").name == "my-artwork"
    assert artwork_folder(tmp_path / "My theme.toml").name == "My theme-artwork"


def test_an_import_never_replaces_a_picture_that_is_already_there(tmp_path):
    imported, file = with_artwork(tmp_path, "mine")
    folder = artwork_folder(file)
    folder.mkdir()
    (folder / "panel.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")  # the user's own
    imported.save(file)
    assert (folder / "panel.svg").read_text() == "<svg xmlns='http://www.w3.org/2000/svg'/>"
    name = Theme.load(file).get("artwork", "panel")
    assert name != "mine-artwork/panel.svg" and (file.parent / name).is_file()


def test_saving_the_same_import_twice_keeps_one_file(tmp_path):
    imported, file = with_artwork(tmp_path, "mine")
    imported.save(file)
    again = archive.import_theme(tmp_path / "x.ptstheme")
    again.save(file)
    assert sorted(p.name for p in artwork_folder(file).iterdir()) == ["panel.svg"]


def test_a_plain_theme_file_keeps_the_artwork_it_names(tmp_path):
    theme = Theme.from_preset("breeze-dark")
    theme.set("artwork", "panel", "mine-artwork/panel.svg")
    (tmp_path / "mine.toml").write_text(theme.to_toml())
    assert archive.import_theme(tmp_path / "mine.toml").get("artwork", "panel") == "mine-artwork/panel.svg"


def test_a_link_in_the_artwork_folder_is_not_followed_when_saving_elsewhere(tmp_path):
    secret = tmp_path / "secret.svg"
    secret.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    old = tmp_path / "old"
    (old / "t-artwork").mkdir(parents=True)
    (old / "t-artwork/panel.svg").symlink_to(secret)
    theme = Theme.from_preset("breeze-dark")
    theme.set("artwork", "panel", "t-artwork/panel.svg")
    theme.save(old / "t.toml")
    (tmp_path / "new").mkdir()
    theme.save(tmp_path / "new/t.toml")
    assert not (tmp_path / "new/t-artwork/panel.svg").exists()


# ---- hostile pictures


def bomb(levels):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">']
    parts.append('<g id="l0"><rect width="1" height="1"/></g>')
    for level in range(1, levels + 1):
        previous = f"l{level - 1}"
        parts.append(f'<g id="l{level}"><use xlink:href="#{previous}"/><use xlink:href="#{previous}"/></g>')
    parts.append(f'<use xlink:href="#l{levels}"/></svg>')
    return "".join(parts).encode()


def test_nested_use_elements_are_refused_before_anything_is_drawn():
    started = time.monotonic()
    text, problems = artwork.check(bomb(30), frozenset())
    assert text is None and problems
    assert time.monotonic() - started < 2


def test_one_use_of_a_small_group_is_still_fine():
    raw = (
        b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        b'<g id="a"><rect width="1" height="1"/></g><use xlink:href="#a"/></svg>'
    )
    text, problems = artwork.check(raw, frozenset())
    assert problems == [] and text


def test_a_pattern_that_points_at_another_one_is_refused():
    raw = (
        b'<svg xmlns="http://www.w3.org/2000/svg"><defs><pattern id="p" width="2" height="2">'
        b'<rect width="1" height="1" fill="url(#q)"/></pattern></defs></svg>'
    )
    text, problems = artwork.check(raw, frozenset())
    assert text is None and problems


def test_the_generated_frames_pass_the_check():
    theme = Theme.from_preset("breeze-dark")
    for frame in ("panel", "popups", "tooltips", "widgets"):
        text, problems = artwork.check(plasmastyle.frame_svg(theme, frame).encode(), frozenset())
        assert problems == [], frame


# ---- undo


def test_the_undo_of_a_font_leaves_a_color_scheme_chosen_since(home, runner):
    config = paths.config_home()
    config.mkdir(parents=True, exist_ok=True)
    (config / "kdeglobals").write_text("[General]\nColorScheme=BreezeLight\n")
    snapshot = snapshots.create("fonts", [], {"fonts": {}})
    (config / "kdeglobals").write_text("[General]\nColorScheme=BreezeDark\n")
    engine.restore(snapshot, runner, consume=True)
    assert "ColorScheme=BreezeDark" in (config / "kdeglobals").read_text()


def test_the_undo_of_a_color_scheme_puts_the_scheme_back(home, runner):
    config = paths.config_home()
    config.mkdir(parents=True, exist_ok=True)
    (config / "kdeglobals").write_text("[General]\nColorScheme=BreezeLight\n")
    snapshot = snapshots.create("colors", [], {"colors": {"color_scheme": "BreezeLight"}})
    (config / "kdeglobals").write_text("[General]\nColorScheme=BreezeDark\n")
    engine.restore(snapshot, runner, consume=True)
    assert "ColorScheme=BreezeLight" in (config / "kdeglobals").read_text()


def test_the_undo_of_the_panel_leaves_the_gtk_files_alone(home, runner):
    gtk = paths.config_home() / "gtk-3.0"
    gtk.mkdir(parents=True)
    (gtk / "settings.ini").write_text("[Settings]\ngtk-font-name=A 10\n")
    snapshot = snapshots.create("panel", [], {"panel": {}})
    (gtk / "settings.ini").write_text("[Settings]\ngtk-font-name=B 10\n")
    engine.restore(snapshot, runner, consume=True)
    assert "B 10" in (gtk / "settings.ini").read_text()


def within(seconds, function):
    """Call `function` in a thread and fail when it has not returned in `seconds`: a read of a pipe that
    nobody writes to would otherwise hang the whole run instead of failing the test."""
    import threading

    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(function()), daemon=True)
    thread.start()
    thread.join(seconds)
    return thread, outcome


def release(pipe):
    """Let a thread that is stuck reading `pipe` go (a writer that closes ends the read)."""
    try:
        os.close(os.open(pipe, os.O_WRONLY | os.O_NONBLOCK))
    except OSError:
        pass


def test_a_pipe_called_kdeglobals_does_not_block_the_snapshot(home):
    config = paths.config_home()
    config.mkdir(parents=True, exist_ok=True)
    pipe = config / "kdeglobals"
    os.mkfifo(pipe)
    try:
        thread, outcome = within(5, lambda: sidefiles.capture(home / "store"))
        assert not thread.is_alive(), "capture waits for the pipe"
        record = outcome[0]
        assert record["kdeglobals"] is None
        record["kdeglobals"] = {"existed": True, "text": "[General]\nColorScheme=A\n"}
        thread, _ = within(5, lambda: sidefiles.restore(record, home / "store"))
        assert not thread.is_alive(), "restore waits for the pipe"  # with a saved copy and a pipe in the way
        assert pipe.is_fifo()
    finally:
        release(pipe)


def test_waiting_for_the_daemons_keeps_the_window_alive(monkeypatch):
    from plasma_theme_studio.apply import desktop

    calls = []
    monkeypatch.undo()  # the real pause, not the test's
    monkeypatch.setattr(desktop, "keep_alive", lambda: calls.append(1))
    desktop.pause(0.1)
    assert len(calls) >= 2


# ---- the panel page and its worker


def test_the_panel_pool_is_made_before_its_answer_object(app, home, desktop_runner):
    from plasma_theme_studio.ui.main_window import MainWindow

    window = MainWindow(desktop_runner)
    window.show_page("panel")
    page = window.page("panel")
    children = page.children()
    assert children.index(page._pool) < children.index(page._answer)
    window.undo_stack.setClean()
    window.close()


# ---- Rofi


def test_rofi_takes_the_font_the_theme_sets_and_the_desktop_otherwise(home):
    theme = Theme({("rofi", "style"): "generated"})
    theme.set("fonts", "general", "DejaVu Sans, 11")
    assert rofi.font_of(theme) == "DejaVu Sans 11"
    theme.set("rofi", "font", "Mono 9")
    assert rofi.font_of(theme) == "Mono 9"
    plain = Theme({("rofi", "style"): "generated"})
    assert rofi.font_of(plain) == rofi.desktop_font()


def test_one_apply_with_a_font_and_rofi_leaves_nothing_to_change(home, desktop_runner):
    from plasma_theme_studio.apply.status import CHANGE, parts_status

    theme = Theme({("rofi", "style"): "generated", ("meta", "name"): "Check"})
    theme.set("fonts", "general", "DejaVu Sans, 11")
    engine.apply(theme, desktop_runner)
    rows = {row.key: row for row in parts_status(theme, desktop_runner)}
    assert rows["rofi"].state != CHANGE


# ---- banner and notes


def test_own_artwork_is_not_called_unapplied_when_the_panel_style_is_generated():
    from plasma_theme_studio.ui.main_window import left_out_sections

    theme = Theme({("panel", "style"): "generated"})
    theme.set("artwork", "panel", "t-artwork/panel.svg")
    assert "artwork" not in left_out_sections(engine.build_plan(theme))
    plain = Theme({})
    plain.set("artwork", "panel", "t-artwork/panel.svg")
    assert "artwork" in left_out_sections(engine.build_plan(plain))


def test_the_shadow_notes_do_not_contradict_each_other():
    theme = Theme({("window", "decoration"): "generated"})
    target = windowframe.WindowFrameGenerator()
    plain = " ".join(str(n) for n in target.section_notes(theme, "shadow"))
    assert "same on all sides" in plain
    theme.set("shadow", "offset_x", 4)
    theme.set("shadow", "offset_y", 8)
    shadow = " ".join(str(n) for n in target.section_notes(theme, "shadow"))
    window = " ".join(str(n) for n in target.section_notes(theme, "window"))
    assert "same on all sides" not in shadow and "same on all sides" not in window
    assert "4 px sideways" in window


def test_a_second_panel_that_does_not_exist_is_said_in_the_theme_column(home, desktop_runner):
    theme = Theme({})
    theme.set("panel_layout", "location", "top")
    theme.set("panel_layout_2", "location", "bottom")
    _desktop, wanted = panellayout.status_texts(theme, desktop_runner)
    assert "Panel 2" in wanted and "does not exist" in wanted


def test_zip_import_keeps_working_with_its_artwork(tmp_path):
    imported, file = with_artwork(tmp_path, "z")
    assert zipfile.is_zipfile(tmp_path / "x.ptstheme")
    with zipfile.ZipFile(tmp_path / "x.ptstheme") as zipped:
        assert {"theme.toml", "assets/panel.svg"} <= set(zipped.namelist())
        packed = zipped.read("assets/panel.svg")
    assert packed == (tmp_path / "src/a-artwork/panel.svg").read_bytes()
    # what came out of the zip is the picture that went in, and the theme names it
    assert imported.pending_artwork == {"panel": packed}
    assert imported.get("artwork", "panel") == "assets/panel.svg"
    assert imported.get("artwork", "popups") is None  # the other frames had none
    with pytest.raises(archive.ArchiveError):
        (tmp_path / "broken.ptstheme").write_bytes((tmp_path / "x.ptstheme").read_bytes()[:-30])
        archive.import_theme(tmp_path / "broken.ptstheme")


def test_a_cached_picture_is_not_shared_between_languages(app):
    from PySide6.QtCore import QLocale, QSize

    from plasma_theme_studio.pickers import cache
    from plasma_theme_studio.pickers.base import Item

    item = Item(id="x", name="x")
    old = QLocale()
    try:
        keys = {}
        for name in ("en_US", "sv_SE", "de_DE", "en_US"):
            QLocale.setDefault(QLocale(name))
            keys.setdefault(name, []).append(cache.key(item, QSize(10, 10), 1.0, None))
        assert keys["en_US"][0] == keys["en_US"][1]  # the same language finds its picture again
        assert len({keys["en_US"][0], keys["sv_SE"][0], keys["de_DE"][0]}) == 3  # each language has its own
        # only the language differs: the item and the size still tell pictures apart
        assert cache.key(item, QSize(11, 10), 1.0, None) != keys["de_DE"][0]
    finally:
        QLocale.setDefault(old)
