from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from sortmedia.cli import (
    create_config_interactive,
    interactive_menu,
    main,
    parser,
    update_config_interactive,
)
from sortmedia.config import load_config


class InteractiveConfigTests(unittest.TestCase):
    def test_wizard_creates_hidden_config_with_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            answers = iter(["", "", "", "", "", "", "", "", "", ""])
            config_path = create_config_interactive(Path(directory), lambda _: next(answers))

            self.assertEqual(config_path.name, ".sortmedia.toml")
            config = load_config(config_path)
            self.assertEqual(config.source, Path(directory).resolve())
            self.assertEqual(config.destination, Path(directory).resolve())
            self.assertEqual(config.operation, "preview")
            self.assertEqual(config.layout, "{year}/{month}/{day}")

    def test_menu_creates_config_in_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            answers = iter(["1", "", "", "", "", "", "", "", "", "", ""])

            result = interactive_menu(Path(directory), lambda _: next(answers))

            self.assertEqual(result, 0)
            self.assertTrue((Path(directory) / ".sortmedia.toml").is_file())

    def test_multiple_override_flags_are_accepted(self) -> None:
        args = parser().parse_args([
            "-r", "--move", "--recursive", "-d", "/archive",
            "--layout", "{year}/{month}", "--duplicates", "skip",
        ])

        self.assertTrue(args.run_local)
        self.assertEqual(args.operation, "move")
        self.assertTrue(args.recursive)
        self.assertEqual(args.layout, "{year}/{month}")

    def test_update_config_overwrites_operation_in_same_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / ".sortmedia.toml"
            source.write_text(
                '# Keep this comment\noperation = "preview"\nlayout = "{year}/{month}/{day}"\n',
                encoding="utf-8",
            )
            answers = iter(["move", "2", "no", "1"])

            updated = update_config_interactive(source, lambda _: next(answers))

            self.assertEqual(updated, source.resolve())
            self.assertEqual(load_config(source).operation, "move")
            self.assertEqual(load_config(source).layout, "{year}/{month}")
            self.assertIn("# Keep this comment", source.read_text(encoding="utf-8"))
            self.assertFalse((Path(directory) / ".sortmedia.move.toml").exists())

    def test_run_local_uses_config_from_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".sortmedia.toml").write_text("", encoding="utf-8")
            original = Path.cwd()
            try:
                os.chdir(root)
                result = main(["-r"])
            finally:
                os.chdir(original)

            self.assertEqual(result, 0)

    def test_filename_normalization_needs_no_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            answers = iter(["6", "no"])
            with patch(
                "sortmedia.cli.plan_filename_normalization", return_value=([], 0)
            ) as planner:
                result = interactive_menu(root, lambda _: next(answers))

            self.assertEqual(result, 0)
            config = planner.call_args.args[1]
            self.assertEqual(config.source, root.resolve())
            self.assertEqual(config.destination, root.resolve())
            self.assertEqual(config.filename, "{date}_{time}_{original}")
            self.assertFalse(planner.call_args.kwargs["recursive"])


if __name__ == "__main__":
    unittest.main()
