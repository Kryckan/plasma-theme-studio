# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What the engine does for any target: optional targets, files that are
recognized by a marker, and generated files that are no longer needed."""

import pytest

from plasma_theme_studio import kconfig
from plasma_theme_studio.apply import engine
from plasma_theme_studio.apply import snapshot as snapshots
from plasma_theme_studio.generators import XML_MARKER, ApplyError, Generator, PlannedFile, made_here
from plasma_theme_studio.generators.colorscheme import ColorSchemeGenerator
from plasma_theme_studio.messages import translate
from plasma_theme_studio.model.theme import Theme


class Frames(Generator):
    """A target like the generated window frame: one folder per look, named
    after the look, and a setting that says which folder is in use."""

    id = "frames"
    title = translate("core", "Frames")
    sections = ("window",)

    def __init__(self, home):
        self.root = home / ".local/share/frames"
        self.fail_reload = False

    def wanted(self, theme):
        return theme.get("window", "decoration") == "generated"

    def notes(self, theme):
        return [] if self.wanted(theme) else [translate("core", "Frames are left alone.")]

    def _name(self, theme):
        return f"pts-{theme.resolved('window', 'radius')}"

    def files(self, theme):
        content = f"{XML_MARKER}\n<svg r='{theme.resolved('window', 'radius')}'/>\n"
        return [PlannedFile(self.root / self._name(theme) / "frame.svg", content, XML_MARKER)]

    def stale_files(self, theme):
        stale = []
        for folder in sorted(self.root.glob("pts-*")):
            if folder.name != self._name(theme) and made_here(folder / "frame.svg"):
                stale += [folder / "frame.svg", folder]
        return stale

    def capture_settings(self, runner):
        return {"frame": kconfig.user_value("framesrc", ["General"], "frame")}

    def is_active(self, theme, runner):
        return kconfig.effective_value(runner, "framesrc", ["General"], "frame") == self._name(theme)

    def reload(self, theme, runner):
        if self.fail_reload:
            raise ApplyError(translate("core", "The frame was refused."))
        kconfig.write_value(runner, "framesrc", ["General"], "frame", self._name(theme))

    def restore_settings(self, settings, runner):
        kconfig.write_value(runner, "framesrc", ["General"], "frame", settings["frame"])


@pytest.fixture
def frames(home, use_generators):
    generator = Frames(home)
    use_generators(ColorSchemeGenerator(), generator)
    return generator


def generated(radius=5):
    return Theme({("window", "decoration"): "generated", ("shape", "radius"): radius})


def test_a_target_the_theme_does_not_ask_for_is_left_alone(home, runner, frames):
    plan = engine.build_plan(Theme(), runner)
    assert [target.wanted for target in plan.targets] == [True, False]
    assert [str(note) for note in plan.targets[1].notes] == ["Frames are left alone."]

    result = engine.apply(Theme(), runner)

    assert not frames.root.exists()
    assert kconfig.user_value("framesrc", ["General"], "frame") is None
    assert list(result.snapshot.settings) == ["colors"]
    assert engine.is_current(engine.build_plan(Theme()), runner)


def test_a_wanted_target_is_written_activated_and_undone(home, runner, frames):
    result = engine.apply(generated(), runner)

    assert (frames.root / "pts-5/frame.svg").read_text().startswith(XML_MARKER)
    assert kconfig.user_value("framesrc", ["General"], "frame") == "pts-5"
    assert engine.is_current(engine.build_plan(generated()), runner)

    assert engine.restore(result.snapshot, runner, consume=True) == []
    assert kconfig.user_value("framesrc", ["General"], "frame") is None
    assert not frames.root.exists()  # the folders the apply created are gone again


def test_a_new_look_replaces_the_old_folder_and_undo_brings_it_back(home, runner, frames):
    engine.apply(generated(5), runner)
    plan = engine.build_plan(generated(9), runner)
    assert plan.targets[1].stale == [frames.root / "pts-5/frame.svg", frames.root / "pts-5"]
    assert not engine.is_current(plan, runner)

    second = engine.apply(generated(9), runner)

    assert [folder.name for folder in frames.root.iterdir()] == ["pts-9"]
    assert kconfig.user_value("framesrc", ["General"], "frame") == "pts-9"

    engine.restore(second.snapshot, runner, consume=True)
    assert [folder.name for folder in frames.root.iterdir()] == ["pts-5"]
    assert "r='5'" in (frames.root / "pts-5/frame.svg").read_text()
    assert kconfig.user_value("framesrc", ["General"], "frame") == "pts-5"
    assert engine.is_current(engine.build_plan(generated(5)), runner)


def test_a_failed_reload_keeps_the_old_look(home, runner, frames):
    engine.apply(generated(5), runner)
    frames.fail_reload = True

    with pytest.raises(ApplyError):
        engine.apply(generated(9), runner)

    assert [folder.name for folder in frames.root.iterdir()] == ["pts-5"]
    assert kconfig.user_value("framesrc", ["General"], "frame") == "pts-5"
    assert runner.settings["ColorScheme"] == "MyTheme"
    assert len(snapshots.list_snapshots()) == 1


def test_folders_made_by_someone_else_are_never_removed(home, runner, frames):
    other = frames.root / "pts-77"
    other.mkdir(parents=True)
    (other / "frame.svg").write_text("<svg/>\n")

    engine.apply(generated(5), runner)

    assert (other / "frame.svg").read_text() == "<svg/>\n"


def test_a_file_without_the_marker_is_foreign(home, runner, frames):
    target = frames.root / "pts-5/frame.svg"
    target.parent.mkdir(parents=True)
    target.write_text("<svg hand-made='yes'/>\n")

    assert engine.build_plan(generated()).foreign_files == [target]
    with pytest.raises(engine.ApplyBlocked):
        engine.apply(generated(), runner)


def test_config_keys_are_written_read_and_removed(home, runner):
    assert kconfig.user_value("somerc", ["A", "B c"], "Key") is None
    runner.defaults[("somerc", ("A", "B c"), "Key")] = "from the system"
    assert kconfig.effective_value(runner, "somerc", ["A", "B c"], "Key") == "from the system"

    kconfig.write_value(runner, "somerc", ["A", "B c"], "Key", "-1 2")
    kconfig.write_value(runner, "somerc", ["A"], "Other", "x")

    assert (home / ".config/somerc").read_text() == "[A][B c]\nKey=-1 2\n\n[A]\nOther=x\n"
    assert kconfig.user_value("somerc", ["A", "B c"], "Key") == "-1 2"
    assert kconfig.effective_value(runner, "somerc", ["A", "B c"], "Key") == "-1 2"

    kconfig.write_value(runner, "somerc", ["A", "B c"], "Key", None)
    assert kconfig.user_value("somerc", ["A", "B c"], "Key") is None
    assert kconfig.effective_value(runner, "somerc", ["A", "B c"], "Key") == "from the system"


def test_a_config_change_that_does_not_stick_is_an_error(home, runner):
    runner.handlers["kwriteconfig6"] = lambda argv: type(runner.run(["true"]))(0)
    with pytest.raises(ApplyError):
        kconfig.write_value(runner, "somerc", ["A"], "Key", "value")


class Recording(Frames):
    """A second target of the same kind that notes when its settings are put back."""

    id = "recording"
    sections = ("panel",)

    def __init__(self, home):
        super().__init__(home)
        self.root = home / ".local/share/recording"
        self.restored = 0

    def capture_settings(self, runner):
        return {"frame": None}

    def reload(self, theme, runner):
        if self.fail_reload:
            raise ApplyError(translate("core", "The frame was refused."))

    def is_active(self, theme, runner):
        return True

    def restore_settings(self, settings, runner):
        self.restored += 1


def test_a_rollback_puts_back_only_the_targets_it_reached(home, runner, use_generators):
    first, second, third = Recording(home), Frames(home), Recording(home)
    third.id, third.root = "third", home / ".local/share/third"
    use_generators(first, second, third)
    second.fail_reload = True

    with pytest.raises(ApplyError):
        engine.apply(generated(5), runner)

    # The first one ran and the second one failed halfway; the third was never asked to change.
    assert (first.restored, third.restored) == (1, 0)
    assert kconfig.user_value("framesrc", ["General"], "frame") is None
    assert not first.root.exists() and not second.root.exists() and not third.root.exists()
    assert snapshots.list_snapshots() == []


def test_undo_puts_back_every_target_of_the_snapshot(home, runner, use_generators):
    first, second = Recording(home), Frames(home)
    use_generators(first, second)
    result = engine.apply(generated(5), runner)

    assert engine.restore(result.snapshot, runner, consume=True) == []

    assert first.restored == 1
    assert kconfig.user_value("framesrc", ["General"], "frame") is None


class Stubborn(Frames):
    """A target whose settings cannot be put back while `refuse` is set."""

    refuse = True

    def restore_settings(self, settings, runner):
        if self.refuse:
            raise ApplyError(translate("core", "The desktop was busy."))
        super().restore_settings(settings, runner)


def test_a_rollback_that_cannot_put_everything_back_keeps_the_snapshot_and_says_so(
    home, runner, use_generators
):
    first, second = Stubborn(home), Recording(home)
    use_generators(first, second)
    second.fail_reload = True

    with pytest.raises(ApplyError) as error:
        engine.apply(generated(5), runner)

    assert not error.value.restored
    message = str(error.value.message)
    assert message.startswith("The frame was refused. Not everything could be put back either: ")
    assert "The desktop was busy." in message and "the undo can be tried again" in message
    (kept,) = snapshots.list_snapshots()
    assert not snapshots.tried(kept)  # the rollback was not the user's undo
    assert kconfig.user_value("framesrc", ["General"], "frame") == "pts-5"  # what could not be undone

    first.refuse = False
    assert engine.restore(kept, runner, consume=True) == []
    assert kconfig.user_value("framesrc", ["General"], "frame") is None
    assert snapshots.list_snapshots() == []


def test_the_undo_after_an_incomplete_rollback_still_gets_two_tries(home, runner, use_generators):
    first, second = Stubborn(home), Recording(home)
    use_generators(first, second)
    second.fail_reload = True
    with pytest.raises(ApplyError):
        engine.apply(generated(5), runner)
    (kept,) = snapshots.list_snapshots()

    assert len(engine.restore(kept, runner, consume=True)) == 1
    assert [s.id for s in snapshots.list_snapshots()] == [kept.id]  # still there after the first undo
    assert len(engine.restore(kept, runner, consume=True)) == 1
    assert snapshots.list_snapshots() == []


def test_a_rollback_that_cannot_put_a_file_back_still_puts_the_settings_back(
    home, runner, use_generators, monkeypatch
):
    first, second = Frames(home), Recording(home)
    use_generators(first, second)
    second.fail_reload = True
    put_back = snapshots.restore_files

    def full_disk(snapshot):
        raise OSError("No space left on device")

    monkeypatch.setattr(snapshots, "restore_files", full_disk)
    with pytest.raises(ApplyError) as error:
        engine.apply(generated(5), runner)

    assert not error.value.restored
    message = str(error.value.message)
    assert message.startswith("The frame was refused. Not everything could be put back either: ")
    assert "Could not put the files back: No space left on device" in message
    assert kconfig.user_value("framesrc", ["General"], "frame") is None  # the settings are back
    (kept,) = snapshots.list_snapshots()
    assert not snapshots.tried(kept)

    monkeypatch.setattr(snapshots, "restore_files", put_back)
    assert engine.restore(kept, runner, consume=True) == []
    assert not first.root.exists() and snapshots.list_snapshots() == []


def test_one_file_that_cannot_be_put_back_does_not_stop_the_others(home, runner, frames, monkeypatch):
    one, two = home / "one.txt", home / "two.txt"
    one.write_text("one")
    two.write_text("two")
    snapshot = snapshots.create("x", [one, two], {})
    one.write_text("changed")
    two.write_text("changed")
    write = snapshots.write_atomic

    def stuck(path, content):
        if path == one:
            raise PermissionError("locked")
        write(path, content)

    monkeypatch.setattr(snapshots, "write_atomic", stuck)

    (failure,) = engine.restore(snapshot, runner)

    assert str(failure) == "Could not put the files back: locked"
    assert (one.read_text(), two.read_text()) == ("changed", "two")


def test_an_apply_that_cannot_save_its_snapshot_changes_nothing(home, runner, frames, monkeypatch):
    def full_disk(*args):
        raise OSError("No space left on device")

    monkeypatch.setattr(snapshots, "create", full_disk)

    with pytest.raises(ApplyError) as error:
        engine.apply(generated(5), runner)

    assert error.value.restored
    assert str(error.value.message) == (
        "Could not save the snapshot, so nothing was changed: No space left on device"
    )
    assert kconfig.user_value("framesrc", ["General"], "frame") is None and not frames.root.exists()


def test_a_rollback_that_puts_everything_back_says_so(home, runner, frames):
    frames.fail_reload = True
    with pytest.raises(ApplyError) as error:
        engine.apply(generated(5), runner)
    assert error.value.restored
    assert str(error.value.message) == "The frame was refused."


def test_an_undo_that_fails_keeps_the_snapshot_for_one_more_try(home, runner, use_generators):
    stubborn = Stubborn(home)
    use_generators(stubborn)
    stubborn.refuse = False
    result = engine.apply(generated(5), runner)
    stubborn.refuse = True

    assert [str(f) for f in engine.restore(result.snapshot, runner, consume=True)] == [
        "The desktop was busy."
    ]
    (kept,) = snapshots.list_snapshots()
    assert kept.id == result.snapshot.id and snapshots.tried(kept)
    assert not (stubborn.root / "pts-5" / "frame.svg").exists()  # the files are back all the same

    # The second failure uses the snapshot up, so Undo can move on to the apply before it.
    assert len(engine.restore(kept, runner, consume=True)) == 1
    assert snapshots.list_snapshots() == []


def test_a_restore_from_the_list_never_uses_the_snapshot_up(home, runner, use_generators):
    stubborn = Stubborn(home)
    use_generators(stubborn)
    stubborn.refuse = False
    result = engine.apply(generated(5), runner)
    stubborn.refuse = True

    assert len(engine.restore(result.snapshot, runner)) == 1
    assert len(engine.restore(result.snapshot, runner)) == 1
    (kept,) = snapshots.list_snapshots()
    assert not snapshots.tried(kept)


def test_an_interrupted_apply_is_rolled_back_and_the_interrupt_goes_on(home, runner, frames, monkeypatch):
    def interrupt(theme, runner):
        kconfig.write_value(runner, "framesrc", ["General"], "frame", "half")
        raise KeyboardInterrupt

    monkeypatch.setattr(frames, "reload", interrupt)

    with pytest.raises(KeyboardInterrupt):
        engine.apply(generated(5), runner)

    assert kconfig.user_value("framesrc", ["General"], "frame") is None
    assert not frames.root.exists()
    assert runner.settings["ColorScheme"] == "BreezeLight"
    assert snapshots.list_snapshots() == []


def test_an_unexpected_error_in_a_target_is_rolled_back_too(home, runner, frames, monkeypatch):
    def broken(theme, runner):
        raise RuntimeError("a bug")

    monkeypatch.setattr(frames, "reload", broken)

    with pytest.raises(RuntimeError, match="a bug"):
        engine.apply(generated(5), runner)

    assert not frames.root.exists()
    assert snapshots.list_snapshots() == []


def test_a_file_that_cannot_be_written_is_a_failed_apply(home, runner, frames, monkeypatch):
    written = []

    def refuse(path, content):
        if written:
            raise OSError("No space left on device")
        written.append(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    monkeypatch.setattr(engine, "write_atomic", refuse)

    with pytest.raises(ApplyError) as error:
        engine.apply(generated(5), runner)

    assert error.value.restored
    assert str(error.value.message) == "Could not write the theme files: No space left on device"
    assert not written[0].exists()  # the one that was written is gone again
    assert snapshots.list_snapshots() == []
