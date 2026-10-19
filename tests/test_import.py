"""Seam N1: the `init` and `import` stages, driven through the command-line tool."""

import pytest

from memrev.store import RunStore

from conftest import lesson, write_bank


def _init(cli, run_dir, tiny_repo):
    assert cli("--run", str(run_dir), "init", "--repo", f"tiny/tiny={tiny_repo.path}").exit_code == 0


def _without(record: dict, field: str) -> dict:
    return {k: v for k, v in record.items() if k != field}


def test_a_repository_path_that_is_not_a_git_clone_is_refused(cli, run_dir, tmp_path):
    not_a_clone = tmp_path / "empty"
    not_a_clone.mkdir()

    result = cli("--run", str(run_dir), "init", "--repo", f"tiny/tiny={not_a_clone}")

    assert result.exit_code != 0
    assert "not a git repository" in result.err


def test_importing_into_a_run_that_does_not_exist_fails_clearly(cli, run_dir, tmp_path):
    bank = write_bank(tmp_path / "bank.jsonl", [])

    result = cli("--run", str(run_dir), "import", str(bank))

    assert result.exit_code != 0
    assert "no run at" in result.err


BAD_LESSONS = {
    "missing lesson text": lambda rev: _without(lesson("tiny/tiny", rev, 9), "lesson_text"),
    "missing trajectory pointer": lambda rev: _without(lesson("tiny/tiny", rev, 9), "trajectory_pointer"),
    "empty task id": lambda rev: lesson("tiny/tiny", rev, 9, task_id=""),
    "unknown repository": lambda rev: lesson("someone/else", rev, 9),
    "source revision not in repository": lambda rev: lesson("tiny/tiny", "f" * 40, 9),
    "abbreviated source revision": lambda rev: lesson("tiny/tiny", rev[:12], 9),
}


@pytest.mark.parametrize("case", BAD_LESSONS)
def test_invalid_lessons_are_rejected_with_reason_invalid_lesson_input(cli, tiny_repo, run_dir, tmp_path, case):
    bad = BAD_LESSONS[case](tiny_repo.commits[1])
    bank = write_bank(tmp_path / "bank.jsonl", [lesson("tiny/tiny", tiny_repo.commits[0], 1), bad])
    _init(cli, run_dir, tiny_repo)

    result = cli("--run", str(run_dir), "import", str(bank))

    assert result.exit_code == 0
    assert "1 accepted" in result.out
    assert "1 rejected" in result.out
    assert "invalid lesson input: 1" in result.out
    store = RunStore.open(run_dir)
    assert [l.lesson_id for l in store.lessons()] == ["L1"]
    [exclusion] = store.exclusions()
    assert (exclusion.stage, exclusion.subject, exclusion.reason) == ("import", "lesson L9", "invalid lesson input")


def test_extra_fields_are_ignored(cli, tiny_repo, run_dir, tmp_path):
    record = lesson("tiny/tiny", tiny_repo.commits[0], 1, model="some-model", score=0.7)
    bank = write_bank(tmp_path / "bank.jsonl", [record])
    _init(cli, run_dir, tiny_repo)

    result = cli("--run", str(run_dir), "import", str(bank))

    assert "1 accepted (1 new), 0 rejected" in result.out
    assert [l.lesson_id for l in RunStore.open(run_dir).lessons()] == ["L1"]


def test_importing_the_same_bank_twice_does_not_duplicate_lessons(cli, tiny_repo, run_dir, tmp_path):
    bank = write_bank(
        tmp_path / "bank.jsonl",
        [
            lesson("tiny/tiny", tiny_repo.commits[0], 1),
            lesson("tiny/tiny", tiny_repo.commits[1], 2),
            lesson("someone/else", tiny_repo.commits[1], 3),
        ],
    )
    _init(cli, run_dir, tiny_repo)

    cli("--run", str(run_dir), "import", str(bank))
    second = cli("--run", str(run_dir), "import", str(bank))

    assert "2 accepted (0 new), 1 rejected" in second.out
    store = RunStore.open(run_dir)
    assert [l.lesson_id for l in store.lessons()] == ["L1", "L2"]
    assert [e.subject for e in store.exclusions()] == ["lesson L3"]


def test_a_lesson_id_reused_with_different_content_is_rejected(cli, tiny_repo, run_dir, tmp_path):
    _init(cli, run_dir, tiny_repo)
    first = write_bank(tmp_path / "first.jsonl", [lesson("tiny/tiny", tiny_repo.commits[0], 1)])
    cli("--run", str(run_dir), "import", str(first))
    changed = lesson("tiny/tiny", tiny_repo.commits[0], 1, lesson_text="Different advice.")
    second = write_bank(tmp_path / "second.jsonl", [changed])

    result = cli("--run", str(run_dir), "import", str(second))

    assert "0 accepted (0 new), 1 rejected" in result.out
    store = RunStore.open(run_dir)
    assert store.lessons()[0].lesson_text == "Lesson number 1: VALUE in module.py is an int."
    assert [(e.subject, e.reason) for e in store.exclusions()] == [("second.jsonl line 1", "invalid lesson input")]


def test_a_lesson_accepted_on_reimport_is_no_longer_excluded(cli, tiny_repo, run_dir, tmp_path):
    bank = write_bank(tmp_path / "bank.jsonl", [lesson("other/tiny", tiny_repo.commits[0], 1)])
    _init(cli, run_dir, tiny_repo)
    cli("--run", str(run_dir), "import", str(bank))
    cli("--run", str(run_dir), "init", "--repo", f"other/tiny={tiny_repo.path}")

    result = cli("--run", str(run_dir), "import", str(bank))

    assert "1 accepted (1 new), 0 rejected" in result.out
    store = RunStore.open(run_dir)
    assert [l.lesson_id for l in store.lessons()] == ["L1"]
    assert store.exclusions() == []


def test_a_line_that_is_not_a_json_object_is_rejected_and_counted(cli, tiny_repo, run_dir, tmp_path):
    bank = write_bank(
        tmp_path / "bank.jsonl",
        [lesson("tiny/tiny", tiny_repo.commits[0], 1), "{not json", "[1, 2]", ""],
    )
    _init(cli, run_dir, tiny_repo)

    result = cli("--run", str(run_dir), "import", str(bank))

    assert "1 accepted" in result.out
    assert "2 rejected" in result.out
    assert "invalid lesson input: 2" in result.out
    exclusions = RunStore.open(run_dir).exclusions()
    assert [e.reason for e in exclusions] == ["invalid lesson input"] * 2
    assert [e.subject for e in exclusions] == ["bank.jsonl line 2", "bank.jsonl line 3"]


def test_imported_lessons_are_stored_in_the_runs_own_database(cli, tiny_repo, run_dir, tmp_path):
    bank = write_bank(
        tmp_path / "bank.jsonl",
        [lesson("tiny/tiny", tiny_repo.commits[0], 1), lesson("tiny/tiny", tiny_repo.commits[2], 2)],
    )

    assert cli("--run", str(run_dir), "init", "--repo", f"tiny/tiny={tiny_repo.path}").exit_code == 0
    result = cli("--run", str(run_dir), "import", str(bank))

    assert result.exit_code == 0
    assert "2 accepted" in result.out
    assert (run_dir / "run.db").is_file()
    assert (run_dir / "work").is_dir()
    stored = RunStore.open(run_dir).lessons()
    assert [(l.lesson_id, l.source_revision) for l in stored] == [
        ("L1", tiny_repo.commits[0]),
        ("L2", tiny_repo.commits[2]),
    ]
    assert stored[0].task_id == "tiny__tiny-1"
    assert stored[0].repository == "tiny/tiny"
    assert stored[0].trajectory_pointer == ""


def test_a_run_inside_a_repository_checkout_is_refused(cli, tiny_repo):
    inside = tiny_repo.path / "runs" / "run-1"

    result = cli("--run", str(inside), "init", "--repo", f"tiny/tiny={tiny_repo.path}")

    assert result.exit_code != 0
    assert "inside a repository checkout" in result.err
    assert not (inside / "run.db").exists()
