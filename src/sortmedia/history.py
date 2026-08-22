from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import uuid


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RunJournal:
    def __init__(self, state_root: Path, operation: str) -> None:
        self.state_root = state_root
        self.history_dir = state_root / "history"
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        self.path = self.history_dir / f"{self.run_id}.json"
        self.data: dict[str, object] = {
            "run_id": self.run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "status": "running",
            "entries": [],
        }
        self._save()

    def _save(self) -> None:
        self.history_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def add(self, operation: str, source: Path, destination: Path, digest: str) -> None:
        entries = self.data["entries"]
        assert isinstance(entries, list)
        entries.append({
            "operation": operation,
            "source": str(source.resolve()),
            "destination": str(destination.resolve()),
            "sha256": digest,
        })
        self._save()

    def finish(self, status: str = "complete") -> None:
        self.data["status"] = status
        self.data["finished_at"] = datetime.now(timezone.utc).isoformat()
        self._save()


def list_runs(state_root: Path) -> list[dict[str, object]]:
    history_dir = state_root / "history"
    runs = []
    for path in sorted(history_dir.glob("*.json"), reverse=True):
        try:
            runs.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return runs


def undo_run(state_root: Path, run_id: str = "latest") -> tuple[str, int]:
    runs = [run for run in list_runs(state_root) if run.get("status") == "complete"]
    if run_id == "latest":
        run = next((item for item in runs if not item.get("undone_at")), None)
    else:
        run = next((item for item in runs if item.get("run_id") == run_id), None)
    if run is None:
        raise ValueError(f"No completed run found: {run_id}")
    if run.get("undone_at"):
        raise ValueError(f"Run has already been undone: {run['run_id']}")

    entries = run.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("Invalid history file")
    undone = 0
    for entry in reversed(entries):
        source = Path(str(entry["source"]))
        destination = Path(str(entry["destination"]))
        digest = str(entry["sha256"])
        if not destination.is_file():
            raise ValueError(f"Cannot undo; destination is missing: {destination}")
        if file_sha256(destination) != digest:
            raise ValueError(f"Cannot undo; destination content changed: {destination}")
        if entry["operation"] == "copy":
            destination.unlink()
        elif entry["operation"] == "move":
            if source.exists():
                raise ValueError(f"Cannot undo; original path is occupied: {source}")
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(destination, source)
        else:
            raise ValueError(f"Unsupported history operation: {entry['operation']}")
        undone += 1

    run["undone_at"] = datetime.now(timezone.utc).isoformat()
    path = state_root / "history" / f"{run['run_id']}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return str(run["run_id"]), undone

