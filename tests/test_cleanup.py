from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sortmedia.cleanup import format_size, find_live_photo_videos, find_live_photo_videos_with_total, purge_trash, trash_live_photo_videos, trash_stats
from sortmedia.core import content_identifier
from sortmedia.history import undo_run


class LivePhotoCleanupTests(unittest.TestCase):
    def test_accepts_newer_heic_media_group_uuid(self) -> None:
        self.assertEqual(
            content_identifier({"Apple:MediaGroupUUID": "LIVE-ID"}), "LIVE-ID"
        )

    def test_pairs_heic_media_group_uuid_with_mov_content_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "IMG_1000.HEIC"
            video = root / "IMG_1000.MOV"
            image.write_bytes(b"image")
            video.write_bytes(b"video")
            metadata = {
                image.resolve(): {"MediaGroupUUID": "LIVE-ID"},
                video.resolve(): {"ContentIdentifier": "LIVE-ID"},
            }

            with patch("sortmedia.cleanup.metadata_for_files", return_value=metadata):
                candidates = find_live_photo_videos(root)

            self.assertEqual([candidate.video for candidate in candidates], [video.resolve()])

    def test_formats_sizes_for_humans(self) -> None:
        self.assertEqual(format_size(42), "42 B")
        self.assertEqual(format_size(1_500_000), "1.5 MB")
        self.assertEqual(format_size(2_500_000_000), "2.5 GB")

    def test_purge_removes_only_trash_and_keeps_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trash_file = root / ".sortmedia" / "trash" / "run" / "clip.MOV"
            history_file = root / ".sortmedia" / "history" / "run.json"
            trash_file.parent.mkdir(parents=True)
            history_file.parent.mkdir(parents=True)
            trash_file.write_bytes(b"video")
            history_file.write_text("{}", encoding="utf-8")

            self.assertEqual(trash_stats(root), (1, 5))
            self.assertEqual(purge_trash(root), (1, 5))
            self.assertFalse((root / ".sortmedia" / "trash").exists())
            self.assertTrue(history_file.exists())

    def test_finds_only_metadata_confirmed_pairs_and_reports_details(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            album = root / "2025" / "07"
            album.mkdir(parents=True)
            (album / "IMG_1000.HEIC").write_bytes(b"image")
            paired = album / "IMG_1000.MOV"
            paired.write_bytes(b"live")
            (album / "holiday.MOV").write_bytes(b"standalone")
            internal = root / ".sortmedia" / "IMG_2000.MOV"
            internal.parent.mkdir()
            internal.write_bytes(b"internal")

            metadata = {
                (album / "IMG_1000.HEIC").resolve(): {"ContentIdentifier": "LIVE-ID"},
                paired.resolve(): {"ContentIdentifier": "LIVE-ID", "Duration": "2.8 s"},
                (album / "holiday.MOV").resolve(): {},
            }
            with patch("sortmedia.cleanup.metadata_for_files", return_value=metadata):
                candidates = find_live_photo_videos(root)

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].video, paired.resolve())
            self.assertEqual(candidates[0].image, (album / "IMG_1000.HEIC").resolve())
            self.assertEqual(candidates[0].size, 4)
            self.assertEqual(candidates[0].duration, "2.8 s")
            self.assertEqual(candidates[0].content_identifier, "LIVE-ID")

    def test_reports_matches_out_of_all_videos_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "IMG_1000.HEIC"
            paired = root / "IMG_1000.MOV"
            unrelated = root / "holiday.MP4"
            image.write_bytes(b"image")
            paired.write_bytes(b"live")
            unrelated.write_bytes(b"video")
            metadata = {
                image.resolve(): {"ContentIdentifier": "LIVE-ID"},
                paired.resolve(): {"ContentIdentifier": "LIVE-ID"},
                unrelated.resolve(): {},
            }

            with patch("sortmedia.cleanup.metadata_for_files", return_value=metadata):
                candidates, total = find_live_photo_videos_with_total(root)

            self.assertEqual(len(candidates), 1)
            self.assertEqual(total, 2)

    def test_same_filename_without_matching_metadata_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "holiday.JPG"
            video = root / "holiday.MOV"
            image.write_bytes(b"image")
            video.write_bytes(b"unrelated video")

            with patch("sortmedia.cleanup.metadata_for_files", return_value={}):
                self.assertEqual(find_live_photo_videos(root), [])

    def test_non_recursive_cleanup_excludes_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir()
            (nested / "IMG_1000.HEIC").write_bytes(b"image")
            (nested / "IMG_1000.MOV").write_bytes(b"video")

            with patch("sortmedia.cleanup.metadata_for_files", return_value={}):
                self.assertEqual(find_live_photo_videos(root, recursive=False), [])

    def test_cleanup_preserves_relative_path_and_is_undoable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            album = root / "2025" / "07"
            album.mkdir(parents=True)
            (album / "IMG_1000.JPG").write_bytes(b"image")
            video = album / "IMG_1000.MOV"
            video.write_bytes(b"live")

            run_id, moved = trash_live_photo_videos(root, [video])

            trashed = root / ".sortmedia" / "trash" / run_id / "2025" / "07" / "IMG_1000.MOV"
            self.assertEqual(moved, 1)
            self.assertTrue(trashed.exists())
            self.assertFalse(video.exists())
            undo_run(root / ".sortmedia", run_id)
            self.assertTrue(video.exists())


if __name__ == "__main__":
    unittest.main()
