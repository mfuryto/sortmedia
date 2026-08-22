from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import shutil
import uuid

from .config import JobConfig
from .core import (
    IMAGE_EXTENSIONS,
    MEDIA_EXTENSIONS,
    SIDECAR_EXTENSIONS,
    metadata_for_files,
    recorded_date,
)
from .history import RunJournal, file_sha256


DATE_PREFIXES = (
    re.compile(r"^\d{4}-\d{2}-\d{2}[ _-]+\d{2}[-:]\d{2}[-:]\d{2}[ _-]+"),
    re.compile(r"^\d{8}[ _-]+\d{6}[ _-]+"),
    re.compile(r"^\d{4}-\d{2}-\d{2}[ _-]+"),
    re.compile(r"^\d{8}[ _-]+"),
)


@dataclass(frozen=True)
class RenamePlan:
    source: Path
    destination: Path
    date_source: str


def clean_original_stem(stem: str) -> str:
    """Remove generated date prefixes while preserving the camera filename."""
    cleaned = stem
    while True:
        updated = cleaned
        for pattern in DATE_PREFIXES:
            updated = pattern.sub("", updated, count=1)
            if updated != cleaned:
                break
        if updated == cleaned:
            break
        cleaned = updated
    return cleaned.strip(" _-") or stem


def _render_base(path: Path, recorded: datetime, config: JobConfig) -> str:
    values = {
        "year": recorded.strftime("%Y"),
        "month": recorded.strftime("%m"),
        "day": recorded.strftime("%d"),
        "date": recorded.strftime("%Y-%m-%d"),
        "time": recorded.strftime("%H-%M-%S"),
        "original": clean_original_stem(path.stem),
        "extension": path.suffix.lower().lstrip("."),
    }
    rendered = config.filename.format(**values)
    if Path(rendered).name != rendered or rendered in {"", ".", ".."}:
        raise ValueError(f"Unsafe filename result: {rendered}")
    return rendered


def _sidecars(media: list[Path]) -> list[Path]:
    stems = {path.stem.casefold() for path in media}
    names = {path.name.casefold() for path in media}
    result: list[Path] = []
    for path in media[0].parent.iterdir():
        if not path.is_file() or path.suffix.lower() not in SIDECAR_EXTENSIONS:
            continue
        base = path.name[: -len(path.suffix)].casefold()
        if base in stems or base in names:
            result.append(path.resolve())
    return sorted(result)


def plan_filename_normalization(root: Path, config: JobConfig) -> tuple[list[RenamePlan], int]:
    root = root.resolve()
    media = [
        path.resolve()
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in MEDIA_EXTENSIONS
        and ".sortmedia" not in path.relative_to(root).parts
    ]
    metadata = metadata_for_files(media)
    groups: dict[tuple[Path, str], list[Path]] = {}
    for path in media:
        groups.setdefault((path.parent, path.stem.casefold()), []).append(path)

    plans: list[RenamePlan] = []
    considered: set[Path] = set()
    for paths in groups.values():
        primary = min(
            paths,
            key=lambda path: (0 if path.suffix.lower() in IMAGE_EXTENSIONS else 1, path.name.lower()),
        )
        recorded, date_source = recorded_date(
            primary, config.timezone, metadata.get(primary.resolve(), {})
        )
        target_base = _render_base(primary, recorded, config)
        companions = paths + _sidecars(paths)
        for source in companions:
            if source in considered:
                continue
            considered.add(source)
            destination = source.with_name(target_base + source.suffix.lower())
            if destination != source:
                plans.append(RenamePlan(source, destination, date_source))

    sources = {plan.source for plan in plans}
    destinations: set[Path] = set()
    for plan in plans:
        if plan.destination in destinations:
            raise ValueError(f"Multiple files would receive the same name: {plan.destination}")
        destinations.add(plan.destination)
        if plan.destination.exists() and plan.destination not in sources:
            raise ValueError(f"Rename would overwrite an existing file: {plan.destination}")
    return sorted(plans, key=lambda plan: plan.source), len(considered)


def apply_filename_normalization(
    root: Path, plans: list[RenamePlan]
) -> tuple[str, int]:
    root = root.resolve()
    journal = RunJournal(root / ".sortmedia", "filename-normalize")
    staged: list[tuple[RenamePlan, Path, str]] = []
    completed: list[tuple[RenamePlan, str]] = []
    try:
        for plan in plans:
            temporary = plan.source.with_name(
                f".sortmedia-rename-{uuid.uuid4().hex}{plan.source.suffix}"
            )
            digest = file_sha256(plan.source)
            shutil.move(plan.source, temporary)
            staged.append((plan, temporary, digest))
        for plan, temporary, digest in staged:
            shutil.move(temporary, plan.destination)
            completed.append((plan, digest))
            journal.add("move", plan.source, plan.destination, digest)
        journal.finish()
    except Exception:
        for plan, digest in reversed(completed):
            if plan.destination.exists() and not plan.source.exists():
                shutil.move(plan.destination, plan.source)
        for plan, temporary, digest in reversed(staged):
            if temporary.exists() and not plan.source.exists():
                shutil.move(temporary, plan.source)
        journal.finish("failed")
        raise
    return journal.run_id, len(completed)
