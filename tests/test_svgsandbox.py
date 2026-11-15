# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Drawing a picture somebody else made in a child process: the job, the cache, the hostile pictures
of test_repair_3 and test_repair_4, a child that hangs, a child that is killed, the frame editor's
placeholder and fallback, and the check an archive import makes."""

import sys
import time

import pytest

from plasma_theme_studio import svgsandbox
from test_frame_editor import EXTRA, editor
from test_repair_3 import bomb, with_artwork
from test_repair_4 import svg

GOOD = svg('<rect width="10" height="10" fill="#336699"/>')
HANG = [sys.executable, "-c", "import time; time.sleep(60)"]
KILLED = [sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"]


@pytest.fixture(autouse=True)
def empty_cache():
    svgsandbox.forget()
    yield
    svgsandbox.forget()


def hostile(*pictures):
    return pytest.mark.parametrize("raw", pictures, ids=lambda raw: str(len(raw)))


def test_a_good_picture_comes_back_as_a_small_png():
    outcome = svgsandbox.probe(GOOD)
    assert outcome.ok and outcome.png.startswith(b"\x89PNG") and len(outcome.png) < 50_000


def test_the_sheet_has_the_size_the_job_says():
    from PySide6.QtGui import QImage

    job = svgsandbox.tiles_job([(100, 40, False), (60, 20, True)], 2.0)
    width, height, places = svgsandbox.layout(job)
    outcome = svgsandbox.render(GOOD, job)
    image = QImage.fromData(outcome.png, "PNG")
    assert (image.width(), image.height()) == (width, height)
    assert len(places) == 2 and places[1][1] == places[0][3]


@pytest.mark.parametrize(
    "job",
    [
        {},
        {"ratio": 1, "tiles": []},
        {"ratio": 9, "tiles": [[10, 10, False]]},
        {"ratio": 1, "tiles": [[10**6, 10, False]]},
        {"ratio": 1, "tiles": [[10, 10, False]] * 9},
        {"ratio": 1, "tiles": [["a", 10, False]]},
    ],
)
def test_a_job_that_asks_for_too_much_is_refused_without_a_child(job, monkeypatch):
    monkeypatch.setattr(svgsandbox, "child_command", lambda: pytest.fail("no child for this job"))
    with pytest.raises(ValueError):
        svgsandbox.layout(job)
    assert svgsandbox.render(GOOD, job).failure == svgsandbox.FAILED


def test_a_broken_picture_fails_and_the_failure_is_kept():
    assert svgsandbox.probe(b"<svg").failure == svgsandbox.FAILED
    assert svgsandbox.cached(b"<svg", svgsandbox.THUMBNAIL).failure == svgsandbox.FAILED


def test_the_answer_is_cached_by_content_and_asks_the_child_once(monkeypatch):
    starts = []
    real = svgsandbox.child_command

    def counting():
        starts.append(1)
        return real()

    monkeypatch.setattr(svgsandbox, "child_command", counting)
    first = svgsandbox.probe(GOOD)
    again = svgsandbox.probe(bytes(bytearray(GOOD)))  # the same content, another object
    assert first is again and len(starts) == 1
    svgsandbox.probe(GOOD + b" ")
    assert len(starts) == 2


def test_the_cache_does_not_grow_without_end(monkeypatch):
    monkeypatch.setattr(
        svgsandbox, "_run", lambda svg, job, timeout: svgsandbox.Outcome(failure=svgsandbox.FAILED)
    )
    for number in range(svgsandbox.CACHE_SIZE + 5):
        svgsandbox.render(b"x%d" % number, svgsandbox.THUMBNAIL)
    assert len(svgsandbox._CACHE) == svgsandbox.CACHE_SIZE
    assert svgsandbox.cached(b"x0", svgsandbox.THUMBNAIL) is None  # the oldest went first


def test_a_child_that_hangs_is_killed_at_the_timeout(monkeypatch):
    monkeypatch.setattr(svgsandbox, "child_command", lambda: HANG)
    started = time.monotonic()
    outcome = svgsandbox.render(GOOD, svgsandbox.THUMBNAIL, timeout=0.5)
    assert outcome.failure == svgsandbox.TIMED_OUT
    assert time.monotonic() - started < 5
    assert svgsandbox.cached(GOOD, svgsandbox.THUMBNAIL).failure == svgsandbox.TIMED_OUT  # not tried again


def test_a_child_that_is_killed_is_a_failure_not_a_crash(monkeypatch):
    monkeypatch.setattr(svgsandbox, "child_command", lambda: KILLED)
    assert svgsandbox.probe(GOOD).failure == svgsandbox.FAILED


def test_a_child_that_cannot_start_is_a_failure(monkeypatch):
    monkeypatch.setattr(svgsandbox, "child_command", lambda: ["/nonexistent/program"])
    assert svgsandbox.probe(GOOD).failure == svgsandbox.FAILED


def test_an_answer_that_is_not_a_png_is_not_believed(monkeypatch):
    monkeypatch.setattr(svgsandbox, "child_command", lambda: [sys.executable, "-c", "print('hello')"])
    assert svgsandbox.probe(GOOD).failure == svgsandbox.FAILED


@hostile(
    bomb(30),
    svg(
        '<defs><filter id="b"><feGaussianBlur stdDeviation="5"/></filter></defs>'
        + '<rect width="4" height="4" filter="url(#b)"/>' * 200
    ),
    svg(
        '<defs><filter id="b"><feGaussianBlur stdDeviation="5"/></filter></defs>'
        '<g id="g">' + '<rect width="4" height="4" filter="url(#b)"/>' * 30 + "</g>"
        '<use xlink:href="#g"/>' * 100
    ),
)
def test_the_hostile_pictures_end_in_an_answer_or_a_failure_within_the_timeout(raw):
    started = time.monotonic()
    outcome = svgsandbox.render(raw, svgsandbox.THUMBNAIL, timeout=3)
    assert outcome.ok or outcome.failure in (svgsandbox.TIMED_OUT, svgsandbox.FAILED)
    assert time.monotonic() - started < 15


def test_the_child_limits_itself_before_it_reads_anything(monkeypatch):
    code = (
        "import resource, sys\n"
        "from plasma_theme_studio.ui import frame_child\n"
        "frame_child._limit(1 << 29, 5)\n"
        "assert resource.getrlimit(resource.RLIMIT_AS)[0] == 1 << 29\n"
        "assert resource.getrlimit(resource.RLIMIT_CPU)[0] == 5\n"
        "assert resource.getrlimit(resource.RLIMIT_CORE)[0] == 0\n"
        "sys.stdout.buffer.write(b'\\x89PNG\\r\\n\\x1a\\n')\n"
    )
    monkeypatch.setattr(svgsandbox, "child_command", lambda: [sys.executable, "-c", code])
    assert svgsandbox.probe(GOOD).ok


# ---- the frame editor


@pytest.fixture
def window(app, home, desktop_runner, monkeypatch):
    from plasma_theme_studio.ui.main_window import MainWindow

    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    window = MainWindow(desktop_runner)
    window.show()
    yield window
    window.undo_stack.setClean()
    window.close()


def own_picture(window, tmp_path):
    window.theme.save(tmp_path / "t.toml")
    window.path = tmp_path / "t.toml"
    fe = editor(window)
    fe.open_in_inkscape()
    target = tmp_path / "t-artwork" / "panel.svg"
    target.write_text(target.read_text().replace("</svg>", EXTRA + "</svg>"))
    fe.stamps["panel"] = (0, 0)
    fe.check_files()
    assert fe.sources["panel"][2].usable
    return fe


def test_an_own_picture_shows_a_placeholder_and_then_the_childs_drawing(window, tmp_path, monkeypatch):
    fe = own_picture(window, tmp_path)
    assert fe.view.message and not fe.view.tiles  # nothing is drawn in the window's thread
    assert fe.renderer("panel") is None
    fe.wait_drawing()
    assert fe.view.tiles and not fe.view.message
    assert fe.failure("panel") is None
    assert not fe.thumbnail("panel").isNull()


def test_an_own_picture_that_takes_too_long_falls_back_to_the_generated_frame(window, tmp_path, monkeypatch):
    monkeypatch.setattr(svgsandbox, "child_command", lambda: HANG)
    monkeypatch.setattr(svgsandbox, "TIMEOUT", 0.3)
    fe = own_picture(window, tmp_path)
    fe.wait_drawing()
    assert fe.failure("panel") == svgsandbox.TIMED_OUT
    assert fe.renderer("panel") is not None and not fe.view.tiles
    assert "takes too long to draw" in fe.problems.text()
    assert "takes too long to draw" in fe._subtitles[0]


def test_an_own_picture_that_cannot_be_drawn_says_so(window, tmp_path, monkeypatch):
    monkeypatch.setattr(svgsandbox, "child_command", lambda: KILLED)
    fe = own_picture(window, tmp_path)
    fe.wait_drawing()
    assert fe.failure("panel") == svgsandbox.FAILED
    assert "cannot be drawn" in fe.problems.text()


def test_a_generated_frame_is_drawn_in_the_app_and_needs_no_child(window, monkeypatch):
    monkeypatch.setattr(svgsandbox, "child_command", lambda: pytest.fail("no child for a generated frame"))
    fe = editor(window)
    assert not fe.wanted and fe.renderer("panel") is not None


# ---- the archive import


def test_an_import_keeps_artwork_the_child_can_draw(tmp_path):
    imported, _file = with_artwork(tmp_path, "ok")
    assert "panel" in imported.pending_artwork
    assert imported.get("artwork", "panel")


@pytest.mark.parametrize("child", [HANG, KILLED])
def test_an_import_drops_artwork_the_child_cannot_draw(tmp_path, monkeypatch, child):
    monkeypatch.setattr(svgsandbox, "child_command", lambda: child)
    monkeypatch.setattr(svgsandbox, "TIMEOUT", 0.3)
    imported, _file = with_artwork(tmp_path, "bad")
    assert imported.pending_artwork == {}
    assert imported.get("artwork", "panel") is None


# ---- repairs after the check


def test_a_timeout_is_only_remembered_for_a_while(monkeypatch):
    monkeypatch.setattr(svgsandbox, "child_command", lambda: HANG)
    assert svgsandbox.render(GOOD, svgsandbox.THUMBNAIL, timeout=0.3).failure == svgsandbox.TIMED_OUT
    assert svgsandbox.cached(GOOD, svgsandbox.THUMBNAIL).failure == svgsandbox.TIMED_OUT
    monkeypatch.setattr(svgsandbox, "RETRY_AFTER", 0.0)  # the busy moment is long past
    time.sleep(0.01)
    assert svgsandbox.cached(GOOD, svgsandbox.THUMBNAIL) is None
    monkeypatch.undo()
    assert svgsandbox.probe(GOOD).ok  # and the next try draws it


def test_an_import_tries_a_picture_that_timed_out_once_more(tmp_path, monkeypatch):
    real = svgsandbox.child_command
    asked = []

    def busy_then_fine():
        asked.append(1)
        return HANG if len(asked) == 1 else real()

    monkeypatch.setattr(svgsandbox, "child_command", busy_then_fine)
    monkeypatch.setattr(svgsandbox, "TIMEOUT", 0.3)
    imported, _file = with_artwork(tmp_path, "slow-once")
    assert "panel" in imported.pending_artwork and len(asked) == 2


def test_a_progress_window_shows_while_the_work_is_slow(window):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QProgressDialog

    seen = []

    def look():
        seen.append(any(d.isVisible() for d in window.findChildren(QProgressDialog)))

    timer = QTimer()
    timer.timeout.connect(look)
    timer.start(50)
    assert window._away(lambda progress: time.sleep(1.0) or "done", "Working…") == "done"
    timer.stop()
    assert any(seen)


def with_slow_own_picture(window, tmp_path):
    """A saved theme whose panel frame is an own picture; its text is returned too."""
    own_picture(window, tmp_path)
    window.theme.save(tmp_path / "t.toml")
    return plasmastyle_text(window)


def plasmastyle_text(window):
    from plasma_theme_studio.generators import plasmastyle

    return plasmastyle.own_artwork(window.theme, "panel").text


def test_an_own_picture_the_child_cannot_draw_in_time_is_not_installed(window, tmp_path, monkeypatch):
    from plasma_theme_studio.apply import engine
    from plasma_theme_studio.generators import plasmastyle

    text = with_slow_own_picture(window, tmp_path)
    assert EXTRA in text
    monkeypatch.setattr(svgsandbox, "child_command", lambda: HANG)
    monkeypatch.setattr(svgsandbox, "TIMEOUT", 0.3)
    svgsandbox.forget()
    theme = window.theme
    engine.apply(theme, window.runner)
    installed = list(
        (tmp_path / ".local/share/plasma/desktoptheme").glob(
            "PlasmaThemeStudio-*/widgets/panel-background.svg"
        )
    )
    assert installed and all(EXTRA not in path.read_text() for path in installed)
    assert any("could not be drawn in time" in str(p) for p in plasmastyle.artwork_problems(theme))
    assert plasmastyle.drawn_artwork(theme, "panel") is None and plasmastyle.status_words(theme) == ""


# ---- the second repair


def test_a_child_killed_from_outside_or_not_started_is_asked_again_later(monkeypatch):
    # The kernel's out-of-memory killer and a failed spawn say nothing about the picture.
    for command in (KILLED, ["/nonexistent/program"]):
        svgsandbox.forget()
        monkeypatch.setattr(svgsandbox, "child_command", lambda command=command: command)
        outcome = svgsandbox.probe(GOOD)
        assert outcome.failure == svgsandbox.FAILED and outcome.retry
        assert svgsandbox.cached(GOOD, svgsandbox.THUMBNAIL) is outcome  # not asked again at once
        monkeypatch.setattr(svgsandbox, "RETRY_AFTER", 0.0)
        time.sleep(0.01)
        assert svgsandbox.cached(GOOD, svgsandbox.THUMBNAIL) is None
        monkeypatch.undo()
    assert svgsandbox.probe(GOOD).ok


def test_a_picture_that_makes_the_child_fail_by_itself_stays_failed(monkeypatch):
    monkeypatch.setattr(svgsandbox, "child_command", lambda: [sys.executable, "-c", "raise SystemExit(3)"])
    outcome = svgsandbox.probe(GOOD)
    assert outcome.failure == svgsandbox.FAILED and not outcome.retry
    monkeypatch.setattr(svgsandbox, "RETRY_AFTER", 0.0)
    time.sleep(0.01)
    assert svgsandbox.cached(GOOD, svgsandbox.THUMBNAIL) is outcome


def test_an_import_tries_a_child_that_was_killed_once_more(tmp_path, monkeypatch):
    real = svgsandbox.child_command
    asked = []

    def killed_then_fine():
        asked.append(1)
        return KILLED if len(asked) == 1 else real()

    monkeypatch.setattr(svgsandbox, "child_command", killed_then_fine)
    imported, _file = with_artwork(tmp_path, "killed-once")
    assert "panel" in imported.pending_artwork and len(asked) == 2


def test_status_in_a_new_process_still_sees_a_package_installed_without_the_vetoed_picture(
    window, tmp_path, monkeypatch
):
    from plasma_theme_studio.apply import engine
    from plasma_theme_studio.generators import plasmastyle

    text = with_slow_own_picture(window, tmp_path)
    assert EXTRA in text
    monkeypatch.setattr(svgsandbox, "child_command", lambda: HANG)
    monkeypatch.setattr(svgsandbox, "TIMEOUT", 0.3)
    svgsandbox.forget()
    theme = window.theme
    engine.apply(theme, window.runner)
    assert engine.is_current(engine.build_plan(theme, window.runner), window.runner)
    generator = plasmastyle.PlasmaStyleGenerator()
    window.stop_page_workers()  # the editor's own drawing would fill the cache again
    svgsandbox.forget()  # another process knows nothing of the veto
    assert svgsandbox.cached(text.encode(), svgsandbox.THUMBNAIL) is None
    assert generator.is_active(theme, window.runner)
    # what the user sees: the plan is the installed package, every file is as it is, Apply has nothing to do
    assert plasmastyle.style_id(theme) == plasmastyle._current_style(window.runner)
    plan = engine.build_plan(theme, window.runner)
    assert engine.is_current(plan, window.runner)
    assert plasmastyle.style_id(theme) in plasmastyle.style_ids(theme)
    assert len(set(plasmastyle.style_ids(theme))) == 2


def test_a_theme_with_a_picture_nobody_has_drawn_is_planned_with_it_until_a_package_says_otherwise(
    window, tmp_path
):
    from plasma_theme_studio.generators import plasmastyle

    text = with_slow_own_picture(window, tmp_path)
    window.stop_page_workers()
    svgsandbox.forget()
    assert not any("vetoed" in name for name in [plasmastyle.style_id(window.theme)])
    assert any(EXTRA in file.content for file in plasmastyle.PlasmaStyleGenerator().files(window.theme))
    assert text


# ---- the fourth repair


def test_the_command_line_apply_draws_the_pictures_first_so_a_left_out_picture_is_installed_later(
    window, tmp_path, monkeypatch, capsys
):
    from plasma_theme_studio import cli
    from plasma_theme_studio.apply import engine

    text = with_slow_own_picture(window, tmp_path)
    window.stop_page_workers()
    real = svgsandbox.child_command
    monkeypatch.setattr(svgsandbox, "child_command", lambda: HANG)
    monkeypatch.setattr(svgsandbox, "TIMEOUT", 0.3)
    svgsandbox.forget()
    engine.apply(window.theme, window.runner)  # the picture is left out once
    monkeypatch.setattr(svgsandbox, "child_command", real)  # a fresh process, a child that works now
    svgsandbox.forget()
    monkeypatch.setattr(cli, "SystemRunner", lambda: window.runner)
    monkeypatch.setattr(cli, "_load_translation", lambda: None)
    assert cli.main(["apply", str(tmp_path / "t.toml")]) == 0
    assert "already uses" not in capsys.readouterr().out
    installed = list(
        (tmp_path / ".local/share/plasma/desktoptheme").glob(
            "PlasmaThemeStudio-*/widgets/panel-background.svg"
        )
    )
    assert any(EXTRA in path.read_text() for path in installed) and text


# ---- the third repair


def test_a_global_theme_export_leaves_out_a_picture_the_child_cannot_draw(window, tmp_path, monkeypatch):
    from plasma_theme_studio import globaltheme

    with_slow_own_picture(window, tmp_path)
    monkeypatch.setattr(svgsandbox, "child_command", lambda: HANG)
    monkeypatch.setattr(svgsandbox, "TIMEOUT", 0.3)
    svgsandbox.forget()
    folder = tmp_path / "exported"
    written = globaltheme.export_global_theme(window.theme, folder)
    svgs = [path for path in written if path.suffix == ".svg"]
    assert svgs and all(EXTRA not in path.read_text() for path in svgs)


def test_the_application_ending_the_wait_does_not_cut_the_work_off(window, monkeypatch):
    from PySide6.QtCore import QEventLoop

    ran = []
    # what QApplication.quit does to a nested loop: it returns at once
    monkeypatch.setattr(QEventLoop, "exec", lambda self, flags=None: 0)

    def slow(progress):
        time.sleep(0.4)
        ran.append(1)
        return "done"

    assert window._away(slow, "Working…") == "done" and ran == [1]


def test_a_window_is_not_closed_while_a_job_runs_off_the_gui_thread(window):
    from PySide6.QtCore import QTimer

    window.show()
    window.discard_on_close = True
    QTimer.singleShot(100, window.close)
    assert window._away(lambda progress: time.sleep(0.6) or "done", "Working…") == "done"
    assert window.isVisible()
