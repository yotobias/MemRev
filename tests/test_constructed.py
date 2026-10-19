"""Seam N1: the `construct` and `variant-bank` stages with the fake LLM and the fake check runner.

Builds on the `check` pipeline from test_checks: one source S with targets T1 and T2 (each commit
changes module.py), lesson L1 at S, and the fake runner scripting each check per revision.
"""

import pytest

from memrev import constructor, llm
from memrev.assumptions import Assumptions
from memrev.llm import FakeLLM, LLMError
from memrev.store import RunStore

from conftest import _git
from memrev.constructed_lessons import ConstructedLessons
from memrev.labels import LabelStore
from test_checks import FAIL, PASS, Pipeline
from test_review import read_csv, write_csv

STALE_CHECK = "python -c 'import module; assert module.VALUE == 1'"
FLAKY_CHECK = "python -c 'import module; assert module.VALUE < 2'"
CONTROL_CHECK = "python -c 'import module; assert isinstance(module.VALUE, int)'"
OTHER_CONTROL_CHECK = "python -c 'import module; assert module.VALUE > 0'"


def candidate(text: str, check: str, atype: str = "config or default value", pointers=("module.py:1",)) -> dict:
    return {
        "lesson_text": text,
        "statement": f"statement for: {text}",
        "assumption_type": atype,
        "scope": "module.py",
        "code_pointers": list(pointers),
        "check_command": check,
        "asserted_target": "module.VALUE",
    }


STALE = candidate("module.VALUE is 1, so code may rely on that constant.", STALE_CHECK)
FLAKY = candidate("module.VALUE stays below 2 in every configuration.", FLAKY_CHECK)
CONTROL = candidate("module.VALUE is an int, so arithmetic on it is safe.", CONTROL_CHECK)
OTHER_CONTROL = candidate("module.VALUE is positive, so use it as a count.", OTHER_CONTROL_CHECK)


class Construction(Pipeline):
    def __init__(self, cli, run_dir, tmp_path, fake):
        super().__init__(cli, run_dir, tmp_path)
        self.fake = fake

    def construct(self, *args: str):
        return self.memrev("construct", "--runner", f"fake={self.script_path}", *args)

    def store(self) -> RunStore:
        return RunStore.open(self.run_dir)


@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    fake = FakeLLM()
    monkeypatch.setattr(constructor, "make_llm", lambda model: fake)
    monkeypatch.setattr(llm, "sleep", lambda seconds: None)
    return fake


@pytest.fixture
def construction(cli, run_dir, tmp_path, fake_llm) -> Construction:
    c = Construction(cli, run_dir, tmp_path, fake_llm)
    assert c.drift().exit_code == 0
    return c


def stale_drafts(c: Construction, *candidates: dict) -> None:
    c.fake.answer("Draft constructed stale lessons", {"candidates": list(candidates)})


def control_drafts(c: Construction, stale: dict, *controls: dict) -> None:
    c.fake.answer(stale["lesson_text"], {"controls": list(controls)})


# Drafting and the 3/3 gate ----------------------------------------------


def test_a_pair_whose_diff_yields_no_candidate_is_recorded_as_no_behaviour_change_found(construction):
    stale_drafts(construction)

    result = construction.construct("--pair", construction.pair1)

    assert result.exit_code == 0, result.err
    assert construction.exclusions("construct") == {
        f"constructed cases for pair {construction.pair1}": (
            "no behaviour change found", "the S..T diff yielded no candidate",
        ),
    }
    assert "no behaviour change found: 1" in result.out
    # The LLM saw the real S..T diff.
    [request] = construction.fake.calls
    assert "-VALUE = 1" in request.prompt and "+VALUE = 2" in request.prompt


def constructed_assumptions(c: Construction):
    return [a for a in Assumptions(c.store()).all() if a.origin == "construct"]


def test_a_candidate_is_kept_only_if_its_check_passes_3_of_3_at_S_and_fails_3_of_3_at_T(construction):
    c = construction
    broken = candidate("module.VALUE is 7.", "python -c 'assert False'")
    stale_drafts(c, STALE, FLAKY, broken)
    control_drafts(c, STALE)
    c.script({
        STALE_CHECK: {c.s: PASS, c.t1: FAIL},
        FLAKY_CHECK: {c.s: PASS, c.t1: [FAIL, PASS, FAIL]},
        broken["check_command"]: {c.s: FAIL, c.t1: FAIL},
    })
    history = c.tmp / "checkouts" / "history"
    head_before = _git(history, "rev-parse", "HEAD")

    result = c.construct("--pair", c.pair1)

    assert result.exit_code == 0, result.err
    [kept] = constructed_assumptions(c)
    assert (kept.content.statement, kept.content.check_command, str(kept.status)) == (
        STALE["statement"], STALE_CHECK, "pending",
    )
    lesson, pair_id = ConstructedLessons(c.store()).get(kept.lesson_id)
    assert (lesson.lesson_text, lesson.source_revision, pair_id) == (STALE["lesson_text"], c.s, c.pair1)
    # Both gate executions are evidence of the kept assumption.
    runs = c.evidence().evidence(kept.assumption_id)
    assert sorted((r.revision, r.run_index, r.outcome) for r in runs) == sorted(
        [(c.s, i, PASS) for i in (1, 2, 3)] + [(c.t1, i, FAIL) for i in (1, 2, 3)]
    )
    gate_failed = [r for r, _ in c.exclusions("construct").values() if r == "gate failed (constructed)"]
    assert len(gate_failed) == 2
    assert "constructed stale lessons kept: 1, gate failed: 2" in result.out
    # Only advice is written: the repository is untouched.
    assert _git(history, "rev-parse", "HEAD") == head_before
    assert _git(history, "status", "--porcelain") == ""


# Matched controls -------------------------------------------------------


def test_each_kept_stale_lesson_gets_one_matched_control_that_passes_3_of_3_at_S_and_T(construction):
    c = construction
    other_type = candidate("module.VALUE exists in module.py for imports.", CONTROL_CHECK, atype="symbol exists")
    other_file = candidate("stable.VALUE is an int, arithmetic is safe.", CONTROL_CHECK, pointers=("stable.py",))
    too_long = candidate("module.VALUE is an int. " * 12, CONTROL_CHECK)
    stale_drafts(c, STALE)
    control_drafts(c, STALE, other_type, other_file, too_long, OTHER_CONTROL, CONTROL)
    c.script({
        STALE_CHECK: {c.s: PASS, c.t1: FAIL},
        OTHER_CONTROL_CHECK: {c.s: PASS, c.t1: [PASS, PASS, FAIL]},
        CONTROL_CHECK: {c.s: PASS, c.t1: PASS},
    })

    result = c.construct("--pair", c.pair1)

    assert result.exit_code == 0, result.err
    by_statement = {a.content.statement: a for a in constructed_assumptions(c)}
    assert set(by_statement) == {STALE["statement"], CONTROL["statement"]}
    control_lesson, pair_id = ConstructedLessons(c.store()).get(by_statement[CONTROL["statement"]].lesson_id)
    assert (control_lesson.lesson_text, pair_id) == (CONTROL["lesson_text"], c.pair1)
    cases = constructor.case_records(c.store(), c.pair1)
    stale_case = next(r for r in cases if r.role == constructor.STALE)
    controls = [r for r in cases if r.role == constructor.CONTROL]
    assert [(r.status, r.stale_case_key) for r in controls] == [
        ("not matched", stale_case.case_key),
        ("not matched", stale_case.case_key),
        ("not matched", stale_case.case_key),
        ("gate failed", stale_case.case_key),
        ("kept", stale_case.case_key),
    ]
    assert "matched controls: 1, no matched control: 0" in result.out


def test_a_stale_lesson_without_a_passing_control_is_counted_as_no_matched_control(construction):
    c = construction
    stale_drafts(c, STALE)
    control_drafts(c, STALE, CONTROL)
    c.script({STALE_CHECK: {c.s: PASS, c.t1: FAIL}, CONTROL_CHECK: {c.s: PASS, c.t1: FAIL}})

    result = c.construct("--pair", c.pair1)

    assert result.exit_code == 0, result.err
    assert [a.content.statement for a in constructed_assumptions(c)] == [STALE["statement"]]
    reasons = [reason for reason, _ in c.exclusions("construct").values()]
    assert reasons == ["no matched control"]
    assert "constructed stale lessons kept: 1, gate failed: 0" in result.out
    assert "matched controls: 0, no matched control: 1" in result.out


# Review, check and sign-off like natural assumptions ---------------------


def review_all(c: Construction, decision: str = "accept") -> list[dict]:
    export = c.tmp / "review.csv"
    assert c.memrev("review-export", str(export)).exit_code == 0
    rows = read_csv(export)
    write_csv(export, [dict(row, decision=decision) for row in rows])
    result = c.memrev("review-import", str(export), "--reviewer", "rev-1")
    assert result.exit_code == 0, result.err
    return rows


def constructed_pair(c: Construction) -> None:
    """Construct STALE with matched CONTROL on pair 1."""
    stale_drafts(c, STALE)
    control_drafts(c, STALE, CONTROL)
    c.script({STALE_CHECK: {c.s: PASS, c.t1: FAIL}, CONTROL_CHECK: {c.s: PASS, c.t1: PASS}})
    assert c.construct("--pair", c.pair1).exit_code == 0


def test_constructed_lessons_go_through_review_check_and_sign_off_like_natural_ones(construction):
    c = construction
    constructed_pair(c)

    exported = review_all(c)
    stale_id, control_id = (
        next(a.assumption_id for a in constructed_assumptions(c) if a.content.statement == d["statement"])
        for d in (STALE, CONTROL)
    )
    assert {r["assumption_id"]: r["status"] for r in exported} == {stale_id: "pending", control_id: "pending"}

    # The gate's runs are the evidence: `check` reuses them, whatever the runner would say now.
    c.script({}, default="harness error")
    checked = c.check()
    assert checked.exit_code == 0, checked.err
    assert "reused evidence: 2 at S, 2 at T" in checked.out

    labels = c.tmp / "labels.csv"
    assert c.memrev("label-export", str(labels)).exit_code == 0
    rows = read_csv(labels)
    # A constructed lesson is labelled only at the pair it was constructed for.
    assert {(r["assumption_id"], r["pair_id"], r["proposed_label"]) for r in rows} == {
        (stale_id, c.pair1, "contradicted"),
        (control_id, c.pair1, "supported within scope"),
    }
    write_csv(labels, [dict(r, decision="accept") for r in rows])
    signed = c.memrev("label-import", str(labels), "--reviewer", "rev-1")
    assert signed.exit_code == 0, signed.err

    label_store = LabelStore(c.store())
    stale_lesson, control_lesson = (a.split("#")[0] for a in (stale_id, control_id))
    assert {(l.lesson_id, l.pair_id, l.label) for l in label_store.constructed_lesson_report().labels} == {
        (stale_lesson, c.pair1, "contradicted"),
        (control_lesson, c.pair1, "supported within scope"),
    }
    # Natural lesson labels stay natural only.
    natural = label_store.lesson_report()
    assert {l.lesson_id for l in natural.labels} | set(natural.without_checkable_assumption) == {"L1"}


def test_a_constructed_assumption_rejected_in_review_is_not_checked(construction):
    c = construction
    constructed_pair(c)
    review_all(c, decision="reject")

    checked = c.check()

    assert checked.exit_code == 0, checked.err
    assert "check: 0 assumptions checked" in checked.out
