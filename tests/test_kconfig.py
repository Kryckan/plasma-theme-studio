# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Single keys in KDE's configuration files, and the `key[$d]` line that
kwriteconfig6 leaves when it removes a key that Plasma's own defaults define."""

import pytest

from plasma_theme_studio import kconfig, paths
from plasma_theme_studio.apply.runner import Result
from plasma_theme_studio.generators import ApplyError

FRAME = ["org.kde.kdecoration2"]


def config(name="kwinrc"):
    return paths.config_home() / name


def write(text, name="kwinrc"):
    config(name).parent.mkdir(parents=True, exist_ok=True)
    config(name).write_text(text)


def test_parse_reads_groups_nested_groups_and_hidden_defaults():
    text = (
        "top=1\n\n# a comment\n[Theme]\nname = Breeze Dark \nempty=\n\n"
        "[Containments][2][General]\nkey=a=b\n\n[org.kde.kdecoration2]\nlibrary[$d]\nnoise\n"
    )
    assert kconfig.parse(text) == {
        (): {"top": "1"},
        ("Theme",): {"name": "Breeze Dark", "empty": ""},
        ("Containments", "2", "General"): {"key": "a=b"},
        ("org.kde.kdecoration2",): {"library[$d]": ""},
    }


def test_a_file_that_cannot_be_read_counts_as_empty(home):
    assert kconfig.user_value("kwinrc", FRAME, "library") is None
    assert not kconfig.masked("kwinrc", FRAME, "library")
    config().parent.mkdir(parents=True)
    config().write_bytes(b"[org.kde.kdecoration2]\nlibrary=\xff\xfe\n")
    assert kconfig.user_value("kwinrc", FRAME, "library") is None


def test_a_hidden_default_is_not_a_value_but_is_reported(home):
    write("[org.kde.kdecoration2]\nlibrary[$d]\ntheme=Other\n")
    assert kconfig.user_value("kwinrc", FRAME, "library") is None
    assert kconfig.masked("kwinrc", FRAME, "library")
    assert kconfig.user_value("kwinrc", FRAME, "theme") == "Other"
    assert not kconfig.masked("kwinrc", FRAME, "theme")
    assert not kconfig.masked("kwinrc", ["Other group"], "library")


def test_the_value_in_use_falls_back_to_plasmas_defaults(home, runner):
    runner.defaults[("kwinrc", ("org.kde.kdecoration2",), "library")] = "org.kde.kwin.aurorae"
    assert kconfig.effective_value(runner, "kwinrc", FRAME, "library", "org.kde.breeze") == (
        "org.kde.kwin.aurorae"
    )
    assert kconfig.effective_value(runner, "kwinrc", FRAME, "theme", "Breeze") == "Breeze"
    runner.handlers["kreadconfig6"] = lambda argv: Result(1, "", "no")
    assert kconfig.effective_value(runner, "kwinrc", FRAME, "library", "org.kde.breeze") == "org.kde.breeze"


def test_the_default_is_the_first_one_in_the_systems_folders(home, runner, monkeypatch):
    first, second = home / "kdedefaults", home / "xdg"
    monkeypatch.setenv("XDG_CONFIG_DIRS", f"{first}::{second}:{home / 'missing'}")
    first.mkdir()
    second.mkdir()
    (first / "plasmarc").write_text("[Theme]\nname=Nordic\n")
    (second / "plasmarc").write_text("[Theme]\nname=default\n\n[Wallpapers]\nusersWallpapers=a.jpg\n")
    write("[Theme]\nname=Mine\n", "plasmarc")  # the user's own value does not count

    assert kconfig.default_value("plasmarc", ["Theme"], "name") == "Nordic"
    assert kconfig.default_value("plasmarc", ["Wallpapers"], "usersWallpapers") == "a.jpg"
    assert kconfig.default_value("plasmarc", ["Theme"], "other") is None
    assert kconfig.default_value("kwinrc", FRAME, "library") is None
    (first / "kwinrc").write_bytes(b"[org.kde.kdecoration2]\nlibrary=\xff\n")
    assert kconfig.default_value("kwinrc", FRAME, "library") is None


def test_removing_a_key_leaves_no_line_that_hides_plasmas_default(home, runner):
    runner.defaults[("kwinrc", ("org.kde.kdecoration2",), "library")] = "org.kde.kwin.aurorae"
    before = "[Compositing]\nBackend=OpenGL\n\n[Windows]\nFocusPolicy=ClickToFocus\n"
    write(before)

    kconfig.write_value(runner, "kwinrc", FRAME, "library", "org.kde.kwin.aurorae.v2")
    assert kconfig.effective_value(runner, "kwinrc", FRAME, "library") == "org.kde.kwin.aurorae.v2"
    kconfig.write_value(runner, "kwinrc", FRAME, "library", None)

    assert config().read_text() == before
    assert not kconfig.masked("kwinrc", FRAME, "library")
    assert kconfig.effective_value(runner, "kwinrc", FRAME, "library") == "org.kde.kwin.aurorae"


def test_the_tool_itself_leaves_that_line(home, runner):
    """What the fake tool does without the cleaning up, as the real one does."""
    runner.defaults[("kwinrc", ("org.kde.kdecoration2",), "library")] = "org.kde.kwin.aurorae"
    kconfig.write_value(runner, "kwinrc", FRAME, "library", "x")
    runner.run(["kwriteconfig6", "--file", "kwinrc", "--group", FRAME[0], "--key", "library", "--delete"])
    assert config().read_text() == "[org.kde.kdecoration2]\nlibrary[$d]\n"
    assert kconfig.effective_value(runner, "kwinrc", FRAME, "library", "fallback") == "fallback"


def test_a_line_the_user_had_is_kept_when_asked(home, runner):
    runner.defaults[("kwinrc", ("org.kde.kdecoration2",), "library")] = "org.kde.kwin.aurorae"
    before = "[org.kde.kdecoration2]\nlibrary[$d]\n"
    write(before)
    assert kconfig.masked("kwinrc", FRAME, "library")

    kconfig.write_value(runner, "kwinrc", FRAME, "library", "org.kde.kwin.aurorae.v2")
    assert not kconfig.masked("kwinrc", FRAME, "library")  # a value takes the place of the line
    kconfig.write_value(runner, "kwinrc", FRAME, "library", None, masked=True)

    assert config().read_text() == before


def test_the_file_goes_when_nothing_is_left_in_it(home, runner):
    runner.defaults[("plasmarc", ("Theme",), "name")] = "default"
    kconfig.write_value(runner, "plasmarc", ["Theme"], "name", "Other")
    assert config("plasmarc").exists()
    kconfig.write_value(runner, "plasmarc", ["Theme"], "name", None)
    assert not config("plasmarc").exists()


def test_no_empty_file_is_left_without_plasmas_defaults_either(home, runner):
    kconfig.write_value(runner, "breezerc", ["Common"], "ShadowSize", "ShadowLarge")
    kconfig.write_value(runner, "breezerc", ["Common"], "ShadowStrength", "140")
    kconfig.write_value(runner, "breezerc", ["Common"], "ShadowSize", None)
    assert config("breezerc").read_text() == "[Common]\nShadowStrength=140\n"
    kconfig.write_value(runner, "breezerc", ["Common"], "ShadowStrength", None)
    assert not config("breezerc").exists()


def test_only_the_named_key_in_the_named_group_is_cleaned(home, runner):
    runner.defaults[("somerc", ("A", "B"), "Key")] = "system"
    before = "[A]\nKey[$d]\n\n[A][B]\nOther[$d]\nkept=1\n\n[C]\nKey[$d]\n"
    write(before, "somerc")

    kconfig.write_value(runner, "somerc", ["A", "B"], "Key", "mine")
    kconfig.write_value(runner, "somerc", ["A", "B"], "Key", None)

    assert config("somerc").read_text() == before


def test_a_group_that_becomes_empty_goes_with_its_blank_lines(home, runner):
    runner.defaults[("somerc", ("B",), "Key")] = "system"
    before = "[A]\none=1\n\n[C]\nthree=3\n"
    # The real tool keeps the groups in order, so the new group lands in the middle.
    write("[A]\none=1\n\n[B]\nKey=mine\n\n[C]\nthree=3\n", "somerc")
    runner.handlers["kwriteconfig6"] = lambda argv: (
        write("[A]\none=1\n\n[B]\nKey[$d]\n\n[C]\nthree=3\n", "somerc") or Result(0)
    )

    kconfig.write_value(runner, "somerc", ["B"], "Key", None)

    assert config("somerc").read_text() == before


def test_a_key_that_is_not_in_the_users_file_is_not_touched(home, runner):
    before = "[org.kde.kdecoration2]\nlibrary[$d]\n"
    write(before)
    kconfig.write_value(runner, "kwinrc", FRAME, "library", None)
    kconfig.write_value(runner, "kwinrc", FRAME, "theme", None)
    assert config().read_text() == before
    assert not [call for call in runner.calls if call[0] == "kwriteconfig6"]


def test_a_removal_that_does_not_happen_is_an_error(home, runner):
    write("[org.kde.kdecoration2]\nlibrary=x\n")
    runner.handlers["kwriteconfig6"] = lambda argv: Result(0)
    with pytest.raises(ApplyError, match="library in kwinrc"):
        kconfig.write_value(runner, "kwinrc", FRAME, "library", None)


def test_a_write_that_does_not_stick_is_an_error(home, runner):
    runner.handlers["kwriteconfig6"] = lambda argv: Result(0)
    with pytest.raises(ApplyError, match="library in kwinrc"):
        kconfig.write_value(runner, "kwinrc", FRAME, "library", "x")
    runner.handlers["kwriteconfig6"] = lambda argv: Result(1, "", "kwriteconfig6: cannot write\nmore")
    with pytest.raises(ApplyError, match="cannot write"):
        kconfig.write_value(runner, "kwinrc", FRAME, "library", "x")


def test_a_line_that_cannot_be_cleaned_is_an_error(home, runner, monkeypatch):
    runner.defaults[("kwinrc", ("org.kde.kdecoration2",), "library")] = "org.kde.kwin.aurorae"
    kconfig.write_value(runner, "kwinrc", FRAME, "library", "x")
    write("[Windows]\nFocusPolicy=ClickToFocus\n\n" + config().read_text())

    def refuse(path, text):
        raise OSError("read-only file system")

    monkeypatch.setattr(kconfig, "write_atomic", refuse)
    with pytest.raises(ApplyError, match="read-only file system"):
        kconfig.write_value(runner, "kwinrc", FRAME, "library", None)


def test_values_are_read_the_way_kde_reads_them():
    text = "[G]\nspaces=\\s two \\s\npath=C:\\\\dir\\tx\nlines=a\\nb\\rc\nother=\\x41 100%\n"
    assert kconfig.parse(text) == {
        (): {},
        ("G",): {"spaces": "  two  ", "path": "C:\\dir\tx", "lines": "a\nb\rc", "other": "\\x41 100%"},
    }


@pytest.mark.parametrize("value", [" padded ", "C:\\dir\\file", "two\nlines", "tab\there", "100% plain"])
def test_a_value_that_is_read_and_written_back_does_not_change(home, runner, value):
    """An undo writes back what it read. Escapes that were read raw would double each time."""
    kconfig.write_value(runner, "somerc", ["G"], "Key", value)
    first = config("somerc").read_text()
    assert kconfig.user_value("somerc", ["G"], "Key") == value

    kconfig.write_value(runner, "somerc", ["G"], "Key", "something else")
    kconfig.write_value(runner, "somerc", ["G"], "Key", kconfig.user_value("somerc", ["G"], "Key"))
    kconfig.write_value(runner, "somerc", ["G"], "Key", value)

    assert config("somerc").read_text() == first
    assert "\n" not in first.split("Key=", 1)[1].rstrip("\n")  # one line in the file, whatever the value


def linked(home, name="kwinrc", text=""):
    """The user's file as a link into a folder of dotfiles."""
    target = home / "dotfiles" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    config(name).parent.mkdir(parents=True, exist_ok=True)
    config(name).symlink_to(target)
    return target


def test_cleaning_up_writes_through_a_linked_file(home, runner):
    runner.defaults[("kwinrc", ("org.kde.kdecoration2",), "library")] = "org.kde.kwin.aurorae"
    before = "[Windows]\nFocusPolicy=ClickToFocus\n\n[org.kde.kdecoration2]\nlibrary=x\n"
    target = linked(home, text=before)
    # The real tool writes through the link; the fake one would replace it.
    runner.handlers["kwriteconfig6"] = lambda argv: (
        target.write_text(before.replace("library=x", "library[$d]")) and Result(0)
    )

    kconfig.write_value(runner, "kwinrc", FRAME, "library", None)

    assert config().is_symlink()
    assert target.read_text() == "[Windows]\nFocusPolicy=ClickToFocus\n"
    assert not kconfig.masked("kwinrc", FRAME, "library")


def test_a_linked_file_that_ends_up_empty_stays_in_place(home, runner):
    runner.defaults[("plasmarc", ("Theme",), "name")] = "default"
    target = linked(home, "plasmarc", "[Theme]\nname=Other\n")
    runner.handlers["kwriteconfig6"] = lambda argv: target.write_text("[Theme]\nname[$d]\n") and Result(0)

    kconfig.write_value(runner, "plasmarc", ["Theme"], "name", None)

    assert config("plasmarc").is_symlink() and target.exists()
    assert target.read_text() == ""
    assert kconfig.user_value("plasmarc", ["Theme"], "name") is None


def test_an_empty_linked_file_is_not_removed_without_plasmas_defaults(home, runner):
    target = linked(home, "breezerc", "[Common]\nShadowSize=ShadowLarge\n")
    runner.handlers["kwriteconfig6"] = lambda argv: target.write_text("") or Result(0)

    kconfig.write_value(runner, "breezerc", ["Common"], "ShadowSize", None)

    assert config("breezerc").is_symlink() and target.exists()


def test_a_notified_write_and_removal_tell_the_programs_that_watch_the_file(home, desktop_runner):
    runner = desktop_runner
    kconfig.write_value(runner, "kdeglobals", ["Icons"], "Theme", "Papirus", notify=True)
    kconfig.write_value(runner, "kdeglobals", ["Icons"], "Theme", None, notify=True)
    kconfig.write_value(runner, "kdeglobals", ["Icons"], "Theme", "Papirus")
    writes = [call for call in runner.calls if call[0] == "kwriteconfig6"]
    assert ["--notify" in call for call in writes] == [True, True, False]
