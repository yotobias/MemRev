"""Seam N1: seeding assumptions and the review CSV round trip, driven through the command-line tool."""

import csv
from pathlib import Path

import pytest

from memrev import assumptions as assumptions_module
from memrev.assumptions import Assumptions
from memrev.store import RunStore

from conftest import lesson, write_bank

SEED_COLUMNS = [
    "lesson_id",
    "statement",
    "assumption_type",
    "scope",
    "code_pointers",
    "check_command",
    "asserted_target",
]

GET_VALUE = {
    "lesson_id": "L1",
    "statement": "module.VALUE is 0",
    "assumption_type": "config or default value",
    "scope": "module.py",
    "code_pointers": "module.py:1",
    "check_command": "python -c 'import module; assert module.VALUE == 0'",
    "asserted_target": "module.VALUE",
}
VALUE_EXISTS = {
    "lesson_id": "L1",
    "statement": "module defines VALUE",
    "assumption_type": "symbol exists",
    "scope": "module.py",
    "code_pointers": "module.py:1; module.py",
    "check_command": "python -c 'import module; module.VALUE'",
    "asserted_target": "module.VALUE",
}
VAGUE = {
    "lesson_id": "L2",
    "statement": "the module is easy to read",
    "assumption_type": "uncheckable",
    "scope": "",
    "code_pointers": "",
    "check_command": "",
    "asserted_target": "",
}


def write_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> Path:
    columns = columns or list(rows[0])
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture
def run(memrev, tiny_repo, tmp_path):
    """A run with lessons L1 and L2 imported; returns a helper calling `memrev --run <run_dir> ...`."""
    assert memrev("init", "--repo", f"tiny/tiny={tiny_repo.path}").exit_code == 0
    bank = write_bank(
        tmp_path / "bank.jsonl",
        [lesson("tiny/tiny", tiny_repo.commits[0], 1), lesson("tiny/tiny", tiny_repo.commits[0], 2)],
    )
    assert memrev("import", str(bank)).exit_code == 0
    return memrev


@pytest.fixture
def seeded(run, tmp_path):
    seed = write_csv(tmp_path / "seed.csv", [GET_VALUE, VALUE_EXISTS, VAGUE])
    result = run("seed-assumptions", str(seed))
    assert result.exit_code == 0, result.err
    return run


def export(run, tmp_path: Path, name: str = "review.csv") -> list[dict]:
    out = tmp_path / name
    result = run("review-export", str(out))
    assert result.exit_code == 0, result.err
    return read_csv(out)


def test_seeded_assumptions_appear_in_the_review_export_as_pending(seeded, tmp_path):
    rows = export(seeded, tmp_path)

    assert [(r["lesson_id"], r["statement"]) for r in rows] == [
        ("L1", "module.VALUE is 0"),
        ("L1", "module defines VALUE"),
        ("L2", "the module is easy to read"),
    ]
    assert len({r["assumption_id"] for r in rows}) == 3
    assert all(r["status"] == "pending" and r["decision"] == "" for r in rows)
    assert rows[1]["code_pointers"] == "module.py:1; module.py"
    assert rows[1]["asserted_target"] == "module.VALUE"
    assert all(len(r["hash"]) == 64 for r in rows)
    assert len({r["hash"] for r in rows}) == 3


def test_seeding_the_same_csv_twice_does_not_duplicate_assumptions(seeded, tmp_path):
    seed = write_csv(tmp_path / "seed.csv", [GET_VALUE, VALUE_EXISTS, VAGUE])

    result = seeded("seed-assumptions", str(seed))

    assert result.exit_code == 0
    assert "0 added, 3 already present" in result.out
    assert len(export(seeded, tmp_path)) == 3


@pytest.mark.parametrize(
    "bad, message",
    [
        ({**VAGUE, "lesson_id": "L99"}, 'lesson "L99" is not in the run'),
        ({**VAGUE, "assumption_type": "claim"}, 'assumption_type "claim" is not one of'),
        ({**VAGUE, "statement": "  "}, "statement is empty"),
    ],
)
def test_a_seed_csv_with_a_bad_row_is_rejected_as_a_whole(run, tmp_path, bad, message):
    seed = write_csv(tmp_path / "seed.csv", [GET_VALUE, bad])

    result = run("seed-assumptions", str(seed))

    assert result.exit_code == 2
    assert "line 3" in result.err and message in result.err
    assert export(run, tmp_path) == []


# review-import -------------------------------------------------------------


def review(run, tmp_path: Path, rows: list[dict], reviewer: str = "alice", name: str = "reviewed.csv"):
    path = write_csv(tmp_path / name, rows)
    return run("review-import", str(path), "--reviewer", reviewer)


def by_statement(rows: list[dict]) -> dict[str, dict]:
    return {r["statement"]: r for r in rows}


def test_importing_the_export_unchanged_changes_nothing(seeded, tmp_path):
    rows = export(seeded, tmp_path)

    result = review(seeded, tmp_path, rows)

    assert result.exit_code == 0, result.err
    assert "0 accepted, 0 edited, 0 rejected, 3 unchanged" in result.out
    assert export(seeded, tmp_path, "again.csv") == rows


def test_review_import_requires_a_reviewer_id(seeded, tmp_path):
    path = write_csv(tmp_path / "reviewed.csv", export(seeded, tmp_path))

    result = seeded("review-import", str(path))

    assert result.exit_code != 0
    assert "--reviewer" in result.err


def test_accepted_assumptions_are_reviewed_and_rejected_ones_keep_the_reviewer_id(seeded, tmp_path):
    rows = by_statement(export(seeded, tmp_path))
    rows["module.VALUE is 0"]["decision"] = "accept"
    rows["the module is easy to read"]["decision"] = "reject"

    result = review(seeded, tmp_path, list(rows.values()), reviewer="alice")

    assert result.exit_code == 0, result.err
    assert "1 accepted, 0 edited, 1 rejected, 1 unchanged" in result.out
    after = by_statement(export(seeded, tmp_path, "after.csv"))
    assert after["module.VALUE is 0"]["status"] == "accepted"
    assert after["module.VALUE is 0"]["reviewer_id"] == "alice"
    assert after["the module is easy to read"]["status"] == "rejected"
    assert after["the module is easy to read"]["reviewer_id"] == "alice"
    assert after["module defines VALUE"]["status"] == "pending"
    assert after["module defines VALUE"]["reviewer_id"] == ""
    assert "accepted L1#1" in result.out and "rejected L2#1" in result.out


def test_only_accepted_assumptions_enter_the_reviewed_set(seeded, run_dir, tmp_path):
    rows = by_statement(export(seeded, tmp_path))
    rows["module.VALUE is 0"]["decision"] = "accept"
    rows["the module is easy to read"]["decision"] = "reject"
    review(seeded, tmp_path, list(rows.values()))

    reviewed = Assumptions(RunStore.open(run_dir)).reviewed()

    assert [a.content.statement for a in reviewed] == ["module.VALUE is 0"]


def test_reimporting_a_rejection_by_the_same_decision_is_unchanged(seeded, tmp_path):
    rows = by_statement(export(seeded, tmp_path))
    rows["the module is easy to read"]["decision"] = "reject"
    review(seeded, tmp_path, list(rows.values()))

    result = review(seeded, tmp_path, export(seeded, tmp_path, "second.csv"), reviewer="bob")

    assert "0 accepted, 0 edited, 0 rejected, 3 unchanged" in result.out
    after = by_statement(export(seeded, tmp_path, "after.csv"))
    assert after["the module is easy to read"]["reviewer_id"] == "alice"


@pytest.mark.parametrize(
    "spoil, message",
    [
        (lambda rows: rows[:-1], "missing rows for assumption ids: L2#1"),
        (lambda rows: rows + [dict(rows[0])], "duplicate assumption ids: L1#1"),
        (lambda rows: rows + [{**rows[0], "assumption_id": "L7#1"}], 'unknown assumption id "L7#1"'),
        (lambda rows: [{**rows[0], "decision": "maybe"}, *rows[1:]], 'decision "maybe" must be'),
        (lambda rows: [{**rows[0], "assumption_type": "vibe"}, *rows[1:]], 'assumption_type "vibe" is not one of'),
        (
            lambda rows: [{**rows[0], "decision": "accept", "check_command": ""}, *rows[1:]],
            "an accepted checkable assumption needs check_command and asserted_target",
        ),
    ],
)
def test_a_review_csv_with_bad_rows_is_rejected_as_a_whole(seeded, tmp_path, spoil, message):
    rows = export(seeded, tmp_path)
    rows[1]["decision"] = "accept"  # a valid change that must not be applied
    rows = spoil(rows)

    result = review(seeded, tmp_path, rows)

    assert result.exit_code == 2
    assert "rejected, nothing was imported" in result.err
    assert message in result.err
    assert all(r["status"] == "pending" for r in export(seeded, tmp_path, "after.csv"))


def test_an_accepted_uncheckable_assumption_needs_no_check(seeded, tmp_path):
    rows = by_statement(export(seeded, tmp_path))
    rows["the module is easy to read"]["decision"] = "accept"

    result = review(seeded, tmp_path, list(rows.values()))

    assert result.exit_code == 0, result.err
    assert "1 accepted" in result.out


def test_editing_an_accepted_assumption_gives_it_a_new_hash_and_keeps_its_id(seeded, tmp_path):
    rows = by_statement(export(seeded, tmp_path))
    rows["module.VALUE is 0"]["decision"] = "accept"
    review(seeded, tmp_path, list(rows.values()))
    rows = by_statement(export(seeded, tmp_path, "second.csv"))
    old = rows["module.VALUE is 0"]
    edited = {**old, "statement": "module.VALUE is the int 0", "decision": "accept"}
    rows["module.VALUE is 0"] = edited

    result = review(seeded, tmp_path, list(rows.values()), reviewer="bob")

    assert result.exit_code == 0, result.err
    assert "0 accepted, 1 edited, 0 rejected, 2 unchanged" in result.out
    assert f"edited L1#1 (hash {old['hash'][:12]} -> " in result.out
    after = by_statement(export(seeded, tmp_path, "after.csv"))["module.VALUE is the int 0"]
    assert after["assumption_id"] == old["assumption_id"]
    assert after["hash"] != old["hash"]
    assert (after["status"], after["reviewer_id"]) == ("accepted", "bob")


def test_editing_without_a_decision_returns_the_assumption_to_pending(seeded, tmp_path):
    rows = by_statement(export(seeded, tmp_path))
    rows["module.VALUE is 0"]["decision"] = "accept"
    review(seeded, tmp_path, list(rows.values()))
    rows = by_statement(export(seeded, tmp_path, "second.csv"))
    rows["module.VALUE is 0"].update(scope="module.py, CPython only", decision="")

    result = review(seeded, tmp_path, list(rows.values()))

    assert "0 accepted, 1 edited, 0 rejected, 2 unchanged" in result.out
    after = by_statement(export(seeded, tmp_path, "after.csv"))["module.VALUE is 0"]
    assert after["status"] == "pending"


def test_code_pointer_spacing_is_not_an_edit(seeded, tmp_path):
    rows = by_statement(export(seeded, tmp_path))
    rows["module defines VALUE"]["code_pointers"] = "module.py:1 ;module.py"

    result = review(seeded, tmp_path, list(rows.values()))

    assert "3 unchanged" in result.out


@pytest.fixture
def downstream_scores(monkeypatch):
    """A downstream table keyed by assumption hash, registered the way tickets 05, 06 and 10 will."""
    monkeypatch.setattr(assumptions_module, "DOWNSTREAM_TABLES", [])
    assumptions_module.register_downstream("test_scores")

    def create(store: RunStore) -> None:
        store.conn.execute(
            "CREATE TABLE test_scores (assumption_id TEXT, assumption_hash TEXT, "
            "score INTEGER, stale INTEGER NOT NULL DEFAULT 0)"
        )
        store.conn.commit()

    return create


def test_an_edit_marks_downstream_rows_of_the_old_hash_stale(seeded, run_dir, tmp_path, downstream_scores):
    rows = by_statement(export(seeded, tmp_path))
    target = rows["module.VALUE is 0"]
    other = rows["module defines VALUE"]
    store = RunStore.open(run_dir)
    downstream_scores(store)
    store.conn.executemany(
        "INSERT INTO test_scores (assumption_id, assumption_hash, score) VALUES (?, ?, ?)",
        [(target["assumption_id"], target["hash"], 1), (other["assumption_id"], other["hash"], 2)],
    )
    store.conn.commit()
    target.update(asserted_target="module.VALUE (int)", decision="accept")

    review(seeded, tmp_path, list(rows.values()))

    stale = dict(RunStore.open(run_dir).conn.execute("SELECT score, stale FROM test_scores"))
    assert stale == {1: 1, 2: 0}
    assert Assumptions(RunStore.open(run_dir)).is_stale(target["assumption_id"], target["hash"])


def test_reverting_an_edit_makes_the_original_rows_current_again(seeded, run_dir, tmp_path, downstream_scores):
    original = by_statement(export(seeded, tmp_path))
    target = original["module.VALUE is 0"]
    store = RunStore.open(run_dir)
    downstream_scores(store)
    store.conn.execute(
        "INSERT INTO test_scores (assumption_id, assumption_hash, score) VALUES (?, ?, 1)",
        (target["assumption_id"], target["hash"]),
    )
    store.conn.commit()
    edited = {k: dict(v) for k, v in original.items()}
    edited["module.VALUE is 0"]["statement"] = "VALUE is zero"
    review(seeded, tmp_path, list(edited.values()), name="edit.csv")

    review(seeded, tmp_path, list(original.values()), name="revert.csv")

    assert RunStore.open(run_dir).conn.execute("SELECT stale FROM test_scores").fetchone() == (0,)
    assert not Assumptions(RunStore.open(run_dir)).is_stale(target["assumption_id"], target["hash"])
