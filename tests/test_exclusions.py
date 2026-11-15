from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sortmedia.cli import interactive_menu, main
from sortmedia.cleanup import LivePhotoScan, scan_live_photo_videos
from sortmedia.config import JobConfig, load_config
from sortmedia.core import media_files, run_job
from sortmedia.exclusions import iter_source_paths, matching_exclusion, validate_exclusions
from sortmedia.normalize import plan_filename_normalization


class ExclusionTests(unittest.TestCase):
    def test_segment_matching_and_root_anchoring(self) -> None:
        cases = [
            ('one/Cache/deeper', 'Cache', True),
            ('one/cache', 'Cache', False),
            ('one/Cache', 'one/Cache', True),
            ('other/one/Cache', 'one/Cache', False),
            ('one/two/Cache', 'one/*/Cache', True),
            ('one/two/three/Cache', 'one/*/Cache', False),
            ('one/Cache', 'one/**/Cache', True),
            ('one/two/three/Cache/deep', 'one/**/Cache', True),
            ('holiday photos/raw', 'holiday photos', True),
        ]
        for relative, pattern, expected in cases:
            with self.subTest(relative=relative, pattern=pattern):
                self.assertEqual(matching_exclusion(Path(relative), (pattern,)) is not None, expected)
        self.assertEqual(validate_exclusions(['./one/Cache/'.replace('/', chr(92))]), ('one/Cache',))

    def test_invalid_config_rejected_before_scan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / '.sortmedia.toml'
            for value in ['Cache', [1], [''], [' '], ['/absolute'], ['../outside'], ['a/../b'], ['.'], ['./'], ['a//b'], ['a**/b'], ['C:\\Cache']]:
                with self.subTest(value=value):
                    config.write_text('exclude_folders = ' + json.dumps(value))
                    with self.assertRaisesRegex(ValueError, 'exclude_folders'):
                        load_config(config)
            config.write_text('exclude_folders = ["Cache", "backups/**/raw"]')
            self.assertEqual(load_config(config).exclude_folders, ('Cache', 'backups/**/raw'))

    def test_prunes_before_visiting_and_reports_rule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('Cache/nested', 'keep', '.sortmedia/trash'):
                target = root / name
                target.mkdir(parents=True)
                (target / 'image.jpg').write_bytes(b'image')
            visited = []
            events = []
            original = os.walk
            def walk(*args, **kwargs):
                for current, names, files in original(*args, **kwargs):
                    visited.append(Path(current).relative_to(root).as_posix())
                    yield current, names, files
            with patch('sortmedia.exclusions.os.walk', side_effect=walk):
                found = list(iter_source_paths(root, True, ('Cache',), on_excluded=lambda *event: events.append(event)))
            self.assertEqual(found, [root / 'keep/image.jpg'])
            self.assertEqual(set(visited), {'.', 'keep'})
            self.assertEqual(events, [(root / 'Cache', 'Cache')])

    def test_nonrecursive_depth_and_symlink_safety(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Cache').mkdir()
            (root / 'Cache/image.jpg').write_bytes(b'private')
            (root / 'root.jpg').write_bytes(b'image')
            (root / 'alias').symlink_to(root / 'Cache', target_is_directory=True)
            (root / 'alias.jpg').symlink_to(root / 'Cache/image.jpg')
            for recursive, depth in [(False, None), (True, 0), (True, None)]:
                self.assertEqual(list(iter_source_paths(root, recursive, ('Cache',), max_depth=depth)), [root / 'root.jpg'])

    def test_scan_error_aborts_before_metadata_or_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def unreadable(*args, **kwargs):
                yield str(root), ['blocked'], ['image.jpg']
                kwargs['onerror'](PermissionError('Cannot read blocked directory'))
            with patch('sortmedia.exclusions.os.walk', side_effect=unreadable), patch('sortmedia.core.metadata_for_files') as metadata:
                with self.assertRaises(PermissionError):
                    run_job(JobConfig(root, root, operation='move', recursive=True))
            metadata.assert_not_called()
            self.assertFalse((root / '.sortmedia').exists())

    def test_shared_exclusions_keep_companions_out_of_all_plans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = {}
            for folder in ('Cache', 'keep'):
                album = root / folder
                album.mkdir()
                for filename in ('IMG.HEIC', 'IMG.MOV', 'IMG.XMP'):
                    path = album / filename
                    path.write_bytes(b'original')
                    metadata[path] = {'ContentIdentifier': folder, 'DateTimeOriginal': '2024:01:02 03:04:05'}
            config = JobConfig(root, root, recursive=True, exclude_folders=('Cache',))
            self.assertEqual({p.parent.name for p in media_files(config)}, {'keep'})
            with patch('sortmedia.normalize.metadata_for_files', return_value=metadata):
                plans, count = plan_filename_normalization(root, config)
            self.assertEqual(count, 3)
            self.assertEqual(len(plans), 3)
            self.assertTrue(all(p.source.parent.name == 'keep' for p in plans))
            with patch('sortmedia.cleanup.metadata_for_files', return_value=metadata) as reader:
                scan = scan_live_photo_videos(root, exclude_folders=('Cache',))
            self.assertEqual(scan.videos_scanned, 1)
            self.assertEqual([c.video for c in scan.candidates], [root / 'keep/IMG.MOV'])
            self.assertTrue(all(p.parent.name == 'keep' for p in reader.call_args.args[0]))
            self.assertEqual((root / 'Cache/IMG.MOV').read_bytes(), b'original')

    def test_menu_uses_local_rules_for_both_tools_and_allows_config_free_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / '.sortmedia.toml'
            for has_config in (True, False):
                if has_config:
                    config_path.write_text('exclude_folders = ["Cache"]')
                else:
                    config_path.unlink()
                for tool in ('normalize', 'cleanup'):
                    choice = '6' if tool == 'normalize' else ('3' if has_config else '2')
                    answers = iter([choice, 'yes', '' if has_config else '["Cache"]'])
                    with patch('sortmedia.cli.plan_filename_normalization', return_value=([], 0)) as planner, patch('sortmedia.cli.scan_live_photo_videos', return_value=LivePhotoScan([], 0, 0, 0)) as cleanup:
                        self.assertEqual(interactive_menu(root, lambda _: next(answers)), 0)
                    if tool == 'normalize':
                        self.assertEqual(planner.call_args.args[1].exclude_folders, ('Cache',))
                    else:
                        self.assertEqual(cleanup.call_args.kwargs['exclude_folders'], ('Cache',))
            self.assertFalse(config_path.exists())

    def test_symlink_sidecar_cannot_bypass_exclusion(self) -> None:
        from sortmedia.core import plan_group
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Cache').mkdir()
            protected = root / 'Cache/IMG.XMP'
            protected.write_bytes(b'protected')
            image = root / 'IMG.jpg'
            image.write_bytes(b'image')
            (root / 'IMG.XMP').symlink_to(protected)
            config = JobConfig(root, root / 'archive', exclude_folders=('Cache',))
            metadata = {image: {'DateTimeOriginal': '2024:01:02 03:04:05'}}
            plans = plan_group([image], config, metadata)
            self.assertEqual([plan.source for plan in plans], [image])
            with patch('sortmedia.normalize.metadata_for_files', return_value=metadata):
                _, considered = plan_filename_normalization(root, config)
            self.assertEqual(considered, 1)
            self.assertEqual(protected.read_bytes(), b'protected')

    def test_json_preview_reports_excluded_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Cache').mkdir()
            (root / 'Cache/image.jpg').write_bytes(b'image')
            config = root / '.sortmedia.toml'
            config.write_text('recursive = true\nexclude_folders = ["Cache"]')
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(['-c', str(config), '--json']), 0)
            events = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertIn({'event': 'excluded_directory', 'path': str(root / 'Cache'), 'pattern': 'Cache'}, events)
            self.assertFalse((root / '.sortmedia').exists())

    def test_maintenance_rejects_rules_for_another_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.sortmedia.toml').write_text('folder = "incoming"\nexclude_folders = ["Cache"]')
            for choice in ('3', '6'):
                answers = iter([choice, 'yes'])
                with patch('sortmedia.cli.scan_live_photo_videos') as cleanup, patch('sortmedia.cli.plan_filename_normalization') as planner:
                    self.assertEqual(interactive_menu(root, lambda _: next(answers)), 1)
                cleanup.assert_not_called()
                planner.assert_not_called()

    def test_invalid_maintenance_rules_stop_before_scan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for value in ('Cache', '["../outside"]', '["/absolute"]'):
                answers = iter(['6', 'yes', value])
                with patch('sortmedia.cli.plan_filename_normalization') as planner:
                    self.assertEqual(interactive_menu(root, lambda _: next(answers)), 1)
                planner.assert_not_called()

    def test_move_and_undo_leave_excluded_media_untouched(self) -> None:
        from sortmedia.history import undo_run
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'incoming'
            (source / 'Cache').mkdir(parents=True)
            protected = source / 'Cache/IMG.jpg'
            protected.write_bytes(b'protected')
            image = source / 'IMG.jpg'
            sidecar = source / 'IMG.XMP'
            image.write_bytes(b'image')
            sidecar.write_bytes(b'sidecar')
            state = root / '.sortmedia'
            config = JobConfig(source, root / 'archive', operation='move', recursive=True, exclude_folders=('Cache',))
            with patch('sortmedia.core.metadata_for_files', return_value={}):
                affected, _ = run_job(config, state)
            self.assertEqual(affected, 2)
            self.assertFalse(image.exists())
            self.assertEqual(protected.read_bytes(), b'protected')
            undo_run(state)
            self.assertEqual(image.read_bytes(), b'image')
            self.assertEqual(sidecar.read_bytes(), b'sidecar')
            self.assertEqual(protected.read_bytes(), b'protected')

    def test_destination_duplicate_search_still_includes_excluded_folders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Cache').mkdir()
            (root / 'Cache/existing.jpg').write_bytes(b'identical')
            source = root / 'incoming.jpg'
            source.write_bytes(b'identical')
            config = JobConfig(root, root, recursive=True, exclude_folders=('Cache',))
            with patch('sortmedia.core.metadata_for_files', return_value={}):
                affected, skipped = run_job(config)
            self.assertEqual((affected, skipped), (0, 1))
            self.assertEqual(source.read_bytes(), b'identical')


if __name__ == '__main__':
    unittest.main()
