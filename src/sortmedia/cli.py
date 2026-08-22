from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import re
import sys
from typing import Callable

from .config import JobConfig, load_config
from .cleanup import format_size, find_live_photo_videos, purge_trash, trash_live_photo_videos, trash_stats
from .core import run_job
from .history import list_runs, undo_run
from .reporting import ConsoleReporter, JsonReporter, QuietReporter


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="sortmedia",
        description=(
            "Sort photos and videos by recording date from EXIF and video "
            "metadata. Each config file defines one independent job."
        ),
        epilog="""examples:
  cd /media/import && sortmedia -r
  sortmedia -r --move --recursive
  sortmedia -f /media/camera -d /photos --copy
  sortmedia -c /media/import/.sortmedia.toml
  sortmedia -c ~/photos/.sortmedia.toml -c /media/camera/.import.toml

config:
  The config must be a hidden TOML file. Relative paths are resolved from
  the config file's directory. If 'folder' is omitted, that directory is used.

  folder = "incoming"
  destination = "."
  operation = "preview"  # preview, copy, or move
  layout = "{year}/{month}/{day}"
  filename = "{date}_{time}_{original}"

safety:
  Use operation = "preview" before copy or move. Existing files are never
  overwritten.

More documentation: man sortmedia""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    result.add_argument(
        "-c", "--config",
        action="append",
        type=Path,
        metavar="FILE",
        help="hidden TOML config; repeat to run multiple jobs in order",
    )
    result.add_argument("--version", action="version", version="%(prog)s 0.1.2")
    result.add_argument(
        "-r", "--run-local",
        action="store_true",
        help="run .sortmedia.toml from the current working directory",
    )
    result.add_argument("-f", "--folder", type=Path, help="override the source directory")
    result.add_argument("-d", "--destination", type=Path, help="override the destination directory")
    result.add_argument("-R", "--recursive", dest="recursive", action="store_true", default=None, help="scan source subdirectories")
    result.add_argument("--no-recursive", dest="recursive", action="store_false", help="do not scan source subdirectories")
    operation = result.add_mutually_exclusive_group()
    operation.add_argument("--preview", dest="operation", action="store_const", const="preview", help="show planned changes only")
    operation.add_argument("--copy", dest="operation", action="store_const", const="copy", help="copy files")
    operation.add_argument("--move", dest="operation", action="store_const", const="move", help="move files")
    result.add_argument("--layout", help="override the directory layout template")
    result.add_argument("--filename", help="override the filename template")
    result.add_argument("--duplicates", choices=("hash", "rename", "skip"), help="override duplicate handling")
    result.add_argument("--perceptual", dest="perceptual_duplicates", action="store_true", default=None, help="detect visually similar images")
    result.add_argument("--max-depth", type=int, help="maximum recursive depth; 0 scans only the source directory")
    result.add_argument("--live-photo-videos", choices=("include", "leave", "trash"), help="override Live Photo short-video handling")
    result.add_argument("--history", action="store_true", help="show runs recorded in the current directory")
    result.add_argument("--undo", nargs="?", const="latest", metavar="RUN_ID", help="undo the latest or selected run")
    output = result.add_mutually_exclusive_group()
    output.add_argument("-q", "--quiet", action="store_true", help="suppress normal output")
    output.add_argument("--json", action="store_true", help="emit newline-delimited JSON events")
    return result


def _prompt(
    label: str,
    default: str,
    input_fn: Callable[[str], str] = input,
) -> str:
    value = input_fn(f"{label} [{default}]: ").strip()
    return value or default


def _path_prompt(
    label: str,
    displayed_default: Path,
    stored_default: str,
    input_fn: Callable[[str], str],
) -> str:
    value = input_fn(f"{label} [{displayed_default}]: ").strip()
    if not value or Path(value).expanduser().resolve() == displayed_default:
        return stored_default
    return value


def _layout_prompt(
    current: str,
    input_fn: Callable[[str], str],
) -> str:
    choices = (
        ("{year}", "Year only", "2026/"),
        ("{year}/{month}", "Year and month", "2026/08/"),
        ("{year}/{month}/{day}", "Year, month, and day", "2026/08/22/"),
    )
    default = next(
        (str(number) for number, (template, _, _) in enumerate(choices, 1) if template == current),
        "c",
    )
    print("\nDirectory layout:")
    for number, (template, description, example) in enumerate(choices, 1):
        marker = " (current)" if template == current else ""
        print(f"{number}) {description}: {template}  ->  {example}{marker}")
    print("c) Custom template")
    print("   Fields: {year}, {month}, {day}, {date}, {time}, {original}, {extension}")
    selection = input_fn(f"Select layout [{default}]: ").strip().lower() or default
    if selection == "c":
        layout = _prompt("Custom directory layout", current, input_fn)
    else:
        try:
            layout = choices[int(selection) - 1][0]
        except (ValueError, IndexError):
            raise ValueError("Invalid directory layout selection") from None
    try:
        layout.format(
            year="2026", month="08", day="22", date="2026-08-22",
            time="12-00-00", original="example", extension="jpg",
        )
    except (KeyError, ValueError) as error:
        raise ValueError(f"Invalid directory layout: {error}") from error
    return layout


def _live_photo_prompt(current: str, input_fn: Callable[[str], str]) -> str:
    choices = (
        ("include", "Include the short video with the photo"),
        ("leave", "Leave the short video in the source directory"),
        ("trash", "Move the short video to recoverable .sortmedia/trash"),
    )
    default = next(str(number) for number, (value, _) in enumerate(choices, 1) if value == current)
    print("\nLive Photo short videos:")
    for number, (value, description) in enumerate(choices, 1):
        marker = " (current)" if value == current else ""
        print(f"{number}) {description}{marker}")
    selection = input_fn(f"Select handling [{default}]: ").strip() or default
    try:
        return choices[int(selection) - 1][0]
    except (ValueError, IndexError):
        raise ValueError("Invalid Live Photo video selection") from None


def create_config_interactive(
    directory: Path,
    input_fn: Callable[[str], str] = input,
) -> Path:
    config_path = directory.resolve() / ".sortmedia.toml"
    if config_path.exists():
        raise ValueError(f"Config already exists: {config_path}")

    print(f"\nCreate {config_path}")
    source = _path_prompt("Source directory", directory.resolve(), ".", input_fn)
    destination = _path_prompt(
        "Destination directory",
        directory.resolve(),
        ".",
        input_fn,
    )
    recursive = _prompt("Scan subdirectories (yes/no)", "no", input_fn).lower()
    max_depth_text = _prompt("Maximum scan depth", "unlimited", input_fn).lower()
    operation = _prompt("Operation (preview/copy/move)", "preview", input_fn).lower()
    layout = _layout_prompt("{year}/{month}/{day}", input_fn)
    filename = _prompt("Filename template", "{date}_{time}_{original}", input_fn)
    duplicates = _prompt("Duplicates (hash/rename/skip)", "hash", input_fn).lower()
    perceptual = _prompt("Detect visually similar images (yes/no)", "no", input_fn).lower()
    live_photo_videos = _live_photo_prompt("include", input_fn)

    if recursive not in {"yes", "no", "y", "n"}:
        raise ValueError("Scan subdirectories must be yes or no")
    if max_depth_text == "unlimited":
        max_depth = None
    else:
        try:
            max_depth = int(max_depth_text)
        except ValueError:
            raise ValueError("Maximum scan depth must be unlimited or a non-negative integer") from None
        if max_depth < 0:
            raise ValueError("Maximum scan depth must be non-negative")
    if operation not in {"preview", "copy", "move"}:
        raise ValueError("Operation must be preview, copy, or move")
    if duplicates not in {"hash", "rename", "skip"}:
        raise ValueError("Duplicates must be hash, rename, or skip")
    if perceptual not in {"yes", "no", "y", "n"}:
        raise ValueError("Perceptual duplicate detection must be yes or no")

    content = "\n".join(
        (
            "# Paths are relative to this config file.",
            f"folder = {json.dumps(source)}",
            f"destination = {json.dumps(destination)}",
            f"recursive = {'true' if recursive in {'yes', 'y'} else 'false'}",
            *(() if max_depth is None else (f"max_depth = {max_depth}",)),
            f"operation = {json.dumps(operation)}",
            f"layout = {json.dumps(layout)}",
            f"filename = {json.dumps(filename)}",
            f"duplicates = {json.dumps(duplicates)}",
            f"perceptual_duplicates = {'true' if perceptual in {'yes', 'y'} else 'false'}",
            f"live_photo_videos = {json.dumps(live_photo_videos)}",
            "",
        )
    )
    config_path.write_text(content, encoding="utf-8")
    print(f"Created: {config_path}")
    return config_path


def update_config_interactive(
    config_path: Path,
    input_fn: Callable[[str], str] = input,
) -> Path:
    config_path = config_path.expanduser().resolve()
    current = load_config(config_path)
    operation = _prompt(
        "Operation (preview/copy/move)",
        current.operation,
        input_fn,
    ).lower()
    if operation not in {"preview", "copy", "move"}:
        raise ValueError("Operation must be preview, copy, or move")
    layout = _layout_prompt(current.layout, input_fn)
    perceptual = _prompt(
        "Detect visually similar images (yes/no)",
        "yes" if current.perceptual_duplicates else "no",
        input_fn,
    ).lower()
    if perceptual not in {"yes", "no", "y", "n"}:
        raise ValueError("Perceptual duplicate detection must be yes or no")
    live_photo_videos = _live_photo_prompt(current.live_photo_videos, input_fn)

    content = config_path.read_text(encoding="utf-8")
    updates = {
        "operation": json.dumps(operation),
        "layout": json.dumps(layout),
        "perceptual_duplicates": "true" if perceptual in {"yes", "y"} else "false",
        "live_photo_videos": json.dumps(live_photo_videos),
    }
    for key, value in updates.items():
        replacement = f"{key} = {value}"
        pattern = rf"^\s*{re.escape(key)}\s*=.*$"
        if re.search(pattern, content, flags=re.MULTILINE):
            content = re.sub(
                pattern,
                replacement,
                content,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            content = content.rstrip() + f"\n{replacement}\n"
    config_path.write_text(content, encoding="utf-8")
    print(f"Updated: {config_path}")
    return config_path


def interactive_menu(
    directory: Path | None = None,
    input_fn: Callable[[str], str] = input,
) -> int:
    current = (directory or Path.cwd()).resolve()
    local_config = current / ".sortmedia.toml"

    while True:
        print(f"\nSortmedia — {current}")
        if local_config.exists():
            print("1) Run the local config")
            print("2) Update the local config")
            print("3) Clean up existing Live Photo short videos")
            print("4) Show the local config path")
        else:
            print("1) Create .sortmedia.toml in this directory")
            print("2) Clean up existing Live Photo short videos")
        print("5) Permanently clean up .sortmedia/trash")
        print("q) Quit")
        choice = input_fn("Select an option: ").strip().lower()

        if choice in {"q", "quit", "exit"}:
            return 0
        if choice == "1" and not local_config.exists():
            try:
                create_config_interactive(current, input_fn)
            except (OSError, ValueError) as error:
                print(f"Error: {error}", file=sys.stderr)
                return 1
            print("Run 'sortmedia' again to preview this job.")
            return 0
        if choice == "1" and local_config.exists():
            try:
                processed, skipped = run_job(load_config(local_config), current / ".sortmedia")
                print(f"Done: {processed} processed, {skipped} skipped")
                return 0
            except (OSError, RuntimeError, ValueError, KeyError) as error:
                print(f"Error: {error}", file=sys.stderr)
                return 1
        if choice == "2" and local_config.exists():
            try:
                update_config_interactive(local_config, input_fn)
            except (OSError, ValueError) as error:
                print(f"Error: {error}", file=sys.stderr)
                return 1
            print("Run it with: sortmedia -r")
            return 0
        cleanup_choice = (choice == "3" and local_config.exists()) or (choice == "2" and not local_config.exists())
        if cleanup_choice:
            videos = find_live_photo_videos(current)
            if not videos:
                print("No metadata-confirmed Live Photo short videos found.")
                return 0
            total_size = sum(candidate.size for candidate in videos)
            print(f"\nFound {len(videos)} metadata-confirmed Live Photo video(s), {format_size(total_size)} total:")
            for candidate in videos:
                duration = f", {candidate.duration}" if candidate.duration else ""
                print(f"\n  Video: {candidate.video.relative_to(current)} ({format_size(candidate.size)}{duration})")
                print(f"  Photo: {candidate.image.relative_to(current)}")
                print(f"  Proof: matching Apple ContentIdentifier {candidate.content_identifier}")
            print("\nVideos matched only by filename are excluded. Files are moved to recoverable trash, not deleted.")
            confirm = input_fn("Type MOVE to move these confirmed videos to .sortmedia/trash: ").strip()
            if confirm != "MOVE":
                print("No files changed.")
                return 0
            try:
                run_id, moved = trash_live_photo_videos(
                    current, [candidate.video for candidate in videos]
                )
            except (OSError, ValueError) as error:
                print(f"Error: {error}", file=sys.stderr)
                return 1
            print(f"Moved {moved} video(s) to trash. Undo run: {run_id}")
            return 0
        if choice == "4" and local_config.exists():
            print(local_config)
            continue
        if choice == "5":
            count, size = trash_stats(current)
            if count == 0:
                print("Trash is empty.")
                return 0
            print(f"\nTrash contains {count} file(s), {format_size(size)}.")
            print("This is permanent. Undo cannot restore these files after deletion.")
            confirm = input_fn("Type DELETE to permanently clean trash: ").strip()
            if confirm != "DELETE":
                print("No files changed.")
                return 0
            try:
                deleted, deleted_size = purge_trash(current)
            except OSError as error:
                print(f"Error: {error}", file=sys.stderr)
                return 1
            print(f"Permanently deleted {deleted} file(s), {format_size(deleted_size)}.")
            return 0
        print("Invalid selection.")


def _apply_overrides(config: JobConfig, args: argparse.Namespace) -> JobConfig:
    values: dict[str, object] = {}
    if args.folder is not None:
        values["source"] = args.folder.expanduser().resolve()
    if args.destination is not None:
        values["destination"] = args.destination.expanduser().resolve()
    for name in ("recursive", "operation", "layout", "filename", "duplicates", "perceptual_duplicates", "max_depth", "live_photo_videos"):
        value = getattr(args, name)
        if value is not None:
            values[name] = value
    return replace(config, **values)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    state_root = Path.cwd() / ".sortmedia"
    if args.history:
        runs = list_runs(state_root)
        if not runs:
            print("No recorded runs.")
            return 0
        for run in runs:
            entries = run.get("entries", [])
            print(f"{run.get('run_id')}  {run.get('status')}  {run.get('operation')}  {len(entries)} files")
        return 0
    if args.undo is not None:
        try:
            run_id, count = undo_run(state_root, args.undo)
        except (OSError, ValueError, KeyError) as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
        print(f"Undone: {run_id} ({count} files)")
        return 0
    if args.run_local and args.config:
        parser().error("--run-local cannot be combined with --config")
    if args.run_local:
        args.config = [Path.cwd() / ".sortmedia.toml"]
    standalone = None
    if not args.config and args.folder is not None:
        source = args.folder.expanduser().resolve()
        standalone = JobConfig(source=source, destination=source)
    override_requested = any(
        value is not None
        for value in (
            args.destination, args.recursive, args.operation,
            args.layout, args.filename, args.duplicates, args.perceptual_duplicates, args.max_depth, args.live_photo_videos,
        )
    )
    if not args.config and standalone is None and override_requested:
        parser().error("override flags require --config, --run-local, or --folder")
    if not args.config and standalone is None:
        if not sys.stdin.isatty():
            parser().print_help(sys.stderr)
            print("\nError: --config is required when not running interactively.", file=sys.stderr)
            return 2
        return interactive_menu()
    total = skipped = 0
    reporter = JsonReporter() if args.json else QuietReporter() if args.quiet else ConsoleReporter()
    try:
        jobs: list[tuple[Path | None, JobConfig]] = []
        if standalone is not None:
            jobs.append((None, standalone))
        for config_path in args.config or []:
            jobs.append((config_path, load_config(config_path)))
        for config_path, base_config in jobs:
            config = _apply_overrides(base_config, args)
            if config_path is not None and not args.quiet and not args.json:
                print(f"Config: {config_path.expanduser().resolve()}")
            job_state = (
                config_path.expanduser().resolve().parent / ".sortmedia"
                if config_path is not None
                else config.source / ".sortmedia"
            )
            processed, job_skipped = run_job(config, job_state, reporter)
            total += processed
            skipped += job_skipped
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        if args.json:
            reporter.event("error", message=str(error))
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 1
    if args.json:
        reporter.event("summary", processed=total, skipped=skipped)
    elif not args.quiet:
        print(f"Done: {total} processed, {skipped} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
