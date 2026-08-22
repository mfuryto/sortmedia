# Contributing to Sortmedia

Thank you for helping make media organization safer and easier.

## Before opening an issue

- Search existing issues for the same problem or idea.
- For a bug, include the Sortmedia version, Linux distribution, Python version,
  ExifTool version, command used, and sanitized output.
- Never upload private photos, videos, metadata, paths, or config secrets.

## Development setup

```bash
git clone https://github.com/mfuryto/sortmedia.git
cd sortmedia
python3 -m unittest discover -s tests -v
./bin/sortmedia -h
```

Keep user-facing text and documentation in English. Add or update tests for
behavior changes. Preview mode must remain the default, and no change may
silently overwrite or permanently delete user media.

## Pull requests

Keep each pull request focused. Describe the user-visible change, its safety
impact, and how it was tested. By contributing, you agree that your work is
provided under the project's MIT license.
