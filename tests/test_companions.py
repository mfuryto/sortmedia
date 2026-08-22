from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sortmedia.config import JobConfig
from sortmedia.core import plan_group, run_job
from sortmedia.history import undo_run


class CompanionTests(unittest.TestCase):
    def test_live_photo_video_can_be_left_in_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "incoming"
            destination = root / "archive"
            source.mkdir()
            image = source / "IMG_1000.HEIC"
            video = source / "IMG_1000.MOV"
            image.write_bytes(b"image")
            video.write_bytes(b"video")
            config = JobConfig(source=source, destination=destination, operation="copy", live_photo_videos="leave")

            metadata = {
                image.resolve(): {"ContentIdentifier": "LIVE-ID"},
                video.resolve(): {"ContentIdentifier": "LIVE-ID"},
            }
            with patch("sortmedia.core.metadata_for_files", return_value=metadata), patch("sortmedia.core.recorded_date", return_value=(datetime(2026, 8, 22, 12, 30), "test")):
                processed, skipped = run_job(config)

            self.assertEqual((processed, skipped), (1, 1))
            self.assertTrue(video.exists())
            self.assertFalse(list(destination.rglob("*.mov")))

    def test_live_photo_video_trash_is_recoverable_with_undo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "incoming"
            destination = root / "archive"
            state = root / ".sortmedia"
            source.mkdir()
            image = source / "IMG_1000.HEIC"
            video = source / "IMG_1000.MOV"
            image.write_bytes(b"image")
            video.write_bytes(b"video")
            config = JobConfig(source=source, destination=destination, operation="copy", live_photo_videos="trash")

            metadata = {
                image.resolve(): {"ContentIdentifier": "LIVE-ID"},
                video.resolve(): {"ContentIdentifier": "LIVE-ID"},
            }
            with patch("sortmedia.core.metadata_for_files", return_value=metadata), patch("sortmedia.core.recorded_date", return_value=(datetime(2026, 8, 22, 12, 30), "test")):
                run_job(config, state)
            self.assertFalse(video.exists())
            self.assertTrue(list((state / "trash").rglob("*.MOV")))

            undo_run(state)
            self.assertTrue(video.exists())
            self.assertFalse(list(destination.rglob("*.heic")))

    def test_same_named_video_without_live_photo_metadata_is_not_trashed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "incoming"
            destination = root / "archive"
            state = root / ".sortmedia"
            source.mkdir()
            image = source / "holiday.JPG"
            video = source / "holiday.MOV"
            image.write_bytes(b"image")
            video.write_bytes(b"unrelated video")
            config = JobConfig(source=source, destination=destination, operation="copy", live_photo_videos="trash")

            with patch("sortmedia.core.metadata_for_files", return_value={}), patch("sortmedia.core.recorded_date", return_value=(datetime(2026, 8, 22, 12, 30), "test")):
                processed, skipped = run_job(config, state)

            self.assertEqual((processed, skipped), (2, 0))
            self.assertTrue(video.exists())
            self.assertTrue(list(destination.rglob("*.mov")))
            self.assertFalse(list((state / "trash").rglob("*.MOV")))

    def test_raw_jpeg_xmp_group_uses_one_name_and_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jpg = root / "IMG_0042.JPG"
            raw = root / "IMG_0042.CR3"
            xmp = root / "IMG_0042.xmp"
            for path in (jpg, raw, xmp):
                path.write_bytes(path.name.encode())
            config = JobConfig(source=root, destination=root)

            with patch("sortmedia.core.recorded_date", return_value=(datetime(2026, 8, 22, 12, 30), "test")):
                plans = plan_group([raw, jpg], config)

            destinations = {plan.destination.name for plan in plans}
            self.assertEqual(
                destinations,
                {
                    "2026-08-22_12-30-00_IMG_0042.jpg",
                    "2026-08-22_12-30-00_IMG_0042.cr3",
                    "2026-08-22_12-30-00_IMG_0042.xmp",
                },
            )

    def test_copy_preserves_companion_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "incoming"
            destination = root / "archive"
            source.mkdir()
            image = source / "IMG_0042.HEIC"
            video = source / "IMG_0042.MOV"
            sidecar = source / "IMG_0042.AAE"
            image.write_bytes(b"image-metadata")
            video.write_bytes(b"video-metadata")
            sidecar.write_bytes(b"edit-metadata")
            config = JobConfig(source=source, destination=destination, operation="copy")

            with patch("sortmedia.core.recorded_date", return_value=(datetime(2026, 8, 22, 12, 30), "test")):
                processed, skipped = run_job(config)

            target = destination / "2026" / "08" / "22"
            self.assertEqual(processed, 3)
            self.assertEqual(skipped, 0)
            self.assertEqual((target / "2026-08-22_12-30-00_IMG_0042.heic").read_bytes(), b"image-metadata")
            self.assertEqual((target / "2026-08-22_12-30-00_IMG_0042.mov").read_bytes(), b"video-metadata")
            self.assertEqual((target / "2026-08-22_12-30-00_IMG_0042.aae").read_bytes(), b"edit-metadata")

    def test_hash_mode_skips_same_content_with_different_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "incoming"
            destination = root / "archive"
            source.mkdir()
            destination.mkdir()
            (source / "new-name.jpg").write_bytes(b"identical-content")
            (destination / "old-name.jpg").write_bytes(b"identical-content")
            config = JobConfig(source=source, destination=destination, operation="copy")

            with patch("sortmedia.core.recorded_date", return_value=(datetime(2026, 8, 22, 12, 30), "test")):
                processed, skipped = run_job(config)

            self.assertEqual(processed, 0)
            self.assertEqual(skipped, 1)
            self.assertEqual(len(list(destination.rglob("*.jpg"))), 1)

    def test_hash_mode_renames_same_name_with_different_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "incoming"
            destination = root / "archive"
            source.mkdir()
            target = destination / "2026" / "08" / "22"
            target.mkdir(parents=True)
            media = source / "IMG.jpg"
            media.write_bytes(b"new-content")
            (target / "2026-08-22_12-30-00_IMG.jpg").write_bytes(b"old-content")
            config = JobConfig(source=source, destination=destination, operation="copy")

            with patch("sortmedia.core.recorded_date", return_value=(datetime(2026, 8, 22, 12, 30), "test")):
                processed, skipped = run_job(config)

            self.assertEqual(processed, 1)
            self.assertEqual(skipped, 0)
            self.assertEqual((target / "2026-08-22_12-30-00_IMG_2.jpg").read_bytes(), b"new-content")

    def test_optional_perceptual_mode_skips_visually_similar_image(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "incoming"
            destination = root / "archive"
            source.mkdir()
            destination.mkdir()
            Image.new("RGB", (32, 32), "red").save(source / "new.jpg", quality=70)
            Image.new("RGB", (64, 64), "red").save(destination / "existing.png")
            config = JobConfig(
                source=source,
                destination=destination,
                operation="copy",
                perceptual_duplicates=True,
            )

            with patch("sortmedia.core.recorded_date", return_value=(datetime(2026, 8, 22, 12, 30), "test")):
                processed, skipped = run_job(config)

            self.assertEqual(processed, 0)
            self.assertEqual(skipped, 1)


if __name__ == "__main__":
    unittest.main()
