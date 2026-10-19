"""Seam N1: the `run-mechanism` stage and the harness, driven through the command-line tool."""

import sqlite3

import pytest

from memrev import harness
from memrev.store import RunStore

from conftest import _git, lesson, write_bank


def _run_with_lessons(cli, run_dir, tmp_path, repo_path, revision, n_lessons):
    assert cli("--run", str(run_dir), "init", "--repo", f"tiny/tiny={repo_path}").exit_code == 0
    bank = write_bank(tmp_path / "bank.jsonl", [lesson("tiny/tiny", revision, n) for n in range(1, n_lessons + 1)])
    assert cli("--run", str(run_dir), "import", str(bank)).exit_code == 0


def _run_mechanism(cli, run_dir, name, source, target):
    return cli(
        "--run", str(run_dir), "run-mechanism", name,
        "--repository", "tiny/tiny", "--source", source, "--target", target,
    )


def test_no_maintenance_keeps_every_lesson_of_the_source_revision(cli, tiny_repo, run_dir, tmp_path):
    s, t = tiny_repo.commits[0], tiny_repo.commits[2]
    _run_with_lessons(cli, run_dir, tmp_path, tiny_repo.path, s, 3)

    result = _run_mechanism(cli, run_dir, "no-maintenance", s, t)

    assert result.exit_code == 0, result.err
    assert "keep: 3" in result.out
    from memrev.harness import recorded_decisions

    decisions = recorded_decisions(RunStore.open(run_dir), "no-maintenance", "tiny/tiny", s, t)
    assert decisions == {"L1": "keep", "L2": "keep", "L3": "keep"}


@pytest.fixture
def two_file_repo(tmp_path):
    """S has module.py and stable.py; T changes only module.py and renames old_name.py."""
    path = tmp_path / "checkouts" / "two-file"
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    (path / "module.py").write_text("VALUE = 0\n")
    (path / "stable.py").write_text("STABLE = True\n")
    (path / "old_name.py").write_text("def helper():\n    return 1\n")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "S")
    s = _git(path, "rev-parse", "HEAD")
    (path / "module.py").write_text("VALUE = 1\n")
    _git(path, "mv", "old_name.py", "new_name.py")
    _git(path, "commit", "-q", "-am", "T")
    t = _git(path, "rev-parse", "HEAD")
    return path, s, t


def test_file_change_invalidation_flags_lessons_whose_supporting_files_changed(
    cli, two_file_repo, run_dir, tmp_path
):
    path, s, t = two_file_repo
    _run_with_lessons(cli, run_dir, tmp_path, path, s, 4)
    store = RunStore.open(run_dir)
    harness.add_supporting_files(store, "L1", ["module.py"])
    harness.add_supporting_files(store, "L2", ["stable.py"])
    harness.add_supporting_files(store, "L3", ["stable.py", "old_name.py"])
    # L4 has no known supporting files.

    result = _run_mechanism(cli, run_dir, "file-change-invalidation", s, t)

    assert result.exit_code == 0, result.err
    assert "flag: 2" in result.out
    decisions = harness.recorded_decisions(RunStore.open(run_dir), "file-change-invalidation", "tiny/tiny", s, t)
    assert decisions == {"L1": "flag", "L2": "keep", "L3": "flag", "L4": "keep"}


def test_run_mechanism_records_cost_per_mechanism_and_pair(cli, tiny_repo, run_dir, tmp_path, monkeypatch):
    s, t1, t2 = tiny_repo.commits
    _run_with_lessons(cli, run_dir, tmp_path, tiny_repo.path, s, 2)

    class Spender:
        def decide(self, view):
            view.cost.count_checks(2)
            view.cost.count_tokens(150)
            return {lesson.lesson_id: harness.Decision.RECHECK for lesson in view.lessons}

    monkeypatch.setitem(harness.MECHANISMS, "spender", Spender())

    result = _run_mechanism(cli, run_dir, "spender", s, t1)
    assert _run_mechanism(cli, run_dir, "no-maintenance", s, t2).exit_code == 0

    assert result.exit_code == 0, result.err
    assert "checks executed: 2" in result.out
    assert "tokens: 150" in result.out
    store = RunStore.open(run_dir)
    spender = harness.recorded_cost(store, "spender", "tiny/tiny", s, t1)
    assert (spender.checks_executed, spender.tokens) == (2, 150)
    assert spender.wall_time_seconds >= 0
    baseline = harness.recorded_cost(store, "no-maintenance", "tiny/tiny", s, t2)
    assert (baseline.checks_executed, baseline.tokens) == (0, 0)
    assert harness.recorded_cost(store, "spender", "tiny/tiny", s, t2) is None


def test_rerunning_a_mechanism_replaces_its_decisions_and_cost_for_that_pair(cli, two_file_repo, run_dir, tmp_path):
    path, s, t = two_file_repo
    _run_with_lessons(cli, run_dir, tmp_path, path, s, 1)
    assert _run_mechanism(cli, run_dir, "file-change-invalidation", s, t).exit_code == 0
    harness.add_supporting_files(RunStore.open(run_dir), "L1", ["module.py"])

    assert _run_mechanism(cli, run_dir, "file-change-invalidation", s, t).exit_code == 0

    store = RunStore.open(run_dir)
    assert harness.recorded_decisions(store, "file-change-invalidation", "tiny/tiny", s, t) == {"L1": "flag"}
    assert harness.recorded_cost(store, "file-change-invalidation", "tiny/tiny", s, t) is not None


BAD_ANSWERS = {
    "a lesson without a decision": lambda ids: {ids[0]: "keep"},
    "a decision for an unknown lesson": lambda ids: {**{i: "keep" for i in ids}, "L99": "keep"},
    "a decision outside keep, recheck, flag, withhold": lambda ids: {i: "delete" for i in ids},
}


@pytest.mark.parametrize("case", BAD_ANSWERS)
def test_a_mechanism_must_return_one_valid_decision_per_lesson(cli, tiny_repo, run_dir, tmp_path, monkeypatch, case):
    s, t = tiny_repo.commits[0], tiny_repo.commits[2]
    _run_with_lessons(cli, run_dir, tmp_path, tiny_repo.path, s, 2)

    class Broken:
        def decide(self, view):
            return BAD_ANSWERS[case]([lesson.lesson_id for lesson in view.lessons])

    monkeypatch.setitem(harness.MECHANISMS, "broken", Broken())

    result = _run_mechanism(cli, run_dir, "broken", s, t)

    assert result.exit_code != 0
    assert "broken" in result.err
    store = RunStore.open(run_dir)
    assert harness.recorded_decisions(store, "broken", "tiny/tiny", s, t) == {}
    assert harness.recorded_cost(store, "broken", "tiny/tiny", s, t) is None


def test_unknown_mechanisms_and_revisions_are_refused(cli, tiny_repo, run_dir, tmp_path):
    s, t = tiny_repo.commits[0], tiny_repo.commits[2]
    _run_with_lessons(cli, run_dir, tmp_path, tiny_repo.path, s, 1)

    unknown_mechanism = _run_mechanism(cli, run_dir, "magic", s, t)
    unknown_target = _run_mechanism(cli, run_dir, "no-maintenance", s, "f" * 40)

    assert unknown_mechanism.exit_code != 0 and "unknown mechanism" in unknown_mechanism.err
    assert unknown_target.exit_code != 0 and "not in repository" in unknown_target.err


SENTINEL = "SECRET-LABEL-7f3a"


def _plant_labels_and_mapping(run_dir, lesson_id):
    """Simulate the tables later tickets add: labels and the constructed-case mapping."""
    store = RunStore.open(run_dir)
    with store.conn:
        store.conn.execute("CREATE TABLE lesson_labels (lesson_id TEXT, label TEXT)")
        store.conn.execute("INSERT INTO lesson_labels VALUES (?, ?)", (lesson_id, f"contradicted {SENTINEL}"))
        store.conn.execute("CREATE TABLE constructed_cases (opaque_id TEXT, provenance TEXT)")
        store.conn.execute("INSERT INTO constructed_cases VALUES (?, ?)", (lesson_id, f"constructed {SENTINEL}"))


def _reachable(root):
    """Every object reachable from `root` through fields, attributes and containers."""
    seen, stack, found = set(), [root], []
    while stack:
        obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        found.append(obj)
        if isinstance(obj, (str, bytes, int, float, bool, type(None))):
            continue
        if isinstance(obj, dict):
            stack.extend(obj.keys())
            stack.extend(obj.values())
        elif isinstance(obj, (list, tuple, set, frozenset)):
            stack.extend(obj)
        else:
            if hasattr(obj, "__dict__"):
                stack.extend(vars(obj).values())
            for slot in getattr(type(obj), "__slots__", ()):
                if hasattr(obj, slot):
                    stack.append(getattr(obj, slot))
    return found


def test_a_mechanism_cannot_reach_labels_or_the_constructed_case_mapping(
    cli, tiny_repo, run_dir, tmp_path, monkeypatch
):
    s, t = tiny_repo.commits[0], tiny_repo.commits[2]
    _run_with_lessons(cli, run_dir, tmp_path, tiny_repo.path, s, 2)
    _plant_labels_and_mapping(run_dir, "L1")
    seen_views = []

    class Spy:
        def decide(self, view):
            seen_views.append(view)
            return {lesson.lesson_id: harness.Decision.KEEP for lesson in view.lessons}

    monkeypatch.setitem(harness.MECHANISMS, "spy", Spy())

    assert _run_mechanism(cli, run_dir, "spy", s, t).exit_code == 0
    [view] = seen_views
    reachable = _reachable(view)
    assert [l.lesson_id for l in view.lessons] == ["L1", "L2"]
    assert not any(isinstance(o, (sqlite3.Connection, sqlite3.Cursor, RunStore)) for o in reachable)
    texts = [str(o) for o in reachable if isinstance(o, (str, bytes)) or hasattr(o, "__fspath__")]
    assert not any(SENTINEL in text for text in texts)
    assert not any(str(run_dir.resolve()) in text for text in texts), "the run directory leaks into the view"
