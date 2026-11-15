"""Exercise installed launchers without importing modules from the checkout."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from sortmedia import __version__


ROOT = Path(__file__).resolve().parents[1]


class InstalledPackageTests(unittest.TestCase):
    def assert_installed_command(self, command: Path, library: Path) -> None:
        expected = {path.name for path in (ROOT / 'src/sortmedia').glob('*.py')}
        self.assertEqual({path.name for path in library.glob('*.py')}, expected)
        environment = os.environ.copy()
        environment.pop('PYTHONPATH', None)
        result = subprocess.run(
            [str(command), '--version'], cwd=command.parent,
            env=environment, check=True, capture_output=True, text=True,
        )
        self.assertEqual(result.stdout.strip(), f'sortmedia {__version__}')

    def test_prefix_install_runs_without_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            subprocess.run(
                ['./install.sh'], cwd=ROOT,
                env={**os.environ, 'PREFIX': str(prefix)},
                check=True, capture_output=True,
            )
            self.assert_installed_command(
                prefix / 'bin/sortmedia', prefix / 'lib/sortmedia/src/sortmedia',
            )

    @unittest.skipUnless(shutil.which('dpkg-deb'), 'dpkg-deb is unavailable')
    def test_deb_contains_all_modules_and_launches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / 'project'
            project.mkdir()
            for name in ('src', 'bin', 'man', 'scripts', 'packaging'):
                shutil.copytree(ROOT / name, project / name)
            shutil.copy2(ROOT / 'README.md', project / 'README.md')
            subprocess.run(
                ['./scripts/build-deb.sh'], cwd=project,
                check=True, capture_output=True,
            )
            package, = (project / 'dist').glob('*.deb')
            installed = root / 'installed'
            subprocess.run(
                ['dpkg-deb', '-x', str(package), str(installed)],
                check=True, capture_output=True,
            )
            self.assert_installed_command(
                installed / 'usr/bin/sortmedia',
                installed / 'usr/lib/sortmedia/src/sortmedia',
            )
