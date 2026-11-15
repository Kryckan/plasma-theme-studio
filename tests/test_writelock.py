# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The lock an undo and the follow mode watcher share (`writelock`)."""

import threading
import time

import pytest

from plasma_theme_studio import writelock


def test_a_second_holder_waits_until_the_first_lets_go():
    held = writelock._acquire(writelock.lock_file())  # another process, as far as flock can tell
    assert held is not None
    entered = threading.Event()

    def other():
        with writelock.exclusive():
            entered.set()

    thread = threading.Thread(target=other)
    thread.start()
    assert not entered.wait(0.3)
    held.close()
    assert entered.wait(5)
    thread.join(5)


def test_the_lock_can_be_taken_again_by_the_one_that_holds_it():
    with writelock.exclusive(), writelock.exclusive():
        pass
    with writelock.exclusive():  # and is free again afterwards
        pass


def test_a_holder_that_never_lets_go_is_waited_for_a_while_and_then_nothing_is_written(monkeypatch):
    monkeypatch.setattr(writelock, "WAIT", 0.2)
    held = writelock._acquire(writelock.lock_file())
    told = []
    monkeypatch.setattr(writelock, "on_wait", lambda: told.append(1))
    ran = []
    started = time.monotonic()
    with pytest.raises(writelock.Busy) as caught:
        with writelock.exclusive():
            ran.append(1)
    assert 0.15 < time.monotonic() - started < 3
    assert not ran and told == [1] and "Nothing was changed" in str(caught.value.message)
    held.close()
    with writelock.exclusive():  # and the lock is free again, nothing was left held
        pass


def test_a_thread_that_holds_the_lock_for_long_is_not_waited_for_longer_than_the_limit(monkeypatch):
    monkeypatch.setattr(writelock, "WAIT", 0.2)
    inside, release = threading.Event(), threading.Event()

    def holder():
        with writelock.exclusive():
            inside.set()
            release.wait(5)

    thread = threading.Thread(target=holder)
    thread.start()
    assert inside.wait(5)
    started = time.monotonic()
    with pytest.raises(writelock.Busy), writelock.exclusive():
        pass
    assert time.monotonic() - started < 3
    release.set()
    thread.join(5)


def test_a_lock_that_cannot_be_opened_does_not_stop_the_work(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "missing"))
    monkeypatch.setattr(writelock.tempfile, "gettempdir", lambda: str(tmp_path / "also-missing"))
    ran = []
    with writelock.exclusive():
        ran.append(1)
    assert ran


def test_a_file_swapped_for_a_pipe_just_before_it_is_opened_does_not_block_the_reader(tmp_path, monkeypatch):
    import os

    from plasma_theme_studio import safefile

    target = tmp_path / "colors.json"
    target.write_text("{}")
    real_open = os.open

    def swap_then_open(path, flags, *args, **kwargs):
        if str(path) == str(target):  # the person (or somebody else) replaces it at the worst moment
            target.unlink()
            os.mkfifo(target)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(safefile.os, "open", swap_then_open)
    answer = []
    thread = threading.Thread(target=lambda: answer.append(safefile.read_regular(target)), daemon=True)
    thread.start()
    thread.join(3)
    assert not thread.is_alive(), "the reader is stuck on a pipe"
    assert answer == [None]


def test_an_undo_that_cannot_get_the_lock_changes_nothing_and_says_so(monkeypatch, runner):
    from plasma_theme_studio.apply import engine

    monkeypatch.setattr(writelock, "WAIT", 0.2)
    held = writelock._acquire(writelock.lock_file())
    try:
        reached, failures = engine.restore_to(None, runner)  # the snapshot is never looked at
        assert engine.restore(None, runner, consume=True) == failures
    finally:
        held.close()
    assert reached is None and failures == [writelock.Busy().message]
