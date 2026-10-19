"""Seam N1: the `pairs` stage, driven through the command-line tool.

Each test builds a tiny real git history with fixed committer dates and a fake
SWE-bench Verified metadata file whose instances point at those commits.
"""

import json
import subprocess
from pathlib import Path

import pytest

from memrev.store import RunStore

from conftest import lesson, write_bank

REPO = "tiny/tiny"
DAY = 86_400
EPOCH = 1_600_000_000


class History:
    """A real git repository whose commits get one-day-apart committer dates."""

    def __init__(self, path: Path):
        self.path = path
        self.day = 0
        path.mkdir(parents=True)
        self._git("init", "-q", "-b", "main")

    def _git(self, *args: str, day: int | None = None) -> str:
        stamp = f"@{EPOCH + (day or 0) * DAY} +0000"
        env = {
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_DATE": stamp,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        }
        result = subprocess.run(
            ["git", "-C", str(self.path), *args], check=True, capture_output=True, text=True, env=env
        )
        return result.stdout.strip()

    def commit(self, branch: str = "main") -> str:
        """Commit on `branch` (an existing branch), one day after the previous commit."""
        self.day += 1
        if branch != "main":
            self._git("checkout", "-q", branch)
        (self.path / "module.py").write_text(f"VALUE = {self.day}\n")
        self._git("add", "module.py")
        self._git("commit", "-q", "-m", f"day {self.day}", day=self.day)
        sha = self._git("rev-parse", "HEAD")
        if branch != "main":
            self._git("checkout", "-q", "main")
        return sha

    def branch_from(self, name: str, sha: str) -> None:
        self._git("branch", name, sha)


@pytest.fixture
def history(tmp_path: Path) -> History:
    return History(tmp_path / "checkouts" / "history")


def instance(n: int, sha: str, version: str, repo: str = REPO) -> dict:
    return {
        "instance_id": f"tiny__tiny-{n}",
        "repo": repo,
        "version": version,
        "base_commit": sha,
        "created_at": "2020-01-01T00:00:00Z",
    }


def write_meta(path: Path, instances: list[dict]) -> Path:
    path.write_text("".join(json.dumps(i) + "\n" for i in instances))
    return path


def setup_run(cli, run_dir, tmp_path, history, sources: list[str], instances: list[dict]) -> Path:
    assert cli("--run", str(run_dir), "init", "--repo", f"{REPO}={history.path}").exit_code == 0
    bank = write_bank(
        tmp_path / "bank.jsonl", [lesson(REPO, sha, n) for n, sha in enumerate(sources, start=1)]
    )
    assert cli("--run", str(run_dir), "import", str(bank)).exit_code == 0
    return write_meta(tmp_path / "meta.jsonl", instances)


def pairs_of(run_dir: Path) -> list[tuple[str, str, str]]:
    store = RunStore.open(run_dir)
    return sorted((p.source_revision, p.target_revision, p.target_role) for p in store.revision_pairs())


def test_a_source_gets_its_nearest_middle_and_furthest_later_instance_as_targets(
    cli, run_dir, tmp_path, history
):
    s, t1, t2, t3, t4, t5 = (history.commit() for _ in range(6))
    meta = setup_run(
        cli, run_dir, tmp_path, history, [s],
        [instance(n, sha, "1.0") for n, sha in enumerate([s, t1, t2, t3, t4, t5])],
    )

    result = cli("--run", str(run_dir), "pairs", "--meta", str(meta))

    assert result.exit_code == 0, result.err
    assert pairs_of(run_dir) == sorted([(s, t1, "nearest"), (s, t3, "middle"), (s, t5, "furthest")])
    assert "pairs: 3 revision pairs from 1 source revision" in result.out


def exclusions_of(run_dir: Path) -> list[tuple[str, str]]:
    return sorted((e.subject, e.reason) for e in RunStore.open(run_dir).exclusions() if e.stage == "pairs")


@pytest.mark.parametrize(
    ("later", "expected_roles"),
    [(1, ["nearest"]), (2, ["nearest", "furthest"]), (3, ["nearest", "middle", "furthest"])],
)
def test_a_source_with_few_later_instances_gets_each_of_them_once(
    cli, run_dir, tmp_path, history, later, expected_roles
):
    s = history.commit()
    targets = [history.commit() for _ in range(later)]
    meta = setup_run(
        cli, run_dir, tmp_path, history, [s],
        [instance(n, sha, "1.0") for n, sha in enumerate([s, *targets])],
    )

    assert cli("--run", str(run_dir), "pairs", "--meta", str(meta)).exit_code == 0

    assert pairs_of(run_dir) == sorted((s, t, role) for t, role in zip(targets, expected_roles))


def test_a_source_without_a_later_instance_in_its_version_is_excluded_with_no_target(
    cli, run_dir, tmp_path, history
):
    earlier, s = history.commit(), history.commit()
    meta = setup_run(
        cli, run_dir, tmp_path, history, [s], [instance(1, earlier, "1.0"), instance(2, s, "1.0")]
    )

    result = cli("--run", str(run_dir), "pairs", "--meta", str(meta))

    assert pairs_of(run_dir) == []
    assert exclusions_of(run_dir) == [(f"source {s}", "no target")]
    assert "pairs: 0 revision pairs from 1 source revision, 1 excluded" in result.out
    assert "no target: 1" in result.out


def test_a_source_that_is_no_swe_bench_base_commit_is_excluded_with_no_target(
    cli, run_dir, tmp_path, history
):
    s, t = history.commit(), history.commit()
    meta = setup_run(cli, run_dir, tmp_path, history, [s], [instance(1, t, "1.0")])

    result = cli("--run", str(run_dir), "pairs", "--meta", str(meta))

    assert result.exit_code == 0
    assert pairs_of(run_dir) == []
    assert exclusions_of(run_dir) == [(f"source {s}", "no target")]
    assert "not the base_commit of any SWE-bench Verified instance" in result.err


def test_a_chosen_target_that_s_is_not_an_ancestor_of_is_excluded_with_ancestry_failed(
    cli, run_dir, tmp_path, history
):
    root = history.commit()
    history.branch_from("side", root)
    s = history.commit()
    t_main = history.commit()
    t_side = history.commit(branch="side")  # later than S by date, but not a descendant of S
    meta = setup_run(
        cli, run_dir, tmp_path, history, [s],
        [instance(1, s, "1.0"), instance(2, t_main, "1.0"), instance(3, t_side, "1.0")],
    )

    result = cli("--run", str(run_dir), "pairs", "--meta", str(meta))

    assert pairs_of(run_dir) == [(s, t_main, "nearest")]
    assert exclusions_of(run_dir) == [(f"pair {s[:12]}..{t_side[:12]}", "ancestry failed")]
    assert "pairs: 1 revision pairs from 1 source revision, 1 excluded" in result.out
    assert "ancestry failed: 1" in result.out


def test_later_instances_of_another_version_are_excluded_as_cross_version_and_never_paired(
    cli, run_dir, tmp_path, history
):
    older, s, t, newer = (history.commit() for _ in range(4))
    meta = setup_run(
        cli, run_dir, tmp_path, history, [s],
        [
            instance(1, older, "0.9"),  # earlier: never a candidate, so not recorded
            instance(2, s, "1.0"),
            instance(3, t, "1.0"),
            instance(4, newer, "1.1"),
            instance(5, newer, "1.0", repo="other/other"),  # another repository: ignored
        ],
    )

    result = cli("--run", str(run_dir), "pairs", "--meta", str(meta))

    assert pairs_of(run_dir) == [(s, t, "nearest")]
    assert exclusions_of(run_dir) == [(f"pair {s[:12]}..{newer[:12]}", "cross-version")]
    assert "cross-version: 1" in result.out
    assert "1.0" in result.err and "1.1" in result.err


def test_rerunning_pairs_gives_the_same_pairs_and_exclusions_without_duplicates(
    cli, run_dir, tmp_path, history
):
    root = history.commit()
    history.branch_from("side", root)
    s, t = history.commit(), history.commit()
    t_side = history.commit(branch="side")
    lonely = history.commit()
    meta = setup_run(
        cli, run_dir, tmp_path, history, [s, s, lonely],  # two lessons share source s
        [
            instance(1, s, "1.0"),
            instance(2, t, "1.0"),
            instance(3, t_side, "1.0"),
            instance(4, lonely, "2.0"),
        ],
    )

    first = cli("--run", str(run_dir), "pairs", "--meta", str(meta))
    pairs_after_first, exclusions_after_first = pairs_of(run_dir), exclusions_of(run_dir)
    second = cli("--run", str(run_dir), "pairs", "--meta", str(meta))

    assert "pairs: 1 revision pairs from 2 source revisions, 3 excluded" in first.out
    assert second.out == first.out
    assert pairs_of(run_dir) == pairs_after_first == [(s, t, "nearest")]
    assert exclusions_of(run_dir) == exclusions_after_first
    assert sorted(reason for _, reason in exclusions_after_first) == [
        "ancestry failed",  # s..t_side
        "cross-version",  # s..lonely
        "no target",  # lonely
    ]


def test_pairs_on_a_run_that_does_not_exist_fails_clearly(cli, run_dir, tmp_path):
    result = cli("--run", str(run_dir), "pairs", "--meta", str(write_meta(tmp_path / "meta.jsonl", [])))

    assert result.exit_code != 0
    assert "no run at" in result.err
