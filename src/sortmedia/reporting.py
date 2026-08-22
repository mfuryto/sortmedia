from __future__ import annotations

import json
import sys


class Reporter:
    def progress(self, current: int, total: int) -> None:
        pass

    def event(self, kind: str, **values: object) -> None:
        pass

    def finish(self) -> None:
        pass


class QuietReporter(Reporter):
    pass


class JsonReporter(Reporter):
    def progress(self, current: int, total: int) -> None:
        self.event("progress", current=current, total=total)

    def event(self, kind: str, **values: object) -> None:
        print(json.dumps({"event": kind, **values}, separators=(",", ":")))


class ConsoleReporter(Reporter):
    def __init__(self) -> None:
        self._progress_active = False

    def progress(self, current: int, total: int) -> None:
        width = 30
        filled = width if total == 0 else int(width * current / total)
        bar = "#" * filled + "-" * (width - filled)
        print(f"\r[{bar}] {current}/{total}", end="", file=sys.stderr, flush=True)
        self._progress_active = True

    def event(self, kind: str, **values: object) -> None:
        if self._progress_active:
            print(file=sys.stderr)
            self._progress_active = False
        if kind == "duplicate":
            print(f"[duplicate:{values['method']}] {values['source']} ~= {values['existing']} (skipped)")
        elif kind == "file":
            print(f"[{values['date_source']}] {values['source']} -> {values['destination']}")
        elif kind == "live_photo_video":
            if values["action"] == "trash":
                print(f"[live-photo:trash] {values['source']} -> {values['destination']}")
            else:
                print(f"[live-photo:{values['action']}] {values['source']}")

    def finish(self) -> None:
        if self._progress_active:
            print(file=sys.stderr)
            self._progress_active = False
