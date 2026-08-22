#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version="0.2.2"
stage="$project_dir/build/tar/sortmedia-$version-linux-any"
output="$project_dir/dist/sortmedia-$version-linux-any.tar.gz"

rm -rf "$stage"
install -d -m 755 \
    "$stage/usr/local/bin" \
    "$stage/usr/local/lib/sortmedia/bin" \
    "$stage/usr/local/lib/sortmedia/src/sortmedia" \
    "$stage/usr/local/share/doc/sortmedia" \
    "$stage/usr/local/share/man/man1" \
    "$project_dir/dist"
install -m 755 "$project_dir/bin/sortmedia" "$stage/usr/local/lib/sortmedia/bin/sortmedia"
install -m 644 "$project_dir/src/sortmedia/"*.py "$stage/usr/local/lib/sortmedia/src/sortmedia/"
install -m 644 "$project_dir/README.md" "$stage/usr/local/share/doc/sortmedia/README.md"
install -m 644 "$project_dir/LICENSE" "$stage/usr/local/share/doc/sortmedia/LICENSE"
ln -s ../lib/sortmedia/bin/sortmedia "$stage/usr/local/bin/sortmedia"
gzip -n -9 -c "$project_dir/man/sortmedia.1" > "$stage/usr/local/share/man/man1/sortmedia.1.gz"
chmod 644 "$stage/usr/local/share/man/man1/sortmedia.1.gz"
tar -C "$stage" -czf "$output" .
echo "$output"
