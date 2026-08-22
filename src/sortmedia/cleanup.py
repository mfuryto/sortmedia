from __future__ import annotations

from pathlib import Path
import shutil

from .core import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from .history import RunJournal, file_sha256


def format_size(size: int) -> str:
    value = float(size)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if value < 1000 or unit == units[-1]:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{size} B"


def find_live_photo_videos(root: Path) -> list[Path]:
    root = root.resolve()
    groups: dict[tuple[Path, str], set[str]] = {}
    files: dict[tuple[Path, str], list[Path]] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if ".sortmedia" in relative.parts or not path.is_file():
            continue
        key = (path.parent, path.stem.casefold())
        groups.setdefault(key, set()).add(path.suffix.lower())
        files.setdefault(key, []).append(path)

    matches = []
    for key, extensions in groups.items():
        if not extensions.intersection(IMAGE_EXTENSIONS):
            continue
        matches.extend(
            path for path in files[key]
            if path.suffix.lower() in VIDEO_EXTENSIONS
        )
    return sorted(matches)


def trash_live_photo_videos(root: Path, videos: list[Path]) -> tuple[str, int]:
    root = root.resolve()
    journal = RunJournal(root / ".sortmedia", "live-photo-cleanup")
    moved = 0
    try:
        for source in videos:
            source = source.resolve()
            relative = source.relative_to(root)
            destination = root / ".sortmedia" / "trash" / journal.run_id / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            digest = file_sha256(source)
            shutil.move(source, destination)
            journal.add("move", source, destination, digest)
            moved += 1
        journal.finish()
    except Exception:
        journal.finish("failed")
        raise
    return journal.run_id, moved


def trash_stats(root: Path) -> tuple[int, int]:
    trash = root.resolve() / ".sortmedia" / "trash"
    files = [path for path in trash.rglob("*") if path.is_file()] if trash.is_dir() else []
    return len(files), sum(path.stat().st_size for path in files)


def purge_trash(root: Path) -> tuple[int, int]:
    trash = root.resolve() / ".sortmedia" / "trash"
    if not trash.is_dir():
        return 0, 0
    files = [path for path in trash.rglob("*") if path.is_file()]
    total_size = sum(path.stat().st_size for path in files)
    for path in files:
        path.unlink()
    directories = sorted(
        (path for path in trash.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        directory.rmdir()
    trash.rmdir()
    return len(files), total_size
