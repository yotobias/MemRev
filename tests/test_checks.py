"""Seam N1: the `drift` and `check` stages with the fake check runner, driven through the command-line tool.

Each test builds a real git history S -> T1 -> T2 (one version, so two revision pairs per
source), a fake SWE-bench metadata file, and a fake-runner script that gives each check
command a scripted outcome per revision and run index.
"""

import json
from pathlib import Path

import pytest

from memrev.assumptions import Assumptions
from memrev.evidence import EvidenceStore
from memrev.store import RunStore

from conftest import lesson, memrev_for, write_bank
from test_pairs import History, instance
from test_review import read_csv, write_csv

REPO = "tiny/tiny"
SANITY = "pytest tests/test_sanity.py"
CHECK = "python -c 'import module; assert module.VALUE'"
OTHER_CHECK = "python -c 'import module; module.helper()'"

PASS, FAIL = "pass", "fail on asserted target"
HARNESS, OUT_OF_SCOPE = "harness error", "out of scope"


def assumption(lesson_id: str, check: str, statement: str, atype: str = "symbol exists") -> dict:
    return {
        "lesson_id": lesson_id,
        "statement": statement,
        "assumption_type": atype,
        "scope": "module.py",
        "code_pointers": "module.py:1",
        "check_command": check if atype != "uncheckable" else "",
        "asserted_target": "module.VALUE" if atype != "uncheckable" else "",
    }


class Pipeline:
    """A run with one source S, two targets T1 (nearest) and T2 (furthest), and lesson L1 at S."""

    def __init__(self, cli, run_dir: Path, tmp_path: Path):
        self.cli, self.run_dir, self.tmp = cli, run_dir, tmp_path
        self.memrev = memrev_for(cli, run_dir)
        history = History(tmp_path / "checkouts" / "history")
        self.s, self.t1, self.t2 = history.commit(), history.commit(), history.commit()
        meta = tmp_path / "meta.jsonl"
        meta.write_text(
            "\n".join(json.dumps(instance(n, sha, "1.0")) for n, sha in enumerate([self.s, self.t1, self.t2], 1))
        )
        self.sanity = tmp_path / "sanity.txt"
        self.sanity.write_text(SANITY + "\n")
        self.script_path = tmp_path / "script.json"
        self.script({})
        assert self.memrev("init", "--repo", f"{REPO}={history.path}").exit_code == 0
        bank = write_bank(tmp_path / "bank.jsonl", [lesson(REPO, self.s, 1)])
        assert self.memrev("import", str(bank)).exit_code == 0
        assert self.memrev("pairs", "--meta", str(meta)).exit_code == 0

    @property
    def pair1(self) -> str:
        return f"{self.s[:12]}..{self.t1[:12]}"

    @property
    def pair2(self) -> str:
        return f"{self.s[:12]}..{self.t2[:12]}"

    def script(self, checks: dict, unavailable: list[str] = (), default: str | None = PASS) -> None:
        """Script the fake runner: {command: {revision: outcome or [outcome per run]}}."""
        body = {"checks": checks, "unavailable": list(unavailable)}
        if default is not None:
            body["default"] = default
        self.script_path.write_text(json.dumps(body))

    def drift(self):
        return self.memrev("drift", "--runner", f"fake={self.script_path}", "--sanity", str(self.sanity))

    def check(self):
        return self.memrev("check", "--runner", f"fake={self.script_path}")

    def seed_and_accept(self, *rows: dict):
        seed = write_csv(self.tmp / "seed.csv", list(rows))
        assert self.memrev("seed-assumptions", str(seed)).exit_code == 0
        export = self.tmp / "review.csv"
        assert self.memrev("review-export", str(export)).exit_code == 0
        rows = read_csv(export)
        for row in rows:
            row["decision"] = "accept"
        write_csv(export, rows)
        result = self.memrev("review-import", str(export), "--reviewer", "rev-1")
        assert result.exit_code == 0, result.err

    def evidence(self) -> EvidenceStore:
        return EvidenceStore(RunStore.open(self.run_dir))

    def current_hash(self, assumption_id: str) -> str:
        return Assumptions(RunStore.open(self.run_dir)).get(assumption_id).hash

    def exclusions(self, stage: str) -> dict[str, tuple[str, str]]:
        store = RunStore.open(self.run_dir)
        return {e.subject: (e.reason, e.detail) for e in store.exclusions() if e.stage == stage}


@pytest.fixture
def pipeline(cli, run_dir, tmp_path) -> Pipeline:
    return Pipeline(cli, run_dir, tmp_path)


# Drift guard ------------------------------------------------------------


def test_drift_guard_keeps_a_pair_whose_sanity_tests_pass_3_of_3_at_S_and_T(pipeline):
    result = pipeline.drift()

    assert result.exit_code == 0, result.err
    assert "drift: 2 revision pairs guarded, 2 kept, 0 dropped" in result.out
    evidence = pipeline.evidence()
    assert evidence.drift_verdicts() == {pipeline.pair1: "kept", pipeline.pair2: "kept"}
    runs = evidence.drift_runs(pipeline.pair1)
    assert sorted((r.revision, r.run_index) for r in runs) == sorted(
        (rev, i) for rev in (pipeline.s, pipeline.t1) for i in (1, 2, 3)
    )
    assert {(r.command, r.outcome) for r in runs} == {(SANITY, PASS)}
    assert pipeline.exclusions("drift") == {}


def test_drift_guard_drops_a_pair_whose_sanity_test_disagrees_with_itself_at_T(pipeline):
    pipeline.script({SANITY: {pipeline.t1: [PASS, FAIL, PASS]}})

    result = pipeline.drift()

    assert result.exit_code == 0, result.err
    assert "1 kept, 1 dropped" in result.out
    assert pipeline.evidence().drift_verdicts() == {pipeline.pair1: "dropped", pipeline.pair2: "kept"}
    reason, detail = pipeline.exclusions("drift")[f"pair {pipeline.pair1}"]
    assert reason == "environment unavailable"
    assert detail.startswith("T:") and f"{PASS}, {FAIL}, {PASS}" in detail


def test_drift_guard_drops_a_pair_whose_sanity_tests_break_at_S(pipeline):
    pipeline.script({SANITY: {pipeline.s: HARNESS}})

    result = pipeline.drift()

    assert "0 kept, 2 dropped" in result.out
    assert set(pipeline.exclusions("drift")) == {f"pair {pipeline.pair1}", f"pair {pipeline.pair2}"}


def test_a_revision_without_image_or_checkout_drops_the_pair_as_environment_unavailable(pipeline):
    pipeline.script({}, unavailable=[pipeline.t2])

    pipeline.drift()

    assert pipeline.evidence().drift_verdicts() == {pipeline.pair1: "kept", pipeline.pair2: "dropped"}
    reason, detail = pipeline.exclusions("drift")[f"pair {pipeline.pair2}"]
    assert reason == "environment unavailable"
    assert pipeline.t2[:12] in detail


def test_rerunning_the_drift_guard_reuses_earlier_verdicts(pipeline):
    pipeline.drift()
    pipeline.script({SANITY: {pipeline.t1: FAIL}})

    result = pipeline.drift()

    assert "2 kept, 0 dropped (2 reused from an earlier run)" in result.out
    assert len(pipeline.evidence().drift_runs(pipeline.pair1)) == 6


def test_an_unknown_check_runner_is_refused(pipeline):
    result = pipeline.memrev("drift", "--runner", "nope", "--sanity", str(pipeline.sanity))

    assert result.exit_code == 2
    assert 'no check runner named "nope"' in result.err


# Checks and proposed labels ---------------------------------------------

VALUE_EXISTS = assumption("L1", CHECK, "module defines VALUE")
HELPER_EXISTS = assumption("L1", OTHER_CHECK, "module defines helper()")


def labels(pipeline) -> dict[tuple[str, str], tuple[str, str]]:
    """(assumption_id, pair_id) -> (label, reason) for current proposed labels."""
    return {(l.assumption_id, l.pair_id): (l.label, l.reason) for l in pipeline.evidence().proposed_labels()}


def test_a_check_passing_3_of_3_at_S_and_T_is_proposed_supported_within_scope(pipeline):
    pipeline.seed_and_accept(VALUE_EXISTS)
    pipeline.drift()

    result = pipeline.check()

    assert result.exit_code == 0, result.err
    assert labels(pipeline) == {
        ("L1#1", pipeline.pair1): ("supported within scope", ""),
        ("L1#1", pipeline.pair2): ("supported within scope", ""),
    }
    runs = pipeline.evidence().evidence("L1#1")
    assert sorted((r.side, r.revision, r.run_index) for r in runs) == sorted(
        [("S", pipeline.s, i) for i in (1, 2, 3)]
        + [("T", t, i) for t in (pipeline.t1, pipeline.t2) for i in (1, 2, 3)]
    )
    first = runs[0]
    assert (first.command, first.asserted_target, first.outcome, first.exit_status) == (CHECK, "module.VALUE", PASS, 0)
    assert first.output_excerpt and first.ran_at and first.duration_seconds >= 0
    assert {r.assumption_hash for r in runs} == {pipeline.current_hash("L1#1")}
    assert "supported within scope: 2" in result.out


def test_a_check_not_passing_3_of_3_at_S_is_invalid_at_S_and_never_run_at_T(pipeline):
    pipeline.seed_and_accept(VALUE_EXISTS)
    pipeline.script({CHECK: {pipeline.s: [PASS, PASS, FAIL]}})
    pipeline.drift()

    result = pipeline.check()

    assert "at S: 0 valid, 1 invalid at S" in result.out
    assert labels(pipeline) == {}
    assert {r.side for r in pipeline.evidence().evidence("L1#1")} == {"S"}
    reason, detail = pipeline.exclusions("check")["assumption L1#1"]
    assert reason == "invalid at S"
    assert f"{PASS}, {PASS}, {FAIL}" in detail
    assert [(v.assumption_id, v.verdict) for v in pipeline.evidence().source_verdicts()] == [("L1#1", "invalid at S")]


@pytest.mark.parametrize(
    "runs_at_t1, expected",
    [
        (FAIL, ("contradicted", "")),
        ([PASS, FAIL, PASS], ("inconclusive", "check disagrees with itself")),
        ([PASS, HARNESS, PASS], ("inconclusive", "harness error")),
        ([FAIL, FAIL, HARNESS], ("inconclusive", "harness error")),
        (OUT_OF_SCOPE, ("inconclusive", "out of scope at T")),
    ],
    ids=["3/3 fail on target", "disagreement", "harness error", "fail then harness error", "missing fixture"],
)
def test_runs_at_T_decide_the_proposed_label(pipeline, runs_at_t1, expected):
    pipeline.seed_and_accept(VALUE_EXISTS)
    pipeline.script({CHECK: {pipeline.t1: runs_at_t1}})
    pipeline.drift()

    pipeline.check()

    assert labels(pipeline) == {
        ("L1#1", pipeline.pair1): expected,
        ("L1#1", pipeline.pair2): ("supported within scope", ""),
    }


def test_an_assumption_is_not_checked_on_a_pair_dropped_by_the_drift_guard(pipeline):
    pipeline.seed_and_accept(VALUE_EXISTS)
    pipeline.script({SANITY: {pipeline.t2: FAIL}})
    pipeline.drift()

    pipeline.check()

    assert set(labels(pipeline)) == {("L1#1", pipeline.pair1)}
    assert pipeline.t2 not in {r.revision for r in pipeline.evidence().evidence()}


def test_without_a_drift_guard_run_nothing_is_checked(pipeline):
    pipeline.seed_and_accept(VALUE_EXISTS)

    result = pipeline.check()

    assert result.exit_code == 0
    assert "0 assumptions checked" in result.out
    assert "run `drift` first" in result.out
    assert pipeline.evidence().evidence() == []


def test_only_reviewed_checkable_assumptions_are_checked(pipeline):
    vague = assumption("L1", "", "the module is tidy", atype="uncheckable")
    pipeline.seed_and_accept(VALUE_EXISTS, vague)
    seed = write_csv(pipeline.tmp / "more.csv", [HELPER_EXISTS])
    assert pipeline.memrev("seed-assumptions", str(seed)).exit_code == 0  # L1#3 stays pending
    pipeline.drift()

    result = pipeline.check()

    assert "1 assumptions checked (1 uncheckable skipped" in result.out
    assert {r.assumption_id for r in pipeline.evidence().evidence()} == {"L1#1"}


def test_rerunning_the_check_stage_reuses_evidence_of_unchanged_assumptions(pipeline):
    pipeline.seed_and_accept(VALUE_EXISTS)
    pipeline.drift()
    pipeline.check()
    pipeline.script({CHECK: {pipeline.s: FAIL, pipeline.t1: FAIL}})

    result = pipeline.check()

    assert "reused evidence: 1 at S, 2 at T" in result.out
    assert len(pipeline.evidence().evidence("L1#1")) == 9
    assert {label for label, _ in labels(pipeline).values()} == {"supported within scope"}


def test_editing_an_assumption_makes_its_evidence_stale_and_the_new_version_is_checked_again(pipeline):
    pipeline.seed_and_accept(VALUE_EXISTS)
    pipeline.drift()
    pipeline.check()
    old_hash = pipeline.current_hash("L1#1")
    export = pipeline.tmp / "edit.csv"
    pipeline.memrev("review-export", str(export))
    rows = read_csv(export)
    rows[0]["check_command"] = OTHER_CHECK
    write_csv(export, rows)
    assert pipeline.memrev("review-import", str(export), "--reviewer", "rev-1").exit_code == 0
    pipeline.script({OTHER_CHECK: {pipeline.t1: FAIL}})

    pipeline.check()

    new_hash = pipeline.current_hash("L1#1")
    current = pipeline.evidence().evidence("L1#1")
    assert {(r.assumption_hash, r.command) for r in current} == {(new_hash, OTHER_CHECK)}
    assert len(current) == 9
    everything = pipeline.evidence().evidence("L1#1", include_stale=True)
    assert {r.assumption_hash for r in everything if r.stale} == {old_hash}
    assert labels(pipeline)[("L1#1", pipeline.pair1)] == ("contradicted", "")
    old_labels = [l for l in pipeline.evidence().proposed_labels(include_stale=True) if l.stale]
    assert {(l.assumption_hash, l.label) for l in old_labels} == {(old_hash, "supported within scope")}


def test_a_check_whose_environment_vanishes_after_the_drift_guard_is_a_harness_error(pipeline):
    pipeline.seed_and_accept(VALUE_EXISTS)
    pipeline.drift()
    pipeline.script({}, unavailable=[pipeline.t2])

    pipeline.check()

    assert labels(pipeline)[("L1#1", pipeline.pair2)] == ("inconclusive", "harness error")
