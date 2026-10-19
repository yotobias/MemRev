"""Repository access: git operations on a local clone."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_GIT_ENV = {
    **os.environ,
    # A partial (blobless) clone would otherwise try to fetch unknown objects
    # from the remote, turning a missing commit into a slow network call.
    "GIT_NO_LAZY_FETCH": "1",
}


class Repository:
    def __init__(self, path: Path):
        self.path = path

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(self.path), *args],
            capture_output=True,
            text=True,
            env=_GIT_ENV,
        )

    def is_git_repository(self) -> bool:
        return self.path.is_dir() and self._git("rev-parse", "--git-dir").returncode == 0

    def has_commit(self, sha: str) -> bool:
        return self._git("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0

    def changed_files(self, source_revision: str, target_revision: str) -> frozenset[str]:
        """Paths added, modified or deleted between two revisions; a rename counts as both paths."""
        result = self._git("diff", "--name-only", "--no-renames", source_revision, target_revision)
        if result.returncode != 0:
            raise ValueError(f"git diff {source_revision}..{target_revision} failed: {result.stderr.strip()}")
        return frozenset(line for line in result.stdout.splitlines() if line)
