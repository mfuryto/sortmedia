"""Source directory exclusions with case-sensitive, segment-aware matching."""
from __future__ import annotations

from fnmatch import fnmatchcase
from functools import lru_cache
import os
from pathlib import Path
from typing import Callable, Iterable, Iterator


def validate_exclusions(values: object) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError("exclude_folders must be an array of strings")
    result = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("exclude_folders entries must be non-empty strings")
        pattern = value.strip().replace("\\", "/").rstrip("/")
        while pattern.startswith("./"):
            pattern = pattern[2:]
        parts = pattern.split("/")
        if (not pattern or pattern.startswith("/") or ":" in pattern
                or any(part in {"", ".", ".."} for part in parts)
                or any("**" in part and part != "**" for part in parts)):
            raise ValueError(f"Invalid exclude_folders pattern (use a source-relative path): {value}")
        result.append(pattern)
    return tuple(result)


def _path_matches(parts: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    @lru_cache(None)
    def match(i: int, j: int) -> bool:
        if j == len(pattern):
            return i == len(parts)
        if pattern[j] == "**":
            return match(i, j + 1) or (i < len(parts) and match(i + 1, j))
        return i < len(parts) and fnmatchcase(parts[i], pattern[j]) and match(i + 1, j + 1)
    return match(0, 0)


def matching_exclusion(relative: Path, patterns: Iterable[str]) -> str | None:
    parts = relative.parts
    for pattern in patterns:
        segments = tuple(pattern.split("/"))
        if len(segments) == 1:
            if any(fnmatchcase(part, pattern) for part in parts):
                return pattern
        elif any(_path_matches(parts[:end], segments) for end in range(1, len(parts) + 1)):
            return pattern
    return None


def iter_source_paths(
    root: Path, recursive: bool, exclude_folders: Iterable[str] = (),
    *, max_depth: int | None = None,
    on_excluded: Callable[[Path, str], None] | None = None,
) -> Iterator[Path]:
    """Prune excluded trees; fail on unreadable directories before applying a plan.

    Symlinks are skipped so aliases cannot bypass exclusions or escape the root.
    """
    root = root.resolve()
    patterns = validate_exclusions(tuple(exclude_folders))

    def scan_error(error: OSError) -> None:
        raise error

    for directory, names, filenames in os.walk(root, topdown=True, onerror=scan_error, followlinks=False):
        current = Path(directory)
        depth = len(current.relative_to(root).parts)
        kept = []
        for name in sorted(names):
            child = current / name
            if name == ".sortmedia" or child.is_symlink():
                continue
            pattern = matching_exclusion(child.relative_to(root), patterns)
            if pattern is not None:
                if on_excluded:
                    on_excluded(child, pattern)
            elif recursive and (max_depth is None or depth < max_depth):
                kept.append(name)
        names[:] = kept
        for filename in sorted(filenames):
            path = current / filename
            if not path.is_symlink():
                yield path
