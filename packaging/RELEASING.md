# Releasing a version

The steps for v0.1.0; for a later version replace the number. Nothing here is done by a script that publishes: every step that leaves this machine is yours.

## Before the tag

1. Version: `__version__` in `src/plasma_theme_studio/__init__.py` (already `0.1.0`; `pyproject.toml` has it too). The same number must be in `packaging/arch/release/PKGBUILD` (`pkgver`), `packaging/obs/plasma-theme-studio.spec` (`Version`), `packaging/obs/plasma-theme-studio.dsc`, the top entry of `packaging/obs/debian/changelog` (also fix its date), the `_service` file (`revision` as `v0.1.0`, `versionformat`) and the first `<release>` in `data/io.github.kryckan.PlasmaThemeStudio.metainfo.xml` (fix `date`). `scripts/check-packaging.py` fails when one of them differs.
2. `CHANGELOG.md`: rename "Unreleased (0.1.0)" to "0.1.0 (date)".
3. Screenshots: the metainfo points at `docs/screenshots/main-window.png` on the `main` branch. Make it again with `scripts/make_screenshots.py` (same name) and look at it before tagging (more pictures: add `<screenshot>` entries).
4. Checks: `ruff check .`, `pytest`, `scripts/check-packaging.py --stage`, `scripts/check-arch-package.sh`, `desktop-file-validate data/*.desktop`, `appstreamcli validate data/*.metainfo.xml`, and a try on a real session. Push and wait for CI to turn green.

## Tag

```sh
git tag -a v0.1.0 -m "Plasma Theme Studio 0.1.0"
git push origin v0.1.0
```

GitHub then serves `https://github.com/Kryckan/plasma-theme-studio/archive/v0.1.0.tar.gz`, which the release PKGBUILD downloads.

## AUR (both packages)

For each package make a clone of its AUR repository (`ssh://aur@aur.archlinux.org/plasma-theme-studio.git` and `.../plasma-theme-studio-git.git`), copy in `PKGBUILD` from `packaging/arch/release/` or `packaging/arch/git/`, then:

```sh
updpkgsums                          # release package only: fills in the sha256sum of the tag archive
makepkg --printsrcinfo > .SRCINFO
makepkg -f                          # a build in a clean place; add -s only if you want missing dependencies installed
git add PKGBUILD .SRCINFO && git commit -m "plasma-theme-studio 0.1.0" && git push
```

The `-git` package keeps `sha256sums=('SKIP')`; its `pkgver()` works out the version from the code and the commit count. Both packages conflict with each other. Commit the filled-in checksum and `.SRCINFO` of the release package back to `packaging/arch/release/` as well, so that the repository holds what the AUR holds.

## Open Build Service

Follow `packaging/obs/README.md`: create the project, add the package, upload `_service`, the spec, the `.dsc` and `debian.tar.xz` (made by `packaging/obs/make-debian-tar.sh`), and run the source service. The package names for Fedora, openSUSE, Debian and Ubuntu are marked there as verified or not; the first build log is the real test.

## After

Check that the AUR page shows the new version and that a build in a clean Arch container works (`scripts/check-arch-package.sh` does the same from the repository).
