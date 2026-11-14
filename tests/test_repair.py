# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Faults found in review and in rig runs, each pinned by a test."""

import subprocess
import zipfile
from pathlib import Path

import pytest

from plasma_theme_studio import archive, library, paths
from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply.runner import Result
from plasma_theme_studio.archive import ArchiveError
from plasma_theme_studio.generators import RofiGenerator
from plasma_theme_studio.generators import kvantum as kv
from plasma_theme_studio.generators import rofi as rofi_module
from plasma_theme_studio.generators.colorscheme import FALLBACK_SCHEME
from plasma_theme_studio.globaltheme import export_global_theme, package_id
from plasma_theme_studio.model.theme import MAX_NAME_LENGTH, Theme, ThemeError

# ---- hostile imports


def test_deeply_nested_toml_is_a_theme_error():
    with pytest.raises(ThemeError):
        Theme.from_toml("a=" + "[" * 60000)
    with pytest.raises(ThemeError):
        Theme.from_toml("a={a=" * 20000)


def test_importing_deeply_nested_files_is_an_archive_error(tmp_path):
    plain = tmp_path / "x.toml"
    plain.write_text("a=" + "[" * 60000)
    with pytest.raises(ArchiveError):
        archive.import_theme(plain)
    packed = tmp_path / "x.ptstheme"
    with zipfile.ZipFile(packed, "w") as z:
        z.writestr("theme.toml", "a=" + "[" * 60000)
    with pytest.raises(ArchiveError):
        archive.import_theme(packed)


def test_a_member_name_with_a_trailing_newline_is_refused(tmp_path):
    path = tmp_path / "x.ptstheme"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("theme.toml", Theme().to_toml())
        z.writestr("assets/a.svg\n", "<svg/>")
    with pytest.raises(ArchiveError):
        archive.import_theme(path)


def test_save_imported_with_a_long_name_ends(home):
    theme = Theme()
    theme.set("meta", "name", "x" * MAX_NAME_LENGTH)
    first, _ = library.save_imported(theme)
    second, _ = library.save_imported(theme)
    third, _ = library.save_imported(theme)
    names = {first.name, second.name, third.name}
    assert len(names) == 3 and all(len(n) <= MAX_NAME_LENGTH for n in names)


# ---- rofi comment


@pytest.mark.parametrize("name", ["x**// } * { background: red; } /* y", "**// * { background: red; } /*"])
def test_a_theme_name_cannot_leave_the_rofi_comment(name):
    theme = Theme({("meta", "name"): name, ("rofi", "style"): "generated"})
    text = rofi_module.rasi_text(theme)
    header = next(line for line in text.splitlines() if line.startswith("/* Theme:"))
    assert header.count("*/") == 1 and header.endswith("*/")
    assert "background: red" in header  # kept inside the comment
    assert "background: red" not in text.replace(header, "")


# ---- undo keeps what the user wrote since


def rofi_theme():
    return Theme({("meta", "name"): "My Theme", ("rofi", "style"): "generated"})


@pytest.fixture
def rofi(home, runner, use_generators):
    use_generators(RofiGenerator())
    return runner


def test_rofi_undo_keeps_a_later_edit_and_removes_only_our_line(rofi):
    config = paths.config_home() / "rofi/config.rasi"
    config.parent.mkdir(parents=True)
    config.write_text('@theme "Arc"\nwindow { }\n')
    result = engine.apply(rofi_theme(), rofi)
    config.write_text(config.read_text() + "configuration { show-icons: true; }\n")
    assert engine.restore(result.snapshot, rofi, consume=True) == []
    text = config.read_text()
    assert "configuration { show-icons: true; }" in text
    assert '@theme "Arc"' in text and "plasma-theme-studio" not in text
    assert "MyTheme" not in text


def test_rofi_undo_keeps_a_file_the_user_added_to_after_the_apply(rofi):
    config = paths.config_home() / "rofi/config.rasi"
    result = engine.apply(rofi_theme(), rofi)
    config.write_text(config.read_text() + "configuration { show-icons: true; }\n")
    assert engine.restore(result.snapshot, rofi, consume=True) == []
    assert config.read_text() == "configuration { show-icons: true; }\n"


def test_rofi_undo_of_an_untouched_apply_removes_the_file_it_made(rofi):
    result = engine.apply(rofi_theme(), rofi)
    assert engine.restore(result.snapshot, rofi, consume=True) == []
    assert not (paths.config_home() / "rofi/config.rasi").exists()


def test_kvantum_selection_after_a_later_edit():
    ours = kv.ID_PREFIX + "X-12345678"
    before = "[General]\ntheme=Nordic\n[Applications]\na=b\n"
    current = kv.with_theme(before, ours) + "[Extra]\nc=d\n"
    out = kv.restored_selection(current, before)
    assert kv.selected_theme(out) == "Nordic" and "[Extra]\nc=d" in out
    # untouched: exactly as before; made by the apply: gone
    assert kv.restored_selection(kv.with_theme(before, ours), before) == before
    assert kv.restored_selection(kv.with_theme("", ours), "absent") == "absent"
    # nothing of ours: left alone
    assert kv.restored_selection(before, before) == before
    # no theme line before: the line goes, the rest stays
    only = "[Applications]\na=b\n"
    assert "theme=" not in kv.restored_selection(kv.with_theme(only, ours) + "[E]\nk=v\n", only)


# ---- the color scheme undo


def test_undo_to_breezelight_accepts_the_key_being_dropped(home, runner):
    runner.settings["ColorScheme"] = ""
    result = engine.apply(Theme(), runner)

    def tool(argv):  # the real tool drops the key for the default scheme
        runner.settings.pop("ColorScheme", None)
        return Result(0, "Successfully applied the color scheme BreezeLight.\n")

    runner.handlers["plasma-apply-colorscheme"] = tool
    assert engine.restore(result.snapshot, runner, consume=True) == []
    assert FALLBACK_SCHEME == "BreezeLight"


# ---- Global Theme scripts


def run_script(out, name, data):
    env = {"PATH": "/usr/bin:/bin", "XDG_DATA_HOME": str(data), "HOME": str(data / "nohome")}
    return subprocess.run(["sh", str(out / name)], env=env, capture_output=True, text=True)


def bundle(tmp_path):
    theme = Theme({("meta", "name"): "My Theme", ("panel", "style"): "generated"})
    out = tmp_path / "out"
    export_global_theme(theme, out)
    return theme, out, tmp_path / "data"


def test_install_refuses_to_replace_a_scheme_it_did_not_make(tmp_path):
    _, out, data = bundle(tmp_path)
    (data / "color-schemes").mkdir(parents=True)
    mine = data / "color-schemes/MyTheme.colors"
    mine.write_text("my own scheme")
    done = run_script(out, "install.sh", data)
    assert done.returncode != 0 and str(mine) in done.stderr
    assert mine.read_text() == "my own scheme"
    assert not (data / "plasma").exists()  # nothing at all was installed


def test_install_refuses_a_link(tmp_path):
    _, out, data = bundle(tmp_path)
    (data / "color-schemes").mkdir(parents=True)
    other = tmp_path / "other.colors"
    other.write_text("# Generated by Plasma Theme Studio.\nmine")
    (data / "color-schemes/MyTheme.colors").symlink_to(other)
    assert run_script(out, "install.sh", data).returncode != 0
    assert other.read_text().endswith("mine")


def test_uninstall_keeps_files_that_are_not_ours_any_more(tmp_path):
    theme, out, data = bundle(tmp_path)
    assert run_script(out, "install.sh", data).returncode == 0
    scheme = data / "color-schemes/MyTheme.colors"
    scheme.write_text("edited by the user")
    done = run_script(out, "uninstall.sh", data)
    assert done.returncode == 0 and scheme.read_text() == "edited by the user"
    assert str(scheme) in done.stderr
    left = sorted(p.relative_to(data).as_posix() for p in data.rglob("*") if p.is_file())
    assert left == ["color-schemes/MyTheme.colors"]


def test_reinstall_and_uninstall_of_our_own_files_leave_no_folders_behind(tmp_path):
    theme, out, data = bundle(tmp_path)
    for _ in range(2):
        assert run_script(out, "install.sh", data).returncode == 0
    package = data / "plasma/look-and-feel" / package_id(theme)
    assert (package / "metadata.json").read_text().startswith('{\n  "X-Generated-By"')
    assert run_script(out, "uninstall.sh", data).returncode == 0
    assert list(data.rglob("*")) == []


def test_the_preview_picture_is_removed_only_with_our_package(tmp_path):
    theme, out, data = bundle(tmp_path)
    package = Path("plasma/look-and-feel") / package_id(theme)
    previews = out / "share" / package / "contents/previews"
    previews.mkdir(parents=True, exist_ok=True)
    (previews / "preview.png").write_bytes(b"\x89PNG")
    # the package is the user's own (no mark in its metadata): the picture must stay
    mine = data / package
    (mine / "contents/previews").mkdir(parents=True)
    (mine / "metadata.json").write_text("{}")
    (mine / "contents/previews/preview.png").write_bytes(b"theirs")
    assert run_script(out, "install.sh", data).returncode != 0
    assert (mine / "contents/previews/preview.png").read_bytes() == b"theirs"


# ---- the sentence on the Files written tab


def test_every_changed_setting_text_fits_the_sentence_that_lists_them():
    """ "It also changes {a}; {b}." takes noun phrases: no capital, no final stop."""
    from plasma_theme_studio import generators

    theme = Theme(
        {
            ("apps", "style"): "generated",
            ("gtk", "style"): "generated",
            ("rofi", "style"): "generated",
            ("window", "decoration"): "generated",
            ("panel", "style"): "generated",
        }
    )
    texts = [str(t) for g in generators.GENERATORS for t in g.changed_settings(theme)]
    assert len(texts) >= 5
    for text in texts:
        assert text[0].islower() and not text.endswith("."), text


# ---- translations


def test_every_translate_call_has_a_swedish_entry():
    import ast
    import html
    import re

    base = Path(__file__).resolve().parents[1] / "src/plasma_theme_studio"
    sources = {
        html.unescape(x)
        for x in re.findall(
            r"<source>(.*?)</source>", (base / "i18n/plasma_theme_studio_sv.ts").read_text(), re.S
        )
    }
    missing = set()
    for file in base.rglob("*.py"):
        for node in ast.walk(ast.parse(file.read_text())):
            is_call = isinstance(node, ast.Call) and getattr(node.func, "id", None) == "translate"
            if is_call and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                if node.args[1].value not in sources:
                    missing.add(node.args[1].value)
    assert not missing
