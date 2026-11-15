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


class ImprovedFilenameDateTests(unittest.TestCase):
    def test_supported_dates_and_fraction_precision(self) -> None:
        from datetime import datetime
        from sortmedia.filename_dates import parse_filename_date
        cases = [
            ('IMG_20240819_143052', 'ymd', datetime(2024, 8, 19, 14, 30, 52), True),
            ('2024-08-19_14-30-52_IMG', 'ymd', datetime(2024, 8, 19, 14, 30, 52), True),
            ('2024-08-19T14:30:52.012_IMG', 'ymd', datetime(2024, 8, 19, 14, 30, 52, 12000), True),
            ('20240819_143052.000001_IMG', 'ymd', datetime(2024, 8, 19, 14, 30, 52, 1), True),
            ('2024-08-19_1.02.03.000_IMG', 'ymd', datetime(2024, 8, 19, 1, 2, 3), True),
            ('19-08-2024_1.02.03.001234_IMG', 'dmy', datetime(2024, 8, 19, 1, 2, 3, 1234), True),
            ('08-19-2024 1:02:03.1_IMG', 'mdy', datetime(2024, 8, 19, 1, 2, 3, 100000), True),
            ('photo_2024-02-29', 'ymd', datetime(2024, 2, 29), False),
            ('photo_20240229', 'ymd', datetime(2024, 2, 29), False),
            ('03-04-2024_photo', 'dmy', datetime(2024, 4, 3), False),
            ('03-04-2024_photo', 'mdy', datetime(2024, 3, 4), False),
            ('2024-04-03_photo', 'mdy', datetime(2024, 4, 3), False),
        ]
        for stem, order, expected, has_time in cases:
            with self.subTest(stem=stem, order=order):
                parsed = parse_filename_date(stem, order)
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed.value, expected)
                self.assertEqual(parsed.has_time, has_time)

    def test_ambiguous_and_invalid_tokens_are_not_guessed(self) -> None:
        from sortmedia.filename_dates import parse_filename_date
        for stem in (
            '03-04-2024_photo', '19-08-2024_photo',
            '2023-02-29_photo', '2024-13-01_photo', '2024-04-31_photo',
            '2024-01-02_24-00-00_photo', '2024-01-02_12-60-00_photo',
            '2024-01-02_12-30-60_photo', '2024-01-02_12-30_photo',
            '2024-01-02_12:30.45_photo',
            '2024-01-02_12:34:56.20240102_photo',
            '2024-01-02_1234567_photo', '2024-01-02_12345678_photo', '2024-01-02_12:34:56.0123456_photo',
            '2024-01-02T12:34:56Z_photo', '2024-01-02T12:34:56+02:00_photo',
            '120240102_photo', '202401021_photo',
        ):
            with self.subTest(stem=stem):
                self.assertIsNone(parse_filename_date(stem))
        self.assertIsNone(parse_filename_date('19-08-2024_photo', 'mdy'))

    def test_complete_timestamp_wins_over_earlier_date_only_token(self) -> None:
        from datetime import datetime
        from sortmedia.filename_dates import parse_filename_date
        parsed = parse_filename_date('album_2020-01-02_IMG_20240819_143052')
        self.assertEqual(parsed.value, datetime(2024, 8, 19, 14, 30, 52))
        self.assertTrue(parsed.has_time)

    def test_metadata_wins_and_date_only_precision_is_reported(self) -> None:
        from datetime import datetime
        path = Path('03-04-2024_12-30-00.jpg')
        parsed, source = recorded_date(path, 'UTC', {'DateTimeOriginal': '2025:01:02 03:04:05'}, 'dmy')
        self.assertEqual((parsed, source), (datetime(2025, 1, 2, 3, 4, 5), 'DateTimeOriginal'))
        parsed, source = recorded_date(Path('2024-02-29.jpg'), 'UTC', {}, 'ymd')
        self.assertEqual((parsed, source), (datetime(2024, 2, 29), 'filename-date'))
        parsed, source = recorded_date(Path('2024-01-02_24-00-00.jpg'), 'UTC', {'FileCreateDate': '2020:01:01 01:02:03'}, 'ymd')
        self.assertEqual((parsed, source), (datetime(2020, 1, 1, 1, 2, 3), 'FileCreateDate'))

    def test_default_ambiguity_falls_back_and_explicit_order_is_used(self) -> None:
        from datetime import datetime
        path = Path('03-04-2024.jpg')
        metadata = {'FileCreateDate': '2020:01:01 00:00:00'}
        self.assertEqual(recorded_date(path, 'UTC', metadata)[1], 'FileCreateDate')
        self.assertEqual(recorded_date(path, 'UTC', metadata, 'dmy')[0], datetime(2024, 4, 3))
        self.assertEqual(recorded_date(path, 'UTC', metadata, 'mdy')[0], datetime(2024, 3, 4))

    def test_config_validation_and_cli_override(self) -> None:
        import json
        from sortmedia.cli import main
        from sortmedia.config import load_config
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / '.sortmedia.toml'
            for value in ('auto', 'DMY', '', True, 1, []):
                config.write_text('filename_date_order = ' + json.dumps(value))
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'filename_date_order'):
                    load_config(config)
            config.write_text('filename_date_order = "dmy"')
            self.assertEqual(load_config(config).filename_date_order, 'dmy')
            with patch('sortmedia.cli.run_job', return_value=(0, 0)) as job:
                self.assertEqual(main(['-c', str(config), '--filename-date-order', 'mdy', '--quiet']), 0)
                self.assertEqual(job.call_args.args[0].filename_date_order, 'mdy')
            self.assertEqual(load_config(config).filename_date_order, 'dmy')
            with patch('sortmedia.cli.run_job', return_value=(0, 0)) as job:
                self.assertEqual(main(['-f', directory, '--filename-date-order', 'dmy', '--quiet']), 0)
                self.assertEqual(job.call_args.args[0].filename_date_order, 'dmy')

    def test_sort_companions_share_explicit_date(self) -> None:
        from sortmedia.config import JobConfig
        from sortmedia.core import plan_group
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / '03-04-2024_1.02.03.012.JPG'
            raw = image.with_suffix('.CR3')
            sidecar = image.with_suffix('.XMP')
            for path in (image, raw, sidecar):
                path.write_bytes(b'original')
            plans = plan_group([image, raw], JobConfig(root, root / 'out', filename_date_order='dmy'), {})
            self.assertEqual(len(plans), 3)
            self.assertTrue(all(plan.destination.parent == root / 'out/2024/04/03' for plan in plans))
            self.assertTrue(all(plan.destination.name.startswith('2024-04-03_01-02-03_') for plan in plans))

    def test_normalization_is_repeatable_and_preserves_invalid_prefixes(self) -> None:
        from sortmedia.config import JobConfig
        from sortmedia.normalize import clean_original_stem, plan_filename_normalization, apply_filename_normalization
        self.assertEqual(clean_original_stem('03-04-2024_IMG'), '03-04-2024_IMG')
        self.assertEqual(clean_original_stem('2024-02-31_IMG'), '2024-02-31_IMG')
        self.assertEqual(clean_original_stem('2024-01-02_24-00-00_IMG'), '2024-01-02_24-00-00_IMG')
        self.assertEqual(clean_original_stem('2024-04-03_03-04-2024_1.02.03.012_IMG', 'dmy'), 'IMG')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for suffix in ('.JPG', '.CR3', '.XMP'):
                (root / ('03-04-2024_1.02.03.012_IMG' + suffix)).write_bytes(b'original')
            config = JobConfig(root, root, filename_date_order='dmy')
            with patch('sortmedia.normalize.metadata_for_files', return_value={}):
                plans, count = plan_filename_normalization(root, config)
                self.assertEqual((len(plans), count), (3, 3))
                apply_filename_normalization(root, plans)
                second, count = plan_filename_normalization(root, config)
            self.assertEqual(second, [])
            self.assertEqual(count, 3)
            self.assertTrue((root / '2024-04-03_01-02-03_IMG.jpg').exists())
            self.assertEqual((root / '2024-04-03_01-02-03_IMG.jpg').read_bytes(), b'original')

    def test_normalization_menu_defaults_and_override_without_config(self) -> None:
        from sortmedia.cli import interactive_menu
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / '.sortmedia.toml'
            config.write_text('filename_date_order = "dmy"')
            for selected, expected in (('', 'dmy'), ('mdy', 'mdy')):
                answers = iter(['6', 'yes', '', selected])
                with patch('sortmedia.cli.plan_filename_normalization', return_value=([], 0)) as planner:
                    self.assertEqual(interactive_menu(root, lambda _: next(answers)), 0)
                self.assertEqual(planner.call_args.args[1].filename_date_order, expected)
            config.unlink()
            answers = iter(['6', 'yes', '', 'mdy'])
            with patch('sortmedia.cli.plan_filename_normalization', return_value=([], 0)) as planner:
                self.assertEqual(interactive_menu(root, lambda _: next(answers)), 0)
            self.assertEqual(planner.call_args.args[1].filename_date_order, 'mdy')
            self.assertFalse(config.exists())


if __name__ == "__main__":
    unittest.main()
