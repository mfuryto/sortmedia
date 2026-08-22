from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sortmedia.config import JobConfig
from sortmedia.core import _parse_metadata_date, media_files, plan_file


class SafetyTests(unittest.TestCase):
    def test_layout_cannot_escape_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media = root / "photo.jpg"
            media.write_bytes(b"photo")
            config = JobConfig(source=root, destination=root, layout="../../escape")

            with patch("sortmedia.core.recorded_date", return_value=(datetime(2026, 8, 22), "test")):
                with self.assertRaisesRegex(ValueError, "Unsafe directory"):
                    plan_file(media, config)

    def test_utc_metadata_remains_timezone_aware(self) -> None:
        parsed = _parse_metadata_date("2026:08:22 12:30:00Z")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.utcoffset(), timezone.utc.utcoffset(parsed))

    def test_recursive_scan_ignores_sortmedia_state_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visible = root / "visible.jpg"
            internal = root / ".sortmedia" / "hidden.jpg"
            internal.parent.mkdir()
            visible.write_bytes(b"visible")
            internal.write_bytes(b"internal")
            config = JobConfig(source=root, destination=root, recursive=True)

            found = list(media_files(config))

            self.assertEqual(found, [visible])

    def test_recursive_scan_respects_max_depth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            level_one = root / "one" / "image.jpg"
            level_two = root / "one" / "two" / "image.jpg"
            level_two.parent.mkdir(parents=True)
            level_one.write_bytes(b"one")
            level_two.write_bytes(b"two")
            config = JobConfig(source=root, destination=root, recursive=True, max_depth=1)

            self.assertEqual(list(media_files(config)), [level_one])


if __name__ == "__main__":
    unittest.main()
