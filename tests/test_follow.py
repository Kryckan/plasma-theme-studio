# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Follow mode: the mapping, the watcher, the one snapshot, switching off and the command line.
No real tool runs, nothing sleeps: the watcher is given a clock, and the palette files are fakes."""

import json
import os
import signal
import threading

import pytest

from plasma_theme_studio import cli, follow, palette, paths
from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply import snapshot as snapshots
from plasma_theme_studio.apply.runner import Result
from plasma_theme_studio.model.theme import Theme

DARK = ("#1e1e2e", "#cdd6f4", ["#f38ba8", "#a6e3a1", "#f9e2af", "#89b4fa", "#cba6f7", "#94e2d5"])
LIGHT = ("#eff1f5", "#4c4f69", ["#d20f39", "#40a02b", "#df8e1d", "#1e66f5", "#8839ef", "#179299"])
OTHER = ("#002b36", "#93a1a1", ["#dc322f", "#859900", "#b58900", "#268bd2", "#d33682", "#2aa198"])


def wal_text(scheme=DARK) -> str:
    background, foreground, hues = scheme
    colors = {f"color{i}": "#808080" for i in range(16)}
    for i, hue in enumerate(hues):
        colors[f"color{i + 1}"] = hue
        colors[f"color{i + 9}"] = hue
    colors["color0"], colors["color15"] = background, foreground
    special = {"background": background, "foreground": foreground, "cursor": foreground}
    return json.dumps({"special": special, "colors": colors})


@pytest.fixture(autouse=True)
def plasma(monkeypatch, home):
    """A Plasma session with its own runtime folder for the watcher's lock."""
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-test")
    runtime = home / "run"
    runtime.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))


@pytest.fixture
def wal(home):
    path = home / ".cache/wal/colors.json"
    path.parent.mkdir(parents=True)
    path.write_text(wal_text())
    return path


@pytest.fixture
def source(wal):
    return palette.PaletteFile("pywal", wal)


@pytest.fixture
def theme():
    theme = Theme()
    theme.set("meta", "name", "My Theme")
    theme.set("colors", "window", "#1e1e2e")  # a dark theme: the dark colors of the palette are followed
    return theme


def tree(home):
    """Every file below the home with its bytes: what undo must give back. The app's own data and the
    lock's folder are left out."""
    found = {}
    for path in sorted(home.rglob("*")):
        relative = path.relative_to(home)
        if relative.parts[0] == "run" or relative.parts[:3] == (".local", "share", "plasma-theme-studio"):
            continue
        if path.is_file():
            found[str(relative)] = path.read_bytes()
    return found


def active_scheme(runner):
    return runner.get("kdeglobals", ["General"], "ColorScheme")


def scheme_file(home):
    return home / ".local/share/color-schemes/MyThemePalette.colors"


# ----------------------------------------------------------------- the mapping


def test_the_colors_are_those_of_import_colors(theme):
    state = follow.State("My Theme", "dark", "pywal", "x")
    colors = follow.colors_from(state, wal_text())
    expected = palette.ensure_contrast(dict(palette.from_pywal_text(wal_text()).dark))
    assert colors == expected
    light = follow.colors_from(follow.State("My Theme", "light", "pywal", "x"), wal_text())
    assert light == palette.ensure_contrast(dict(palette.from_pywal_text(wal_text()).light))


def test_poor_contrast_is_corrected():
    muddy = ("#202020", "#2a2a2a", ["#303030"] * 6)  # text almost as dark as the background
    colors = follow.colors_from(follow.State("T", "dark", "pywal", "x"), wal_text(muddy))
    assert not [pair for pair in palette.contrast_report(colors) if not pair.passes]


def test_choices_of_the_mapping_dialog_are_kept_for_the_next_palette():
    state = follow.State("T", "dark", "pywal", "x")
    mapped = dict(palette.from_pywal_text(wal_text(DARK)).dark)
    chosen = dict(mapped, accent="#f38ba8")  # the person took color1 for the accent
    assert chosen["accent"] != mapped["accent"]
    state.overrides = follow.overrides_from_choice("pywal", wal_text(DARK), mapped, chosen)
    assert list(state.overrides) == ["accent"]
    colors = follow.colors_from(state, wal_text(OTHER))
    assert (
        colors["accent"].lower()
        == palette.ensure_contrast(dict(palette.from_pywal_text(wal_text(OTHER)).dark, accent="#dc322f"))[
            "accent"
        ].lower()
    )
    # a color that is not in the file is not kept: that role follows the automatic mapping
    derived = dict(mapped, view="#123456")
    assert follow.overrides_from_choice("pywal", wal_text(DARK), mapped, derived) == {}


def test_matugen_text_is_followed_too():
    dark = {"primary": "#a8c8ff", "surface": "#111318", "on_surface": "#e2e2e9", "error": "#ffb4ab"}
    light = {"primary": "#415f91", "surface": "#f9f9ff", "on_surface": "#191c20", "error": "#ba1a1a"}
    text = json.dumps({"colors": {"dark": dark, "light": light}})
    assert follow.detect_kind(text) == "matugen"
    state = follow.State("T", "dark", "matugen", "x")
    expected = palette.ensure_contrast(dict(palette.from_matugen_text(text).dark))
    assert follow.colors_from(state, text) == expected
    assert expected["window"] == "#111318"


def test_a_bad_palette_gives_a_reason_not_colors():
    state = follow.State("T", "dark", "pywal", "x")
    for text in ("", "{", "[]", '{"colors": 3}', "not json"):
        assert not isinstance(follow.colors_from(state, text), dict)


def test_offered_when_a_file_exists_or_a_tool_is_installed(home, runner, wal):
    assert follow.offered(runner)
    wal.unlink()
    runner.missing = set()
    assert follow.offered(runner) is True  # no file, but a tool
    runner.missing = {"wal", "matugen"}
    assert follow.offered(runner) is False
    runner.missing = {"matugen"}
    assert follow.default_source(runner).path == home / ".cache/wal/colors.json"


# ----------------------------------------------------------------- switching on


def test_switching_on_takes_one_snapshot_and_applies(home, desktop_runner, theme, source):
    runner = desktop_runner
    done = follow.enable(theme, runner, source, variant="dark")
    assert done.applied
    assert len(snapshots.list_snapshots()) == 1
    assert active_scheme(runner) == "MyThemePalette"
    text = scheme_file(home).read_text()
    assert "BackgroundNormal=30,30,46" in text  # the palette's background
    assert follow.is_on()
    assert follow.state_path().is_file() and follow.autostart_path().is_file()
    assert runner.launched and runner.launched[-1][-1] == "follow"
    entry = follow.autostart_path().read_text()
    exec_line = next(line for line in entry.splitlines() if line.startswith("Exec="))
    assert exec_line.endswith(" follow")
    assert "OnlyShowIn=KDE;" in entry


def test_the_snapshot_covers_every_file_follow_mode_writes(home, desktop_runner, theme, source):
    follow.enable(theme, desktop_runner, source)
    snapshot = snapshots.latest()
    covered = {entry["path"] for entry in snapshot.files}
    assert covered == {
        str(follow.state_path()),
        str(follow.autostart_path()),
        str(scheme_file(home)),
    }
    assert snapshot.reached == ("colors", "accent")


def test_automatic_changes_take_no_snapshot_and_change_the_colors(home, desktop_runner, theme, source, wal):
    runner = desktop_runner
    follow.enable(theme, runner, source, variant="dark")
    first = scheme_file(home).read_text()
    wal.write_text(wal_text(OTHER))
    outcome = follow.apply_palette(follow.load_state(), runner)
    assert outcome.kind == "applied"
    assert scheme_file(home).read_text() != first
    assert "BackgroundNormal=0,43,54" in scheme_file(home).read_text()
    assert len(snapshots.list_snapshots()) == 1
    assert active_scheme(runner) == "MyThemePalette"


def test_only_colors_are_touched(home, desktop_runner, theme, source, wal):
    runner = desktop_runner
    for key, value in (("General", "fontsetting"), ("Icons", "Theme")):
        runner.set("kdeglobals", [key], "Keep", value)
    runner.set("kwinrc", ["org.kde.kdecoration2"], "theme", "Breeze")
    before = {k: v for k, v in tree(home).items() if "color-schemes" not in k and "follow" not in k}
    follow.enable(theme, runner, source)
    wal.write_text(wal_text(OTHER))
    follow.apply_palette(follow.load_state(), runner)
    assert runner.get("kwinrc", ["org.kde.kdecoration2"], "theme") == "Breeze"
    assert runner.get("kdeglobals", ["Icons"], "Keep") == "Theme"
    assert (home / ".config/kwinrc").read_bytes() == before[".config/kwinrc"]
    assert not (home / ".local/share/plasma").exists() and not (home / ".local/share/aurorae").exists()
    # the theme's own scheme, a theme file or anything else the app writes is not made
    assert not (home / ".local/share/plasma-theme-studio/themes").exists()


def test_switching_off_goes_back_byte_for_byte(home, desktop_runner, theme, source, wal):
    runner = desktop_runner
    runner.set("kdeglobals", ["General"], "ColorScheme", "BreezeDark")
    runner.set("kdeglobals", ["Colors:Window"], "BackgroundNormal", "35,38,41")
    before = tree(home)
    follow.enable(theme, runner, source)
    wal.write_text(wal_text(OTHER))
    follow.apply_palette(follow.load_state(), runner)
    wal.write_text(wal_text(LIGHT))
    follow.apply_palette(follow.load_state(), runner)
    assert tree(home) != before
    done = follow.disable(runner)
    assert not done.failures
    after = {k: v for k, v in tree(home).items()}
    after.pop(".cache/wal/colors.json"), before.pop(".cache/wal/colors.json")
    assert after == before
    assert active_scheme(runner) == "BreezeDark"
    assert snapshots.list_snapshots() == []
    assert not follow.is_on()


def test_undo_of_the_snapshot_switches_it_off_and_stops_the_watcher(home, desktop_runner, theme, source):
    runner = desktop_runner
    before = {k: v for k, v in tree(home).items()}
    follow.enable(theme, runner, source)
    watcher = follow.Watcher(runner, clock=lambda: 0.0, log=lambda line: None)
    assert watcher.tick() is True
    failures = engine.restore(snapshots.latest(), runner, consume=True)
    assert not failures
    assert tree(home) == before
    assert not follow.is_on()
    assert watcher.tick() is False  # the watcher ends by itself: its state file is gone


def test_off_after_another_apply_keeps_what_was_applied_later(home, desktop_runner, theme, source):
    runner = desktop_runner
    follow.enable(theme, runner, source)
    other = Theme()
    other.set("meta", "name", "Other One")
    other.set("colors", "window", "#e8e0d0")
    engine.apply(other, runner)
    done = follow.disable(runner)
    assert not follow.is_on() and not follow.autostart_path().exists()
    assert "stay" in str(done.message)
    assert scheme_file(home).exists()  # not undone behind the person's back
    assert len(snapshots.list_snapshots()) == 2
    assert active_scheme(runner) == "OtherOne"


def test_a_failed_switch_on_leaves_nothing(home, desktop_runner, theme, source):
    runner = desktop_runner
    before = tree(home)
    working = runner.handlers["plasma-apply-colorscheme"]
    runner.handlers["plasma-apply-colorscheme"] = lambda argv: (
        Result(1, "", "it broke") if "MyThemePalette" in argv else working(argv)
    )
    with pytest.raises(follow.FollowError):
        follow.enable(theme, runner, source)
    assert tree(home) == before
    assert snapshots.list_snapshots() == []
    assert not follow.is_on()


def test_a_scheme_file_that_is_not_ours_blocks_it(home, desktop_runner, theme, source):
    scheme_file(home).parent.mkdir(parents=True)
    scheme_file(home).write_text("[General]\nName=Somebody else's\n")
    before = tree(home)
    with pytest.raises(follow.FollowError):
        follow.enable(theme, desktop_runner, source)
    assert tree(home) == before and snapshots.list_snapshots() == []


def test_not_in_a_plasma_session_nothing_is_switched_on_or_applied(
    home, desktop_runner, theme, source, monkeypatch
):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    with pytest.raises(follow.FollowError):
        follow.enable(theme, desktop_runner, source)
    assert snapshots.list_snapshots() == [] and not follow.is_on()
    state = follow.State("My Theme", "dark", "pywal", str(source.path))
    assert follow.apply_palette(state, desktop_runner).kind == "ignored"
    assert not follow.is_plasma_session({"XDG_CURRENT_DESKTOP": "KDE"})  # no display
    assert follow.is_plasma_session({"XDG_CURRENT_DESKTOP": "ubuntu:KDE", "DISPLAY": ":0"})


def test_switching_on_again_changes_the_choice_without_a_new_snapshot(
    home, desktop_runner, theme, source, wal
):
    runner = desktop_runner
    follow.enable(theme, runner, source, variant="dark")
    first = follow.load_state().snapshot
    follow.enable(theme, runner, source, variant="light")
    assert len(snapshots.list_snapshots()) == 1
    assert follow.load_state().snapshot == first and follow.load_state().variant == "light"


def test_no_palette_yet_waits_for_one(home, desktop_runner, theme):
    source = palette.PaletteFile("pywal", home / ".cache/wal/colors.json")
    done = follow.enable(theme, desktop_runner, source)
    assert not done.applied and follow.is_on()
    assert not scheme_file(home).exists()


# ----------------------------------------------------------------- the watcher


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def watching(home, desktop_runner, theme, source):
    follow.enable(theme, desktop_runner, source)
    lines = []
    clock = Clock()
    watcher = follow.Watcher(desktop_runner, clock=clock, log=lines.append)
    watcher.tick()  # looks at the palette that is there: the same colors, nothing is done
    clock.now += follow.POLL
    watcher.tick()
    lines.clear()
    return watcher, clock, lines, desktop_runner, source.path


def write(path, text):
    path.write_text(text)
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))  # a later time, not a real wait


def step(watcher, clock, seconds=None):
    clock.now += follow.POLL if seconds is None else seconds
    return watcher.tick()


def test_a_burst_of_writes_is_one_apply(watching):
    watcher, clock, lines, runner, path = watching
    applied = len(runner.applied)
    for scheme in (OTHER, LIGHT, DARK, OTHER):
        write(path, wal_text(scheme))
        step(watcher, clock, 0.4)  # shorter than the debounce: the file is still being written
    assert lines == [] and len(runner.applied) == applied
    step(watcher, clock)  # it has stayed as it is: first sight of the final version
    step(watcher, clock)
    assert len(lines) == 1 and lines[0].startswith("follow: applied")
    step(watcher, clock), step(watcher, clock)
    assert len(lines) == 1  # nothing more while nothing changes


def test_nothing_runs_while_nothing_changes(watching):
    watcher, clock, lines, runner, path = watching
    calls = len(runner.calls)
    for _ in range(50):
        assert step(watcher, clock)
    assert len(runner.calls) == calls and lines == []


def test_a_palette_that_is_replaced_by_a_new_file_is_followed(watching, home):
    watcher, clock, lines, runner, path = watching
    new = path.with_name("colors.json.new")
    new.write_text(wal_text(OTHER))
    os.replace(new, path)  # what pywal does: a new file takes the place
    step(watcher, clock), step(watcher, clock)
    assert len(lines) == 1
    assert "BackgroundNormal=0,43,54" in scheme_file(home).read_text()
    # and the file is missing for a moment in between
    path.unlink()
    assert step(watcher, clock)
    path.write_text(wal_text(LIGHT))
    step(watcher, clock), step(watcher, clock)
    assert len(lines) == 2


def test_an_unreadable_half_written_or_wrong_palette_is_ignored(watching, home):
    watcher, clock, lines, runner, path = watching
    first = scheme_file(home).read_text()
    for text in ('{"special": {"backgr', "", "[1, 2]", '{"colors": {"color0": "nope"}}'):
        write(path, text)
        step(watcher, clock), step(watcher, clock)
    assert scheme_file(home).read_text() == first
    assert all("ignored" in line for line in lines) and lines
    seen = len(lines)
    step(watcher, clock), step(watcher, clock)
    assert len(lines) == seen  # a version that was dealt with is not looked at again
    write(path, wal_text(OTHER))  # the finished file is followed
    step(watcher, clock), step(watcher, clock)
    assert lines[-1].startswith("follow: applied")


def test_an_oversized_palette_is_not_read_beyond_the_limit(watching, home, monkeypatch):
    watcher, clock, lines, runner, path = watching
    asked = []
    real = follow.safefile.read_regular

    def spy(file, limit=0):
        asked.append(limit)
        return real(file, limit)

    monkeypatch.setattr(follow.safefile, "read_regular", spy)
    with open(path, "wb") as handle:  # a header and then a hole: the size is only claimed
        handle.write(b'{"special": ')
        handle.truncate(palette.MAX_FILE_BYTES + 5_000_000)
    step(watcher, clock), step(watcher, clock)
    assert max(asked) <= palette.MAX_FILE_BYTES
    assert follow.read_palette_text(path) is None
    assert lines and "ignored" in lines[-1]


def test_the_same_colors_written_again_change_nothing(watching):
    watcher, clock, lines, runner, path = watching
    applied = len(runner.applied)
    write(path, wal_text(DARK) + "\n\n")  # new time and size, the same palette
    step(watcher, clock), step(watcher, clock)
    assert lines == [] and len(runner.applied) == applied


def test_a_palette_that_is_a_pipe_or_a_folder_is_ignored(watching, home):
    watcher, clock, lines, runner, path = watching
    path.unlink()
    os.mkfifo(path)  # reading it would block
    step(watcher, clock), step(watcher, clock)
    assert follow.read_palette_text(path) is None
    assert lines and "ignored" in lines[-1]


def test_the_watcher_never_applies_outside_a_plasma_session(home, desktop_runner, theme, source, monkeypatch):
    follow.enable(theme, desktop_runner, source)
    first = scheme_file(home).read_text()
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    lines = []
    clock = Clock()
    watcher = follow.Watcher(desktop_runner, clock=clock, log=lines.append)
    write(source.path, wal_text(OTHER))
    step(watcher, clock), step(watcher, clock)
    assert scheme_file(home).read_text() == first
    assert lines and "not a Plasma session" in lines[-1]


def test_nothing_is_looked_at_faster_than_once_a_second():
    assert follow.POLL >= 1.0 and follow.DEBOUNCE >= 1.0


def test_watch_stops_on_sigterm_and_restores_the_signal_handlers(
    home, desktop_runner, theme, source, monkeypatch
):
    follow.enable(theme, desktop_runner, source)
    lines = []
    sent = []
    real = follow.Watcher.tick

    def tick(self):
        if not sent:
            sent.append(True)
            os.kill(os.getpid(), signal.SIGTERM)  # the handler of watch() runs, the loop then ends
        return real(self)

    monkeypatch.setattr(follow.Watcher, "tick", tick)
    before = signal.getsignal(signal.SIGTERM)
    assert follow.watch(desktop_runner, log=lines.append) == 0
    assert lines[0] == "follow: watching" and lines[-1] == "follow: stopped"
    assert signal.getsignal(signal.SIGTERM) == before
    assert not follow.watcher_running()  # the lock was let go


def test_a_second_watcher_does_not_start(home, desktop_runner, theme, source):
    follow.enable(theme, desktop_runner, source)
    held = follow._try_lock(follow.lock_path())
    try:
        assert follow.watcher_running()
        lines = []
        assert follow.watch(desktop_runner, log=lines.append) == 0
        assert lines == ["follow: another watcher is already running"]
    finally:
        held.close()
    assert not follow.watcher_running()


def test_watch_does_nothing_when_follow_mode_is_off(home, desktop_runner):
    lines = []
    assert follow.watch(desktop_runner, log=lines.append) == 0
    assert "off" in lines[-1]
    assert not follow.watcher_running()


# ----------------------------------------------------------------- the command line


@pytest.fixture
def system(desktop_runner, monkeypatch):
    monkeypatch.setattr(cli, "SystemRunner", lambda: desktop_runner)
    monkeypatch.setattr(cli, "_load_translation", lambda: None)
    return desktop_runner


def test_cli_on_status_once_off(home, system, wal, theme, capsys):
    path = home / "theme.toml"
    theme.save(path)
    before = {k: v for k, v in tree(home).items() if k != "theme.toml"}
    assert cli.main(["follow", "status"]) == 0
    assert "off" in capsys.readouterr().out
    capsys.readouterr()
    assert cli.main(["follow", "--once"]) == 1  # off: nothing to apply
    assert "off" in capsys.readouterr().err

    assert cli.main(["follow", "on", str(path), "--palette", str(wal)]) == 0
    assert active_scheme(system) == "MyThemePalette"
    assert cli.main(["follow", "status"]) == 0
    out = capsys.readouterr().out
    assert "on, following" in out and str(wal) in out

    write(wal, wal_text(OTHER))
    assert cli.main(["follow", "--once"]) == 0
    assert "BackgroundNormal=0,43,54" in scheme_file(home).read_text()
    assert cli.main(["follow", "--once"]) == 0
    assert "already" in capsys.readouterr().out.splitlines()[-1]
    assert len(snapshots.list_snapshots()) == 1

    assert cli.main(["follow", "off"]) == 0
    after = {k: v for k, v in tree(home).items() if k not in ("theme.toml", ".cache/wal/colors.json")}
    before.pop(".cache/wal/colors.json", None)
    assert after == before


def test_cli_on_needs_a_theme_file_and_reports_a_refusal(home, system, wal, capsys):
    assert cli.main(["follow", "on"]) == 2
    assert cli.main(["follow", "on", str(home / "missing.toml")]) == 1
    bad = home / "bad.json"
    bad.write_text("{}")
    path = home / "theme.toml"
    Theme().save(path)
    assert cli.main(["follow", "on", str(path), "--palette", str(bad)]) == 1
    assert "not switched on" in capsys.readouterr().err
    assert not follow.is_on() and snapshots.list_snapshots() == []


def test_the_paths_stay_inside_the_home(home, desktop_runner, theme, source):
    follow.enable(theme, desktop_runner, source)
    for path in (follow.state_path(), follow.autostart_path(), scheme_file(home)):
        assert path.is_relative_to(home)
    assert follow.state_path().is_relative_to(paths.config_home())


# ----------------------------------------------------------------- repairs after the check


def test_switching_on_again_under_another_name_leaves_no_second_scheme_file(
    home, desktop_runner, theme, source
):
    before = tree(home)
    follow.enable(theme, desktop_runner, source, variant="dark")
    other = Theme()
    other.set("meta", "name", "Other")
    other.set("colors", "window", "#1e1e2e")
    follow.enable(other, desktop_runner, source, variant="dark")
    assert follow.load_state().name == "My Theme"  # the one scheme file the snapshot knows
    assert not scheme_file(home).with_name("OtherPalette.colors").exists()
    follow.disable(desktop_runner)
    assert tree(home) == before


def test_the_state_file_does_not_come_back_after_an_undo_during_an_apply(
    home, desktop_runner, theme, source, monkeypatch
):
    follow.enable(theme, desktop_runner, source)
    state = follow.load_state()
    real = follow._write_and_reload

    def undone_meanwhile(follow_theme, runner):
        changed = real(follow_theme, runner)
        follow.state_path().unlink()  # the undo restores the snapshot: no state file
        return changed

    monkeypatch.setattr(follow, "_write_and_reload", undone_meanwhile)
    write(source.path, wal_text(OTHER))
    follow.apply_palette(state, desktop_runner)
    assert not follow.state_path().exists() and not follow.is_on()


def test_an_undo_that_comes_during_the_write_waits_and_leaves_the_home_as_it_was(
    home, desktop_runner, theme, source, monkeypatch
):
    def without_palette():
        return {path: data for path, data in tree(home).items() if path != ".cache/wal/colors.json"}

    before = without_palette()
    follow.enable(theme, desktop_runner, source)
    state = follow.load_state()
    real = follow._write_and_reload
    answer = {}

    def undo_arrives_first(follow_theme, runner):
        # The undo (switching off is one) starts when the watcher has checked the state and is about to write.
        thread = threading.Thread(target=lambda: answer.update(done=follow.disable(desktop_runner)))
        thread.start()
        thread.join(0.5)
        answer["waited"] = thread.is_alive()  # it has to wait for the write to end
        answer["thread"] = thread
        return real(follow_theme, runner)

    monkeypatch.setattr(follow, "_write_and_reload", undo_arrives_first)
    write(source.path, wal_text(OTHER))
    follow.apply_palette(state, desktop_runner)
    answer["thread"].join(20)
    assert answer["waited"] and "done" in answer
    assert without_palette() == before and not follow.is_on()


def test_nothing_is_applied_when_follow_mode_went_off_before_the_colors_are_written(
    home, desktop_runner, theme, source
):
    follow.enable(theme, desktop_runner, source)
    state = follow.load_state()
    follow.state_path().unlink()
    write(source.path, wal_text(OTHER))
    assert follow.apply_palette(state, desktop_runner).kind == "ignored"
    assert "BackgroundNormal=0,43,54" not in scheme_file(home).read_text()


def test_a_launcher_path_with_a_line_break_cannot_make_lines_of_its_own(
    home, desktop_runner, theme, source, monkeypatch
):
    monkeypatch.setattr(follow, "launcher", lambda: ["/tmp/a\nX-Evil=1\nExec=/bin/evil"])
    before = tree(home)
    with pytest.raises(follow.FollowError):
        follow.autostart_text()
    with pytest.raises(follow.FollowError):
        follow.enable(theme, desktop_runner, source)
    assert tree(home) == before and snapshots.list_snapshots() == []


def test_an_autostart_entry_that_is_not_ours_is_not_replaced(home, desktop_runner, theme, source):
    entry = follow.autostart_path()
    entry.parent.mkdir(parents=True)
    entry.write_text("[Desktop Entry]\nType=Application\nName=Mine\nExec=/bin/true\n")
    before = tree(home)
    with pytest.raises(follow.FollowError):
        follow.enable(theme, desktop_runner, source)
    assert tree(home) == before and not follow.is_on()


def test_the_lock_file_is_not_opened_through_a_link(home):
    target = home / "victim"
    target.write_text("keep")
    link = home / "run" / "lock-link"
    link.symlink_to(target)
    assert follow._try_lock(link) is None
    assert target.read_text() == "keep"
    handle = follow._try_lock(home / "run" / "plain.lock")
    assert handle is not None
    handle.close()


def test_a_watcher_that_cannot_get_the_lock_writes_nothing_and_leaves_the_state(
    home, desktop_runner, theme, source, monkeypatch
):
    from plasma_theme_studio import writelock

    follow.enable(theme, desktop_runner, source)
    state = follow.load_state()
    before = tree(home)
    monkeypatch.setattr(writelock, "WAIT", 0.2)
    held = writelock._acquire(writelock.lock_file())  # another process: only the file lock tells
    try:
        write(source.path, wal_text(OTHER))
        before = tree(home)
        outcome = follow.apply_palette(state, desktop_runner)
    finally:
        held.close()
    assert outcome.kind == "busy" and outcome.message == writelock.Busy().message
    assert tree(home) == before and follow.is_on()


def test_a_palette_that_met_a_busy_lock_is_applied_at_a_later_look(watching, monkeypatch):
    from plasma_theme_studio import writelock

    watcher, clock, lines, runner, path = watching
    monkeypatch.setattr(writelock, "WAIT", 0.1)
    held = writelock._acquire(writelock.lock_file())  # an undo in another process holds the lock
    try:
        write(path, wal_text(OTHER))
        step(watcher, clock), step(watcher, clock)
        assert any("busy" in line for line in lines)
    finally:
        held.close()
    lines.clear()
    step(watcher, clock), step(watcher, clock)  # the lock is free: the same palette version is tried again
    assert len(lines) == 1 and lines[0].startswith("follow: applied")


def test_a_switch_off_that_cannot_get_the_lock_says_so_and_changes_nothing(
    home, desktop_runner, theme, source, monkeypatch
):
    from plasma_theme_studio import writelock

    follow.enable(theme, desktop_runner, source)
    before = tree(home)
    monkeypatch.setattr(writelock, "WAIT", 0.2)
    held = writelock._acquire(writelock.lock_file())
    try:
        done = follow.disable(desktop_runner)
    finally:
        held.close()
    assert done.failures and "not switched off" in str(done.message)
    assert tree(home) == before and follow.is_on()
