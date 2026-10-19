"""Shared fixtures for seam N1: a tiny real git repository and a CLI runner."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from memrev.cli import main


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        },
    )
    return result.stdout.strip()


@dataclass
class TinyRepo:
    """A real git repository with a few commits, created inside the test."""

    path: Path
    commits: list[str]


@pytest.fixture
def tiny_repo(tmp_path: Path) -> TinyRepo:
    path = tmp_path / "checkouts" / "tiny"
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    commits = []
    for n in range(3):
        (path / "module.py").write_text(f"VALUE = {n}\n")
        _git(path, "add", "module.py")
        _git(path, "commit", "-q", "-m", f"commit {n}")
        commits.append(_git(path, "rev-parse", "HEAD"))
    return TinyRepo(path=path, commits=commits)


@dataclass
class CliResult:
    exit_code: int
    out: str
    err: str


@pytest.fixture
def cli(capsys):
    """Call the command-line tool in-process, exactly as the console script does."""

    def run(*args: str) -> CliResult:
        try:
            code = main(list(args))
        except SystemExit as exc:  # argparse errors
            code = exc.code if isinstance(exc.code, int) else 1
        captured = capsys.readouterr()
        return CliResult(exit_code=code or 0, out=captured.out, err=captured.err)

    return run


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    return tmp_path / "runs" / "run-1"


def memrev_for(cli, run_dir: Path):
    """`memrev(*args)`: the command-line tool on one run, i.e. `memrev --run <run_dir> *args`."""

    def memrev(*args: str) -> CliResult:
        return cli("--run", str(run_dir), *args)

    return memrev


@pytest.fixture
def memrev(cli, run_dir):
    """The command-line tool on this test's run directory."""
    return memrev_for(cli, run_dir)


def write_bank(path: Path, lines: list) -> Path:
    """Write a lesson-bank JSONL file; dicts are serialised, strings written as-is."""
    with path.open("w") as fh:
        for line in lines:
            fh.write(line if isinstance(line, str) else json.dumps(line))
            fh.write("\n")
    return path


def lesson(repo_name: str, revision: str, n: int = 1, **overrides) -> dict:
    record = {
        "lesson_id": f"L{n}",
        "lesson_text": f"Lesson number {n}: VALUE in module.py is an int.",
        "task_id": f"tiny__tiny-{n}",
        "repository": repo_name,
        "source_revision": revision,
        "trajectory_pointer": "",
    }
    record.update(overrides)
    return record
