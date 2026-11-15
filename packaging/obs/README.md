# Open Build Service

One OBS package, `plasma-theme-studio`, builds the RPM (Fedora, openSUSE) and the `.deb` (Debian, Ubuntu). The program is plain Python and the package is `noarch`/`all`; all three kinds of package (also the Arch ones) install through `packaging/install.sh`, so they contain the same files. Nothing in this folder has been run on OBS: the files were checked by reading, by `scripts/check-packaging.py` (same version everywhere; the spec's `%files` and `debian/install` cover everything `install.sh` installs) and the Arch packages were built for real. `rpmspec`, `rpmlint`, `dpkg-buildpackage` and `lintian` were not available here.

## Files

| File | What it is |
|---|---|
| `_service` | Source services: checks out the tag from GitHub, takes the spec and the `.dsc` out of it, makes `plasma-theme-studio-VERSION.tar.xz`, sets the version. |
| `plasma-theme-studio.spec` | The RPM recipe for Fedora and openSUSE (`%if 0%{?suse_version}` where the names differ). |
| `plasma-theme-studio.dsc` | The Debian source description OBS needs next to the recipe (`3.0 (native)`). |
| `debian/` | `control`, `rules`, `changelog`, `copyright` (DEP-5), `install`, `source/format`. Packed by `make-debian-tar.sh` into `debian.tar.xz`, which OBS lays over the source. |

## Setting it up

1. Make an OBS project, for example `home:YOURNAME:plasma-theme-studio`, and add repositories: Fedora (a current release and rawhide), openSUSE Tumbleweed and openSUSE Leap 16.x, Debian (testing or the release you want) and Ubuntu 26.04 or newer. Anything that has no Plasma 6 and no PySide6 (Ubuntu 24.04, Leap 15) cannot run the app: leave it out.
2. `osc mkpac plasma-theme-studio` in a checkout of the project, then copy in `_service`, `plasma-theme-studio.spec` and `plasma-theme-studio.dsc` from this folder and run `packaging/obs/make-debian-tar.sh .` to get `debian.tar.xz`.
3. `osc add` the files, `osc service manualrun`, `osc add` what it made (`plasma-theme-studio-0.1.0.obscpio` and so on), `osc commit`. The tag named in `_service` (`revision`) must exist on GitHub first.
4. For a package that follows the latest code, make a second package, set `revision` to `main` and `versionformat` to `@PARENT_TAG@+git@TAG_OFFSET@.%h`, and add `-git` to the names.
5. Optional: enable the OBS "Source Service" webhook for the GitHub repository so a new tag rebuilds the package.

## Package names

Verified means looked up on the distribution's package site on 2026-11-15; unverified names are best knowledge and the first OBS build will show if one is wrong. Where possible the spec asks for a program by its file name (`/usr/bin/kreadconfig6`), which is right on every RPM distribution without knowing the package.

| Need | Fedora | openSUSE | Debian / Ubuntu | State |
|---|---|---|---|---|
| Python bindings of Qt 6 | `python3-pyside6` | `python3-pyside6` | `python3-pyside6.qtcore`, `.qtgui`, `.qtwidgets`, `.qtsvg`, `.qtquick` | Fedora and Debian verified; openSUSE unverified (Tumbleweed may name it by Python version) |
| Templates | `python3-jinja2` | `python3-Jinja2` | `python3-jinja2` | all unverified (the openSUSE spelling is from memory) |
| Kvantum | `/usr/bin/kvantummanager` (package `kvantum`) | same file (package `kvantum-qt6`) | `qt6-style-kvantum` | Fedora `kvantum` and Debian verified; openSUSE package name unverified |
| `kreadconfig6`, `kwriteconfig6` | file name | file name | `libkf6config-bin` | Debian verified |
| `plasma-apply-*` | file name | file name | `plasma-workspace` | Debian verified |
| `qdbus6` (recommended) | file name | file name | `qdbus-qt6` | Debian verified |
| Translation compiler at build time | `qt6-linguist` | `qt6-linguist-devel` | `qt6-l10n-tools` (`/usr/lib/qt6/bin/lrelease`) | Debian verified; Fedora and openSUSE unverified |
| `desktop-file-utils`, `appstream` (build checks) | same | same | same | unverified |
| `rofi`, `inkscape` (recommended) | same | same | same | unverified |
| `matugen`, `python3-pywal` (suggested) | may be missing | may be missing | may be missing | unverified; they are only suggestions |
| Sound players for *Play* | not listed | not listed | `pipewire-bin` or `pulseaudio-utils` (suggested) | unverified |

Notes:

- The spec does not require `qt6-qtsvg` or `qt6-qtdeclarative` by name: the PySide6 package of each distribution needs those libraries itself. The Arch package lists them because PRD section 10 does.
- The launcher uses `/usr/bin/python3`, so the PySide6 package has to be the one for the system's default Python.
- Debian gets its bytecode from `dh_python3` at install time; the RPM and Arch packages carry it.
- `Recommends` and `Suggests` are weak dependencies: a missing one only switches the matching feature off.
