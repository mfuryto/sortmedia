from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import os
import re

from .config import JobConfig
from .history import RunJournal
from .reporting import ConsoleReporter, Reporter


MEDIA_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".webp",
    ".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2",
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".mts", ".m2ts", ".3gp", ".webm",
}

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".webp",
    ".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2",
}
VIDEO_EXTENSIONS = MEDIA_EXTENSIONS - IMAGE_EXTENSIONS
SIDECAR_EXTENSIONS = {".xmp", ".aae", ".thm"}

DATE_FIELDS = (
    "DateTimeOriginal",
    "CreateDate",
    "MediaCreateDate",
    "TrackCreateDate",
    "QuickTime:CreateDate",
)

FILENAME_DATE_PATTERNS = (
    re.compile(r"(?<!\d)(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})[_-](?P<hour>\d{2})(?P<minute>\d{2})(?P<second>\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})[_ -](?P<hour>\d{2})[-:.](?P<minute>\d{2})[-:.](?P<second>\d{2})(?!\d)"),
)


@dataclass(frozen=True)
class PlannedFile:
    source: Path
    destination: Path
    date_source: str


def _group_priority(path: Path) -> tuple[int, str]:
    # Prefer an image as the date and naming source for RAW+JPEG and Live Photo
    # groups. The remaining files inherit the same date and base filename.
    return (0 if path.suffix.lower() in IMAGE_EXTENSIONS else 1, path.name.lower())


def _sidecars_for(media: list[Path]) -> list[Path]:
    if not media:
        return []
    directory = media[0].parent
    stems = {path.stem.casefold() for path in media}
    names = {path.name.casefold() for path in media}
    companions: list[Path] = []
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.lower() not in SIDECAR_EXTENSIONS:
            continue
        sidecar_base = path.name[: -len(path.suffix)].casefold()
        if sidecar_base in stems or sidecar_base in names:
            companions.append(path)
    return sorted(companions)


def media_files(config: JobConfig) -> Iterable[Path]:
    iterator = config.source.rglob("*") if config.recursive else config.source.glob("*")
    destination = config.destination.resolve()
    for path in iterator:
        try:
            relative_parts = path.relative_to(config.source).parts
        except ValueError:
            relative_parts = ()
        if ".sortmedia" in relative_parts:
            continue
        depth = max(0, len(relative_parts) - 1)
        if config.max_depth is not None and depth > config.max_depth:
            continue
        if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        if config.recursive and destination != config.source.resolve() and destination in path.resolve().parents:
            continue
        yield path


def _parse_metadata_date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace(":", "-", 2)
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    for candidate in (normalized, normalized.split("+")[0].strip()):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    return None


def metadata_for_files(paths: list[Path]) -> dict[Path, dict[str, object]]:
    if not paths:
        return {}
    try:
        result = subprocess.run(
            ["exiftool", "-json", "-api", "QuickTimeUTC=1", "-@", "-"],
            check=True,
            capture_output=True,
            text=True,
            input="\n".join(str(path.resolve()) for path in paths) + "\n",
        )
    except FileNotFoundError as error:
        raise RuntimeError("ExifTool is not installed or is not available in PATH") from error
    except subprocess.CalledProcessError as error:
        return {}
    try:
        values = json.loads(result.stdout)
        return {
            Path(str(value["SourceFile"])).resolve(): value
            for value in values
            if isinstance(value, dict) and "SourceFile" in value
        }
    except (json.JSONDecodeError, TypeError, KeyError):
        return {}


def metadata_for(path: Path) -> dict[str, object]:
    return metadata_for_files([path]).get(path.resolve(), {})


def _configured_timezone(name: str):
    if name == "local":
        return datetime.now().astimezone().tzinfo
    if name.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown timezone: {name}") from error


def recorded_date(
    path: Path,
    timezone_name: str = "local",
    metadata: dict[str, object] | None = None,
) -> tuple[datetime, str]:
    target_timezone = _configured_timezone(timezone_name)
    metadata = metadata if metadata is not None else metadata_for(path)
    for field in DATE_FIELDS:
        parsed = _parse_metadata_date(metadata.get(field))
        if parsed is not None:
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(target_timezone)
            return parsed, field

    for pattern in FILENAME_DATE_PATTERNS:
        match = pattern.search(path.stem)
        if match:
            try:
                return datetime(**{key: int(value) for key, value in match.groupdict().items()}), "filename"
            except ValueError:
                pass

    # ExifTool exposes the filesystem timestamp separately from embedded media
    # dates. It is deliberately considered only after all recording dates.
    file_created = _parse_metadata_date(metadata.get("FileCreateDate"))
    if file_created is not None:
        if file_created.tzinfo is not None:
            file_created = file_created.astimezone(target_timezone)
        return file_created, "FileCreateDate"

    stat = path.stat()
    birthtime = getattr(stat, "st_birthtime", None)
    if birthtime is not None:
        return datetime.fromtimestamp(birthtime), "filesystem-created"
    return datetime.fromtimestamp(stat.st_mtime), "filesystem-modified"


def _available_destination(path: Path, duplicate_mode: str) -> Path | None:
    if not path.exists():
        return path
    if duplicate_mode == "skip":
        return None
    if duplicate_mode == "hash":
        # Content comparison is performed immediately before the operation.
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def plan_file(
    path: Path,
    config: JobConfig,
    metadata: dict[str, object] | None = None,
) -> PlannedFile | None:
    recorded, source = recorded_date(path, config.timezone, metadata)
    values = {
        "year": recorded.strftime("%Y"),
        "month": recorded.strftime("%m"),
        "day": recorded.strftime("%d"),
        "date": recorded.strftime("%Y-%m-%d"),
        "time": recorded.strftime("%H-%M-%S"),
        "original": path.stem,
        "extension": path.suffix.lower().lstrip("."),
    }
    folder = config.layout.format(**values)
    filename = config.filename.format(**values) + path.suffix.lower()
    folder_path = Path(folder)
    if folder_path.is_absolute() or ".." in folder_path.parts:
        raise ValueError(f"Unsafe directory layout result: {folder}")
    if Path(filename).name != filename or filename in {".", ".."}:
        raise ValueError(f"Unsafe filename result: {filename}")
    root = config.destination.resolve()
    candidate = (root / folder_path / filename).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"Destination escapes configured directory: {candidate}")
    destination = _available_destination(candidate, config.duplicates)
    if destination is None:
        return None
    return PlannedFile(path, destination, source)


def plan_group(
    paths: list[Path],
    config: JobConfig,
    metadata_cache: dict[Path, dict[str, object]] | None = None,
) -> list[PlannedFile]:
    primary = min(paths, key=_group_priority)
    metadata = metadata_cache.get(primary.resolve()) if metadata_cache is not None else None
    primary_plan = plan_file(primary, config, metadata)
    if primary_plan is None:
        return []

    plans = [primary_plan]
    base_destination = primary_plan.destination.with_suffix("")
    companions = [path for path in paths if path != primary] + _sidecars_for(paths)
    for companion in companions:
        destination = base_destination.with_suffix(companion.suffix.lower())
        if destination.resolve() == companion.resolve():
            continue
        available = _available_destination(destination, config.duplicates)
        if available is not None:
            plans.append(PlannedFile(companion, available, primary_plan.date_source))
    return plans


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ContentIndex:
    def __init__(self, root: Path, excluded: set[Path], relevant_sizes: set[int]) -> None:
        self._by_size: dict[int, list[Path]] = {}
        self._digests: dict[Path, str] = {}
        if not root.is_dir():
            return
        supported = MEDIA_EXTENSIONS | SIDECAR_EXTENSIONS
        for path in root.rglob("*"):
            resolved = path.resolve()
            if path.is_file() and path.suffix.lower() in supported and resolved not in excluded and path.stat().st_size in relevant_sizes:
                self._by_size.setdefault(path.stat().st_size, []).append(path)
        candidates = [path for paths in self._by_size.values() for path in paths]
        if candidates:
            workers = min(32, (os.cpu_count() or 1) + 4)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                self._digests.update(zip(candidates, executor.map(_sha256, candidates)))

    def find(self, path: Path) -> tuple[str, Path | None]:
        digest = _sha256(path)
        for candidate in self._by_size.get(path.stat().st_size, []):
            candidate_digest = self._digests.get(candidate)
            if candidate_digest is None:
                candidate_digest = _sha256(candidate)
                self._digests[candidate] = candidate_digest
            if candidate_digest == digest:
                return digest, candidate
        return digest, None

    def add(self, path: Path, digest: str, size: int) -> None:
        self._by_size.setdefault(size, []).append(path)
        self._digests[path] = digest


def _image_fingerprint(path: Path) -> tuple[int, int, tuple[int, int, int]] | None:
    try:
        from PIL import Image
        with Image.open(path) as image:
            rgb = image.convert("RGB").resize((8, 8))
            gray_pixels = list(rgb.convert("L").tobytes())
            diff_pixels = list(image.convert("L").resize((9, 8)).tobytes())
            raw_rgb = rgb.tobytes()
            rgb_pixels = list(zip(raw_rgb[0::3], raw_rgb[1::3], raw_rgb[2::3]))
        difference_hash = 0
        for row in range(8):
            for column in range(8):
                difference_hash = (difference_hash << 1) | (
                    diff_pixels[row * 9 + column] > diff_pixels[row * 9 + column + 1]
                )
        average = sum(gray_pixels) / len(gray_pixels)
        average_hash = 0
        for pixel in gray_pixels:
            average_hash = (average_hash << 1) | (pixel >= average)
        color = tuple(sum(pixel[channel] for pixel in rgb_pixels) // len(rgb_pixels) for channel in range(3))
        return difference_hash, average_hash, color
    except Exception:
        return None


class PerceptualIndex:
    def __init__(self, root: Path, excluded: set[Path]) -> None:
        paths = [] if not root.is_dir() else [
            path for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS and path.resolve() not in excluded
        ]
        workers = min(32, (os.cpu_count() or 1) + 4)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            hashes = list(executor.map(_image_fingerprint, paths))
        self.items = [(path, value) for path, value in zip(paths, hashes) if value is not None]

    def find(self, path: Path, threshold: int = 5) -> Path | None:
        value = _image_fingerprint(path)
        if value is None:
            return None
        difference_hash, average_hash, color = value
        for candidate, other in self.items:
            other_difference, other_average, other_color = other
            color_distance = sum(abs(left - right) for left, right in zip(color, other_color))
            if (
                (difference_hash ^ other_difference).bit_count() <= threshold
                and (average_hash ^ other_average).bit_count() <= threshold
                and color_distance <= 60
            ):
                return candidate
        return None

    def add(self, path: Path) -> None:
        value = _image_fingerprint(path)
        if value is not None:
            self.items.append((path, value))


def _rollback_group(
    completed: list[tuple[PlannedFile, Path, str]],
    operation: str,
) -> None:
    for planned, destination, digest in reversed(completed):
        if not destination.exists() or _sha256(destination) != digest:
            continue
        if operation == "copy":
            destination.unlink()
        elif operation == "move" and not planned.source.exists():
            planned.source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(destination, planned.source)


def run_job(
    config: JobConfig,
    state_root: Path | None = None,
    reporter: Reporter | None = None,
) -> tuple[int, int]:
    if not config.source.is_dir():
        raise ValueError(f"Source directory does not exist: {config.source}")
    processed = skipped = 0
    reporter = reporter or ConsoleReporter()
    groups: dict[tuple[Path, str], list[Path]] = {}
    sources = list(media_files(config))
    metadata_cache = metadata_for_files(sources)
    for source in sources:
        groups.setdefault((source.parent, source.stem.casefold()), []).append(source)
    input_paths = sources + [
        sidecar
        for paths in groups.values()
        for sidecar in _sidecars_for(paths)
    ]
    excluded = {path.resolve() for path in input_paths}
    relevant_sizes = {path.stat().st_size for path in input_paths}
    content_index = ContentIndex(config.destination, excluded, relevant_sizes) if config.duplicates == "hash" else None
    perceptual_index = PerceptualIndex(config.destination, excluded) if config.perceptual_duplicates else None
    journal = None
    if config.operation in {"copy", "move"} and state_root is not None:
        journal = RunJournal(state_root, config.operation)

    try:
        total_groups = len(groups)
        for group_number, paths in enumerate(groups.values(), start=1):
            reporter.progress(group_number, total_groups)
            has_image = any(path.suffix.lower() in IMAGE_EXTENSIONS for path in paths)
            live_videos = [
                path for path in paths
                if has_image and path.suffix.lower() in VIDEO_EXTENSIONS
            ]
            planned_paths = (
                [path for path in paths if path not in live_videos]
                if config.live_photo_videos in {"leave", "trash"}
                else paths
            )
            plans = plan_group(planned_paths, config, metadata_cache)
            if not plans:
                skipped += len(paths)
                continue
            completed_group: list[tuple[PlannedFile, Path, str]] = []
            try:
                for planned in plans:
                    destination = planned.destination
                    digest = _sha256(planned.source)
                    source_size = planned.source.stat().st_size
                    if content_index is not None:
                        digest, duplicate = content_index.find(planned.source)
                        if duplicate is not None:
                            reporter.event("duplicate", method="sha256", source=str(planned.source), existing=str(duplicate))
                            skipped += 1
                            continue
                        if destination.exists():
                            destination = _available_destination(destination, "rename")
                            if destination is None:
                                skipped += 1
                                continue
                    if perceptual_index is not None and planned.source.suffix.lower() in IMAGE_EXTENSIONS:
                        similar = perceptual_index.find(planned.source)
                        if similar is not None:
                            reporter.event("duplicate", method="perceptual", source=str(planned.source), existing=str(similar))
                            skipped += 1
                            continue
                    reporter.event("file", date_source=planned.date_source, source=str(planned.source), destination=str(destination))
                    if config.operation != "preview":
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        if config.operation == "move":
                            shutil.move(planned.source, destination)
                        else:
                            shutil.copy2(planned.source, destination)
                        completed_group.append((planned, destination, digest))
                    if content_index is not None:
                        content_index.add(destination, digest, source_size)
                    if perceptual_index is not None and config.operation != "preview" and destination.suffix.lower() in IMAGE_EXTENSIONS:
                        perceptual_index.add(destination)
                    processed += 1
            except Exception:
                _rollback_group(completed_group, config.operation)
                raise
            if journal is not None:
                for planned, destination, digest in completed_group:
                    journal.add(config.operation, planned.source, destination, digest)
            for live_video in live_videos if config.live_photo_videos in {"leave", "trash"} else []:
                if config.live_photo_videos == "leave" or config.operation == "preview":
                    reporter.event("live_photo_video", action=config.live_photo_videos, source=str(live_video))
                    skipped += 1
                    continue
                if state_root is None or journal is None:
                    raise ValueError("Live Photo trash handling requires run history")
                trash_destination = state_root / "trash" / journal.run_id / live_video.name
                trash_destination.parent.mkdir(parents=True, exist_ok=True)
                digest = _sha256(live_video)
                shutil.move(live_video, trash_destination)
                journal.add("move", live_video, trash_destination, digest)
                reporter.event("live_photo_video", action="trash", source=str(live_video), destination=str(trash_destination))
                processed += 1
        if journal is not None:
            journal.finish()
        reporter.finish()
    except Exception:
        if journal is not None:
            journal.finish("failed")
        raise
    return processed, skipped
