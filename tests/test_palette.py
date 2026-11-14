# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import random
import time

import pytest

pytest.importorskip("PySide6.QtGui")

from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter  # noqa: E402

from plasma_theme_studio import palette  # noqa: E402
from plasma_theme_studio.model.color import Color, contrast  # noqa: E402


@pytest.fixture(autouse=True)
def _app(app):
    return app


def make(tmp_path, name, width, height, paint, fmt="png"):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#000000"))
    painter = QPainter(image)
    paint(painter, width, height)
    painter.end()
    path = tmp_path / f"{name}.{fmt}"
    assert image.save(str(path))
    return path


def flat(color):
    return lambda p, w, h: p.fillRect(0, 0, w, h, QColor(color))


def hue_of(hexcolor):
    return palette.to_oklch(Color.parse(hexcolor))[2]


def assert_aa(colors):
    report = palette.contrast_report(colors)
    assert len(report) == 7 * 4 + 1
    assert [str(p.label) for p in report if not p.passes] == []


def noise(p, w, h):
    rng = random.Random(3)
    for _ in range(400):
        p.fillRect(
            rng.randrange(w),
            rng.randrange(h),
            30,
            30,
            QColor(rng.randrange(256), rng.randrange(256), rng.randrange(256)),
        )


def gradient(p, w, h):
    g = QLinearGradient(0, 0, w, 0)
    g.setColorAt(0, QColor("#ff0000"))
    g.setColorAt(0.5, QColor("#00ff00"))
    g.setColorAt(1, QColor("#0000ff"))
    p.fillRect(0, 0, w, h, g)


def two_tone(p, w, h):
    p.fillRect(0, 0, w, h, QColor("#101820"))
    p.fillRect(0, 0, w // 3, h, QColor("#e0a020"))


@pytest.mark.parametrize(
    "name,paint",
    [
        ("flat", flat("#2a7fff")),
        ("two", two_tone),
        ("gradient", gradient),
        ("noise", noise),
        ("black", flat("#000000")),
        ("white", flat("#ffffff")),
        ("gray", flat("#808080")),
        ("yellow", flat("#ffff00")),
        ("pure_red", flat("#ff0000")),
    ],
)
def test_every_variant_passes_aa(tmp_path, name, paint):
    result = palette.extract(make(tmp_path, name, 160, 90, paint))
    assert result.ok
    assert set(result.light) == set(result.dark) == set(palette.ROLES)
    assert_aa(result.light)
    assert_aa(result.dark)
    assert palette.MIN_SWATCHES <= len(result.swatches) <= palette.MAX_SWATCHES
    assert len(set(result.swatches)) == len(result.swatches)
    assert Color.parse(result.dark["window"]).is_dark
    assert not Color.parse(result.light["window"]).is_dark


def test_accent_hue_and_contrast(tmp_path):
    result = palette.extract(make(tmp_path, "blue", 100, 60, flat("#2a7fff")))
    for colors in (result.light, result.dark):
        assert 230 < hue_of(colors["accent"]) < 275
        assert contrast(Color.parse(colors["accent"]), Color.parse(colors["window"])) >= 3.0
    assert result.colorful
    red = palette.extract(make(tmp_path, "red", 100, 60, flat("#e02020")))
    assert hue_of(red.dark["accent"]) < 40 or hue_of(red.dark["accent"]) > 350
    assert hue_of(result.swatches[0]) == pytest.approx(hue_of(result.dark["accent"]), abs=12)


def test_small_dominant_color_wins_over_dark_background(tmp_path):
    def streaks(p, w, h):
        p.fillRect(0, 40, w, 6, QColor("#ff20c0"))

    result = palette.extract(make(tmp_path, "streak", 200, 100, streaks))
    assert 310 < hue_of(result.dark["accent"]) < 360


def test_gray_image_is_not_colorful(tmp_path):
    result = palette.extract(make(tmp_path, "gray", 50, 50, flat("#777777")))
    assert not result.colorful
    assert result.dark["accent"] == palette._derive(None, 0, 0, True)["accent"]


def test_deterministic(tmp_path):
    path = make(tmp_path, "n", 300, 200, noise)
    assert palette.extract(path) == palette.extract(path)


def test_tiny_and_huge_images(tmp_path):
    tiny = palette.extract(make(tmp_path, "tiny", 1, 1, flat("#33aa55")))
    assert tiny.ok
    assert_aa(tiny.dark)
    huge = make(tmp_path, "huge", 6000, 3000, gradient)
    start = time.perf_counter()
    result = palette.extract(huge)
    assert time.perf_counter() - start < 5
    assert result.ok
    assert_aa(result.light)


def test_timing(tmp_path):
    path = make(tmp_path, "t", 1920, 1080, noise)
    start = time.perf_counter()
    palette.extract(path)
    assert time.perf_counter() - start < 3


def test_not_an_image(tmp_path):
    fake = tmp_path / "x.png"
    fake.write_text("not an image")
    result = palette.extract(fake)
    assert not result.ok
    assert str(result.error)
    assert not palette.extract(tmp_path / "missing.png").ok
    assert not palette.extract(tmp_path).ok


def test_with_accent(tmp_path):
    result = palette.extract(make(tmp_path, "blue", 100, 60, flat("#2a7fff")))
    green = palette.with_accent(result, "#22aa44")
    for colors in (green.light, green.dark):
        assert 130 < hue_of(colors["accent"]) < 160
        assert_aa(colors)
    assert green.swatches == result.swatches
    assert green.dark["window"] != result.dark["window"]
    assert palette.with_accent(result, "nonsense") is result
    # a plain variant: only the accent moves, and a faint one is darkened to 3:1
    plain = palette.with_accent(result.light, "#ffff99")
    assert plain["window"] == result.light["window"]
    assert contrast(Color.parse(plain["accent"]), Color.parse(plain["window"])) >= 3.0
    kept = palette.with_accent(result.dark, "#3b6ee0")
    assert kept["accent"] == "#3b6ee0"


def test_ensure_contrast_fixes_and_keeps():
    colors = {
        "accent": "#ffff00", "window": "#ffffff", "view": "#ffffff", "button": "#eeeeee", "header": "#dddddd",
        "text": "#bbbbbb", "text_muted": "#cccccc", "link": "#0000ff", "visited": "#ffcc00",
        "negative": "#ff8080", "neutral": "#ffff00", "positive": "#80ff80",
    }  # fmt: skip
    fixed = palette.ensure_contrast(colors)
    assert_aa(fixed)
    assert fixed["link"] == "#0000ff"
    assert fixed["window"] == "#ffffff"
    assert palette.ensure_contrast(fixed) == fixed
    assert palette.ensure_contrast({"text": "#fff"}) == {"text": "#fff"}


def test_contrast_report_text():
    result = palette.contrast_report({"window": "#ffffff", "text": "#000000", "accent": "#ffffff"})
    texts = {str(p.label): p for p in result}
    assert "Text on window background" in texts
    assert texts["Text on window background"].ratio_text == "21.0 : 1"
    assert texts["Accent on window background"].passes is False
    assert palette.contrast_report({}) == []
    assert (
        palette.ContrastPair(texts["Text on window background"].label, "a", "b", 4.49, 4.5).ratio_text
        == "4.4 : 1"
    )


WAL = {
    "wallpaper": "/x.png",
    "special": {"background": "#1b2b24", "foreground": "#d8e0dc", "cursor": "#d8e0dc"},
    "colors": {
        f"color{i}": c
        for i, c in enumerate(
            ["#1b2b24", "#8a5a4b", "#4f9a62", "#b89b4a", "#4b78a8", "#8a5f99", "#4a9a94", "#d8e0dc"] * 2
        )
    },
}
WAL_LIGHT = {
    "special": {"background": "#f2ecdf", "foreground": "#2b2a26"},
    "colors": WAL["colors"],
}


def write(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


def test_pywal(tmp_path):
    result = palette.from_pywal(write(tmp_path, "colors.json", WAL))
    assert result.ok
    assert result.given == "dark"
    assert_aa(result.dark)
    assert_aa(result.light)
    assert Color.parse(result.dark["window"]) == Color.parse("#1b2b24")
    assert len(result.swatches) >= palette.MIN_SWATCHES
    light = palette.from_pywal(write(tmp_path, "l.json", WAL_LIGHT))
    assert light.given == "light"
    assert_aa(light.light)
    assert light.light["window"] == "#f2ecdf"


def test_pywal_tolerant_and_broken(tmp_path):
    no_special = {"colors": WAL["colors"]}
    assert palette.from_pywal(write(tmp_path, "a.json", no_special)).ok
    rgb = {
        "special": {"background": "rgb(20, 20, 30)", "foreground": "EEEEEE"},
        "colors": {"color1": "#ff0000"},
    }
    assert palette.from_pywal(write(tmp_path, "b.json", rgb)).ok
    for bad in (
        "{broken",
        "[1, 2]",
        {"colors": 3},
        {"colors": {}},
        "",
        {"special": {"background": 1}, "colors": {}},
    ):
        result = palette.from_pywal(write(tmp_path, "c.json", bad))
        assert not result.ok
        assert str(result.error)
    assert not palette.from_pywal(tmp_path / "nothing.json").ok


MATUGEN_ROLES = {
    "dark": {"primary": "#a8c8ff", "surface": "#111318", "on_surface": "#e2e2e9", "error": "#ffb4ab",
             "tertiary": "#dabde2", "on_surface_variant": "#c4c6d0", "surface_container": "#1d2024"},
    "light": {"primary": "#415f91", "surface": "#f9f9ff", "on_surface": "#191c20", "error": "#ba1a1a",
              "tertiary": "#705575", "on_surface_variant": "#44474e", "surface_container": "#ededf4"},
}  # fmt: skip


def test_matugen_both_layouts(tmp_path):
    new = {
        "colors": {
            r: {m: {"color": MATUGEN_ROLES[m][r]} for m in MATUGEN_ROLES} for r in MATUGEN_ROLES["dark"]
        }
    }
    old = {"colors": MATUGEN_ROLES}
    flat_new = {"colors": {r: {m: MATUGEN_ROLES[m][r] for m in MATUGEN_ROLES} for r in MATUGEN_ROLES["dark"]}}
    results = [
        palette.from_matugen(write(tmp_path, f"{i}.json", d)) for i, d in enumerate((new, old, flat_new))
    ]
    for result in results:
        assert result.ok
        assert result.given == "both"
        assert result.dark["window"] == "#111318"
        assert result.light["window"] == "#f9f9ff"
        assert_aa(result.dark)
        assert_aa(result.light)
    assert results[0].dark == results[1].dark == results[2].dark


def test_matugen_one_mode_and_bad(tmp_path):
    one = {"colors": {"dark": MATUGEN_ROLES["dark"]}}
    result = palette.from_matugen(write(tmp_path, "one.json", one))
    assert result.given == "dark"
    assert_aa(result.light)
    for bad in ({"colors": {}}, {"colors": {"dark": {"primary": "#ffffff"}}}, {"x": 1}, "nope", [1],
                {"colors": {"dark": {"primary": "#fff", "surface": 5, "on_surface": None}}}):  # fmt: skip
        assert not palette.from_matugen(write(tmp_path, "bad.json", bad)).ok


SCHEME = """[General]
Name=Mini
[Colors:Window]
BackgroundNormal=32,35,38
ForegroundNormal=252,252,252
[Colors:Selection]
BackgroundNormal=61,174,233
"""


def test_colors_file(tmp_path):
    result = palette.from_colors_file(write(tmp_path, "m.colors", SCHEME))
    assert result.ok
    assert result.given == "dark"
    assert result.dark["window"] == "#202326"
    assert result.dark["accent"] == "#3daee9"
    assert result.dark["view"] != result.dark["window"]
    assert set(result.dark) == set(palette.ROLES)
    assert_aa(result.light)


def test_colors_file_hostile(tmp_path):
    hostile = [
        b"\0\1\2" * 1000,
        b"[Colors:Window]\nBackgroundNormal=" + b"9" * 2_000_000,
        ("[" * 5000 + "\n" + "x=" + "=" * 5000).encode(),
        b"[Colors:Window]\nBackgroundNormal=999,0,0\nForegroundNormal=zzz\n",
        b"[Colors:Window]\nBackgroundNormal=#12\nForegroundNormal=1,2\n",
        b"\xff\xfe[Colors:Window]",
        b"",
    ]
    for i, data in enumerate(hostile):
        path = tmp_path / f"h{i}.colors"
        path.write_bytes(data)
        result = palette.from_colors_file(path)
        assert not result.ok
        assert str(result.error)
    assert not palette.from_colors_file(tmp_path / "missing.colors").ok
    assert not palette.from_colors_file(tmp_path).ok


def test_available_sources(home):
    assert palette.available_sources() == []
    wal = home / ".cache/wal/colors.json"
    wal.parent.mkdir(parents=True)
    wal.write_text("{}")
    mat = home / ".config/matugen/colors.json"
    mat.parent.mkdir(parents=True)
    mat.write_text("{}")
    found = palette.available_sources()
    assert [(f.kind, f.path) for f in found] == [("pywal", wal), ("matugen", mat)]


def watchdog(seconds=10):
    """A test that would block on a pipe fails instead of hanging."""
    import signal

    def fail(*args):
        raise AssertionError("blocked")

    signal.signal(signal.SIGALRM, fail)
    signal.alarm(seconds)


def test_hostile_files_do_not_block(tmp_path):
    import os

    from plasma_theme_studio import palette

    watchdog()
    try:
        os.mkfifo(tmp_path / "w.png")
        os.mkfifo(tmp_path / "p.colors")
        assert palette.extract(tmp_path / "w.png").error
        assert palette.from_colors_file(tmp_path / "p.colors").error
        (tmp_path / "z.colors").symlink_to("/dev/zero")
        assert palette.from_colors_file(tmp_path / "z.colors").error
        started = time.monotonic()
        (tmp_path / "long.colors").write_text("[" * 200_000)
        assert palette.from_colors_file(tmp_path / "long.colors").error
        assert time.monotonic() - started < 3
    finally:
        import signal

        signal.alarm(0)
