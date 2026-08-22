# Sortmedia

[![Linux](https://img.shields.io/badge/platform-Linux-2ea44f)](https://github.com/mfuryto/sortmedia)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Package validation](https://github.com/mfuryto/sortmedia/actions/workflows/packages.yml/badge.svg)](https://github.com/mfuryto/sortmedia/actions/workflows/packages.yml)

**Safe, local media organization that lives with your folders.**

Sort photos, videos, RAW files, Live Photos, and sidecars by their real capture
date—without importing a library, changing metadata, or giving up control of
your filesystem. Preview every operation first, then copy or move with run
history and hash-verified undo.

```text
Camera upload/                 Photo archive/
├── IMG_8421.HEIC              └── 2026/
├── IMG_8421.MOV        →          └── 08/
├── DSC_1042.NEF                       ├── 20260822_142311_IMG_8421.HEIC
├── DSC_1042.JPG                       ├── 20260822_142311_IMG_8421.MOV
└── DSC_1042.XMP                       ├── 20260822_161905_DSC_1042.NEF
                                      ├── 20260822_161905_DSC_1042.JPG
                                      └── 20260822_161905_DSC_1042.XMP
```

Companions stay together. Embedded metadata stays untouched. Existing files
are never overwritten.

## Quick start

```bash
# Download the .deb from the latest GitHub release, then:
sudo apt install ./dist/sortmedia_0.1.0-1_all.deb
cd /path/to/your/photos
sortmedia
```

The interactive menu creates a local `.sortmedia.toml`, previews the result,
and lets you update the same config when you are ready to copy or move. For a
repository checkout, use `sudo ./install.sh` instead of the package command.

## What makes Sortmedia different

Sortmedia is designed for people who want predictable filesystem organization
without importing their library into a database, cloud service, or graphical
photo manager.

- **Directory-local jobs:** A hidden `.sortmedia.toml` travels with each media
  directory. Enter the directory and run `sortmedia` or `sortmedia -r`.
- **Safe by default:** Preview is the default operation. Existing files are
  never overwritten, dangerous output paths are rejected, and completed runs
  are recorded for hash-verified undo.
- **Metadata stays intact:** Files are copied or moved without re-encoding or
  rewriting embedded EXIF, XMP, RAW, QuickTime, or video metadata.
- **Companion-aware:** RAW+JPEG pairs, Live Photo image+video pairs, and XMP,
  AAE, or THM sidecars keep the same destination folder and base filename.
- **Live Photo maintenance:** Choose whether short video companions are
  included, left behind, or moved to recoverable trash. A separate recursive
  cleanup tool handles existing libraries without running a sort job.
- **Reliable duplicate handling:** Exact SHA-256 detection works across
  different filenames. Optional perceptual fingerprints detect visually
  similar images using structure, luminance, and color information.
- **Recoverable housekeeping:** Run history, undo, recoverable trash, and an
  explicitly confirmed permanent trash cleanup protect valuable archives.
- **Automation-ready:** Progress output, quiet mode, newline-delimited JSON,
  exit statuses, multiple configs, temporary flag overrides, and recursive
  depth limits support scripts and cron.
- **Broad Linux delivery:** DEB, RPM, Arch, Alpine, and generic Linux package
  definitions are included, with native package validation in CI.
- **Local and transparent:** Metadata analysis and duplicate detection run on
  the local machine. The config, history, and generated structure remain easy
  to inspect with ordinary filesystem tools.

## Designed around real photo libraries

Sortmedia treats related media as a unit instead of a collection of unrelated
files. A RAW original, JPEG edit, XMP sidecar, and an iPhone Live Photo video
can retain their relationship throughout naming, sorting, collision handling,
and undo.

It also solves a less glamorous problem that photo organizers often leave
behind: unwanted Live Photo video clips. Keep them with their photos, leave
them at the source, move them to recoverable trash during sorting, or run the
dedicated cleanup tool against an existing library. Nothing is permanently
deleted without a separate, explicit confirmation.

## Requirements

- Python 3.11 or newer
- ExifTool available as `exiftool`

## Run from the repository

```bash
./bin/sortmedia -c /path/to/job/.sortmedia.toml
```

Run without arguments in a terminal to open the interactive menu for the
current working directory:

```bash
cd /path/to/media-job
sortmedia
```

The menu can create `.sortmedia.toml` in that directory or run an existing
local config. Non-interactive scripts and cron jobs must use `--config`.

When a local config already exists, the menu can update its operation and
directory layout in place. The same `.sortmedia.toml` is overwritten while its
other settings and comments are preserved.

Run the config in the current working directory without opening the menu:

```bash
sortmedia -r
```

The wizard displays the current working directory as both the suggested source
and destination. The default layout uses year as the primary level:

```text
<current directory>/<year>/<month>/<day>/
```

The create and update menus show described layout choices with examples:

```text
1) Year only: {year}                         -> 2026/
2) Year and month: {year}/{month}            -> 2026/08/
3) Year, month, and day: {year}/{month}/{day} -> 2026/08/22/
```

A custom template may use `{year}`, `{month}`, `{day}`, `{date}`, `{time}`,
`{original}`, and `{extension}`.

Settings can be overridden with multiple flags. Overrides affect only the
current run and do not modify the config file:

```bash
sortmedia -r --move --recursive
sortmedia -r -d /archive --layout "{year}/{month}"
sortmedia -f /media/camera -d /photos --copy
```

## Configuration

Config files must be hidden TOML files such as `.sortmedia.toml`. Relative
paths are resolved from the directory containing the config file. If `folder`
is omitted, the config file's directory is used as the source.

```toml
folder = "incoming"
destination = "."
recursive = true
operation = "preview"
layout = "{year}/{month}/{day}"
filename = "{date}_{time}_{original}"
duplicates = "hash"
timezone = "local"
perceptual_duplicates = false
live_photo_videos = "include"
```

`timezone` may be `local`, `UTC`, or an IANA name such as `Europe/Oslo`.
Timezone-aware video timestamps are converted before directory and filename
templates are rendered.

Start with `operation = "preview"`. Change it to `copy` or `move` only after
reviewing the planned operations. Existing files are never overwritten.

Related files with the same base name are handled as one companion group. This
includes RAW+JPEG pairs, Apple Live Photo image+video pairs, and `.xmp`, `.aae`,
or `.thm` sidecars. Every companion keeps its original bytes and metadata while
receiving the same destination folder and base filename.

`duplicates = "hash"` is the default. SHA-256 detects identical content even
when filenames differ. Identical files are skipped; a filename collision with
different content receives a numeric suffix. `rename` always keeps both, while
`skip` skips any filename collision without comparing content.

Live Photo short videos can follow one of three policies:

```toml
live_photo_videos = "include" # sort the MOV together with the photo
live_photo_videos = "leave"   # leave the MOV in the source directory
live_photo_videos = "trash"   # move the MOV to recoverable .sortmedia/trash
```

`trash` is journaled and can be restored with `sortmedia --undo`. Standalone
videos without a same-named image continue through the normal video workflow.

The main interactive menu also provides a separate cleanup tool for existing
libraries. It scans all subdirectories for same-named image/video pairs, shows
every candidate, and asks for confirmation before moving only the video files
to recoverable trash. It works with or without a `.sortmedia.toml` config and
does not perform any sorting.

Main-menu option 5 permanently removes files from `.sortmedia/trash` after
showing file count and total size. It requires typing `DELETE` exactly and
keeps history files, although runs referencing deleted trash content can no
longer be undone.

Set `perceptual_duplicates = true` or pass `--perceptual` to detect visually
similar images with a difference hash. This is optional and never replaces the
exact SHA-256 check.

Metadata is read for the entire job in one ExifTool batch instead of launching
one process per file. Destination hashes and perceptual image hashes are built
in parallel, and progress is printed as `[current/total]`. If embedded metadata
has no date, common camera names such as `IMG_20240819_143052.jpg` are checked
before filesystem timestamps.

Use `--quiet` for cron jobs, `--json` for newline-delimited machine-readable
events, and `--max-depth N` to limit recursive scanning (`0` means only the
source directory):

```bash
sortmedia -r --quiet
sortmedia -r --json
sortmedia -r --recursive --max-depth 2
```

Multiple configs are executed in the order given:

```bash
sortmedia -c ~/photos/.sortmedia.toml -c /media/camera/.import.toml
```

## System-wide installation

```bash
sudo ./install.sh
sortmedia -h
man sortmedia
```

The command is available to every user, but normal Linux permissions still
apply to config, source, and destination directories.

The internal `.sortmedia/` state directory contains plans and run history. It
is always excluded from recursive media scans.

Every completed `copy` or `move` run is recorded as structured JSON under
`.sortmedia/history/`. View and undo runs from the job directory:

```bash
sortmedia --history
sortmedia --undo
sortmedia --undo RUN_ID
```

Undo verifies the SHA-256 content before deleting a copied file or moving a
file back. It refuses to continue if a destination changed. Companion groups
roll back their already-completed operations if another member fails. Layout
and filename templates cannot use absolute paths or escape the destination
with `..`.

## Distribution packages

Build all package formats supported by the current host:

```bash
./scripts/build-packages.sh
```

Available package targets:

- Debian, Ubuntu, and Linux Mint: `.deb`
- Fedora, RHEL, Rocky Linux, AlmaLinux, and openSUSE: `.rpm`
- Arch Linux and Manjaro: `PKGBUILD`
- Alpine Linux: `APKBUILD`
- Other Linux distributions: generic `.tar.gz`

GitHub Actions builds and validates DEB, RPM, Arch, and Alpine packages in
their native environments on every push and pull request.

Install the Debian package:

```bash
sudo apt install ./dist/sortmedia_0.1.0-1_all.deb
```

The generic archive installs under `/usr/local` when extracted at the root:

```bash
sudo tar -xzf dist/sortmedia-0.1.0-linux-any.tar.gz -C /
```

## Cron

```cron
*/15 * * * * /usr/bin/sortmedia -c /data/import/.sortmedia.toml
```

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## License

MIT
