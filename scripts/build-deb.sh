#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version="0.3.0-1"
package_name="sortmedia_${version}_all"
build_root="$project_dir/build/deb/$package_name"
output_dir="$project_dir/dist"

rm -rf "$build_root"
install -d -m 755 \
    "$build_root/DEBIAN" \
    "$build_root/usr/bin" \
    "$build_root/usr/lib/sortmedia/bin" \
    "$build_root/usr/lib/sortmedia/src/sortmedia" \
    "$build_root/usr/share/doc/sortmedia" \
    "$build_root/usr/share/man/man1" \
    "$output_dir"

install -m 644 "$project_dir/packaging/debian/control" "$build_root/DEBIAN/control"
install -m 755 "$project_dir/bin/sortmedia" "$build_root/usr/lib/sortmedia/bin/sortmedia"
install -m 644 "$project_dir/src/sortmedia/"*.py "$build_root/usr/lib/sortmedia/src/sortmedia/"
install -m 644 "$project_dir/README.md" "$build_root/usr/share/doc/sortmedia/README.md"
install -m 644 "$project_dir/packaging/debian/copyright" "$build_root/usr/share/doc/sortmedia/copyright"

ln -s ../lib/sortmedia/bin/sortmedia "$build_root/usr/bin/sortmedia"
gzip -n -9 -c "$project_dir/man/sortmedia.1" > "$build_root/usr/share/man/man1/sortmedia.1.gz"
chmod 644 "$build_root/usr/share/man/man1/sortmedia.1.gz"

find "$build_root" -type d -exec chmod 755 {} +
dpkg-deb --root-owner-group --build "$build_root" "$output_dir/${package_name}.deb"
echo "$output_dir/${package_name}.deb"
