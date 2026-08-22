Name:           sortmedia
Version:        0.1.0
Release:        1%{?dist}
Summary:        Sort photos and videos using recording metadata
License:        MIT
URL:            https://github.com/mfuryto/sortmedia
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
Requires:       python3 >= 3.11
Requires:       python3-pillow
Requires:       perl-Image-ExifTool

%description
Sortmedia reads recording dates from EXIF and video metadata and sorts media
into configurable directory structures.

%prep
%setup -q

%build

%install
install -d %{buildroot}%{_bindir} %{buildroot}%{_libdir}/sortmedia/bin
install -d %{buildroot}%{_libdir}/sortmedia/src/sortmedia
install -d %{buildroot}%{_mandir}/man1 %{buildroot}%{_docdir}/sortmedia
install -m 755 bin/sortmedia %{buildroot}%{_libdir}/sortmedia/bin/sortmedia
install -m 644 src/sortmedia/*.py %{buildroot}%{_libdir}/sortmedia/src/sortmedia/
ln -s ../%{_lib}/sortmedia/bin/sortmedia %{buildroot}%{_bindir}/sortmedia
install -m 644 man/sortmedia.1 %{buildroot}%{_mandir}/man1/sortmedia.1
install -m 644 README.md LICENSE %{buildroot}%{_docdir}/sortmedia/

%files
%license LICENSE
%doc README.md
%{_bindir}/sortmedia
%{_libdir}/sortmedia/
%{_mandir}/man1/sortmedia.1*

%changelog
* Sat Aug 22 2026 Mikal Furyto <mfuryto@users.noreply.github.com> - 0.1.0-1
- Initial package
