from pathlib import Path
import tempfile
import unittest

from sortmedia.config import load_config


class ConfigTests(unittest.TestCase):
    def test_relative_paths_use_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "job"
            config_dir.mkdir()
            config = config_dir / ".settings.toml"
            config.write_text('folder = "incoming"\ndestination = "sorted"\n', encoding="utf-8")

            loaded = load_config(config)

            self.assertEqual(loaded.source, (config_dir / "incoming").resolve())
            self.assertEqual(loaded.destination, (config_dir / "sorted").resolve())

    def test_missing_folder_defaults_to_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / ".settings.toml"
            config.write_text("", encoding="utf-8")

            loaded = load_config(config)

            self.assertEqual(loaded.source, Path(directory).resolve())

    def test_visible_config_filename_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "settings.toml"
            config.write_text("", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "hidden TOML file"):
                load_config(config)


if __name__ == "__main__":
    unittest.main()
