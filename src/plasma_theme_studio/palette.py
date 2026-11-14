# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Theme colors from an image or an imported palette, and the contrast check.

An image gives a light and a dark variant of the twelve color roles of a theme, plus accent
candidates. A pywal, matugen or KDE color scheme file gives the same kind of result. Every text
color of a result reaches WCAG AA (4.5:1) on the window, view, button and header backgrounds, and
the accent 3:1 on the window. The image reader needs a Qt application (the app always has one).
Nothing here runs an external tool.
"""

from __future__ import annotations

import colorsys
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage

from . import images, paths, safefile
from .messages import Msg, translate
from .model.color import BLACK, WHITE, Color, contrast

ROLES = (
    "accent",
    "window",
    "view",
    "button",
    "header",
    "text",
    "text_muted",
    "link",
    "visited",
    "negative",
    "neutral",
    "positive",
)
SURFACES = ("window", "view", "button", "header")
TEXT_ROLES = ("text", "text_muted", "link", "visited", "negative", "neutral", "positive")
AA = 4.5
ACCENT_RATIO = 3.0
DEFAULT_ACCENT = "#3daee9"  # Breeze blue, for an image without any color
SAMPLE_SIDE = 96  # an image is read at about this many pixels on the long side
MAX_FILE_BYTES = 1_000_000  # a palette or color scheme file is a few KB
MAX_SWATCHES = 8
MIN_SWATCHES = 5
# Fills the accent candidates of an image that has few colors (Breeze's and Plasma's accent hues).
_PRESETS = ("#3daee9", "#e93a9a", "#f67400", "#27ae60", "#9b59b6", "#da4453", "#1abc9c", "#c9a800")
_BREEZE = {
    "negative": "#da4453",
    "neutral": "#f67400",
    "positive": "#27ae60",
    "link": "#2980b9",
    "visited": "#9b59b6",
}


@dataclass
class PaletteResult:
    """Colors for a light and a dark theme (role -> "#rrggbb"), or the reason there are none."""

    light: dict[str, str] = field(default_factory=dict)
    dark: dict[str, str] = field(default_factory=dict)
    swatches: list[str] = field(default_factory=list)  # accent candidates, most suitable first
    colorful: bool = True  # False: the source had no color to take an accent from
    # Which variant(s) the source itself had ("light", "dark", "both"); None: made from an image.
    given: str | None = None
    error: Msg | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class ContrastPair:
    label: Msg
    foreground: str  # role
    background: str  # role
    ratio: float
    minimum: float

    @property
    def passes(self) -> bool:
        return self.ratio >= self.minimum - 1e-9

    @property
    def ratio_text(self) -> str:
        """ "13.9 : 1", cut (not rounded) so that a failing pair never reads as its minimum."""
        return f"{math.floor(self.ratio * 10 + 1e-9) / 10:.1f} : 1"


@dataclass(frozen=True)
class PaletteFile:
    kind: str  # "pywal" or "matugen"
    path: Path


def _failure(message: Msg) -> PaletteResult:
    return PaletteResult(error=message)


# ----------------------------------------------------------------- OKLab / OKLCH


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gamma(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def _to_oklab(r: int, g: int, b: int) -> tuple[float, float, float]:
    r, g, b = _linear(r / 255), _linear(g / 255), _linear(b / 255)
    lc = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    mc = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    sc = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (
        0.2104542553 * lc + 0.7936177850 * mc - 0.0040720468 * sc,
        1.9779984951 * lc - 2.4285922050 * mc + 0.4505937099 * sc,
        0.0259040371 * lc + 0.7827717662 * mc - 0.8086757660 * sc,
    )


def _oklab_to_linear(lightness: float, a: float, b: float) -> tuple[float, float, float]:
    lc = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    mc = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    sc = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        4.0767416621 * lc - 3.3077115913 * mc + 0.2309699292 * sc,
        -1.2684380046 * lc + 2.6097574011 * mc - 0.3413193965 * sc,
        -0.0041960863 * lc - 0.7034186147 * mc + 1.7076147010 * sc,
    )


def oklch_to_color(lightness: float, chroma: float, hue: float) -> Color:
    """OKLCH to sRGB. A color outside the gamut loses chroma; hue and lightness stay."""
    lightness = min(1.0, max(0.0, lightness))
    angle = math.radians(hue)

    def rgb(c: float):
        return _oklab_to_linear(lightness, c * math.cos(angle), c * math.sin(angle))

    def inside(c: float) -> bool:
        return all(-1e-6 <= v <= 1 + 1e-6 for v in rgb(c))

    lo, hi = 0.0, chroma
    if inside(chroma):
        lo = chroma
    else:
        for _ in range(18):
            mid = (lo + hi) / 2
            if inside(mid):
                lo = mid
            else:
                hi = mid
    return Color(*(round(_gamma(min(1.0, max(0.0, v))) * 255) for v in rgb(lo)))


def to_oklch(color: Color) -> tuple[float, float, float]:
    lightness, a, b = _to_oklab(color.r, color.g, color.b)
    return lightness, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _mix_hue(a: float, b: float, amount: float) -> float:
    """Move hue `a` towards hue `b` along the short arc."""
    return (a + (((b - a + 180) % 360) - 180) * amount) % 360


# ----------------------------------------------------------------- reading an image


def _histogram(path: Path) -> list[tuple[int, int, int, int]] | None:
    """The image on a 5-bit color grid, from a small copy: [(r, g, b, count)]. None: not readable."""
    reader = images.open_reader(path)
    if reader is None:
        return None
    size = reader.size()
    if size.isValid() and size.width() > 0 and size.height() > 0:
        scale = SAMPLE_SIDE / max(size.width(), size.height())
        if scale < 1:  # a JPEG decodes at the reduced size; other formats are scaled after reading
            reader.setScaledSize(
                QSize(max(1, round(size.width() * scale)), max(1, round(size.height() * scale)))
            )
    image = reader.read()
    if image.isNull():
        return None
    if max(image.width(), image.height()) > SAMPLE_SIDE:
        image = image.scaled(
            SAMPLE_SIDE,
            SAMPLE_SIDE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    data = bytes(image.constBits())
    stride = image.bytesPerLine()
    bins: dict[int, list[int]] = {}
    for y in range(image.height()):
        row = y * stride
        for x in range(image.width()):
            r, g, b = data[row + 3 * x], data[row + 3 * x + 1], data[row + 3 * x + 2]
            key = ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
            entry = bins.get(key)
            if entry is None:
                bins[key] = [r, g, b, 1]
            else:
                entry[0] += r
                entry[1] += g
                entry[2] += b
                entry[3] += 1
    return [(e[0] // e[3], e[1] // e[3], e[2] // e[3], e[3]) for _, e in sorted(bins.items())]


@dataclass
class _Cluster:
    share: float
    lightness: float
    chroma: float
    hue: float


def _dist2(p, c) -> float:
    return (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2


def _kmeans(points: list[tuple[int, int, int, int]], k: int = 12, iterations: int = 10) -> list[_Cluster]:
    """The main colors of the image (deterministic: a farthest-point start, no random numbers)."""
    labs = [(*_to_oklab(r, g, b), n) for r, g, b, n in points]
    total = sum(p[3] for p in labs)
    centers = [max(labs, key=lambda p: p[3])[:3]]
    dist = [_dist2(p, centers[0]) for p in labs]
    while len(centers) < min(k, len(labs)):
        best = max(range(len(labs)), key=lambda i: dist[i] * (labs[i][3] ** 0.3))
        if dist[best] < 1e-5:
            break
        centers.append(labs[best][:3])
        for i, p in enumerate(labs):
            dist[i] = min(dist[i], _dist2(p, centers[-1]))
    counts = [0] * len(centers)
    for _ in range(iterations):
        sums = [[0.0, 0.0, 0.0, 0] for _ in centers]
        for p in labs:
            nearest = min(range(len(centers)), key=lambda i: _dist2(p, centers[i]))
            s = sums[nearest]
            s[0] += p[0] * p[3]
            s[1] += p[1] * p[3]
            s[2] += p[2] * p[3]
            s[3] += p[3]
        counts = [s[3] for s in sums]
        centers = [
            (s[0] / s[3], s[1] / s[3], s[2] / s[3]) if s[3] else c for s, c in zip(sums, centers, strict=True)
        ]
    found = [
        _Cluster(n / total, c[0], math.hypot(c[1], c[2]), math.degrees(math.atan2(c[2], c[1])) % 360)
        for c, n in zip(centers, counts, strict=True)
        if n
    ]
    return sorted(found, key=lambda c: (-c.share, c.hue))


def _hue_peaks(points: list[tuple[int, int, int, int]], count: int) -> list[_Cluster]:
    """The most prominent colorful hues of the image, strongest first, at least 35 degrees apart.

    Taken from the pixels, not from clusters (which average small vivid areas away: a black
    wallpaper with a few magenta streaks must give magenta). Each pixel votes for its hue with
    count * chroma squared, mid lightness counts most."""
    votes = [0.0] * 36  # 10 degree sectors
    items = []
    for r, g, b, n in points:
        lightness, a, bb = _to_oklab(r, g, b)
        chroma = math.hypot(a, bb)
        if chroma < 0.02 or not 0.2 <= lightness <= 0.95:
            continue
        hue = math.degrees(math.atan2(bb, a)) % 360
        weight = n * chroma * chroma * (1.0 - min(1.0, abs(lightness - 0.58) / 0.42) * 0.75)
        items.append((lightness, a, bb, hue, weight, n))
        votes[int(hue // 10) % 36] += weight
    total = sum(item[5] for item in items)
    peaks: list[_Cluster] = []
    first = 0.0
    for _ in range(count):
        window = [votes[i - 1] + votes[i] + votes[(i + 1) % 36] for i in range(36)]
        best = max(range(36), key=lambda i: (window[i], -i))
        if window[best] <= 0 or (peaks and window[best] < first * 0.01):
            break
        first = first or window[best]
        center = best * 10 + 5
        chosen = [it for it in items if _hue_distance(it[3], center) <= 20]
        weight = sum(it[4] for it in chosen)
        lightness = sum(it[0] * it[4] for it in chosen) / weight
        a = sum(it[1] * it[4] for it in chosen) / weight
        bb = sum(it[2] * it[4] for it in chosen) / weight
        share = sum(it[5] for it in chosen) / max(1, total)
        peaks.append(_Cluster(share, lightness, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360))
        for i in range(36):
            if _hue_distance(i * 10 + 5, center) <= 35:
                votes[i] = 0.0
    return peaks


# ----------------------------------------------------------------- the roles


def _fit(lightness: float, chroma: float, hue: float, backgrounds: list[Color], ratio: float, direction: int):
    """Walk lightness in `direction` (-1 darker, 1 lighter) until `ratio` holds on every background."""
    color = oklch_to_color(lightness, chroma, hue)
    for _ in range(200):
        if min(contrast(color, bg) for bg in backgrounds) >= ratio:
            break
        lightness += 0.005 * direction
        color = oklch_to_color(lightness, chroma, hue)
    return color


def _fit_accent(raw: Color | None, dark: bool, window: Color, view: Color, exact: bool = False) -> Color:
    """An accent usable in this variant: 3:1 on the window and the view, and 4.5:1 for the better
    of white and the dark text color that a color scheme puts on it. The hue is kept. `exact`
    keeps a color that already passes as it is; otherwise lightness and chroma are brought into
    the range that looks good as an accent."""
    if raw is None:
        raw = Color.parse(DEFAULT_ACCENT)
    on_accent = (WHITE, Color(35, 38, 41))

    def passes(c: Color) -> bool:
        return (
            min(contrast(c, window), contrast(c, view)) >= ACCENT_RATIO
            and max(contrast(c, o) for o in on_accent) >= AA
        )

    if exact and passes(raw):
        return raw
    lightness, chroma, hue = to_oklch(raw)
    if not exact:
        chroma = min(max(chroma, 0.09), 0.20)
        lightness = min(0.78, max(0.64, lightness)) if dark else min(0.58, max(0.46, lightness))
    color = oklch_to_color(lightness, chroma, hue)
    for _ in range(120):
        if passes(color):
            break
        lightness += 0.005 * (1 if dark else -1)
        color = oklch_to_color(lightness, chroma, hue)
    return color


def _derive(accent: Color | None, tint_hue: float, tint_chroma: float, dark: bool, exact: bool = False):
    """The twelve roles of one variant: surfaces tinted with the image's hue, text and status
    colors fitted to every surface, the accent fitted to the window."""
    t = tint_chroma
    if dark:
        surfaces = [oklch_to_color(0.245, t, tint_hue), oklch_to_color(0.205, t * 0.8, tint_hue)]
        surfaces += [oklch_to_color(0.285, t, tint_hue), oklch_to_color(0.215, t * 0.8, tint_hue)]
    else:
        surfaces = [oklch_to_color(0.955, t * 0.6, tint_hue), oklch_to_color(0.992, t * 0.3, tint_hue)]
        surfaces += [oklch_to_color(0.980, t * 0.4, tint_hue), oklch_to_color(0.915, t * 0.8, tint_hue)]
    window, view = surfaces[0], surfaces[1]
    direction = 1 if dark else -1

    def fg(lightness: float, chroma: float, hue: float, ratio: float) -> Color:
        return _fit(lightness, chroma, hue, surfaces, ratio, direction)

    fitted = _fit_accent(accent, dark, window, view, exact)
    accent_hue = to_oklch(fitted)[2] if accent else 250
    roles = {
        "accent": fitted,
        "window": window,
        "view": view,
        "button": surfaces[2],
        "header": surfaces[3],
        "text": fg(0.93 if dark else 0.27, t * 0.5, tint_hue, 8.0),
        "text_muted": fg(0.72 if dark else 0.50, t * 1.2, tint_hue, 4.6),
        "link": fg(0.76 if dark else 0.50, 0.13, _mix_hue(250, accent_hue, 0.25), 4.6),
        "visited": fg(0.74 if dark else 0.50, 0.12, _mix_hue(318, accent_hue, 0.15), 4.6),
        "negative": fg(0.72 if dark else 0.52, 0.17, 25, 4.6),
        "neutral": fg(0.78 if dark else 0.55, 0.15, 62, 4.6),
        "positive": fg(0.76 if dark else 0.52, 0.15, 150, 4.6),
    }
    return {role: roles[role].hex for role in ROLES}


def _tint_of(accent: Color) -> tuple[float, float]:
    _, chroma, hue = to_oklch(accent)
    return hue, min(0.018, 0.006 + chroma * 0.08)


def _swatches(peaks: list[_Cluster]) -> list[str]:
    """Distinct accent candidates: the image's hues first, then accent presets for the missing ones."""
    out: list[Color] = []
    for peak in peaks[:MAX_SWATCHES]:
        out.append(
            oklch_to_color(min(0.72, max(0.55, peak.lightness)), min(0.20, max(0.09, peak.chroma)), peak.hue)
        )
    for preset in _PRESETS:
        if len(out) >= MIN_SWATCHES:
            break
        color = Color.parse(preset)
        hue = to_oklch(color)[2]
        if all(_hue_distance(hue, to_oklch(c)[2]) >= 30 for c in out):
            out.append(color)
    for preset in _PRESETS:  # an image with many near hues, still needs five
        if len(out) >= MIN_SWATCHES:
            break
        if Color.parse(preset) not in out:
            out.append(Color.parse(preset))
    return [c.hex for c in out]


# ----------------------------------------------------------------- the shared correction


def _worst(color: Color, backgrounds: list[Color]) -> float:
    return min(contrast(color, b) for b in backgrounds)


def _correct(color: Color, backgrounds: list[Color], ratio: float) -> Color:
    """`color` unchanged when it reaches `ratio` on every background; else lighter or darker with
    its hue and as much chroma as fits, else black or white."""
    if _worst(color, backgrounds) >= ratio:
        return color
    lightness, chroma, hue = to_oklch(color)
    lighter_first = sum(b.luminance for b in backgrounds) / len(backgrounds) < 0.18
    for direction in (1, -1) if lighter_first else (-1, 1):
        for step in range(1, 201):
            candidate = oklch_to_color(lightness + direction * 0.005 * step, chroma, hue)
            if _worst(candidate, backgrounds) >= ratio:
                return candidate
    return max((BLACK, WHITE), key=lambda c: _worst(c, backgrounds))


def ensure_contrast(colors: dict[str, str]) -> dict[str, str]:
    """The colors with every text role at 4.5:1 on window, view, button and header, and the accent
    at 3:1 on the window. A color that already passes is not changed; others keep their hue."""
    out = dict(colors)
    try:
        surfaces = [Color.parse(colors[role]) for role in SURFACES]
        for role in TEXT_ROLES:
            if role in colors:
                out[role] = _correct(Color.parse(colors[role]), surfaces, AA).hex
        if "accent" in colors:
            out["accent"] = _correct(Color.parse(colors["accent"]), surfaces[:1], ACCENT_RATIO).hex
    except (KeyError, ValueError):
        return dict(colors)  # not a complete set of colors: nothing to measure against
    return out


def _text_labels() -> dict[str, Msg]:
    return {
        "text": translate("core", "Text"),
        "text_muted": translate("core", "Muted text"),
        "link": translate("core", "Links"),
        "visited": translate("core", "Visited links"),
        "negative": translate("core", "Negative text"),
        "neutral": translate("core", "Neutral text"),
        "positive": translate("core", "Positive text"),
        "accent": translate("core", "Accent"),
    }


def _surface_labels() -> dict[str, Msg]:
    return {
        "window": translate("core", "window background"),
        "view": translate("core", "view background"),
        "button": translate("core", "button background"),
        "header": translate("core", "header background"),
    }


def contrast_report(colors: dict[str, str]) -> list[ContrastPair]:
    """Every text color on every background, and the accent on the window, with the ratio and the
    minimum it must reach. Roles that are missing or not colors are left out."""
    foregrounds, backgrounds = _text_labels(), _surface_labels()
    parsed: dict[str, Color] = {}
    for role in ROLES:
        try:
            parsed[role] = Color.parse(colors[role])
        except (KeyError, ValueError):
            pass
    pairs = []
    for role in TEXT_ROLES:
        for surface in SURFACES:
            if role in parsed and surface in parsed:
                label = translate("core", "{text} on {background}").format(
                    text=foregrounds[role], background=backgrounds[surface]
                )
                pairs.append(ContrastPair(label, role, surface, contrast(parsed[role], parsed[surface]), AA))
    if "accent" in parsed and "window" in parsed:
        label = translate("core", "{text} on {background}").format(
            text=foregrounds["accent"], background=backgrounds["window"]
        )
        pairs.append(
            ContrastPair(
                label, "accent", "window", contrast(parsed["accent"], parsed["window"]), ACCENT_RATIO
            )
        )
    return pairs


# ----------------------------------------------------------------- results


def _from_image_accent(accent: Color | None, tint: tuple[float, float], exact: bool = False):
    light = _derive(accent, *tint, dark=False, exact=exact)
    dark = _derive(accent, *tint, dark=True, exact=exact)
    return light, dark


def extract(image_path: str | Path) -> PaletteResult:
    """Colors from an image. The same image always gives the same colors."""
    try:
        points = _histogram(Path(image_path)) if safefile.is_regular(Path(image_path)) else None
    except (OSError, ValueError, MemoryError):
        points = None
    if not points:
        return _failure(translate("core", "The image cannot be read."))
    peaks = _hue_peaks(points, MAX_SWATCHES)
    if peaks:
        accent = oklch_to_color(peaks[0].lightness, peaks[0].chroma, peaks[0].hue)
        tint = _tint_of(accent)
    else:
        # A gray image: the neutrals take the dominant color's own, small, hue.
        main = _kmeans(points)[0]
        accent, tint = None, (main.hue, min(0.012, main.chroma))
    light, dark = _from_image_accent(accent, tint)
    return PaletteResult(light, dark, _swatches(peaks), colorful=bool(peaks))


def _as_color(accent: str | Color) -> Color | None:
    if isinstance(accent, Color):
        return accent
    try:
        return Color.parse(accent)
    except ValueError:
        return None


def with_accent(
    source: PaletteResult | dict[str, str], accent: str | Color
) -> PaletteResult | dict[str, str]:
    """`source` with another accent. For the result of an image the surfaces, links and visited
    links follow the new accent as they do for the image's own. For imported colors, or a plain
    dict of one variant, only the accent changes (moved in lightness when it is too faint on the
    window). A color that already works is kept exactly. A bad `accent` changes nothing."""
    color = _as_color(accent)
    if color is None:
        return source
    if isinstance(source, PaletteResult):
        if not source.ok:
            return source
        if source.given is None:
            light, dark = _from_image_accent(color, _tint_of(color), exact=True)
        else:
            light, dark = (with_accent(v, color) for v in (source.light, source.dark))
        return PaletteResult(light, dark, source.swatches, source.colorful, source.given)
    try:
        window, view = Color.parse(source["window"]), Color.parse(source.get("view", source["window"]))
    except (KeyError, ValueError):
        return dict(source)
    return {**source, "accent": _fit_accent(color, window.is_dark, window, view, exact=True).hex}


# ----------------------------------------------------------------- importing


def _read_text(path: Path) -> str | Msg:
    if not safefile.is_regular(path):
        return translate("core", "The file cannot be read.")
    try:
        with open(path, "rb") as file:
            data = file.read(MAX_FILE_BYTES + 1)
    except OSError:
        return translate("core", "The file cannot be read.")
    if len(data) > MAX_FILE_BYTES:
        return translate("core", "The file is too large to be a color file.")
    if b"\0" in data:
        return translate("core", "The file is not a text file.")
    return data.decode("utf-8", errors="replace")


def _read_json(path: Path) -> dict | Msg:
    text = _read_text(path)
    if isinstance(text, Msg):
        return text
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return translate("core", "The file is not valid JSON.")
    if not isinstance(data, dict):
        return translate("core", "The file does not hold a color palette.")
    return data


_FUNCTION = re.compile(
    r"^rgba?\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*(?:[,/ ]\s*[\d.%]+\s*)?\)$"
)


def _color(value) -> Color | None:
    """A color from "#rrggbb", "rrggbb", "#rgb", "#rrggbbaa", "rgb(r, g, b)", "r,g,b" or {"color": ...}."""
    if isinstance(value, dict):
        for key in ("color", "hex", "default"):
            if key in value:
                return _color(value[key])
        return None
    if not isinstance(value, str) or len(value) > 64:
        return None
    text = value.strip()
    match = _FUNCTION.match(text)
    if match is None and re.fullmatch(r"\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}(\s*,\s*\d{1,3})?", text):
        match = re.match(r"(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", text)
    if match:
        r, g, b = (int(v) for v in match.groups()[:3])
        return Color(r, g, b) if max(r, g, b) <= 255 else None
    if re.fullmatch(r"#?[0-9a-fA-F]{8}", text):
        text = text[:-2]
    if not text.startswith("#"):
        text = "#" + text
    return Color.parse(text) if Color.is_valid(text) else None


def _hsv(c: Color) -> tuple[float, float, float]:
    return colorsys.rgb_to_hsv(c.r / 255, c.g / 255, c.b / 255)


def _closest_hue(candidates: list[Color], hue: float, min_saturation: float) -> Color | None:
    usable = [c for c in candidates if _hsv(c)[1] >= min_saturation]
    return min(usable, key=lambda c: _hue_distance(_hsv(c)[0] * 360, hue)) if usable else None


def _breeze(role: str) -> Color:
    return Color.parse(_BREEZE[role])


def _complete(roles: dict[str, Color], given_dark: bool, given: str, source_swatches: list[Color]):
    """A result from the roles of one variant (as Colors): the other variant is derived from the
    same accent and surface hue."""
    own = {role: roles[role].hex for role in ROLES}
    _, chroma, hue = to_oklch(roles["window"])
    other = _derive(roles["accent"], hue, min(0.018, chroma), dark=not given_dark, exact=True)
    light, dark = (own, other) if not given_dark else (other, own)
    chosen: list[Color] = []
    for c in [roles["accent"], *source_swatches]:
        if all(_hue_distance(to_oklch(c)[2], to_oklch(o)[2]) >= 15 for o in chosen):
            chosen.append(c)
    for preset in map(Color.parse, _PRESETS):
        if len(chosen) < MIN_SWATCHES and all(
            _hue_distance(to_oklch(preset)[2], to_oklch(o)[2]) >= 30 for o in chosen
        ):
            chosen.append(preset)
    hexes = [c.hex for c in chosen]
    return PaletteResult(light, dark, hexes[:MAX_SWATCHES], given=given)


def _map_pywal(special: dict, colors: dict) -> PaletteResult:
    background = _color(special.get("background")) or _color(colors.get("color0"))
    foreground = (
        _color(special.get("foreground")) or _color(colors.get("color15")) or _color(colors.get("color7"))
    )
    if background is None or foreground is None:
        return _failure(translate("core", "The pywal file has no background and foreground colors."))
    ansi = [_color(colors.get(f"color{i}")) for i in (1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14)]
    hues = [c for c in ansi if c is not None]
    dark = background.luminance < foreground.luminance
    accent = max(
        hues[:6] or hues or [Color.parse(DEFAULT_ACCENT)], key=lambda c: _hsv(c)[1] * (0.4 + _hsv(c)[2])
    )
    roles = {
        "accent": accent,
        "window": background,
        "view": background.mix(BLACK, 0.25) if dark else background.mix(WHITE, 0.55),
        "button": background.mix(foreground, 0.09),
        "header": background.mix(foreground, 0.04),
        "text": foreground,
        "text_muted": foreground.mix(background, 0.38),
        "link": _closest_hue(hues, 210, 0.18) or _breeze("link"),
        "visited": _closest_hue(hues, 290, 0.18) or _breeze("visited"),
        "negative": _closest_hue(hues, 5, 0.25) or _breeze("negative"),
        "neutral": _closest_hue(hues, 35, 0.25) or _breeze("neutral"),
        "positive": _closest_hue(hues, 130, 0.2) or _breeze("positive"),
    }
    fixed = ensure_contrast({role: c.hex for role, c in roles.items()})
    corrected = {role: Color.parse(fixed[role]) for role in ROLES}
    return _complete(corrected, dark, "dark" if dark else "light", [c for c in hues if _hsv(c)[1] >= 0.2][:8])


def from_pywal(path: str | Path) -> PaletteResult:
    """Colors from pywal's `colors.json` (`special` and `color0` to `color15`)."""
    data = _read_json(Path(path))
    if isinstance(data, Msg):
        return _failure(data)
    special, colors = data.get("special"), data.get("colors")
    if not isinstance(colors, dict):
        return _failure(translate("core", "The file is not a pywal color file."))
    return _map_pywal(special if isinstance(special, dict) else {}, colors)


def _matugen_modes(colors: dict) -> dict[str, dict[str, Color]]:
    """{"dark": {role: color}, "light": ...} from either layout of matugen's JSON."""
    modes: dict[str, dict[str, Color]] = {}
    for mode in ("dark", "light"):
        if isinstance(colors.get(mode), dict):  # colors.<mode>.<role>
            roles = {r: c for r, v in colors[mode].items() if (c := _color(v)) is not None}
        else:  # colors.<role>.<mode>
            roles = {}
            for role, value in colors.items():
                if isinstance(value, dict) and mode in value and (c := _color(value[mode])) is not None:
                    roles[role] = c
        if roles:
            modes[mode] = roles
    if not modes:  # one palette without modes: colors.<role> = color
        roles = {r: c for r, v in colors.items() if (c := _color(v)) is not None}
        if roles and "surface" in roles:
            modes["dark" if roles["surface"].is_dark else "light"] = roles
    return modes


def _map_matugen(m: dict[str, Color], dark: bool) -> dict[str, Color] | None:
    def pick(*names, default=None):
        return next((m[n] for n in names if n in m), default)

    surface, on_surface = pick("surface", "background"), pick("on_surface", "on_background")
    primary = pick("primary")
    if surface is None or on_surface is None or primary is None:
        return None
    extreme = BLACK if dark else WHITE
    roles = {
        "accent": primary,
        "window": surface,
        "view": pick("surface_container_lowest", default=surface.mix(extreme, 0.3)),
        "button": pick("surface_container_high", "secondary_container", "surface_variant")
        or surface.mix(on_surface, 0.12),
        "header": pick("surface_container", default=surface.mix(on_surface, 0.05)),
        "text": on_surface,
        "text_muted": pick("on_surface_variant", default=on_surface.mix(surface, 0.35)),
        "link": primary,
        "visited": pick("tertiary", default=_breeze("visited")),
        "negative": pick("error", default=_breeze("negative")),
        # matugen has no yellow or green: Breeze's, pulled a little towards the primary color
        "neutral": _breeze("neutral").mix(primary, 0.15),
        "positive": _breeze("positive").mix(primary, 0.15),
    }
    fixed = ensure_contrast({role: c.hex for role, c in roles.items()})
    return {role: Color.parse(fixed[role]) for role in ROLES}


def from_matugen(path: str | Path) -> PaletteResult:
    """Colors from matugen's JSON output, either layout (`colors.<role>.<mode>` or `colors.<mode>.<role>`)."""
    data = _read_json(Path(path))
    if isinstance(data, Msg):
        return _failure(data)
    colors = data.get("colors") if isinstance(data.get("colors"), dict) else data
    mapped = {}
    for mode, values in _matugen_modes(colors).items():
        roles = _map_matugen(values, mode == "dark")
        if roles is not None:
            mapped[mode] = roles
    if not mapped:
        return _failure(translate("core", "The file is not a matugen color file."))
    extra = [c for name in ("secondary", "tertiary") if (c := next(iter(mapped.values()), {}).get(name))]
    keep = "dark" if "dark" in mapped else "light"
    result = _complete(mapped[keep], keep == "dark", keep, extra)
    if len(mapped) == 2:
        result.light = {r: c.hex for r, c in mapped["light"].items()}
        result.dark = {r: c.hex for r, c in mapped["dark"].items()}
        result.given = "both"
    return result


# KDE color scheme groups and keys for each role, best source first (as the library reads schemes).
_SCHEME_SOURCES = {
    "accent": (("Colors:Selection", "BackgroundNormal"), ("Colors:Window", "DecorationFocus")),
    "window": (("Colors:Window", "BackgroundNormal"),),
    "view": (("Colors:View", "BackgroundNormal"),),
    "button": (("Colors:Button", "BackgroundNormal"),),
    "header": (("Colors:Header", "BackgroundNormal"), ("WM", "activeBackground")),
    "text": (("Colors:Window", "ForegroundNormal"), ("Colors:View", "ForegroundNormal")),
    "text_muted": (("Colors:Window", "ForegroundInactive"), ("Colors:View", "ForegroundInactive")),
    "link": (("Colors:View", "ForegroundLink"), ("Colors:Window", "ForegroundLink")),
    "visited": (("Colors:View", "ForegroundVisited"), ("Colors:Window", "ForegroundVisited")),
    "negative": (("Colors:View", "ForegroundNegative"), ("Colors:Window", "ForegroundNegative")),
    "neutral": (("Colors:View", "ForegroundNeutral"), ("Colors:Window", "ForegroundNeutral")),
    "positive": (("Colors:View", "ForegroundPositive"), ("Colors:Window", "ForegroundPositive")),
}  # fmt: skip


def from_colors_file(path: str | Path) -> PaletteResult:
    """Colors from a KDE color scheme file (`.colors`) from anywhere. The file's own colors are kept
    as they are (see `contrast_report` for how readable they are); roles it lacks are derived.
    Never raises."""
    try:
        text = _read_text(Path(path))
        if isinstance(text, Msg):
            return _failure(text)
        groups = safefile.parse_config(text)
    except Exception:  # a hostile file must not take the app down
        return _failure(translate("core", "The file cannot be read."))
    found: dict[str, Color] = {}
    for role, sources in _SCHEME_SOURCES.items():
        for group, key in sources:
            color = _color(groups.get((group,), {}).get(key))
            if color is not None:
                found[role] = color
                break
    if "window" not in found or "text" not in found:
        return _failure(translate("core", "The file is not a KDE color scheme."))
    window, text_color = found["window"], found["text"]
    dark = window.luminance < text_color.luminance
    defaults = {
        "view": window.mix(BLACK, 0.25) if dark else window.mix(WHITE, 0.55),
        "button": window.mix(text_color, 0.09),
        "header": window.mix(text_color, 0.04),
        "text_muted": text_color.mix(window, 0.38),
        "accent": Color.parse(DEFAULT_ACCENT),
        "link": _breeze("link"),
        "visited": _breeze("visited"),
        "negative": _breeze("negative"),
        "neutral": _breeze("neutral"),
        "positive": _breeze("positive"),
    }
    roles = {role: found.get(role) or defaults[role] for role in ROLES}
    return _complete(roles, dark, "dark" if dark else "light", [])


def available_sources() -> list[PaletteFile]:
    """The pywal and matugen files that exist right now, at the places those tools write them."""
    candidates = [
        PaletteFile("pywal", paths.cache_home() / "wal" / "colors.json"),
        PaletteFile("matugen", paths.cache_home() / "matugen" / "colors.json"),
        PaletteFile("matugen", paths.config_home() / "matugen" / "colors.json"),
    ]
    found = []
    for candidate in candidates:
        try:
            if candidate.path.is_file():
                found.append(candidate)
        except OSError:
            pass
    return found
