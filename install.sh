#!/bin/sh
set -eu

install_prefix="${PREFIX:-/usr/local}"
library_dir="$install_prefix/lib/sortmedia"
command_path="$install_prefix/bin/sortmedia"
man_dir="$install_prefix/share/man/man1"

install -d -m 755 "$library_dir/bin" "$library_dir/src/sortmedia" "$install_prefix/bin" "$man_dir"
install -m 755 bin/sortmedia "$library_dir/bin/sortmedia"
install -m 644 pyproject.toml "$library_dir/pyproject.toml"
install -m 644 src/sortmedia/__init__.py "$library_dir/src/sortmedia/__init__.py"
install -m 644 src/sortmedia/cli.py "$library_dir/src/sortmedia/cli.py"
install -m 644 src/sortmedia/config.py "$library_dir/src/sortmedia/config.py"
install -m 644 src/sortmedia/core.py "$library_dir/src/sortmedia/core.py"
install -m 644 src/sortmedia/history.py "$library_dir/src/sortmedia/history.py"
install -m 644 src/sortmedia/reporting.py "$library_dir/src/sortmedia/reporting.py"
install -m 644 src/sortmedia/cleanup.py "$library_dir/src/sortmedia/cleanup.py"
install -m 644 src/sortmedia/normalize.py "$library_dir/src/sortmedia/normalize.py"
install -m 644 man/sortmedia.1 "$man_dir/sortmedia.1"
ln -sfn "$library_dir/bin/sortmedia" "$command_path"

echo "Installed: $command_path"
