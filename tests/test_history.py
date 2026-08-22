from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sortmedia.config import JobConfig
from sortmedia.core import run_job
from sortmedia.history import list_runs, undo_run


class HistoryTests(unittest.TestCase):
    def test_copy_run_is_recorded_and_can_be_undone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "incoming"
            destination = root / "archive"
            state = root / ".sortmedia"
            source.mkdir()
            original = source / "photo.jpg"
            original.write_bytes(b"photo")
            config = JobConfig(source=source, destination=destination, operation="copy")

            with patch("sortmedia.core.recorded_date", return_value=(datetime(2026, 8, 22, 12, 30), "test")):
                run_job(config, state)

            runs = list_runs(state)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["status"], "complete")
            run_id, count = undo_run(state)
            self.assertEqual(run_id, runs[0]["run_id"])
            self.assertEqual(count, 1)
            self.assertTrue(original.exists())
            self.assertFalse((destination / "2026" / "08" / "22" / "2026-08-22_12-30-00_photo.jpg").exists())

    def test_undo_refuses_modified_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "incoming"
            destination = root / "archive"
            state = root / ".sortmedia"
            source.mkdir()
            (source / "photo.jpg").write_bytes(b"photo")
            config = JobConfig(source=source, destination=destination, operation="copy")

            with patch("sortmedia.core.recorded_date", return_value=(datetime(2026, 8, 22, 12, 30), "test")):
                run_job(config, state)
            copied = destination / "2026" / "08" / "22" / "2026-08-22_12-30-00_photo.jpg"
            copied.write_bytes(b"changed")

            with self.assertRaisesRegex(ValueError, "content changed"):
                undo_run(state)


if __name__ == "__main__":
    unittest.main()

