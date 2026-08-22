from pathlib import Path
import tempfile
import unittest

from sortmedia.cleanup import format_size, find_live_photo_videos, purge_trash, trash_live_photo_videos, trash_stats
from sortmedia.history import undo_run


class LivePhotoCleanupTests(unittest.TestCase):
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

    def test_finds_pairs_recursively_but_ignores_standalone_videos_and_state(self) -> None:
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

            self.assertEqual(find_live_photo_videos(root), [paired])

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
