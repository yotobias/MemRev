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

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        """True if `ancestor` is reachable from `descendant` (a commit is its own ancestor)."""
        return self._git("merge-base", "--is-ancestor", ancestor, descendant).returncode == 0

    def commit_times(self, shas: list[str]) -> dict[str, int]:
        """Committer timestamp per commit; commits missing from the clone are left out."""
        present = [sha for sha in dict.fromkeys(shas) if self.has_commit(sha)]
        if not present:
            return {}
        result = self._git("log", "--no-walk=unsorted", "--format=%H %ct", *present)
        result.check_returncode()
        return {sha: int(stamp) for sha, stamp in (line.split() for line in result.stdout.splitlines())}

    def changed_files(self, source_revision: str, target_revision: str) -> frozenset[str]:
        """Paths added, modified or deleted between two revisions; a rename counts as both paths."""
        result = self._git("diff", "--name-only", "--no-renames", source_revision, target_revision)
        if result.returncode != 0:
            raise ValueError(f"git diff {source_revision}..{target_revision} failed: {result.stderr.strip()}")
        return frozenset(line for line in result.stdout.splitlines() if line)

    def diff(self, source_revision: str, target_revision: str, paths: tuple[str, ...] = ()) -> str:
        """The unified diff from S to T, optionally limited to pathspecs (e.g. `*.py`). Read-only."""
        result = self._git("diff", "--no-renames", source_revision, target_revision, "--", *paths)
        if result.returncode != 0:
            raise ValueError(f"git diff {source_revision}..{target_revision} failed: {result.stderr.strip()}")
        return result.stdout
