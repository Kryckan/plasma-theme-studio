# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""An undo over several snapshots waits for the desktop's daemons once, not once per snapshot."""

from plasma_theme_studio import paths
from plasma_theme_studio.apply import engine, sidefiles
from plasma_theme_studio.apply import snapshot as snapshots
from plasma_theme_studio.model.theme import Theme


def waits(monkeypatch):
    seen = []
    monkeypatch.setattr(sidefiles, "_wait_until_quiet", lambda recorded: seen.append(list(recorded)))
    return seen


def daemon_writes(text):
    """What a daemon of the desktop writes in reaction to an apply."""
    path = paths.config_home() / "xsettingsd" / "xsettingsd.conf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def three_applies(runner):
    theme = Theme()
    first = engine.apply(theme, runner).snapshot
    daemon_writes("one")
    for number, color in enumerate(("#ff0000", "#00ff00")):
        theme.set("colors", "accent", color)
        engine.apply(theme, runner)
        daemon_writes(f"two{number}")
    return first


def test_the_undo_of_three_applies_waits_once(home, runner, monkeypatch):
    first = three_applies(runner)
    seen = waits(monkeypatch)
    reached, failures = engine.restore_to(first, runner)
    assert (reached.id, failures) == (first.id, [])
    assert len(seen) == 1 and seen[0]
    assert snapshots.list_snapshots() == []


def test_each_snapshot_alone_still_waits_for_itself(home, runner, monkeypatch):
    three_applies(runner)
    seen = waits(monkeypatch)
    newest = snapshots.list_snapshots()[-1]
    engine.restore(newest, runner, consume=True)
    assert len(seen) == 1


def test_a_chain_without_a_difference_does_not_wait(home, runner, monkeypatch):
    first = engine.apply(Theme(), runner).snapshot
    seen = waits(monkeypatch)
    monkeypatch.setattr(sidefiles, "to_wait_for", lambda *a, **k: [])
    engine.restore_to(first, runner)
    assert seen == []


def test_the_progress_is_reported_once_per_snapshot(home, runner):
    first = three_applies(runner)
    steps = []
    engine.restore_to(first, runner, progress=lambda done, total: steps.append((done, total)))
    assert steps == [(1, 3), (2, 3), (3, 3)]


def test_a_failing_side_step_keeps_the_older_snapshots(home, runner, monkeypatch):
    first = three_applies(runner)

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(sidefiles, "restore", broken)
    reached, failures = engine.restore_to(first, runner)
    assert failures and reached.id != first.id
    assert len(snapshots.list_snapshots()) == 3  # the newest is marked tried, none is used up
