# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import configparser
import json
import os
import subprocess

import pytest

from plasma_theme_studio import paths
from plasma_theme_studio.generators import ColorSchemeGenerator
from plasma_theme_studio.generators.plasmastyle import style_id
from plasma_theme_studio.generators.windowframe import frame_folder
from plasma_theme_studio.globaltheme import ExportError, export_global_theme, package_id
from plasma_theme_studio.model.theme import Theme


def colors_only(name="My Theme"):
    return Theme({("meta", "name"): name, ("meta", "author"): "Ada"})


def full(name="My Theme"):
    return Theme(
        {
            ("meta", "name"): name,
            ("window", "decoration"): "generated",
            ("panel", "style"): "generated",
            ("panel", "radius"): 10,
        }
    )


def rels(folder, written):
    return {p.relative_to(folder).as_posix() for p in written}


def defaults_of(folder, pid):
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    text = (folder / "share/plasma/look-and-feel" / pid / "contents/defaults").read_text()
    sections = {}
    group = None
    for line in text.splitlines():
        if line.startswith("["):
            group = line
            sections[group] = {}
        elif "=" in line:
            key, value = line.split("=", 1)
            sections[group][key] = value
    return sections


def test_colors_only_bundle(tmp_path):
    theme = colors_only()
    out = tmp_path / "out"
    written = export_global_theme(theme, out)
    pid = "io.github.kryckan.plasmathemestudio.mytheme"
    assert package_id(theme) == pid
    assert rels(out, written) >= {
        "install.sh",
        "uninstall.sh",
        f"share/plasma/look-and-feel/{pid}/metadata.json",
        f"share/plasma/look-and-feel/{pid}/contents/defaults",
        f"share/plasma/look-and-feel/{pid}/contents/colors",
        "share/color-schemes/MyTheme.colors",
    }
    assert not [r for r in rels(out, written) if "aurorae" in r or "desktoptheme" in r]
    meta = json.loads((out / f"share/plasma/look-and-feel/{pid}/metadata.json").read_text())
    assert meta["KPackageStructure"] == "Plasma/LookAndFeel"
    assert meta["X-Plasma-APIVersion"] == "2"
    assert meta["KPlugin"]["Id"] == pid
    assert meta["KPlugin"]["Name"] == "My Theme"
    assert meta["KPlugin"]["Authors"] == [{"Name": "Ada"}]
    assert "My Theme" in meta["KPlugin"]["Description"]
    assert defaults_of(out, pid) == {
        "[kdeglobals][General]": {"ColorScheme": "MyTheme"},
        "[ksplashrc][KSplash]": {"Theme": "None"},
    }
    scheme = ColorSchemeGenerator().files(theme)[0].content
    assert (out / "share/color-schemes/MyTheme.colors").read_text() == scheme
    assert (out / f"share/plasma/look-and-feel/{pid}/contents/colors").read_text() == scheme


def test_bundle_with_frame_and_panel(tmp_path):
    theme = full()
    out = tmp_path / "out"
    written = export_global_theme(theme, out)
    pid = package_id(theme)
    names = rels(out, written)
    frame, style = frame_folder(theme), style_id(theme)
    assert f"share/aurorae/themes/{frame}/metadata.desktop" in names
    assert f"share/plasma/desktoptheme/{style}/metadata.json" in names
    assert f"share/plasma/desktoptheme/{style}/widgets/panel-background.svg" in names
    assert defaults_of(out, pid) == {
        "[kdeglobals][General]": {"ColorScheme": "MyTheme"},
        "[plasmarc][Theme]": {"name": style},
        "[kwinrc][org.kde.kdecoration2]": {
            "library": "org.kde.kwin.aurorae.v2",
            "theme": f"__aurorae__svg__{frame}",
        },
        "[ksplashrc][KSplash]": {"Theme": "None"},
    }
    # Same content as an apply would write.
    for planned_name in ("metadata.desktop",):
        assert (out / "share/aurorae/themes" / frame / planned_name).is_file()


def test_breeze_decoration_is_named_without_files(tmp_path):
    theme = Theme({("meta", "name"): "B", ("window", "decoration"): "breeze"})
    out = tmp_path / "out"
    written = export_global_theme(theme, out)
    assert not [r for r in rels(out, written) if "aurorae" in r]
    assert defaults_of(out, package_id(theme))["[kwinrc][org.kde.kdecoration2]"] == {
        "library": "org.kde.breeze",
        "theme": "Breeze",
    }


def test_defaults_name_what_the_bundle_ships(tmp_path):
    for theme in (colors_only(), full()):
        out = tmp_path / package_id(theme) / str(len(theme.to_toml()))
        written = rels(out, export_global_theme(theme, out))
        values = defaults_of(out, package_id(theme))
        assert f"share/color-schemes/{values['[kdeglobals][General]']['ColorScheme']}.colors" in written
        if "[plasmarc][Theme]" in values:
            name = values["[plasmarc][Theme]"]["name"]
            assert f"share/plasma/desktoptheme/{name}/metadata.json" in written
        else:
            assert not [w for w in written if "desktoptheme" in w]
        if "[kwinrc][org.kde.kdecoration2]" in values:
            frame = values["[kwinrc][org.kde.kdecoration2]"]["theme"].removeprefix("__aurorae__svg__")
            assert f"share/aurorae/themes/{frame}/metadata.desktop" in written


def test_unwanted_parts_are_left_out(tmp_path):
    out = tmp_path / "out"
    export_global_theme(colors_only(), out)
    assert "plasmarc" not in (out / "share/plasma/look-and-feel").rglob("defaults").__next__().read_text()


def test_preview_is_rendered_when_qt_is_there(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    assert app
    out = tmp_path / "out"
    written = export_global_theme(colors_only(), out)
    pid = package_id(colors_only())
    preview = out / "share/plasma/look-and-feel" / pid / "contents/previews/preview.png"
    assert preview in written
    assert preview.read_bytes().startswith(b"\x89PNG")


def test_preview_is_skipped_without_qt_application(tmp_path, monkeypatch):
    monkeypatch.setattr("plasma_theme_studio.globaltheme._preview", lambda theme: None)
    out = tmp_path / "out"
    written = export_global_theme(colors_only(), out)
    assert not [r for r in rels(out, written) if r.endswith("preview.png")]


@pytest.mark.parametrize("theme", [colors_only(), full()])
def test_scripts_are_valid_posix_sh(tmp_path, theme):
    out = tmp_path / "out"
    export_global_theme(theme, out)
    for script in ("install.sh", "uninstall.sh"):
        assert os.access(out / script, os.X_OK)
        assert (out / script).read_text().startswith("#!/bin/sh\n")
        subprocess.run(["sh", "-n", str(out / script)], check=True)


def test_install_and_uninstall_touch_only_their_own_files(tmp_path):
    out = tmp_path / "out"
    export_global_theme(full("Odd Name"), out)
    data = tmp_path / "data"
    (data / "color-schemes").mkdir(parents=True)
    (data / "color-schemes/Other.colors").write_text("mine")
    (data / "plasma/desktoptheme/other").mkdir(parents=True)
    (data / "plasma/desktoptheme/other/x").write_text("mine")
    env = {"PATH": "/usr/bin:/bin", "XDG_DATA_HOME": str(data), "HOME": str(tmp_path / "nohome")}
    subprocess.run(["sh", str(out / "install.sh")], check=True, env=env, capture_output=True)
    pid = package_id(full("Odd Name"))
    assert (data / "plasma/look-and-feel" / pid / "metadata.json").is_file()
    assert (data / "color-schemes/OddName.colors").is_file()
    subprocess.run(["sh", str(out / "uninstall.sh")], check=True, env=env, capture_output=True)
    left = sorted(p.relative_to(data).as_posix() for p in data.rglob("*") if p.is_file())
    assert left == ["color-schemes/Other.colors", "plasma/desktoptheme/other/x"]
    assert (data / "plasma/desktoptheme/other").is_dir()
    assert not (data / "aurorae").exists()  # the folders the install made go with it
    assert not (data / "plasma/look-and-feel").exists() or not any((data / "plasma/look-and-feel").iterdir())


def test_install_uses_home_when_no_data_home(tmp_path):
    out = tmp_path / "out"
    export_global_theme(colors_only(), out)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path / "h")}
    subprocess.run(["sh", str(out / "install.sh")], check=True, env=env, capture_output=True)
    assert (tmp_path / "h/.local/share/color-schemes/MyTheme.colors").is_file()


@pytest.mark.parametrize(
    ("name", "slug"),
    [("Blå natt 2", "blanatt2"), ("../../etc/passwd", "etcpasswd"), ("a'b\"c; rm -rf $HOME", "abcrmrfhome")],
)
def test_odd_names_are_slugged_safely(tmp_path, name, slug):
    theme = colors_only(name)
    out = tmp_path / "out"
    written = export_global_theme(theme, out)
    assert package_id(theme) == f"io.github.kryckan.plasmathemestudio.{slug}"
    root = out.resolve()
    assert all(root in p.resolve().parents for p in written)
    meta = json.loads(next(out.rglob("metadata.json")).read_text())
    assert meta["KPlugin"]["Name"] == name.strip()
    for script in ("install.sh", "uninstall.sh"):
        subprocess.run(["sh", "-n", str(out / script)], check=True)
    # Nothing outside the folder, and nothing in the home of the test but the output.
    assert sorted(p.name for p in tmp_path.iterdir() if p.name not in {".local", ".config", ".cache"}) == [
        "out"
    ]
    assert not paths.data_home().exists()


def test_name_without_letters_is_refused(tmp_path):
    with pytest.raises(ExportError):
        export_global_theme(colors_only("日本"), tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_non_empty_folder_is_refused(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep").write_text("x")
    with pytest.raises(ExportError):
        export_global_theme(colors_only(), out)
    assert [p.name for p in out.iterdir()] == ["keep"]
    file = tmp_path / "file"
    file.write_text("x")
    with pytest.raises(ExportError):
        export_global_theme(colors_only(), file)


def test_empty_existing_folder_is_accepted(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    assert export_global_theme(colors_only(), out)


def test_export_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr("plasma_theme_studio.globaltheme._preview", lambda theme: None)
    export_global_theme(full(), tmp_path / "a")
    export_global_theme(full(), tmp_path / "b")
    a = {p.relative_to(tmp_path / "a"): p.read_bytes() for p in (tmp_path / "a").rglob("*") if p.is_file()}
    b = {p.relative_to(tmp_path / "b"): p.read_bytes() for p in (tmp_path / "b").rglob("*") if p.is_file()}
    assert a == b
