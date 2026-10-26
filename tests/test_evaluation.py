import copy
import hashlib
import json
from pathlib import Path

import pytest

from memrev.evaluation import build_evaluation_draft, import_evaluation, export_evaluation
from memrev.provenance import load_acquisition, prepare_acquisition


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "pilot-a/fixtures/test"
REVIEWER = {"id": "test-reviewer", "type": "ai", "independent": False, "note": "Synthetic test-only evaluation."}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


@pytest.fixture
def package(tmp_path):
    output = tmp_path / "acquisition"
    prepare_acquisition(
        FIXTURES / "full_trajectory_example.traj.json",
        FIXTURES / "gpt-6-high_test_lessons_102526.json",
        FIXTURES / "gpt-6-high_test_lessons_102526.metadata.json", output,
    )
    return output


@pytest.fixture
def completed(package, tmp_path):
    record = load_acquisition(package)
    review = build_evaluation_draft(record, REVIEWER)
    for lesson in review["lessons"]:
        lesson["evaluation"].update(outcome="usable_as_extracted", reason="Test-only evaluation.")
        for assumption in lesson["assumptions"]:
            assumption["evaluation"].update(
                outcome="usable_as_extracted", reason="Test-only evaluation.",
                rubric={key: "yes" for key in review["rubric_definitions"]},
                reviewer_evidence_message_indices=assumption["original"]["evidence_message_indices"],
            )
    candidates = [a for l in review["lessons"] for a in l["assumptions"]]
    candidates[0]["evaluation"].update(outcome="needs_repair", issue_codes=["compound_assumption"])
    candidates[0]["evaluation"]["rubric"]["single_behaviour"] = "no"
    candidates[1]["evaluation"].update(outcome="uncertain", issue_codes=["granularity_ambiguous"])
    candidates[1]["evaluation"]["rubric"]["single_behaviour"] = "uncertain"
    candidates[2]["evaluation"].update(outcome="context_only", issue_codes=["environment_context"])
    candidates[2]["evaluation"]["rubric"]["repository_behaviour"] = "no"
    path = tmp_path / "evaluation.json"
    write(path, review)
    return path


def test_export_is_pending_and_cannot_overwrite_existing_review(package, tmp_path):
    output = tmp_path / "blank.json"
    draft = export_evaluation(package, output, REVIEWER)
    assert read(output) == draft
    assert all(l["evaluation"]["outcome"] == "pending" for l in draft["lessons"])
    assert all(a["evaluation"]["outcome"] == "pending" for l in draft["lessons"] for a in l["assumptions"])
    assert "proposed_replacements" not in output.read_text()
    assert "proposed_advice" not in output.read_text()
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        export_evaluation(package, output, REVIEWER)
    assert output.read_bytes() == before
    with pytest.raises(ValueError, match="pending"):
        import_evaluation(package, output, tmp_path / "incomplete")


def test_import_preserves_every_original_and_recomputes_counts(package, completed, tmp_path):
    original = read(package / "record.json")
    output = tmp_path / "imported"
    summary = import_evaluation(package, completed, output)
    bank = read(output / "evaluated_bank.json")
    assert bank["reviewer"]["type"] == "ai"
    assert bank["source_validity"] == "not_assessed"
    assert bank["metadata"]["purpose"] == "development"
    assert summary["original_assumptions_evaluated"] == 17
    assert summary["assumption_outcomes"] == {"usable_as_extracted": 14, "needs_repair": 1, "uncertain": 1, "context_only": 1}
    assert sum(summary["assumption_outcomes"].values()) == 17
    assert (output / "evaluation.input.json").read_bytes() == completed.read_bytes()
    for lesson, before in zip(bank["lessons"], original["lessons"]):
        assert lesson["lesson_id"] == before["lesson_id"] and lesson["advice"] == before["advice"]
        assert len(lesson["assumptions"]) == len(before["assumptions"])
        for assumption, source in zip(lesson["assumptions"], before["assumptions"]):
            assert {key: value for key, value in assumption.items() if key != "evaluation"} == source
    assert read(package / "record.json") == original
    assert summary == read(output / "summary.json")
    manifest = read(output / "manifest.json")
    for name, digest in manifest["artifacts"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    assert manifest["record_sha256"] == hashlib.sha256((package / "record.json").read_bytes()).hexdigest()
    assert manifest["evaluation_sha256"] == hashlib.sha256(completed.read_bytes()).hexdigest()


@pytest.mark.parametrize("change", [
    "missing_lesson", "duplicate_lesson", "missing_assumption", "duplicate_assumption", "unknown_id",
    "wrong_parent", "changed_advice", "changed_statement", "boolean_index", "bad_index", "missing_rating",
    "unknown_rating", "changed_protocol", "bad_reviewer", "false_usable", "false_context", "empty_reason",
    "replacement_field", "pending", "false_summary", "source_label", "boolean_version", "changed_lesson_protocol",
])
def test_invalid_review_rejected_before_writing(package, completed, tmp_path, change):
    review = read(completed)
    lesson = review["lessons"][0]
    assumption = lesson["assumptions"][0]
    evaluation = assumption["evaluation"]
    if change == "missing_lesson": review["lessons"].pop()
    elif change == "duplicate_lesson": review["lessons"].append(copy.deepcopy(lesson))
    elif change == "missing_assumption": lesson["assumptions"].pop()
    elif change == "duplicate_assumption": lesson["assumptions"].append(copy.deepcopy(assumption))
    elif change == "unknown_id": assumption["assumption_id"] = "foreign"
    elif change == "wrong_parent":
        lesson["assumptions"][0], review["lessons"][1]["assumptions"][0] = review["lessons"][1]["assumptions"][0], assumption
    elif change == "changed_advice": lesson["original_advice"] += " changed"
    elif change == "changed_statement": assumption["original"]["statement"] += " changed"
    elif change == "boolean_index": evaluation["reviewer_evidence_message_indices"] = [True]
    elif change == "bad_index": evaluation["reviewer_evidence_message_indices"] = [78]
    elif change == "missing_rating": del evaluation["rubric"]["scope_sufficient"]
    elif change == "unknown_rating": evaluation["rubric"]["scope_sufficient"] = "maybe"
    elif change == "changed_protocol": review["rubric_definitions"]["scope_sufficient"] = "Different criterion"
    elif change == "changed_lesson_protocol": review["lesson_outcome_definitions"]["uncertain"] = "Different meaning"
    elif change == "bad_reviewer": review["reviewer"]["type"] = "verified_human"
    elif change == "false_usable": evaluation["outcome"] = "usable_as_extracted"
    elif change == "false_context": evaluation["outcome"] = "context_only"
    elif change == "empty_reason": evaluation["reason"] = " "
    elif change == "replacement_field": assumption["proposed_replacements"] = []
    elif change == "pending": evaluation["outcome"] = "pending"
    elif change == "false_summary": review["summary"] = {"original_assumptions_evaluated": 999}
    elif change == "source_label": review["source_validity"] = "verified"
    else: review["evaluation_version"] = True
    write(completed, review)
    with pytest.raises(ValueError):
        import_evaluation(package, completed, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


@pytest.mark.parametrize("artifact", ["inputs/trajectory.json", "inputs/extraction.json", "inputs/metadata.json", "record.json"])
def test_acquisition_tampering_is_detected(package, completed, tmp_path, artifact):
    path = package / artifact
    value = read(path)
    if artifact == "record.json": value["lessons"][0]["advice"] += " altered"
    else: value["unexpected"] = "altered"
    write(path, value)
    with pytest.raises(ValueError):
        import_evaluation(package, completed, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_reordered_reviews_join_by_id_and_reimports_do_not_overwrite(package, completed, tmp_path):
    review = read(completed)
    review["lessons"].reverse()
    for lesson in review["lessons"]: lesson["assumptions"].reverse()
    write(completed, review)
    output = tmp_path / "imported"
    summary = import_evaluation(package, completed, output)
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    assert import_evaluation(package, completed, output) == summary
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    review["reviewer"]["note"] += " revised"
    write(completed, review)
    with pytest.raises(FileExistsError):
        import_evaluation(package, completed, output)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


@pytest.mark.parametrize("reviewer_type", ["human", "human_ai_assisted", "ai"])
def test_reviewer_attribution_is_retained_without_source_signoff(package, completed, tmp_path, reviewer_type):
    review = read(completed)
    review["reviewer"]["type"] = reviewer_type
    write(completed, review)
    summary = import_evaluation(package, completed, tmp_path / reviewer_type)
    assert summary["reviewer"]["type"] == reviewer_type
    assert summary["reviewer"]["independent"] is False
    assert summary["source_validity"] == "not_assessed"


def test_empty_extraction_produces_zero_counts_without_inventing_candidates(tmp_path):
    extraction = tmp_path / "empty.json"
    write(extraction, {"schema_version": 2, "lessons": []})
    package = tmp_path / "empty-package"
    prepare_acquisition(FIXTURES / "full_trajectory_example.traj.json", extraction,
                        FIXTURES / "gpt-6-high_test_lessons_102526.metadata.json", package)
    review_path = tmp_path / "review.json"
    export_evaluation(package, review_path, REVIEWER)
    summary = import_evaluation(package, review_path, tmp_path / "output")
    assert summary["original_lessons_evaluated"] == 0
    assert summary["original_assumptions_evaluated"] == 0
    assert set(summary["assumption_outcomes"].values()) == {0}
    assert read(tmp_path / "output/evaluated_bank.json")["lessons"] == []
