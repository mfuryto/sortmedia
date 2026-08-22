import base64
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from sortmedia.core import recorded_date


@unittest.skipUnless(shutil.which("exiftool"), "ExifTool is not installed")
class ExifToolIntegrationTests(unittest.TestCase):
    def test_reads_real_embedded_recording_date(self) -> None:
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "photo.png"
            media.write_bytes(png)
            try:
                subprocess.run(
                    ["exiftool", "-overwrite_original", "-DateTimeOriginal=2026:08:22 12:30:45", str(media)],
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as error:
                self.skipTest(f"ExifTool cannot write the integration fixture: {error}")

            recorded, source = recorded_date(media, "UTC")

            self.assertEqual(recorded.strftime("%Y-%m-%d %H:%M:%S"), "2026-08-22 12:30:45")
            self.assertEqual(source, "DateTimeOriginal")

    def test_reads_generated_dng_metadata(self) -> None:
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "camera.dng"
            Image.new("RGB", (16, 16), "blue").save(media, format="TIFF")
            subprocess.run(
                [
                    "exiftool", "-overwrite_original", "-DNGVersion=1.4.0.0",
                    "-DateTimeOriginal=2025:07:14 18:42:09", str(media),
                ],
                check=True,
                capture_output=True,
            )

            recorded, source = recorded_date(media, "UTC")

            self.assertEqual(recorded.strftime("%Y-%m-%d %H:%M:%S"), "2025-07-14 18:42:09")
            self.assertEqual(source, "DateTimeOriginal")

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is not installed")
    def test_reads_generated_mp4_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "clip.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=black:s=32x32:d=0.2", "-metadata",
                    "creation_time=2024-03-02T10:11:12Z", "-y", str(media),
                ],
                check=True,
                capture_output=True,
            )

            recorded, source = recorded_date(media, "UTC")

            self.assertEqual(recorded.strftime("%Y-%m-%d %H:%M:%S"), "2024-03-02 10:11:12")
            self.assertIn(source, {"CreateDate", "MediaCreateDate", "TrackCreateDate"})


if __name__ == "__main__":
    unittest.main()
