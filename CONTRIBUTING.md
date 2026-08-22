# Contributing to Sortmedia

Thank you for helping make media organization safer and easier.

## Before opening an issue

- Search existing issues for the same problem or idea.
- For a bug, include the Sortmedia version, Linux distribution, Python version,
  ExifTool version, command used, and sanitized output.
- Never upload private photos, videos, metadata, paths, or config secrets.

## Required contribution process

All user-visible changes must start with a GitHub issue so the problem, safety
impact, and intended behavior can be discussed before implementation. Security
vulnerabilities are the only exception and must follow `SECURITY.md` instead.

1. Open or select an issue and agree on its scope.
2. Create a branch linked to that issue.
3. Submit a focused pull request that references the issue.
4. Wait for every required automated check to pass and resolve all review
   conversations.
5. Merge through GitHub. Do not push directly to `main`.

Repository maintainers may close changes that bypass this process, combine
unrelated work, or weaken media-safety guarantees.

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
