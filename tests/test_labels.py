"""Seam N1: label sign-off (`label-export` / `label-import`) and lesson labels, driven through the CLI.

Builds on the `check` pipeline from test_checks: one source S with targets T1 and T2, lesson L1 at S,
and the fake check runner deciding the proposed labels.
"""

from pathlib import Path

import pytest

from memrev.assumptions import Assumptions
from memrev.labels import LabelStore
from memrev.store import RunStore

from conftest import lesson, write_bank
from test_checks import CHECK, FAIL, OTHER_CHECK, PASS, REPO, Pipeline, assumption
from test_review import read_csv, write_csv

THIRD_CHECK = "python -c 'import module; module.other()'"

VALUE_EXISTS = assumption("L1", CHECK, "module defines VALUE")
HELPER_EXISTS = assumption("L1", OTHER_CHECK, "module defines helper()")


class SignOff(Pipeline):
    def labels(self) -> LabelStore:
        return LabelStore(RunStore.open(self.run_dir))

    def checked(self, *rows: dict, script: dict | None = None) -> None:
        """Seed and accept `rows`, then run drift and check with `script`."""
        self.seed_and_accept(*rows)
        self.script(script or {})
        assert self.drift().exit_code == 0
        assert self.check().exit_code == 0

    def accept_in_review(self) -> None:
        export = self.tmp / "review.csv"
        assert self.memrev("review-export", str(export)).exit_code == 0
        write_csv(export, [dict(row, decision="accept") for row in read_csv(export)])
        result = self.memrev("review-import", str(export), "--reviewer", "rev-1")
        assert result.exit_code == 0, result.err

    def export(self, name: str = "labels.csv") -> list[dict]:
        path = self.tmp / name
        result = self.memrev("label-export", str(path))
        assert result.exit_code == 0, result.err
        return read_csv(path)

    def sign(self, rows: list[dict], reviewer: str = "rev-1", *extra: str, name: str = "signed.csv"):
        path = write_csv(self.tmp / name, rows)
        return self.memrev("label-import", str(path), "--reviewer", reviewer, *extra)

    def finals(self) -> dict[tuple[str, str], tuple[str, str]]:
        """(assumption_id, pair_id) -> (final label, reviewer id) for current final labels."""
        return {(f.assumption_id, f.pair_id): (f.label, f.reviewer_id) for f in self.labels().final_labels()}


@pytest.fixture
def signoff(cli, run_dir, tmp_path) -> SignOff:
    return SignOff(cli, run_dir, tmp_path)


def decide(rows: list[dict], decision: str, **where) -> list[dict]:
    for row in rows:
        if all(row[k] == v for k, v in where.items()):
            row["decision"] = decision
    return rows


# Sign-off round trip ----------------------------------------------------


def test_label_export_lists_every_proposed_label_and_accepting_it_makes_it_final(signoff):
    signoff.checked(VALUE_EXISTS, script={CHECK: {signoff.t1: FAIL}})

    rows = signoff.export()

    assert {(r["assumption_id"], r["pair_id"], r["proposed_label"], r["decision"]) for r in rows} == {
        ("L1#1", signoff.pair1, "contradicted", ""),
        ("L1#1", signoff.pair2, "supported within scope", ""),
    }
    assert {r["runs_at_T"] for r in rows if r["pair_id"] == signoff.pair1} == {f"{FAIL}, {FAIL}, {FAIL}"}

    result = signoff.sign(decide(rows, "accept"))

    assert result.exit_code == 0, result.err
    assert "label-import: 2 accepted, 0 downgraded, 0 sent back, 0 unchanged, 0 not signed off (reviewer rev-1)" in (
        result.out
    )
    assert signoff.finals() == {
        ("L1#1", signoff.pair1): ("contradicted", "rev-1"),
        ("L1#1", signoff.pair2): ("supported within scope", "rev-1"),
    }
    final = signoff.labels().final_labels()[0]
    assert final.assumption_hash == signoff.current_hash("L1#1")


def test_a_reviewer_can_downgrade_a_proposed_label_to_inconclusive(signoff):
    signoff.checked(VALUE_EXISTS, script={CHECK: {signoff.t1: FAIL}})
    rows = decide(signoff.export(), "accept")
    decide(rows, "inconclusive", pair_id=signoff.pair1)

    result = signoff.sign(rows)

    assert "1 accepted, 1 downgraded" in result.out
    final = {f.pair_id: f for f in signoff.labels().final_labels()}[signoff.pair1]
    assert (final.proposed_label, final.label, final.action) == ("contradicted", "inconclusive", "downgraded")
    assert final.reason == "downgraded by reviewer"


@pytest.mark.parametrize(
    "t1_runs, decision",
    [(FAIL, "supported within scope"), (PASS, "contradicted"), ([PASS, FAIL, PASS], "contradicted")],
    ids=["contradicted to supported", "supported to contradicted", "inconclusive to contradicted"],
)
def test_a_direct_flip_of_the_proposed_label_rejects_the_whole_file(signoff, t1_runs, decision):
    signoff.checked(VALUE_EXISTS, script={CHECK: {signoff.t1: t1_runs}})
    rows = decide(signoff.export(), "accept")
    decide(rows, decision, pair_id=signoff.pair1)

    result = signoff.sign(rows)

    assert result.exit_code == 2
    assert "nothing was imported" in result.err
    assert "rewrite" in result.err  # points the reviewer at the allowed route
    assert signoff.finals() == {}


def test_naming_the_proposed_label_or_inconclusive_works_like_accept_and_downgrade(signoff):
    signoff.checked(VALUE_EXISTS, script={CHECK: {signoff.t1: FAIL}})
    rows = decide(signoff.export(), "contradicted", pair_id=signoff.pair1)
    decide(rows, "inconclusive", pair_id=signoff.pair2)

    result = signoff.sign(rows)

    assert result.exit_code == 0, result.err
    assert "1 accepted, 1 downgraded" in result.out
    assert signoff.finals() == {
        ("L1#1", signoff.pair1): ("contradicted", "rev-1"),
        ("L1#1", signoff.pair2): ("inconclusive", "rev-1"),
    }


def test_changing_the_check_without_sending_it_back_is_rejected(signoff):
    signoff.checked(VALUE_EXISTS)
    rows = decide(signoff.export(), "accept")
    rows[0]["check_command"] = OTHER_CHECK

    result = signoff.sign(rows)

    assert result.exit_code == 2
    assert 'only "rewrite" may change the check' in result.err
    assert signoff.finals() == {}


def test_a_sign_off_file_with_missing_duplicate_or_unknown_rows_is_rejected_as_a_whole(signoff):
    signoff.checked(VALUE_EXISTS)
    rows = decide(signoff.export(), "accept")
    unknown = dict(rows[0], pair_id="nope..nope")

    result = signoff.sign([rows[0], rows[0], unknown])

    assert result.exit_code == 2
    assert f"duplicate rows: L1#1 on pair {signoff.pair1}" in result.err
    assert f"missing rows: L1#1 on pair {signoff.pair2}" in result.err
    assert "no proposed label for L1#1 on pair nope..nope" in result.err
    assert signoff.finals() == {}


def test_an_unknown_decision_is_rejected(signoff):
    signoff.checked(VALUE_EXISTS)
    rows = decide(signoff.export(), "maybe")

    result = signoff.sign(rows)

    assert result.exit_code == 2
    assert 'decision "maybe"' in result.err


def test_the_reviewer_id_is_required(signoff):
    signoff.checked(VALUE_EXISTS)
    path = write_csv(signoff.tmp / "signed.csv", decide(signoff.export(), "accept"))

    assert signoff.memrev("label-import", str(path)).exit_code != 0
    assert signoff.memrev("label-import", str(path), "--reviewer", " ").exit_code == 2
    assert signoff.finals() == {}


def test_reimporting_an_exported_sign_off_changes_nothing(signoff):
    signoff.checked(VALUE_EXISTS, script={CHECK: {signoff.t1: FAIL}})
    rows = decide(signoff.export(), "accept")
    decide(rows, "inconclusive", pair_id=signoff.pair2)
    signoff.sign(rows)

    again = signoff.export("again.csv")
    result = signoff.sign(again, "rev-2", name="again-signed.csv")

    assert {r["decision"] for r in again} == {"accept", "inconclusive"}
    assert "0 accepted, 0 downgraded, 0 sent back, 2 unchanged" in result.out
    assert signoff.finals() == {
        ("L1#1", signoff.pair1): ("contradicted", "rev-1"),
        ("L1#1", signoff.pair2): ("inconclusive", "rev-1"),
    }


# Send back for a rewritten check ----------------------------------------


def test_sending_an_assumption_back_rewrites_its_check_and_returns_it_to_review_and_rerun(signoff):
    signoff.checked(VALUE_EXISTS, script={CHECK: {signoff.t1: FAIL}})
    old_hash = signoff.current_hash("L1#1")
    rows = decide(signoff.export(), "accept")
    decide(rows, "rewrite", pair_id=signoff.pair1)
    for row in rows:
        row["check_command"] = OTHER_CHECK

    result = signoff.sign(rows)

    assert result.exit_code == 0, result.err
    assert "0 accepted, 0 downgraded, 2 sent back" in result.out
    assert "sent back L1#1" in result.out
    store = RunStore.open(signoff.run_dir)
    sent_back = Assumptions(store).get("L1#1")
    assert (str(sent_back.status), sent_back.content.check_command) == ("pending", OTHER_CHECK)
    assert sent_back.hash != old_hash
    decisions = store.conn.execute(
        "SELECT assumption_hash, decision, reviewer_id FROM review_decisions ORDER BY rowid"
    ).fetchall()
    assert decisions[-1] == (sent_back.hash, "sent back", "rev-1")
    assert signoff.finals() == {}
    assert signoff.export("after.csv") == []  # nothing to sign off until it is reviewed and rerun

    signoff.accept_in_review()
    signoff.script({OTHER_CHECK: {signoff.t1: PASS}})
    signoff.check()

    rerun = signoff.export("rerun.csv")
    assert {(r["pair_id"], r["proposed_label"], r["check_command"]) for r in rerun} == {
        (signoff.pair1, "supported within scope", OTHER_CHECK),
        (signoff.pair2, "supported within scope", OTHER_CHECK),
    }


def test_rewrite_without_a_rewritten_check_is_rejected(signoff):
    signoff.checked(VALUE_EXISTS)
    rows = decide(signoff.export(), "rewrite", pair_id=signoff.pair1)

    result = signoff.sign(rows)

    assert result.exit_code == 2
    assert "rewrite needs a rewritten check_command or asserted_target" in result.err


def test_two_different_rewrites_of_one_assumption_are_rejected(signoff):
    signoff.checked(VALUE_EXISTS)
    rows = decide(signoff.export(), "rewrite")
    rows[0]["check_command"] = OTHER_CHECK
    rows[1]["check_command"] = THIRD_CHECK

    result = signoff.sign(rows)

    assert result.exit_code == 2
    assert "L1#1 is rewritten in two different ways" in result.err


def test_a_row_exported_before_the_assumption_changed_is_rejected(signoff):
    signoff.checked(VALUE_EXISTS)
    rows = decide(signoff.export(), "accept")
    rows[0]["hash"] = "0" * 64

    result = signoff.sign(rows)

    assert result.exit_code == 2
    assert "L1#1 has changed since this file was exported; export again" in result.err


def test_editing_an_assumption_in_review_makes_its_final_labels_stale(signoff):
    signoff.checked(VALUE_EXISTS)
    signoff.sign(decide(signoff.export(), "accept"))
    old_hash = signoff.current_hash("L1#1")
    export = signoff.tmp / "edit.csv"
    signoff.memrev("review-export", str(export))
    rows = read_csv(export)
    rows[0]["statement"] = "module still defines VALUE"
    write_csv(export, rows)
    assert signoff.memrev("review-import", str(export), "--reviewer", "rev-1").exit_code == 0

    assert signoff.finals() == {}
    stale = signoff.labels().final_labels(include_stale=True)
    assert {(f.assumption_hash, f.stale) for f in stale} == {(old_hash, True)}


# Lesson labels ----------------------------------------------------------


def lesson_labels(signoff) -> dict[tuple[str, str], tuple[str, bool]]:
    """(lesson_id, pair_id) -> (lesson label, scored)."""
    return {(l.lesson_id, l.pair_id): (l.label, l.scored) for l in signoff.labels().lesson_labels()}


def test_a_lesson_is_contradicted_if_any_assumption_is_and_supported_only_if_all_are(signoff):
    signoff.checked(VALUE_EXISTS, HELPER_EXISTS, script={CHECK: {signoff.t1: FAIL}})
    signoff.sign(decide(signoff.export(), "accept"))

    result = signoff.memrev("lesson-labels")

    assert result.exit_code == 0, result.err
    assert lesson_labels(signoff) == {
        ("L1", signoff.pair1): ("contradicted", True),
        ("L1", signoff.pair2): ("supported within scope", True),
    }
    l1_pair1 = {(l.lesson_id, l.pair_id): l for l in signoff.labels().lesson_labels()}[("L1", signoff.pair1)]
    assert l1_pair1.assumptions == (
        ("L1#1", signoff.current_hash("L1#1")),
        ("L1#2", signoff.current_hash("L1#2")),
    )
    assert "supported within scope: 1, contradicted: 1, inconclusive: 0 (excluded from metrics)" in result.out


def test_a_lesson_with_an_inconclusive_and_no_contradicted_assumption_is_inconclusive_and_not_scored(signoff):
    signoff.checked(VALUE_EXISTS, HELPER_EXISTS, script={CHECK: {signoff.t1: [PASS, FAIL, PASS]}})
    signoff.sign(decide(signoff.export(), "accept"))

    result = signoff.memrev("lesson-labels")

    assert lesson_labels(signoff)[("L1", signoff.pair1)] == ("inconclusive", False)
    assert "inconclusive: 1 (excluded from metrics)" in result.out
    assert [(l.lesson_id, l.pair_id) for l in signoff.labels().scored_lesson_labels()] == [("L1", signoff.pair2)]


def test_an_assumption_invalid_at_S_keeps_its_lesson_from_being_supported(signoff):
    signoff.checked(VALUE_EXISTS, HELPER_EXISTS, script={CHECK: {signoff.s: FAIL}})
    signoff.sign(decide(signoff.export(), "accept"))

    assert lesson_labels(signoff) == {
        ("L1", signoff.pair1): ("inconclusive", False),
        ("L1", signoff.pair2): ("inconclusive", False),
    }


def test_a_lesson_gets_no_label_until_every_assumption_is_checked_and_signed_off(signoff):
    signoff.checked(VALUE_EXISTS, HELPER_EXISTS, script={CHECK: {signoff.t1: FAIL}})
    rows = decide(signoff.export(), "accept", assumption_id="L1#1")
    decide(rows, "accept", assumption_id="L1#2", pair_id=signoff.pair2)
    signoff.sign(rows)

    result = signoff.memrev("lesson-labels")

    assert lesson_labels(signoff) == {("L1", signoff.pair2): ("supported within scope", True)}
    assert "awaiting check or sign-off: 1" in result.out


def test_a_lesson_with_a_pending_assumption_gets_no_label(signoff):
    signoff.checked(VALUE_EXISTS, HELPER_EXISTS)
    rows = decide(signoff.export(), "accept")
    decide(rows, "rewrite", assumption_id="L1#2")
    for row in rows:
        if row["assumption_id"] == "L1#2":
            row["check_command"] = THIRD_CHECK
    signoff.sign(rows)

    assert lesson_labels(signoff) == {}


def test_lessons_without_a_checkable_assumption_stay_in_the_bank_are_counted_and_get_no_label(signoff):
    bank = write_bank(signoff.tmp / "more.jsonl", [lesson(REPO, signoff.s, 2), lesson(REPO, signoff.s, 3)])
    assert signoff.memrev("import", str(bank)).exit_code == 0
    vague = assumption("L2", "", "the module is tidy", atype="uncheckable")
    signoff.checked(VALUE_EXISTS, vague)
    signoff.sign(decide(signoff.export(), "accept"))

    result = signoff.memrev("lesson-labels")

    assert {lesson_id for lesson_id, _ in lesson_labels(signoff)} == {"L1"}
    assert signoff.labels().lessons_without_checkable_assumption() == ["L2", "L3"]
    assert "lesson-labels: 3 lessons in the bank, 2 with no checkable assumption (kept, not scored)" in result.out
    assert len(RunStore.open(signoff.run_dir).lessons()) == 3


def test_a_lesson_on_a_pair_dropped_by_the_drift_guard_gets_no_label_there(signoff):
    signoff.checked(VALUE_EXISTS, script={"pytest tests/test_sanity.py": {signoff.t2: FAIL}})
    signoff.sign(decide(signoff.export(), "accept"))

    assert lesson_labels(signoff) == {("L1", signoff.pair1): ("supported within scope", True)}


# Second reviewer ---------------------------------------------------------


@pytest.fixture
def two_signed(signoff) -> SignOff:
    """L1#1 contradicted and L1#2 supported at pair 1, both supported at pair 2, all accepted by rev-1."""
    signoff.checked(VALUE_EXISTS, HELPER_EXISTS, script={CHECK: {signoff.t1: FAIL}})
    assert signoff.sign(decide(signoff.export(), "accept")).exit_code == 0
    return signoff


def sample(signoff, pair_id: str, decisions: dict[str, str]) -> list[dict]:
    """The second reviewer's sample: the rows of `pair_id`, with fresh decisions."""
    rows = [r for r in signoff.export("for-second.csv") if r["pair_id"] == pair_id]
    for row in rows:
        row["decision"] = decisions[row["assumption_id"]]
    return rows


def test_a_second_reviewers_sample_reports_agreement_and_disagreements_become_inconclusive(two_signed):
    s = two_signed
    rows = sample(s, s.pair1, {"L1#1": "accept", "L1#2": "inconclusive"})

    result = s.sign(rows, "rev-2", "--second", name="second.csv")

    assert result.exit_code == 0, result.err
    assert "label-agreement: 1 of 2 sampled labels agree (50%) (second reviewer rev-2)" in result.out
    assert f"disagree L1#2 on pair {s.pair1}: rev-1 supported within scope, rev-2 inconclusive" in result.out
    finals = {(f.assumption_id, f.pair_id): f for f in s.labels().final_labels()}
    disagreed = finals[("L1#2", s.pair1)]
    assert (disagreed.label, disagreed.reason) == ("inconclusive", "reviewers disagree")
    assert (disagreed.reviewer_label, disagreed.second_label, disagreed.second_reviewer_id) == (
        "supported within scope", "inconclusive", "rev-2",
    )  # fmt: skip
    agreed = finals[("L1#1", s.pair1)]
    assert (agreed.label, agreed.second_label) == ("contradicted", "contradicted")
    assert finals[("L1#1", s.pair2)].second_label is None  # not in the sample
    assert s.labels().reviewer_agreement() == (1, 2)


def test_a_disagreement_survives_the_first_reviewer_signing_off_again(two_signed):
    s = two_signed
    s.sign(sample(s, s.pair1, {"L1#1": "accept", "L1#2": "inconclusive"}), "rev-2", "--second", name="second.csv")

    s.sign(decide(s.export("again.csv"), "accept"), "rev-1", name="again-signed.csv")

    assert s.finals()[("L1#2", s.pair1)] == ("inconclusive", "rev-1")


@pytest.mark.parametrize(
    "decision, message",
    [("rewrite", "a second reviewer can only accept or downgrade"), ("supported within scope", "would flip")],
)
def test_a_second_reviewer_cannot_send_back_or_flip(two_signed, decision, message):
    s = two_signed
    rows = sample(s, s.pair1, {"L1#1": decision, "L1#2": "accept"})
    if decision == "rewrite":
        rows[0]["check_command"] = THIRD_CHECK

    result = s.sign(rows, "rev-2", "--second", name="second.csv")

    assert result.exit_code == 2
    assert message in result.err
    assert all(f.second_label is None for f in s.labels().final_labels())


def test_a_second_review_needs_a_first_sign_off_and_another_reviewer(signoff):
    signoff.checked(VALUE_EXISTS)
    rows = decide(signoff.export(), "accept")

    unsigned = signoff.sign(rows, "rev-2", "--second", name="second.csv")
    signoff.sign(rows)
    same = signoff.sign(rows, "rev-1", "--second", name="same.csv")

    assert unsigned.exit_code == 2
    assert "has no first sign-off yet" in unsigned.err
    assert same.exit_code == 2
    assert "rev-1 signed off" in same.err and "a second reviewer must be someone else" in same.err
