# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os

from plasma_theme_studio import wallpaper

PNG = b"\x89PNG\r\n\x1a\n"


def image(path, content=PNG):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def package(folder, sizes=("1080x1920", "3840x2160", "1280x720"), dark=()):
    for size in sizes:
        image(folder / "contents/images" / f"{size}.png")
    for size in dark:
        image(folder / "contents/images_dark" / f"{size}.png")
    return folder


def containment(number, plugin="org.kde.image", screen=0, activity=None, image_value=None, extra=""):
    text = f"[Containments][{number}]\nlastScreen={screen}\nplugin=org.kde.plasma.folder\n"
    text += f"wallpaperplugin={plugin}\n"
    if activity:
        text += f"activityId={activity}\n"
    text += "\n"
    if image_value is not None:
        text += f"[Containments][{number}][Wallpaper][{plugin}][General]\nImage={image_value}\n\n"
    return text + extra


def write_config(home, text):
    path = home / ".config" / wallpaper.APPLETSRC
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_no_config(home):
    source = wallpaper.wallpaper_source()
    assert source.path is None
    assert str(source.reason)
    assert wallpaper.current_wallpaper() is None


def test_plain_path_and_url(home):
    jpg = image(home / "pics/My Pic.jpg")
    write_config(home, containment(1, image_value=str(jpg)))
    assert wallpaper.current_wallpaper() == jpg
    write_config(home, containment(1, image_value="file://" + str(jpg).replace(" ", "%20")))
    source = wallpaper.wallpaper_source()
    assert source.path == jpg
    assert source.plugin == "org.kde.image"
    write_config(home, containment(1, image_value=str(home / "gone.jpg")))
    source = wallpaper.wallpaper_source()
    assert source.path is None
    assert str(source.reason)


def test_package_forms(home):
    folder = package(home / "pkgs/Next", dark=("2560x1440",))
    for value in (str(folder), f"file://{folder}", f"file://{folder}/"):
        write_config(home, containment(1, image_value=value))
        assert wallpaper.current_wallpaper() == folder / "contents/images/3840x2160.png"
    write_config(home, containment(1, image_value=f"file://{folder}#dark"))
    assert wallpaper.current_wallpaper() == folder / "contents/images_dark/2560x1440.png"
    write_config(home, containment(1, image_value=f"{folder}#light"))
    assert wallpaper.current_wallpaper(dark=True) == folder / "contents/images/3840x2160.png"
    write_config(home, containment(1, image_value=str(folder)))
    assert wallpaper.current_wallpaper(dark=True) == folder / "contents/images_dark/2560x1440.png"


def test_bare_name_and_fragment(home):
    folder = package(home / ".local/share/wallpapers/Cool")
    write_config(home, containment(1, image_value="Cool#day-night"))
    assert wallpaper.current_wallpaper() == folder / "contents/images/3840x2160.png"
    write_config(home, containment(1, image_value="Unknown"))
    assert wallpaper.current_wallpaper() is None


def test_screens_and_activities(home):
    a, b, c = (image(home / f"{n}.png") for n in "abc")
    text = containment(1, screen=1, image_value=str(a))
    text += containment(2, activity="one", image_value=str(b))
    text += containment(3, activity="two", image_value=str(c))
    text += "[Containments][4]\nlastScreen=-1\nplugin=org.kde.panel\n\n"
    write_config(home, text)
    assert wallpaper.current_wallpaper(screen=1) == a
    assert wallpaper.current_wallpaper(activity="two") == c
    assert wallpaper.current_wallpaper(activity="one") == b
    assert wallpaper.current_wallpaper() == b  # no running activity known: the first one
    rc = home / ".config/kactivitymanagerdrc"
    rc.write_text("[main]\ncurrentActivity=two\n")
    assert wallpaper.current_wallpaper() == c
    assert wallpaper.current_wallpaper(screen=5) is None


def test_old_plugin_group_ignored(home):
    old = image(home / "old.png")
    text = containment(1, plugin="org.kde.color", image_value=None)
    text += f"[Containments][1][Wallpaper][org.kde.image][General]\nImage={old}\n"
    write_config(home, text)
    assert wallpaper.current_wallpaper() is None


def test_color_wallpaper(home):
    text = containment(1, plugin="org.kde.color")
    text += "[Containments][1][Wallpaper][org.kde.color][General]\nColor=10,20,30\n"
    write_config(home, text)
    source = wallpaper.wallpaper_source()
    assert source.path is None
    assert source.plugin == "org.kde.color"
    assert source.value == "10,20,30"
    assert str(source.reason)


def test_slideshow(home):
    folder = home / "slides"
    first, second = image(folder / "a.png"), image(folder / "b.jpg")
    image(folder / "notes.txt", b"x")
    text = containment(1, plugin="org.kde.slideshow")
    text += f"[Containments][1][Wallpaper][org.kde.slideshow][General]\nSlidePaths={folder}\n"
    write_config(home, text)
    assert wallpaper.current_wallpaper() == first
    write_config(home, text + f"UncheckedSlides={first}\n")
    assert wallpaper.current_wallpaper() == second
    empty = containment(1, plugin="org.kde.slideshow")
    empty += "[Containments][1][Wallpaper][org.kde.slideshow][General]\nSlidePaths=/nope\n"
    write_config(home, empty)
    source = wallpaper.wallpaper_source()
    assert source.path is None
    assert str(source.reason)


def test_picture_of_the_day(home):
    write_config(home, containment(1, plugin="org.kde.potd"))
    assert wallpaper.wallpaper_source().path is None
    cache = home / ".cache/plasma_engine_potd"
    old, new = image(cache / "old.jpg"), image(cache / "new.jpg")
    os.utime(old, (1, 1))
    assert wallpaper.wallpaper_source().path == new


def test_empty_image_uses_global_theme_default(home):
    defaults = home / "system/share/plasma/look-and-feel/org.example.theme/contents/defaults"
    defaults.parent.mkdir(parents=True)
    pic = image(home / "default.png")
    defaults.write_text(f"[Wallpaper]\nImage={pic}\n")
    (home / ".config/kdedefaults").mkdir(parents=True)
    (home / ".config/kdedefaults/package").write_text("org.example.theme\n")
    write_config(home, containment(1, image_value=""))
    assert wallpaper.current_wallpaper() == pic


def test_other_plugin_and_hostile_config(home):
    write_config(home, containment(1, plugin="com.example.fancy"))
    assert str(wallpaper.wallpaper_source().reason)
    write_config(home, "[Containments][x]\nlastScreen=abc\nplugin=org.kde.plasma.folder\n\x00junk")
    assert wallpaper.current_wallpaper() is None


def test_installed_wallpapers(home):
    package(home / "system/share/wallpapers/Next")
    package(home / "system/share/wallpapers/Plain")
    (home / "system/share/wallpapers/Plain/metadata.json").write_text(
        json.dumps({"KPlugin": {"Name": "Plain Name"}})
    )
    package(home / ".local/share/wallpapers/Next", sizes=("1920x1080",))
    image(home / ".local/share/wallpapers/loose.jpg")
    image(home / ".local/share/wallpapers/readme.txt", b"x")
    (home / ".local/share/wallpapers/empty").mkdir()
    found = {w.name: w for w in wallpaper.installed_wallpapers()}
    assert set(found) == {"Next", "Plain Name", "loose"}
    assert found["Next"].path == home / ".local/share/wallpapers/Next/contents/images/1920x1080.png"
    assert found["Next"].is_package
    assert not found["loose"].is_package
    assert found["loose"].path == found["loose"].folder
    assert list(found) == sorted(found, key=str.casefold)


def test_no_wallpaper_folders(home):
    assert wallpaper.installed_wallpapers() == []


def test_a_pipe_for_a_config_or_a_package_file_does_not_block(home):
    import signal
    import time

    def fail(*args):
        raise AssertionError("blocked")

    signal.signal(signal.SIGALRM, fail)
    signal.alarm(10)
    try:
        folder = home / ".config"
        folder.mkdir(parents=True, exist_ok=True)
        os.mkfifo(folder / wallpaper.APPLETSRC)
        assert wallpaper.current_wallpaper() is None
        (folder / wallpaper.APPLETSRC).unlink()
        started = time.monotonic()
        write_config(home, "[" * 200_000)
        assert wallpaper.current_wallpaper() is None
        assert time.monotonic() - started < 3
    finally:
        signal.alarm(0)
