# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import stat
import struct
import zipfile

import pytest

from plasma_theme_studio import archive
from plasma_theme_studio.archive import ArchiveError, export_theme, import_theme
from plasma_theme_studio.model.theme import Theme


def sample():
    theme = Theme.from_preset("breeze-dark")
    theme.set("meta", "name", 'Nörd "Tema"')
    theme.set("colors", "accent", "#112233")
    return theme


def make(path, entries):
    """An archive of (name, data[, mode]) entries, written the way an attacker could."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data, *mode in entries:
            info = zipfile.ZipInfo(name)
            if mode:
                info.external_attr = mode[0] << 16
            z.writestr(info, data)
    return path


def rejected(path):
    with pytest.raises(ArchiveError) as caught:
        import_theme(path)
    assert str(caught.value)
    return str(caught.value)


def test_round_trip(tmp_path):
    export_theme(sample(), tmp_path / "a.ptstheme")
    assert import_theme(tmp_path / "a.ptstheme") == sample()


def test_export_is_deterministic(tmp_path):
    export_theme(sample(), tmp_path / "a.ptstheme")
    export_theme(sample(), tmp_path / "b.ptstheme")
    assert (tmp_path / "a.ptstheme").read_bytes() == (tmp_path / "b.ptstheme").read_bytes()


def test_archive_holds_only_the_theme(tmp_path):
    export_theme(sample(), tmp_path / "a.ptstheme")
    with zipfile.ZipFile(tmp_path / "a.ptstheme") as z:
        assert z.namelist() == ["theme.toml"]
        assert z.read("theme.toml").decode() == sample().to_toml()


def test_plain_toml_file_is_imported(tmp_path):
    (tmp_path / "t.toml").write_text(sample().to_toml(), encoding="utf-8")
    assert import_theme(tmp_path / "t.toml") == sample()


def test_valid_assets_are_accepted_and_ignored(tmp_path):
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
    path = make(
        tmp_path / "a.zip", [("theme.toml", sample().to_toml()), ("assets/", b""), ("assets/f.svg", svg)]
    )
    assert import_theme(path) == sample()


@pytest.mark.parametrize(
    "entry",
    [
        ("/etc/passwd", "x"),
        ("assets/../../x.svg", "x"),
        ("../evil", "x"),
        ("assets\\x.svg", "x"),
        ("C:/x.svg", "x"),
        ("assets/sub/x.svg", "x"),
        ("assets/x.png", "x"),
        ("run.sh", "x"),
        ("sub/", b""),
        ("assets/l.svg", "/etc/passwd", stat.S_IFLNK | 0o777),
        ("assets/dev.svg", "x", stat.S_IFCHR | 0o666),
    ],
)
def test_unexpected_members_are_refused(tmp_path, entry):
    rejected(make(tmp_path / "x.zip", [("theme.toml", sample().to_toml()), entry]))


def test_symlink_theme_is_refused(tmp_path):
    rejected(make(tmp_path / "x.zip", [("theme.toml", "/etc/passwd", stat.S_IFLNK | 0o777)]))


def test_duplicate_member_is_refused(tmp_path):
    with pytest.warns(UserWarning):
        path = make(tmp_path / "x.zip", [("theme.toml", sample().to_toml()), ("theme.toml", "x")])
    rejected(path)


def test_missing_theme_is_refused(tmp_path):
    rejected(make(tmp_path / "x.zip", [("assets/x.svg", "<svg/>")]))


def test_too_many_entries_are_refused(tmp_path):
    entries = [("theme.toml", sample().to_toml())] + [(f"assets/{i}.svg", "<svg/>") for i in range(100)]
    rejected(make(tmp_path / "x.zip", entries))


def test_oversized_theme_is_refused(tmp_path):
    rejected(make(tmp_path / "x.zip", [("theme.toml", "#" + "a" * 5_000_000)]))


def test_oversized_asset_is_refused(tmp_path):
    rejected(
        make(tmp_path / "x.zip", [("theme.toml", sample().to_toml()), ("assets/x.svg", " " * 3_000_000)])
    )


def test_total_size_is_limited(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "MAX_TOTAL", 100_000)
    entries = [("theme.toml", sample().to_toml())] + [(f"assets/{i}.svg", " " * 60_000) for i in range(2)]
    rejected(make(tmp_path / "x.zip", entries))


def test_not_a_zip_is_refused(tmp_path):
    (tmp_path / "x.zip").write_bytes(b"PK\x03\x04 not really")
    rejected(tmp_path / "x.zip")
    (tmp_path / "y.zip").write_bytes(b"just text, not a theme")
    rejected(tmp_path / "y.zip")


def test_bad_theme_content_is_refused(tmp_path):
    rejected(make(tmp_path / "a.zip", [("theme.toml", "colors = [")]))
    rejected(make(tmp_path / "b.zip", [("theme.toml", "schema_version = 1\n[colors]\nevil = 1\n")]))
    rejected(make(tmp_path / "c.zip", [("theme.toml", b"\xff\xfe\x00bad")]))
    (tmp_path / "d.toml").write_bytes(b"\xff\xfe")
    rejected(tmp_path / "d.toml")


def test_missing_file_is_refused(tmp_path):
    rejected(tmp_path / "nothing.ptstheme")


def test_folder_is_refused(tmp_path):
    rejected(tmp_path)


def test_huge_plain_file_is_refused(tmp_path):
    (tmp_path / "t.toml").write_text("#" + "a" * 200_000)
    rejected(tmp_path / "t.toml")


def _patch_sizes(path, size):
    """Make the local and central headers claim `size` as the uncompressed size of every member."""
    data = bytearray(path.read_bytes())
    pos = 0
    while (pos := data.find(b"PK\x03\x04", pos)) >= 0:
        data[pos + 22 : pos + 26] = struct.pack("<I", size)
        pos += 4
    pos = 0
    while (pos := data.find(b"PK\x01\x02", pos)) >= 0:
        data[pos + 24 : pos + 28] = struct.pack("<I", size)
        pos += 4
    path.write_bytes(bytes(data))


def test_header_that_claims_too_much_is_refused(tmp_path):
    export_theme(sample(), tmp_path / "a.ptstheme")
    _patch_sizes(tmp_path / "a.ptstheme", 10**9)
    assert "too large" in rejected(tmp_path / "a.ptstheme")


def test_header_that_claims_too_little_is_refused(tmp_path):
    big = Theme.from_toml(sample().to_toml())
    # A comment-padded file is real data that is longer than its header says.
    text = big.to_toml() + "#" + "x" * 20_000 + "\n"
    path = make(tmp_path / "a.zip", [("theme.toml", text)])
    _patch_sizes(path, 100)
    rejected(path)


def test_bomb_with_small_header_never_reads_more_than_the_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "MAX_THEME", 1000)
    path = make(tmp_path / "a.zip", [("theme.toml", "#" + "a" * 100_000)])
    _patch_sizes(path, 10)
    rejected(path)


def test_corrupt_data_is_refused(tmp_path):
    export_theme(sample(), tmp_path / "a.ptstheme")
    data = bytearray((tmp_path / "a.ptstheme").read_bytes())
    data[40] ^= 0xFF
    (tmp_path / "a.ptstheme").write_bytes(bytes(data))
    rejected(tmp_path / "a.ptstheme")
