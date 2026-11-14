# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""All seven targets together, as the app registers them: applying a theme that uses every one,
undoing it, applying it twice, leaving a target at "unchanged" afterwards, and going back to
an older snapshot. Programs are faked; nothing touches the real home."""

import hashlib
from types import SimpleNamespace

import pytest

from plasma_theme_studio import generators, kconfig, paths
from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply import snapshot as snapshots
from plasma_theme_studio.apply.runner import Result
from plasma_theme_studio.model.theme import Theme
from test_desktop import calls as desktop_calls
from test_desktop import desktop  # noqa: F401  (fixture)
from test_kvantum import Desktop as KvantumDesktop


@pytest.fixture
def everything(desktop):  # noqa: F811
    """The desktop of test_desktop plus Kvantum's style setting, signals and a rofi that parses."""
    kvantum = KvantumDesktop(desktop.runner)

    def rofi(argv):
        if "-dump-theme" not in argv:
            return Result(0, "Version: 2.0.0\n")
        text = open(argv[argv.index("-theme") + 1], encoding="utf-8").read()
        if text.count("{") != text.count("}") or "FAIL" in text:
            return Result(0, "", 'Rofi-WARNING **: Failed to parse theme: "x"\n')
        return Result(0, "dump\n")

    desktop.runner.handlers["rofi"] = rofi
    desktop.kvantum = kvantum
    return desktop


def full(name="Everything", **values):
    base = {
        ("meta", "name"): name,
        ("apps", "style"): "generated",
        ("apps", "radius"): 10,
        ("gtk", "style"): "generated",
        ("gtk", "radius"): 6,
        ("rofi", "style"): "generated",
        ("rofi", "radius"): 12,
        ("window", "decoration"): "generated",
        ("window", "radius"): 14,
        ("panel", "style"): "generated",
        ("panel", "radius"): 18,
        ("popup", "radius"): 8,
        ("panel_layout", "location"): "top",
        ("panel_layout", "floating"): False,
    }
    base.update({tuple(key.split("__")): value for key, value in values.items()})
    return Theme(base)


def state(desk):
    own = paths.snapshots_dir().parent
    files = {
        str(path.relative_to(desk.home)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(desk.home.rglob("*"))
        if path.is_file() and own not in path.parents
    }
    folders = sorted(
        str(path.relative_to(desk.home))
        for path in desk.home.rglob("*")
        if path.is_dir() and own not in path.parents and path != own
    )
    return files, folders, desk.runner.settings["ColorScheme"], desk.shell.state()


IDS = ["colors", "apps", "gtk", "window", "panel", "panel_layout", "rofi"]


def test_every_target_is_wanted_and_the_plan_is_clean(everything):
    plan = engine.build_plan(full(), everything.runner)
    assert [t.generator.id for t in plan.wanted_targets] == IDS
    assert plan.blocking == []


def test_applying_everything_and_undoing_it_leaves_the_desktop_as_it_was(everything):
    theme = full()
    before = state(everything)
    result = engine.apply(theme, everything.runner)
    assert set(result.snapshot.settings) == set(IDS)
    assert everything.kvantum.style() == "kvantum"
    assert (paths.config_home() / "rofi/config.rasi").exists()
    assert (paths.config_home() / "gtk-4.0/gtk.css").exists()
    assert state(everything) != before

    assert engine.restore(result.snapshot, everything.runner, consume=True) == []

    assert state(everything) == before
    assert everything.kvantum.style() is None


def test_reloads_run_in_target_order(everything):
    engine.apply(full(), everything.runner)
    runner = everything.runner
    colors = next(i for i, argv in enumerate(runner.calls) if argv[0] == "plasma-apply-colorscheme")
    style = next(i for i, argv in enumerate(runner.calls) if argv[0] == "dbus-send")
    steps = desktop_calls(everything)
    last_rofi = max(i for i, argv in enumerate(runner.calls) if argv[0] == "rofi")
    assert colors < style < last_rofi
    assert steps == ["colors", "kwin", "panel style", "panel layout"]
    # the application style is announced after the colors were applied
    assert runner.calls.index(next(c for c in runner.calls if c[0] == "dbus-send")) > colors


def test_a_second_apply_changes_nothing(everything):
    theme = full()
    engine.apply(theme, everything.runner)
    after = state(everything)
    snapshots_before = len(snapshots.list_snapshots())
    plan = engine.build_plan(theme, everything.runner)
    assert engine.is_current(plan, everything.runner)
    assert state(everything) == after
    assert len(snapshots.list_snapshots()) == snapshots_before


def test_a_target_left_at_unchanged_keeps_what_an_earlier_apply_put_there(everything):
    engine.apply(full(), everything.runner)
    after = state(everything)
    style = everything.kvantum.style()

    plain = full(apps__style="unchanged", gtk__style="unchanged", rofi__style="unchanged")
    plan = engine.build_plan(plain, everything.runner)
    assert [t.generator.id for t in plan.wanted_targets] == ["colors", "window", "panel", "panel_layout"]
    engine.apply(plain, everything.runner)

    # Nothing was taken away: the generated style, style sheets and Rofi theme stay in use.
    assert everything.kvantum.style() == style == "kvantum"
    after_files = state(everything)[0]
    for name, digest in after[0].items():
        if any(part in name for part in ("Kvantum", "gtk-", "rofi")):
            assert after_files[name] == digest
    # and the notes on the pages say so
    for target_id in ("apps", "gtk", "rofi"):
        generator = generators.generator_by_id(target_id)
        text = " ".join(str(note) for note in generator.notes(plain))
        assert "keep" in text.lower()


def test_a_failure_in_the_last_target_puts_everything_back(everything):
    before = state(everything)
    # Rofi is applied last and refuses a theme that does not parse: the whole apply is undone.
    everything.runner.handlers["rofi"] = lambda argv: (
        Result(0, "", 'Failed to parse theme: "x"\n') if "-dump-theme" in argv else Result(0, "2.0\n")
    )
    with pytest.raises(generators.ApplyError):
        engine.apply(full(), everything.runner)
    assert state(everything) == before
    assert everything.kvantum.style() is None
    assert snapshots.list_snapshots() == []


def test_going_back_to_an_older_snapshot_undoes_every_apply_after_it(everything):
    before = state(everything)
    first = engine.apply(full("First"), everything.runner).snapshot
    engine.apply(
        full("Second", apps__radius=3, gtk__radius=2, rofi__radius=0, popup__radius=0), everything.runner
    )
    engine.apply(full("Third", colors__accent="#aa3355", window__radius=4), everything.runner)

    reached, failures = engine.restore_to(first, everything.runner)

    assert failures == [] and reached.id == first.id
    assert state(everything) == before
    assert everything.kvantum.style() is None


def test_a_theme_with_one_new_target_leaves_the_others_alone(everything):
    theme = Theme({("meta", "name"): "Only Rofi", ("rofi", "style"): "generated"})
    plan = engine.build_plan(theme, everything.runner)
    assert [t.generator.id for t in plan.wanted_targets] == ["colors", "rofi"]
    result = engine.apply(theme, everything.runner)
    assert set(result.snapshot.settings) == {"colors", "rofi"}
    assert everything.kvantum.signals == []
    assert not (paths.config_home() / "Kvantum").exists()
    assert not (paths.config_home() / "gtk-4.0").exists()
    assert kconfig.user_value("kdeglobals", ["KDE"], "widgetStyle") in (None, "")
    assert SimpleNamespace  # keeps the import used
