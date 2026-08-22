from pathlib import Path
import tempfile
import time
import unittest

from sortmedia.config import JobConfig
from sortmedia.core import media_files


class PerformanceTests(unittest.TestCase):
    def test_recursive_discovery_of_1000_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number in range(1000):
                folder = root / str(number // 100)
                folder.mkdir(exist_ok=True)
                (folder / f"image-{number}.jpg").touch()

            started = time.monotonic()
            found = list(media_files(JobConfig(source=root, destination=root, recursive=True)))
            elapsed = time.monotonic() - started

            self.assertEqual(len(found), 1000)
            self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
