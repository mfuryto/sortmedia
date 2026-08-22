from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sortmedia.config import JobConfig
from sortmedia.history import undo_run
from sortmedia.normalize import (
    apply_filename_normalization,
    clean_original_stem,
    plan_filename_normalization,
)


class FilenameNormalizationTests(unittest.TestCase):
    def test_removes_repeated_date_prefixes_but_keeps_camera_name(self) -> None:
        self.assertEqual(
            clean_original_stem("2025-07-01_12-30-00_2024-06-02_09-10-11_IMG_0042"),
            "IMG_0042",
        )
        self.assertEqual(clean_original_stem("20250701_123000_DSC_1000"), "DSC_1000")
        self.assertEqual(clean_original_stem("family_holiday"), "family_holiday")

    def test_plans_recursive_companions_without_changing_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            album = root / "2025" / "07"
            album.mkdir(parents=True)
            image = album / "2024-06-02_09-10-11_IMG_0042.JPG"
            raw = album / "2024-06-02_09-10-11_IMG_0042.CR3"
            sidecar = album / "2024-06-02_09-10-11_IMG_0042.XMP"
            for path in (image, raw, sidecar):
                path.write_bytes(path.name.encode())
            config = JobConfig(
                source=root,
                destination=root,
                filename="{date}_{time}_{original}",
            )

            with patch("sortmedia.normalize.metadata_for_files", return_value={}), patch(
                "sortmedia.normalize.recorded_date",
                return_value=(datetime(2024, 6, 2, 9, 10, 11), "DateTimeOriginal"),
            ):
                plans, considered = plan_filename_normalization(root, config)

            self.assertEqual(considered, 3)
            self.assertEqual(len(plans), 3)
            self.assertEqual(
                {plan.destination.name for plan in plans},
                {
                    "2024-06-02_09-10-11_IMG_0042.jpg",
                    "2024-06-02_09-10-11_IMG_0042.cr3",
                    "2024-06-02_09-10-11_IMG_0042.xmp",
                },
            )
            self.assertTrue(all(plan.destination.parent == album for plan in plans))

    def test_apply_is_hash_verified_and_undoable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "2024-06-02_IMG_0042.JPG"
            source.write_bytes(b"unchanged media bytes")
            config = JobConfig(source=root, destination=root, filename="{original}")

            with patch("sortmedia.normalize.metadata_for_files", return_value={}), patch(
                "sortmedia.normalize.recorded_date",
                return_value=(datetime(2024, 6, 2), "DateTimeOriginal"),
            ):
                plans, _ = plan_filename_normalization(root, config)
            run_id, renamed = apply_filename_normalization(root, plans)

            destination = root / "IMG_0042.jpg"
            self.assertEqual(renamed, 1)
            self.assertEqual(destination.read_bytes(), b"unchanged media bytes")
            undo_run(root / ".sortmedia", run_id)
            self.assertEqual(source.read_bytes(), b"unchanged media bytes")

    def test_existing_destination_is_rejected_before_rename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "2024-06-02_IMG_0042.JPG").write_bytes(b"source")
            (root / "IMG_0042.jpg").write_bytes(b"occupied")
            config = JobConfig(source=root, destination=root, filename="{original}")

            with patch("sortmedia.normalize.metadata_for_files", return_value={}), patch(
                "sortmedia.normalize.recorded_date",
                return_value=(datetime(2024, 6, 2), "DateTimeOriginal"),
            ):
                with self.assertRaisesRegex(ValueError, "overwrite"):
                    plan_filename_normalization(root, config)


if __name__ == "__main__":
    unittest.main()
