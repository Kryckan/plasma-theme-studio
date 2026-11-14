# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import gzip
import json
import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QEventLoop, QLocale, QSize, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from plasma_theme_studio import pickers  # noqa: E402
from plasma_theme_studio.pickers import base, cache  # noqa: E402
from plasma_theme_studio.pickers import loader as loader_module  # noqa: E402
from plasma_theme_studio.pickers.loader import ThumbnailLoader  # noqa: E402

SIZE = QSize(20, 10)


def solid(color="#ff0000", size=SIZE, dpr=1.0):
    return base.blank(size, dpr, QColor(color))


def item_in(folder, name="Theme", **kw):
    folder.mkdir(parents=True, exist_ok=True)
    return base.Item(name, name, path=folder, **kw)


# names -------------------------------------------------------------------


def test_localized_name_follows_language_order():
    values = {"Name": "Plain", "Name[sv]": "Svenska", "Name[de]": "Deutsch", "Name[pt_BR]": "Brasil"}
    assert base.localized(values, "Name", ["de", "sv"]) == "Deutsch"
    assert base.localized(values, "Name", ["fr", "sv"]) == "Svenska"
    assert base.localized(values, "Name", ["pt_BR", "pt"]) == "Brasil"
    assert base.localized(values, "Name", ["fr"]) == "Plain"
    assert base.localized({}, "Name", ["sv"]) == ""


def test_languages_use_the_ui_languages(monkeypatch):
    monkeypatch.setattr(QLocale, "uiLanguages", lambda self, *a: ["sv-SE", "en-US"])
    assert base.languages() == ["sv_SE", "sv", "en_US", "en"]


def test_metadata_json_and_desktop(tmp_path):
    one = tmp_path / "one"
    one.mkdir()
    (one / "metadata.json").write_text(
        json.dumps(
            {
                "KPlugin": {
                    "Id": "org.x.one",
                    "Name": "One",
                    "Name[sv]": "Ett",
                    "Description": "d",
                    "Authors": [{"Name": "Ann"}],
                }
            }
        )
    )
    assert base.read_metadata(one, ["sv"]) == {
        "name": "Ett",
        "description": "d",
        "id": "org.x.one",
        "author": "Ann",
    }
    two = tmp_path / "two"
    two.mkdir()
    (two / "metadata.desktop").write_text(
        "[Desktop Entry]\nName=Two\nName[sv]=Tva\nComment=c\nX-KDE-PluginInfo-Name=org.x.two\n"
    )
    meta = base.read_metadata(two, ["sv"])
    assert (meta["name"], meta["description"], meta["id"]) == ("Tva", "c", "org.x.two")
    assert base.read_metadata(tmp_path / "none") is None
    (tmp_path / "none").mkdir()
    (tmp_path / "none" / "metadata.json").write_text("{broken")
    assert base.read_metadata(tmp_path / "none") is None


def test_index_theme(tmp_path):
    (tmp_path / "index.theme").write_text("[Icon Theme]\nName=Ic\nName[sv]=Ik\nComment=c\n")
    assert base.read_index_theme(tmp_path, ["sv"])["name"] == "Ik"
    (tmp_path / "index.theme").write_text("[Icon Theme]\nName=Ic\nHidden=true\n")
    assert base.read_index_theme(tmp_path) is None


# folders -------------------------------------------------------------------


def test_data_folders_order_and_home_wins(home):
    system = home / "system/share"
    (system / "icons/Same").mkdir(parents=True)
    (system / "icons/Only").mkdir(parents=True)
    (home / ".local/share/icons/Same").mkdir(parents=True)
    (home / ".icons/Legacy").mkdir(parents=True)
    folders = base.data_folders("icons", legacy_home=".icons")
    assert [user for _, user in folders] == [True, True, False]
    assert folders[0][0] == home / ".local/share/icons"
    found = base.installed("icons", legacy_home=".icons")
    assert found["Same"] == (home / ".local/share/icons/Same", True)
    assert found["Only"][1] is False and found["Legacy"][1] is True
    assert base.data_folders("nothing") == []


def test_unique_sorted_prefers_home_and_ignores_case():
    items = [
        base.Item("b", "beta"),
        base.Item("a", "Alpha", user=False),
        base.Item("a", "Alpha home", user=True),
        base.Item("c", "Charlie"),
    ]
    result = base.unique_sorted(items)
    assert [i.name for i in result] == ["Alpha home", "beta", "Charlie"]


# pictures ------------------------------------------------------------------


def test_fit_image_letterboxes(app):
    wide = solid("#00ff00", QSize(40, 10))
    out = base.fit_image(wide, QSize(20, 20), 2.0)
    assert (out.width(), out.height()) == (40, 40) and out.devicePixelRatio() == 2.0
    assert out.pixelColor(20, 20).green() == 255
    assert out.pixelColor(20, 2).alpha() == 0
    assert base.fit_image(QImage(), SIZE, 1.0).isNull()


def test_placeholder_and_svg(app, tmp_path):
    assert not base.placeholder(SIZE, 1.5).isNull()
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><rect width="4" height="4"/></svg>'
    (tmp_path / "a.svg").write_bytes(svg)
    (tmp_path / "b.svgz").write_bytes(gzip.compress(svg))
    (tmp_path / "c.svg").write_text("nope")
    assert base.load_svg(tmp_path / "a.svg") is not None
    assert base.load_svg(tmp_path / "b.svgz") is not None
    assert base.load_svg(tmp_path / "c.svg") is None
    assert base.load_svg(tmp_path / "missing.svg") is None


# cache ---------------------------------------------------------------------


def test_cache_hit_and_miss(app, home):
    item = item_in(home / "t")
    name = cache.key(item, SIZE, 1.0, {"a": "#000000"})
    assert cache.get("k", name) is None
    assert cache.put("k", name, solid())
    image = cache.get("k", name, 1.0)
    assert image.size() == SIZE and image.pixelColor(0, 0) == QColor("#ff0000")
    assert str(cache.directory("k")).startswith(str(home / ".cache/plasma-theme-studio/thumbs"))
    assert not cache.put("k", name, QImage())


def test_cache_key_changes(app, home):
    item = item_in(home / "t")
    plain = cache.key(item, SIZE, 1.0, None)
    assert plain == cache.key(item, SIZE, 1.0, {})
    assert cache.key(item, SIZE, 1.0, {"a": "#000000"}) != plain
    assert cache.key(item, SIZE, 1.0, {"a": "#000001"}) != cache.key(item, SIZE, 1.0, {"a": "#000000"})
    assert cache.key(item, QSize(21, 10), 1.0, None) != plain
    assert cache.key(item, SIZE, 2.0, None) != plain
    file = home / "f.txt"
    file.write_text("x")
    file_item = base.Item("f", "f", path=file)
    before = cache.key(file_item, SIZE, 1.0, None)
    os.utime(file, ns=(1, 1))
    assert cache.key(file_item, SIZE, 1.0, None) != before


def test_cache_sees_a_changed_file_in_a_folder(app, home):
    item = item_in(home / "t")
    before = cache.key(item, SIZE, 1.0, None)
    child = home / "t/x"
    child.write_text("1")
    os.utime(child, ns=(5, 5))
    assert cache.key(item, SIZE, 1.0, None) != before


def test_corrupt_cache_file_is_a_miss_and_removed(app, home):
    cache.put("k", "abc-def", solid())
    path = cache.directory("k") / "abc-def.png"
    path.write_bytes(b"not a png")
    assert cache.get("k", "abc-def") is None
    assert not path.exists()


def test_cache_write_is_atomic(app, home, monkeypatch):
    cache.put("k", "n", solid("#ff0000"))
    replaced = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (replaced.append((a, b)), real(a, b))[1])
    assert cache.put("k", "n", solid("#0000ff"))
    ((temporary, target),) = replaced
    assert os.path.basename(temporary).startswith(".tmp-") and target == cache.directory("k") / "n.png"
    assert cache.get("k", "n").pixelColor(0, 0) == QColor("#0000ff")
    assert [p.name for p in cache.directory("k").iterdir()] == ["n.png"]


def test_failed_write_leaves_no_file_and_keeps_the_old_one(app, home, monkeypatch):
    cache.put("k", "n", solid("#ff0000"))

    def broken(a, b):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken)
    assert not cache.put("k", "n", solid("#0000ff"))
    assert [p.name for p in cache.directory("k").iterdir()] == ["n.png"]
    assert cache.get("k", "n").pixelColor(0, 0) == QColor("#ff0000")


def test_prune_drops_items_that_are_gone(app, home):
    keep = item_in(home / "keep", "keep")
    gone = item_in(home / "gone", "gone")
    for item in (keep, gone):
        cache.put("k", cache.key(item, SIZE, 1.0, None), solid())
        cache.put("k", cache.key(item, SIZE, 2.0, None), solid())
    (cache.directory("k") / ".tmp-left.png").write_bytes(b"x")
    (home / "gone").rmdir()
    assert cache.prune("k", [keep, gone]) == 3
    assert len(list(cache.directory("k").iterdir())) == 2
    assert cache.get("k", cache.key(keep, SIZE, 1.0, None)) is not None
    assert cache.prune("missing-kind", [keep]) == 0


# loader --------------------------------------------------------------------


class FakeKind(base.Kind):
    def __init__(self, key="fast", gui=False, delay=0.0, scheme=False, fail=False):
        self.key, self.gui_thread_only, self.scheme_dependent = key, gui, scheme
        self.delay, self.fail = delay, fail
        self.calls = []
        self.threads = []
        self.release = threading.Event()
        self.release.set()

    def thumbnail(self, item, size, dpr, colors):
        self.calls.append(item.id)
        self.threads.append(threading.current_thread())
        self.release.wait(5)
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("broken theme")
        return solid((colors or {}).get("c", "#ff0000"), size, dpr)


def collect(loader):
    got = []
    loader.ready.connect(lambda k, i, image: got.append((k, i, image)))
    return got


def wait_for(predicate, ms=3000):
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: predicate() and loop.quit())
    timer.start()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    timer.stop()
    return predicate()


@pytest.fixture
def loader(app, home):
    loader = ThumbnailLoader()
    yield loader
    loader.shutdown()
    loader.deleteLater()


def test_loader_renders_off_thread_then_answers_at_once(loader, home):
    kind, item = FakeKind(), item_in(home / "t")
    got = collect(loader)
    assert loader.request(kind, item, SIZE, 1.0, None) is None
    assert wait_for(lambda: got)
    assert got[0][:2] == ("fast", "Theme") and got[0][2].pixelColor(0, 0) == QColor("#ff0000")
    assert kind.threads[0] is not threading.main_thread()
    again = loader.request(kind, item, SIZE, 1.0, None)  # memory
    assert again is not None and not again.isNull()
    assert kind.calls == ["Theme"] and len(got) == 1


def test_loader_answers_from_disk_in_a_new_loader(app, home, loader):
    kind, item = FakeKind(), item_in(home / "t")
    loader.request(kind, item, SIZE, 1.0, None)
    assert wait_for(lambda: kind.calls)
    wait_for(lambda: cache.get("fast", cache.key(item, SIZE, 1.0, None)) is not None)
    other = ThumbnailLoader()
    try:
        image = other.request(kind, item, SIZE, 1.0, None)
        assert image is not None and image.pixelColor(0, 0) == QColor("#ff0000")
        assert kind.calls == ["Theme"]
    finally:
        other.shutdown()


def test_loader_does_not_duplicate_work(loader, home):
    kind, item = FakeKind(), item_in(home / "t")
    kind.release.clear()
    got = collect(loader)
    for _ in range(3):
        assert loader.request(kind, item, SIZE, 1.0, None) is None
    kind.release.set()
    assert wait_for(lambda: got)
    QTest.qWait(50)
    assert kind.calls == ["Theme"] and len(got) == 1


def test_colors_matter_only_for_scheme_dependent_kinds(loader, home):
    item = item_in(home / "t")
    plain, scheme = FakeKind("plain"), FakeKind("scheme", scheme=True)
    got = collect(loader)
    loader.request(plain, item, SIZE, 1.0, {"c": "#00ff00"})
    loader.request(scheme, item, SIZE, 1.0, {"c": "#00ff00"})
    assert wait_for(lambda: len(got) == 2)
    assert loader.request(plain, item, SIZE, 1.0, {"c": "#0000ff"}) is not None
    assert loader.request(scheme, item, SIZE, 1.0, {"c": "#0000ff"}) is None
    assert wait_for(lambda: len(got) == 3)
    assert plain.calls == ["Theme"] and scheme.calls == ["Theme", "Theme"]


def test_failed_render_gives_a_null_image_once(loader, home):
    kind, item = FakeKind(fail=True), item_in(home / "t")
    got = collect(loader)
    loader.request(kind, item, SIZE, 1.0, None)
    assert wait_for(lambda: got)
    assert got[0][2].isNull()
    assert loader.request(kind, item, SIZE, 1.0, None).isNull()
    assert kind.calls == ["Theme"]


def test_failed_render_is_tried_again_after_the_retry_time(loader, home, monkeypatch):
    kind, item = FakeKind(fail=True), item_in(home / "t")
    got = collect(loader)
    loader.request(kind, item, SIZE, 1.0, None)
    assert wait_for(lambda: got)
    assert loader.request(kind, item, SIZE, 1.0, None).isNull()  # not at every paint
    later = time.monotonic() + loader_module.RETRY + 1
    monkeypatch.setattr(loader_module, "time", SimpleNamespace(monotonic=lambda: later))
    kind.fail = False
    assert loader.request(kind, item, SIZE, 1.0, None) is None  # rendering again
    assert wait_for(lambda: len(got) == 2)
    assert not got[1][2].isNull() and kind.calls == ["Theme", "Theme"]
    assert not loader.request(kind, item, SIZE, 1.0, None).isNull()


def test_a_kind_can_send_some_items_to_a_worker(loader, home):
    class Mixed(FakeKind):
        def on_gui_thread(self, item):
            return item.id == "Theme"

    kind = Mixed(gui=True)
    other = item_in(home / "u", "Other")
    got = collect(loader)
    loader.request(kind, item_in(home / "t"), SIZE, 1.0, None)
    loader.request(kind, other, SIZE, 1.0, None)
    assert wait_for(lambda: len(got) == 2)
    on_gui = dict(zip(kind.calls, kind.threads, strict=True))
    assert on_gui["Theme"] is threading.main_thread()
    assert on_gui["Other"] is not threading.main_thread()


def test_shutdown_kills_running_helpers(app, home, monkeypatch):
    killed = []
    monkeypatch.setattr(loader_module._process, "terminate_all", lambda: killed.append(1))
    loader = ThumbnailLoader()
    loader.shutdown()
    loader.shutdown()
    assert killed == [1]
    loader.deleteLater()


def test_cancel_drops_queued_work(loader, home):
    kind = FakeKind(delay=0.05)
    kind.release.clear()
    got = collect(loader)
    items = [item_in(home / f"t{n}", f"t{n}") for n in range(20)]
    for item in items:
        loader.request(kind, item, SIZE, 1.0, None)
    loader.cancel()
    kind.release.set()
    QTest.qWait(300)
    assert len(kind.calls) <= 4  # only what the pool had already started
    assert got == []
    assert loader.request(kind, items[-1], SIZE, 1.0, None) is None  # can be asked again
    assert wait_for(lambda: got)


def test_cancel_one_kind_only(loader, home):
    a, b = FakeKind("a", gui=True), FakeKind("b", gui=True)
    item = item_in(home / "t")
    got = collect(loader)
    loader.request(a, item, SIZE, 1.0, None)
    loader.request(b, item, SIZE, 1.0, None)
    loader.cancel("a")
    assert wait_for(lambda: got)
    QTest.qWait(30)
    assert [k for k, _, _ in got] == ["b"] and a.calls == []


def test_gui_thread_only_one_per_turn_on_the_gui_thread(loader, home):
    kind = FakeKind("gui", gui=True)
    got = collect(loader)
    items = [item_in(home / f"t{n}", f"t{n}") for n in range(3)]
    for item in items:
        assert loader.request(kind, item, SIZE, 1.0, None) is None
    assert kind.calls == [] and got == []  # nothing in the request itself
    QTest.qWait(0)
    assert len(got) <= 1
    assert wait_for(lambda: len(got) == 3)
    assert all(t is threading.main_thread() for t in kind.threads)
    assert [i for _, i, _ in got] == ["t0", "t1", "t2"]


def test_shutdown_is_clean_and_final(app, home):
    kind = FakeKind(delay=0.05)
    loader = ThumbnailLoader()
    got = collect(loader)
    for n in range(10):
        loader.request(kind, item_in(home / f"t{n}", f"t{n}"), SIZE, 1.0, None)
    loader.shutdown()
    loader.shutdown()
    count = len(kind.calls)
    assert loader._pool.activeThreadCount() == 0
    QTest.qWait(100)
    assert len(kind.calls) == count and got == []
    assert loader.request(kind, item_in(home / "late", "late"), SIZE, 1.0, None).isNull()
    loader.deleteLater()
    QTest.qWait(10)


def test_no_signal_to_a_deleted_loader(app, home):
    kind = FakeKind(delay=0.05)
    loader = ThumbnailLoader()
    loader.request(kind, item_in(home / "t"), SIZE, 1.0, None)
    loader.shutdown()
    loader.deleteLater()
    QTest.qWait(100)  # a late result must not raise or crash


# registry -------------------------------------------------------------------


def test_kinds_tolerates_missing_modules(monkeypatch):
    monkeypatch.setattr(pickers, "_kinds", {})
    result = pickers.kinds()
    assert all(isinstance(k, base.Kind) for k in result)
    assert pickers.kind("no-such-kind") is None


def test_kinds_finds_a_module(monkeypatch, tmp_path):
    package = tmp_path / "fakepkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "mine.py").write_text(
        "from plasma_theme_studio.pickers.base import Kind\n"
        "class Mine(Kind):\n    key = 'mine'\n"
        "class Nokey(Kind):\n    pass\n"
    )
    (package / "broken.py").write_text("raise RuntimeError\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    import fakepkg

    monkeypatch.setattr(pickers, "__name__", "fakepkg")
    monkeypatch.setattr(pickers, "_kinds", {})
    monkeypatch.setattr(pickers, "MODULES", ("mine", "broken", "absent"))
    assert [k.key for k in pickers.kinds()] == ["mine"]
    assert pickers.kind("mine").key == "mine"
    del fakepkg, sys.modules["fakepkg"]


# hostile files -------------------------------------------------------------


def test_metadata_that_is_not_text_gives_no_exception(tmp_path):
    for number, plugin in enumerate(
        [{"Name": ["x"]}, {"Name": {"a": 1}}, {"Name": "ok", "Description": 3, "Name[sv]": 5, "Id": 7}]
    ):
        folder = tmp_path / str(number)
        folder.mkdir()
        (folder / "metadata.json").write_text(json.dumps({"KPlugin": plugin}))
        meta = base.read_metadata(folder, ["sv"])
        assert isinstance(meta["name"], str) and isinstance(meta["description"], str)
        assert isinstance(meta["id"], str)
    assert meta["name"] == "ok"


def test_every_listing_survives_a_package_with_a_list_for_a_name(home):
    from plasma_theme_studio.pickers import globalthemes, plasmastyles, splash

    data = home / "system/share"
    for sub in ("plasma/look-and-feel/bad", "plasma/desktoptheme/bad"):
        (data / sub / "contents/splash").mkdir(parents=True)
        (data / sub / "metadata.json").write_text('{"KPlugin":{"Name":["x"]}}')
    for kind in (globalthemes.GlobalThemes(), plasmastyles.PlasmaStyles(), splash.SplashScreens()):
        assert isinstance(kind.items(), list)


def fifo_and_zero(folder, name):
    os.mkfifo(folder / name)
    (folder / f"zero-{name}").symlink_to("/dev/zero")


def test_files_that_are_not_regular_files_are_not_read(tmp_path):
    fifo_and_zero(tmp_path, "index.theme")
    assert base.read_regular(tmp_path / "index.theme") is None
    assert base.read_regular(tmp_path / "zero-index.theme") is None
    assert base.read_ini(tmp_path / "index.theme") == {}
    assert base.read_metadata(tmp_path) is None
    big = tmp_path / "big"
    big.write_bytes(b"x" * (base.MAX_FILE + 1))
    assert base.read_regular(big) is None and base.read_regular(big, base.MAX_FILE + 1) is not None
    assert base.read_svg(tmp_path / "index.theme") is None


def test_a_gzip_bomb_is_not_unpacked(tmp_path):
    bomb = tmp_path / "bomb.svgz"
    bomb.write_bytes(gzip.compress(b"<svg/>" + b" " * (base.MAX_FILE * 9)))
    assert base.read_svg(bomb) is None
    fine = tmp_path / "fine.svgz"
    fine.write_bytes(gzip.compress(b"<svg/>"))
    assert base.read_svg(fine) == b"<svg/>"
