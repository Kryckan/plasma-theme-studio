# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The second repair of Build 3: undo scope, GTK files, damaged records, costly pictures, names."""

from __future__ import annotations

import json
import os
import time

from plasma_theme_studio import archive, paths
from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply import snapshot as snapshots
from plasma_theme_studio.generators import artwork, plasmastyle
from plasma_theme_studio.model.theme import Theme, artwork_folder, write_atomic

IMPORT = "@import 'colors.css';\n"


# ---- undo


def test_the_undo_of_gtk_puts_back_what_the_daemon_wrote_after_the_apply(home, runner):
    config = paths.config_home()
    (config / "gtk-3.0").mkdir(parents=True)
    (config / "gtk-3.0/gtk.css").write_text("\n")  # gtk-4.0 has no gtk.css at all
    snapshot = snapshots.create("gtk", [], {"gtk": {}})
    snapshots.set_reached(snapshot, ["gtk"])
    snapshot = snapshots.get(snapshot.id)
    (config / "gtk-3.0/gtk.css").write_text(IMPORT)  # what kde-gtk-config writes
    (config / "gtk-4.0").mkdir()
    (config / "gtk-4.0/gtk.css").write_text(IMPORT)
    assert engine.restore(snapshot, runner, consume=True) == []
    assert (config / "gtk-3.0/gtk.css").read_text() == "\n"
    assert not (config / "gtk-4.0/gtk.css").exists()


def _kdeglobals(scheme):
    path = paths.config_home() / "kdeglobals"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"[General]\nColorScheme={scheme}\n")


def test_the_undo_of_a_fonts_only_apply_keeps_a_scheme_chosen_since(home, desktop_runner):
    theme = Theme.from_preset("breeze-light")
    engine.apply(theme, desktop_runner)  # colors and the rest are now as the theme says
    theme.set("fonts", "general", "DejaVu Sans, 11")
    result = engine.apply(theme, desktop_runner)
    assert result.snapshot.reached == ("fonts",)
    desktop_runner.set("kdeglobals", ["General"], "ColorScheme", "Chosen")
    gtk = paths.config_home() / "gtk-3.0"
    gtk.mkdir(parents=True, exist_ok=True)
    (gtk / "colors.css").write_text("@define-color a #123456;\n")
    assert engine.restore(snapshots.get(result.snapshot.id), desktop_runner, consume=True) == []
    assert desktop_runner.get("kdeglobals", ["General"], "ColorScheme") == "Chosen"
    assert (gtk / "colors.css").read_text() == "@define-color a #123456;\n"
    assert desktop_runner.get("kdeglobals", ["General"], "Font") != "DejaVu Sans,11"


def test_a_snapshot_without_a_list_of_reached_targets_counts_every_target(home, runner):
    _kdeglobals("BreezeLight")
    snapshot = snapshots.create("old", [], {"colors": {"color_scheme": "BreezeLight"}})
    assert snapshot.reached is None
    _kdeglobals("BreezeDark")
    engine.restore(snapshot, runner, consume=True)
    assert "ColorScheme=BreezeLight" in (paths.config_home() / "kdeglobals").read_text()


# ---- a damaged record of the side files


def _victims(home):
    outside = home / "outside"
    outside.mkdir()
    (outside / "a.txt").write_text("a")
    (outside / "b.txt").write_text("b")
    return outside


def _tampered(home, runner, change):
    snapshot = snapshots.create("fonts", [], {"fonts": {}})
    manifest = snapshot.directory / "manifest.json"
    data = json.loads(manifest.read_text())
    change(data["side"], snapshot)
    manifest.write_text(json.dumps(data))
    return snapshots.get(snapshot.id)


def test_a_manifest_that_names_other_files_does_not_make_the_undo_touch_them(home, runner):
    outside = _victims(home)

    def change(side, snapshot):
        side["files"].append({"path": str(outside / "a.txt"), "existed": False, "stored": None})
        (snapshot.directory / "side").mkdir(exist_ok=True)
        (snapshot.directory / "side/9").write_text("changed")
        side["files"].append({"path": str(outside / "b.txt"), "existed": True, "stored": "9"})
        side["files"].append(
            {"path": str(outside / "b.txt"), "existed": True, "stored": "../../manifest.json"}
        )
        side["trees"].append({"path": str(outside), "existed": False, "entries": [], "dirs": []})
        side["created_dirs"].append(str(outside))

    snapshot = _tampered(home, runner, change)
    engine.restore(snapshot, runner, consume=True)
    assert (outside / "a.txt").read_text() == "a" and (outside / "b.txt").read_text() == "b"


def test_a_malformed_side_record_is_a_failure_not_a_crash(home, runner):
    for broken in ({"files": "x"}, "x", {"files": [5]}, {"trees": [5]}):
        snapshot = _tampered(home, runner, lambda side, _s: None)
        manifest = snapshot.directory / "manifest.json"
        data = json.loads(manifest.read_text())
        data["side"] = broken
        manifest.write_text(json.dumps(data))
        failures = engine.restore(snapshots.get(snapshot.id), runner, consume=True)
        assert failures, broken


# ---- pictures that cost too much


def svg(body):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        + body
        + "</svg>"
    ).encode()


def test_many_blurred_elements_are_refused_however_they_are_written():
    blur = '<defs><filter id="b"><feGaussianBlur stdDeviation="5"/></filter></defs>'
    flat = svg(blur + '<rect width="4" height="4" filter="url(#b)"/>' * 200)
    group = '<g id="g">' + '<rect width="4" height="4" filter="url(#b)"/>' * 30 + "</g>"
    reused = svg(blur + group + '<use xlink:href="#g"/>' * 100)
    styled = svg(blur + '<rect width="4" height="4" style="fill:red;filter:url(#b)"/>' * 200)
    started = time.monotonic()
    for raw in (flat, reused, styled):
        text, problems = artwork.check(raw, frozenset())
        assert text is None and problems
    assert time.monotonic() - started < 2


def test_markers_at_every_point_of_a_long_path_are_refused():
    marker = '<defs><marker id="m"><circle r="1"/>' + "<circle r='1'/>" * 300 + "</marker></defs>"
    path = "M0 0 " + "L1 1 " * 300
    text, problems = artwork.check(svg(marker + f'<path d="{path}" marker-mid="url(#m)"/>'), frozenset())
    assert text is None and problems


def test_a_frame_with_a_few_shadows_is_still_fine():
    raw = svg(
        '<defs><filter id="b"><feGaussianBlur stdDeviation="2"/></filter></defs>'
        '<rect width="9" height="9" filter="url(#b)"/><rect width="5" height="5" filter="url(#b)"/>'
    )
    text, problems = artwork.check(raw, frozenset())
    assert problems == [] and text


# ---- names and artwork when saving


def _imported(tmp_path, stem):
    source = Theme.from_preset("breeze-dark")
    source.set("panel", "style", "generated")
    folder = tmp_path / "src"
    (folder / "a-artwork").mkdir(parents=True, exist_ok=True)
    (folder / "a-artwork/panel.svg").write_text(plasmastyle.frame_svg(source, "panel"))
    source.set("artwork", "panel", "a-artwork/panel.svg")
    source.save(folder / "a.toml")
    return Theme.load(folder / "a.toml")


def test_saving_in_a_folder_that_has_another_picture_of_that_name_gives_a_free_name(tmp_path):
    theme = Theme.from_preset("breeze-dark")
    theme.set("panel", "style", "generated")
    (tmp_path / "base/mine-artwork").mkdir(parents=True)
    (tmp_path / "base/mine-artwork/panel.svg").write_text(plasmastyle.frame_svg(theme, "panel"))
    theme.set("artwork", "panel", "mine-artwork/panel.svg")
    theme.save(tmp_path / "base/mine.toml")
    theme = Theme.load(tmp_path / "base/mine.toml")
    (tmp_path / "dst/mine-artwork").mkdir(parents=True)
    (tmp_path / "dst/mine-artwork/panel.svg").write_text("OTHER")
    theme.save(tmp_path / "dst/mine.toml")
    assert (tmp_path / "dst/mine-artwork/panel.svg").read_text() == "OTHER"
    name = Theme.load(tmp_path / "dst/mine.toml").get("artwork", "panel")
    assert name != "mine-artwork/panel.svg"
    assert (tmp_path / "dst" / name).read_text() == (tmp_path / "base/mine-artwork/panel.svg").read_text()


def test_two_file_names_that_clean_up_alike_get_two_artwork_folders(tmp_path):
    assert artwork_folder(tmp_path / "it's.toml") != artwork_folder(tmp_path / "it-s.toml")
    assert artwork_folder(tmp_path / "plain.toml").name == "plain-artwork"


def test_a_theme_file_with_a_very_long_name_can_be_saved(tmp_path):
    name = "x" * 245 + ".toml"
    Theme.from_preset("breeze-dark").save(tmp_path / name)
    assert (tmp_path / name).is_file()


def test_an_archive_import_keeps_its_artwork_when_saved(tmp_path):
    theme = _imported(tmp_path, "a")
    archive.export_theme(theme, tmp_path / "x.ptstheme")
    imported = archive.import_theme(tmp_path / "x.ptstheme")
    (tmp_path / "out").mkdir()
    imported.save(tmp_path / "out/z.toml")
    reloaded = Theme.load(tmp_path / "out/z.toml")
    saved = tmp_path / "out" / reloaded.get("artwork", "panel")
    text, problems = artwork.check(saved.read_bytes(), frozenset())
    assert problems == [] and text


# ---- the picture cache


def test_the_cache_keeps_only_the_newest_files_of_an_item(app, home):
    from plasma_theme_studio.pickers import cache
    from plasma_theme_studio.pickers.base import Item

    item = Item(id="x", name="x")
    folder = cache.directory("kind")
    folder.mkdir(parents=True)
    prefix = cache.item_hash(item)
    for number in range(cache.MAX_VARIANTS + 4):
        file = folder / f"{prefix}-{number}.png"
        file.write_bytes(b"x")
        os.utime(file, (1000 + number, 1000 + number))
    cache.prune("kind", [item])
    left = sorted(int(file.stem.split("-")[1]) for file in folder.iterdir())
    assert left == list(range(4, cache.MAX_VARIANTS + 4))


def test_write_atomic_still_replaces_a_file(tmp_path):
    write_atomic(tmp_path / "a", "1")
    write_atomic(tmp_path / "a", "2")
    assert (tmp_path / "a").read_text() == "2"


# ---- the screen chooser of the Panel page


def test_the_screens_of_the_panel_page_fit_beside_the_form(app):
    from plasma_theme_studio.ui.pages.panel_screen import MAX_WIDTH, ScreenChooser

    chooser = ScreenChooser()
    for count in (1, 2, 3):
        chooser.set_panels([{"number": n + 1, "location": "bottom", "screen": n} for n in range(count)], 1)
        assert chooser.width() <= MAX_WIDTH
        for screen in range(count):  # every screen is whole and inside the widget
            assert chooser.rect().adjusted(-1, -1, 1, 1).contains(chooser.screen_rect(screen).toRect())
