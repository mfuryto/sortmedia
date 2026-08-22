from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sortmedia.core import recorded_date


class FilenameDateTests(unittest.TestCase):
    def test_camera_filename_is_used_before_filesystem_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "IMG_20240819_143052.jpg"
            media.write_bytes(b"photo")

            with patch("sortmedia.core.metadata_for", return_value={}):
                recorded, source = recorded_date(media)

            self.assertEqual(recorded.strftime("%Y-%m-%d %H:%M:%S"), "2024-08-19 14:30:52")
            self.assertEqual(source, "filename")


if __name__ == "__main__":
    unittest.main()
