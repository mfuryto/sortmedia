from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


@dataclass(frozen=True)
class JobConfig:
    source: Path
    destination: Path
    layout: str = "{year}/{month}/{day}"
    filename: str = "{date}_{time}_{original}"
    operation: str = "preview"
    recursive: bool = False
    unknown_date: str = "unknown-date"
    duplicates: str = "hash"
    timezone: str = "local"
    perceptual_duplicates: bool = False
    max_depth: int | None = None
    live_photo_videos: str = "include"


def _relative_to_config(value: str, config_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (config_dir / path).resolve()


def load_config(path: Path) -> JobConfig:
    path = path.expanduser().resolve()
    if not path.name.startswith(".") or path.suffix.lower() != ".toml":
        raise ValueError(
            f"Config must be a hidden TOML file, for example .sortmedia.toml: {path}"
        )
    with path.open("rb") as stream:
        raw = tomllib.load(stream)

    base = path.parent
    source = _relative_to_config(str(raw.get("folder", ".")), base)
    destination = _relative_to_config(str(raw.get("destination", ".")), base)
    operation = str(raw.get("operation", "preview"))
    if operation not in {"preview", "move", "copy"}:
        raise ValueError(f"Invalid operation in {path}: {operation}")

    duplicates = str(raw.get("duplicates", "hash"))
    if duplicates not in {"hash", "rename", "skip"}:
        raise ValueError(f"Invalid duplicates value in {path}: {duplicates}")

    max_depth = raw.get("max_depth")
    if max_depth is not None and (not isinstance(max_depth, int) or max_depth < 0):
        raise ValueError(f"max_depth must be a non-negative integer in {path}")
    live_photo_videos = str(raw.get("live_photo_videos", "include"))
    if live_photo_videos not in {"include", "leave", "trash"}:
        raise ValueError(f"Invalid live_photo_videos value in {path}: {live_photo_videos}")
    return JobConfig(
        source=source,
        destination=destination,
        layout=str(raw.get("layout", "{year}/{month}/{day}")),
        filename=str(raw.get("filename", "{date}_{time}_{original}")),
        operation=operation,
        recursive=bool(raw.get("recursive", False)),
        unknown_date=str(raw.get("unknown_date", "unknown-date")),
        duplicates=duplicates,
        timezone=str(raw.get("timezone", "local")),
        perceptual_duplicates=bool(raw.get("perceptual_duplicates", False)),
        max_depth=max_depth,
        live_photo_videos=live_photo_videos,
    )
