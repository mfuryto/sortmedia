#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$project_dir/scripts/build-tar.sh"

if command -v dpkg-deb >/dev/null 2>&1; then
    "$project_dir/scripts/build-deb.sh"
else
    echo "Skipping DEB: dpkg-deb is not installed."
fi

if command -v rpmbuild >/dev/null 2>&1; then
    "$project_dir/scripts/build-rpm.sh"
else
    echo "Skipping RPM: rpmbuild is not installed."
fi

echo "Packages are available in $project_dir/dist"

