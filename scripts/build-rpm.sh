#!/bin/sh
set -eu

if ! command -v rpmbuild >/dev/null 2>&1; then
    echo "Error: rpmbuild is required to build the RPM package." >&2
    exit 1
fi

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
topdir="$project_dir/build/rpm"
install -d -m 755 "$topdir/BUILD" "$topdir/BUILDROOT" "$topdir/RPMS" "$topdir/SOURCES" "$topdir/SPECS" "$topdir/SRPMS" "$project_dir/dist"
cp "$project_dir/packaging/rpm/sortmedia.spec" "$topdir/SPECS/"
tar -C "$project_dir" --transform='s,^,sortmedia-0.1.1/,' -czf "$topdir/SOURCES/sortmedia-0.1.1.tar.gz" \
    LICENSE README.md bin src man
rpmbuild --define "_topdir $topdir" -bb "$topdir/SPECS/sortmedia.spec"
find "$topdir/RPMS" -name '*.rpm' -exec cp {} "$project_dir/dist/" \;
