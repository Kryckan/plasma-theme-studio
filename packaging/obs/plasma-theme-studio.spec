#
# spec file for package plasma-theme-studio
#
# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# One spec for Fedora and openSUSE. The program is plain Python and ships as
# a copy in /usr/share/plasma-theme-studio (see packaging/install.sh), so the
# package is noarch. Tools the program runs are required by file name
# (/usr/bin/kreadconfig6 ...), which resolves to the right package on both
# distributions; see packaging/obs/README.md for which names are unverified.

Name:           plasma-theme-studio
Version:        0.1.0
Release:        0
Summary:        Edit every part of a KDE Plasma theme in one place
License:        GPL-3.0-or-later
URL:            https://github.com/Kryckan/plasma-theme-studio
Source0:        %{name}-%{version}.tar.xz
BuildArch:      noarch

BuildRequires:  python3
BuildRequires:  desktop-file-utils
BuildRequires:  appstream
%if 0%{?suse_version}
BuildRequires:  qt6-linguist-devel
%else
BuildRequires:  qt6-linguist
%endif

Requires:       python3
Requires:       python3-pyside6
%if 0%{?suse_version}
Requires:       python3-Jinja2
%else
Requires:       python3-jinja2
%endif
Requires:       hicolor-icon-theme
# The programs the app runs to read and write KDE settings and to apply a theme.
Requires:       /usr/bin/kreadconfig6
Requires:       /usr/bin/kwriteconfig6
Requires:       /usr/bin/plasma-apply-colorscheme
Requires:       /usr/bin/plasma-apply-desktoptheme
# The Application Style target and its preview.
Requires:       /usr/bin/kvantummanager
# Reloading KWin and reaching Plasma; busctl from systemd is the fallback.
Recommends:     /usr/bin/qdbus6
Recommends:     rofi
Recommends:     inkscape
Suggests:       matugen
Suggests:       python3-pywal

%description
Plasma Theme Studio keeps a whole KDE Plasma desktop theme in one file, shows
it in a visual preview, and applies it to the running desktop: colors, window
frame, Plasma style, panels, application style, GTK, fonts, icons, pointers
and more, each part on its own page.

Every apply takes a snapshot first, so it can be undone exactly, from the app
or from a text console. The app only writes inside your home folder and shows
the files it is about to write.

%prep
%autosetup

%build
# Nothing to build: packaging/install.sh compiles the translations.

%install
packaging/install.sh %{buildroot} %{_prefix}

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.kryckan.PlasmaThemeStudio.desktop
appstreamcli validate --no-net %{buildroot}%{_datadir}/metainfo/io.github.kryckan.PlasmaThemeStudio.metainfo.xml

%files
%license LICENSE
%{_bindir}/plasma-theme-studio
%{_datadir}/plasma-theme-studio/
%{_datadir}/applications/io.github.kryckan.PlasmaThemeStudio.desktop
%{_datadir}/metainfo/io.github.kryckan.PlasmaThemeStudio.metainfo.xml
%{_datadir}/icons/hicolor/*/apps/io.github.kryckan.PlasmaThemeStudio.svg

%changelog
