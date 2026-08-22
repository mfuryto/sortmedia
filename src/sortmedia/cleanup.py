from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from .core import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, content_identifier, metadata_for_files
from .history import RunJournal, file_sha256


def format_size(size: int) -> str:
    value = float(size)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if value < 1000 or unit == units[-1]:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{size} B"


@dataclass(frozen=True)
class LivePhotoCandidate:
    image: Path
    video: Path
    size: int
    duration: str | None
    content_identifier: str


def _duration(metadata: dict[str, object]) -> str | None:
    for key, value in metadata.items():
        if key.rsplit(":", 1)[-1] == "Duration" and value not in (None, ""):
            return str(value)
    return None


def find_live_photo_videos(root: Path) -> list[LivePhotoCandidate]:
    root = root.resolve()
    media: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if ".sortmedia" in relative.parts or not path.is_file():
            continue
        if path.suffix.lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            media.append(path.resolve())

    metadata = metadata_for_files(media)
    images_by_id: dict[tuple[Path, str], Path] = {}
    for image in media:
        if image.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        identifier = content_identifier(metadata.get(image, {}))
        if identifier:
            images_by_id[(image.parent, identifier)] = image

    matches: list[LivePhotoCandidate] = []
    for video in media:
        if video.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        video_metadata = metadata.get(video, {})
        identifier = content_identifier(video_metadata)
        image = images_by_id.get((video.parent, identifier)) if identifier else None
        if image is None or identifier is None:
            continue
        matches.append(
            LivePhotoCandidate(
                image=image,
                video=video,
                size=video.stat().st_size,
                duration=_duration(video_metadata),
                content_identifier=identifier,
            )
        )
    return sorted(matches, key=lambda candidate: candidate.video)


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
