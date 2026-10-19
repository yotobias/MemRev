"""Seam N1: the `report` and `export` stages over a full small run, driven through the CLI.

The run (fake LLM, fake check runner): source S with targets T1 and T2, natural lessons L1..L3 at S.
Extraction gives L1 one checkable and one uncheckable assumption, L2 only an uncheckable one, and fails
for L3. L1's check passes at S and T2 but fails at T1, so L1 is contradicted at pair 1 and supported
within scope at pair 2. On pair 1 a constructed stale lesson (STALE) and its matched control
(CONTROL) are built, reviewed, checked and signed off, and the variant bank is built. Both shipped
mechanisms then run over the original bank of both pairs and the variant bank of pair 1.
"""

import csv
import json

import pytest

from memrev import harness, llm
from memrev.llm import FakeLLM, LLMError

from test_checks import FAIL, PASS, REPO
from test_constructed import CONTROL, CONTROL_CHECK, STALE, STALE_CHECK, Construction, review_all
from conftest import lesson, write_bank
from test_review import read_csv, write_csv

NATURAL_CHECK = "python -c 'import module; assert module.VALUE != 1'"
VALUE_NOT_ONE = {
    "statement": "module.VALUE is not 1",
    "assumption_type": "config or default value",
    "scope": "module.py",
    "code_pointers": ["module.py:1"],
    "check_command": NATURAL_CHECK,
    "asserted_target": "module.VALUE",
}
READABLE = {
    "statement": "module.py is easy to read",
    "assumption_type": "code style",
    "scope": "",
    "code_pointers": [],
    "check_command": "",
    "asserted_target": "",
}


class FullRun(Construction):
    def sign_all(self) -> None:
        labels = self.tmp / "labels.csv"
        assert self.memrev("label-export", str(labels)).exit_code == 0
        write_csv(labels, [dict(r, decision="accept") for r in read_csv(labels)])
        signed = self.memrev("label-import", str(labels), "--reviewer", "rev-1")
        assert signed.exit_code == 0, signed.err

    def report(self) -> tuple[str, dict]:
        out = self.tmp / "out" / "report.md"
        result = self.memrev("report", "--out", str(out))
        assert result.exit_code == 0, result.err
        return out.read_text(), json.loads(out.with_suffix(".json").read_text())


@pytest.fixture
def fake(monkeypatch) -> FakeLLM:
    fake = FakeLLM()
    monkeypatch.setattr(llm, "make_llm", lambda model: fake)
    monkeypatch.setattr(llm, "sleep", lambda seconds: None)
    return fake


@pytest.fixture
def run(cli, run_dir, tmp_path, fake) -> FullRun:
    r = FullRun(cli, run_dir, tmp_path, fake)
    more = write_bank(tmp_path / "more.jsonl", [lesson(REPO, r.s, n) for n in (2, 3)])
    assert r.memrev("import", str(more)).exit_code == 0
    fake.answer("Lesson number 1:", {"assumptions": [VALUE_NOT_ONE, READABLE]})
    fake.answer("Lesson number 2:", {"assumptions": [READABLE]})
    fake.answer("Lesson number 3:", LLMError("overloaded"))
    assert r.memrev("extract").exit_code == 0
    assert r.drift().exit_code == 0
    r.script({
        NATURAL_CHECK: {r.s: PASS, r.t1: FAIL, r.t2: PASS},
        STALE_CHECK: {r.s: PASS, r.t1: FAIL},
        CONTROL_CHECK: {r.s: PASS, r.t1: PASS},
    })
    fake.answer("Draft constructed stale lessons", {"candidates": [STALE]})
    fake.answer(STALE["lesson_text"], {"controls": [CONTROL]})
    assert r.construct("--pair", r.pair1).exit_code == 0
    review_all(r)
    assert r.check().exit_code == 0
    r.sign_all()
    assert r.memrev("variant-bank", "--pair", r.pair1).exit_code == 0
    return r


def run_mechanisms(r: FullRun, *names: str) -> None:
    for name in names:
        for pair in (r.pair1, r.pair2):
            result = r.memrev("run-mechanism", name, "--pair", pair)
            assert result.exit_code == 0, result.err
        result = r.memrev("run-mechanism", name, "--pair", r.pair1, "--bank", "variant")
        assert result.exit_code == 0, result.err


# Labels -----------------------------------------------------------------


def test_label_counts_per_repository_and_assumption_type_keep_natural_and_constructed_apart(run):
    text, data = run.report()

    assert data["natural"]["assumption_labels"] == [
        {
            "repository": REPO, "assumption_type": "config or default value",
            "supported within scope": 1, "contradicted": 1, "inconclusive": 0,
        },
    ]
    assert data["constructed"]["assumption_labels"] == [
        {
            "repository": REPO, "assumption_type": "config or default value",
            "supported within scope": 1, "contradicted": 1, "inconclusive": 0,
        },
    ]
    assert data["natural"]["lesson_labels"] == [
        {
            "repository": REPO, "supported within scope": 1, "contradicted": 1, "inconclusive": 0,
            "awaiting check or sign-off": 0,
        },
    ]
    assert data["natural"]["lessons"] == {"in the bank": 3, "without a checkable assumption": 2}
    assert data["constructed"]["lessons"] == {"in the bank": 2, "without a checkable assumption": 0}
    natural, constructed = text.index("## Natural cases"), text.index("## Constructed cases")
    assert natural < constructed
    row = f"| {REPO} | config or default value | 1 | 1 | 0 |"
    assert text.count(row) == 2


# Yield, exclusions and reviewer agreement ---------------------------------


def test_the_report_gives_extraction_yield_and_llm_cost_per_stage(run):
    text, data = run.report()

    assert data["natural"]["extraction"] == {
        "lessons processed": 3, "assumptions": 3, "checkable": 1, "uncheckable": 2, "extraction failed": 1,
    }
    assert data["constructed"]["cases"] == {
        "stale candidates drafted": 1, "constructed stale lessons kept": 1, "gate failed": 0,
        "with a matched control": 1, "without a matched control": 0,
    }
    # FakeLLM: 1000 input and 500 output tokens per call at $2 / $10 per MTok = $0.007 a call.
    cost = {row["stage"]: row for row in data["llm_cost"]}
    assert (cost["extract"]["calls"], cost["extract"]["cost_usd"]) == (5, pytest.approx(0.014))
    assert (cost["construct"]["calls"], cost["construct"]["cost_usd"]) == (2, pytest.approx(0.014))
    assert "lessons processed: 3, checkable assumptions: 1, uncheckable: 2, extraction failed: 1" in text


def test_exclusions_are_counted_per_reason_with_natural_and_constructed_apart(run, fake):
    fake.answer("Draft constructed stale lessons", {"candidates": []})
    assert run.construct("--pair", run.pair2).exit_code == 0

    text, data = run.report()

    assert data["natural"]["exclusions"] == {"extraction failed": 1}
    assert data["constructed"]["exclusions"] == {"no behaviour change found": 1}
    assert "| no behaviour change found | 1 |" in text.split("## Constructed cases")[1]
    assert "no behaviour change found" not in text.split("## Constructed cases")[0]


def test_a_drafting_failure_is_its_own_reason_and_leaves_the_extraction_count_alone(run, fake):
    fake.answer("Draft constructed stale lessons", LLMError("overloaded"))
    assert run.construct("--pair", run.pair2).exit_code == 0

    _, data = run.report()

    assert data["constructed"]["exclusions"]["drafting failed"] == 1
    assert "extraction failed" not in data["constructed"]["exclusions"]
    assert data["natural"]["extraction"]["extraction failed"] == 1


def test_reviewer_agreement_is_reported_and_a_disagreement_is_an_inconclusive_label(run):
    labels = run.tmp / "sample.csv"
    assert run.memrev("label-export", str(labels)).exit_code == 0
    sample = [
        dict(r, decision="inconclusive") for r in read_csv(labels)
        if r["pair_id"] == run.pair2 and r["statement"] == VALUE_NOT_ONE["statement"]
    ]  # fmt: skip
    write_csv(labels, sample)
    second = run.memrev("label-import", str(labels), "--reviewer", "rev-2", "--second")
    assert second.exit_code == 0, second.err

    text, data = run.report()

    assert data["natural"]["reviewer_agreement"] == {"sampled": 1, "agreeing": 0}
    assert data["constructed"]["reviewer_agreement"] == {"sampled": 0, "agreeing": 0}
    assert data["natural"]["inconclusive_reasons"] == {"reviewers disagree": 1}
    [row] = data["natural"]["assumption_labels"]
    assert (row["supported within scope"], row["contradicted"], row["inconclusive"]) == (0, 1, 1)
    assert "Reviewer agreement: 0 of 1 sampled labels agree (0%)." in text


# Mechanisms ----------------------------------------------------------------

SCORED = ("revision pairs", "lessons scored", "contradicted", "contradicted kept", "contradicted rejected", "recheck")


def metrics(data: dict, kind: str) -> dict[str, dict]:
    return {row["mechanism"]: row for row in data[kind]["mechanisms"]}


def test_per_mechanism_metrics_score_contradicted_lessons_kept_separately_for_natural_and_constructed(run):
    run_mechanisms(run, "no-maintenance", "file-change-invalidation")

    text, data = run.report()

    natural, constructed = metrics(data, "natural"), metrics(data, "constructed")
    # Natural: L1 is contradicted at pair 1 and supported at pair 2; L1's module.py changed at both.
    assert [natural["no-maintenance"][k] for k in SCORED] == [2, 2, 1, 1, 0, 0]
    assert [natural["file-change-invalidation"][k] for k in SCORED] == [2, 2, 1, 0, 1, 0]
    # Unnecessary rejection is measured on constructed cases only (V6).
    assert natural["no-maintenance"]["unnecessary rejection"] is None
    # Constructed: STALE (contradicted) and its matched CONTROL (supported) in pair 1's variant bank.
    assert [constructed["no-maintenance"][k] for k in SCORED] == [1, 2, 1, 1, 0, 0]
    assert [constructed["file-change-invalidation"][k] for k in SCORED] == [1, 2, 1, 0, 1, 0]
    assert constructed["no-maintenance"]["unnecessary rejection"] == {"rejected": 0, "matched controls": 1}
    assert constructed["file-change-invalidation"]["unnecessary rejection"] == {"rejected": 1, "matched controls": 1}
    assert natural["no-maintenance"]["cost: checks"] == 0 and natural["no-maintenance"]["tokens"] == 0
    constructed_part = text.split("## Constructed cases")[1]
    assert "| file-change-invalidation | 1 | 2 | 1 | 0 | 1 | 0 | 1 of 1 |" in constructed_part
    assert "| file-change-invalidation | 2 | 2 | 1 | 0 | 1 | 0 | n/a |" in text.split("## Constructed cases")[0]


def test_a_stale_lesson_without_a_matched_control_is_left_out_of_unnecessary_rejection(run):
    # On pair 2, STALE flips too, but its only control fails at T2: no matched control (V6).
    run.script({
        NATURAL_CHECK: {run.s: PASS, run.t1: FAIL, run.t2: PASS},
        STALE_CHECK: {run.s: PASS, run.t1: FAIL, run.t2: FAIL},
        CONTROL_CHECK: {run.s: PASS, run.t1: PASS, run.t2: FAIL},
    })
    assert run.construct("--pair", run.pair2).exit_code == 0
    review_all(run)
    assert run.check().exit_code == 0
    run.sign_all()
    assert run.memrev("variant-bank", "--pair", run.pair2).exit_code == 0
    run_mechanisms(run, "file-change-invalidation")
    assert run.memrev("run-mechanism", "file-change-invalidation", "--pair", run.pair2, "--bank", "variant").exit_code == 0

    _, data = run.report()

    row = metrics(data, "constructed")["file-change-invalidation"]
    assert [row[k] for k in SCORED] == [2, 3, 2, 0, 2, 0]
    # Only pair 1's matched control counts; pair 2's unmatched stale lesson adds nothing.
    assert row["unnecessary rejection"] == {"rejected": 1, "matched controls": 1}
    assert data["constructed"]["cases"]["without a matched control"] == 1


class RecheckAll:
    def decide(self, view):
        view.cost.count_checks(1)
        return {lesson.lesson_id: harness.Decision.RECHECK for lesson in view.lessons}


def test_a_recheck_is_neither_kept_nor_rejected_has_its_own_column_and_adds_to_cost(run, monkeypatch):
    monkeypatch.setitem(harness.MECHANISMS, "recheck-all", RecheckAll())
    assert run.memrev("run-mechanism", "recheck-all", "--pair", run.pair1).exit_code == 0
    assert run.memrev("run-mechanism", "recheck-all", "--pair", run.pair1, "--bank", "variant").exit_code == 0

    text, data = run.report()

    natural = metrics(data, "natural")["recheck-all"]
    # Original bank of pair 1: L1..L3, all rechecked; L1 is the one scored (contradicted) lesson.
    assert [natural[k] for k in SCORED] == [1, 1, 1, 0, 0, 3]
    assert natural["cost: checks"] == 1 + 3
    constructed = metrics(data, "constructed")["recheck-all"]
    assert [constructed[k] for k in SCORED] == [1, 2, 1, 0, 0, 2]
    assert constructed["unnecessary rejection"] == {"rejected": 0, "matched controls": 1}
    # Cost is the whole variant-bank run: 3 lessons rechecked plus the one check the mechanism ran.
    assert constructed["cost: checks"] == 1 + 3
    assert "| recheck-all | 1 | 1 | 1 | 0 | 0 | 3 | n/a | 4 |" in text


# Export --------------------------------------------------------------------


def exported(directory, name: str) -> tuple[list[dict], list[dict]]:
    with (directory / f"{name}.jsonl").open() as fh:
        records = [json.loads(line) for line in fh]
    with (directory / f"{name}.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    return records, rows


def test_export_writes_lessons_assumptions_evidence_and_final_labels_as_jsonl_and_csv(run):
    out = run.tmp / "dataset"

    result = run.memrev("export", str(out))

    assert result.exit_code == 0, result.err
    lessons, lesson_rows = exported(out, "lessons")
    by_text = {r["lesson_text"]: r for r in lessons}
    assert len(lessons) == 5
    assert by_text[STALE["lesson_text"]]["case"] == "constructed stale lesson"
    assert by_text[CONTROL["lesson_text"]]["case"] == "matched control"
    assert by_text[STALE["lesson_text"]]["pair_id"] == run.pair1
    assert sorted(r["case"] for r in lessons).count("natural lesson") == 3
    assert [r["lesson_id"] for r in lesson_rows] == [r["lesson_id"] for r in lessons]

    assumptions, assumption_rows = exported(out, "assumptions")
    l1 = next(a for a in assumptions if a["statement"] == VALUE_NOT_ONE["statement"])
    assert (l1["lesson_id"], l1["assumption_type"], l1["status"], l1["code_pointers"]) == (
        "L1", "config or default value", "accepted", ["module.py:1"],
    )
    assert len(assumptions) == 5 and len(assumption_rows) == 5
    assert json.loads(next(r for r in assumption_rows if r["assumption_id"] == l1["assumption_id"])["code_pointers"]) == [
        "module.py:1"
    ]

    evidence, evidence_rows = exported(out, "evidence")
    natural_runs = [e for e in evidence if e["assumption_id"] == l1["assumption_id"]]
    assert sorted((e["revision"], e["run_index"], e["outcome"]) for e in natural_runs) == sorted(
        [(run.s, i, PASS) for i in (1, 2, 3)] + [(run.t1, i, FAIL) for i in (1, 2, 3)]
        + [(run.t2, i, PASS) for i in (1, 2, 3)]
    )
    assert len(evidence) == 9 + 6 + 6 == len(evidence_rows)
    assert {e["case"] for e in evidence} == {"natural lesson", "constructed stale lesson", "matched control"}

    finals, final_rows = exported(out, "final_labels")
    assert sorted((f["case"], f["pair_id"], f["label"], f["reviewer_id"]) for f in finals) == sorted([
        ("natural lesson", run.pair1, "contradicted", "rev-1"),
        ("natural lesson", run.pair2, "supported within scope", "rev-1"),
        ("constructed stale lesson", run.pair1, "contradicted", "rev-1"),
        ("matched control", run.pair1, "supported within scope", "rev-1"),
    ])
    assert {f["repository"] for f in finals} == {REPO}
    assert len(final_rows) == 4
    assert "export: 5 lessons, 5 assumptions, 21 evidence rows, 4 final labels" in result.out
