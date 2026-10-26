"""Export pending extraction evaluations and import completed reviews without rewriting."""

import argparse
import copy
import json
from pathlib import Path
import re
import tempfile

from memrev.provenance import _fields, _json_bytes, _sha256, _text, load_acquisition
from memrev.trajectory import parse_extraction


PROTOCOL = parse_extraction(Path(__file__).with_name("evaluation_protocol.json").read_text(encoding="utf-8"))


def _same(left, right):
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def _original(assumption):
    return {key: copy.deepcopy(value) for key, value in assumption.items()
            if key not in ["assumption_id", "raw_assumption_index"]}


def _validate_reviewer(reviewer):
    _fields(reviewer, ["id", "type", "independent", "note"], "reviewer")
    for key in ["id", "note"]:
        _text(reviewer[key], f"reviewer.{key}", nullable=False)
    if reviewer["type"] not in ["human", "human_ai_assisted", "ai"]:
        raise ValueError("reviewer.type: expected human, human_ai_assisted or ai")
    if type(reviewer["independent"]) is not bool:
        raise ValueError("reviewer.independent: expected a boolean (self-reported)")


def build_evaluation_draft(record, reviewer):
    """Leave all judgments pending; originals and the rubric are not editable fields."""
    _validate_reviewer(reviewer)
    lessons = list()
    for lesson in record["lessons"]:
        evaluation = {"outcome": "pending", "issue_codes": [], "reason": None,
                      "reviewer_evidence_message_indices": []}
        assumptions = list()
        for assumption in lesson["assumptions"]:
            assumption_evaluation = copy.deepcopy(evaluation)
            assumption_evaluation["rubric"] = {key: None for key in PROTOCOL["rubric_definitions"]}
            assumptions.append({"assumption_id": assumption["assumption_id"],
                                "original": _original(assumption), "evaluation": assumption_evaluation})
        lessons.append({"lesson_id": lesson["lesson_id"], "original_advice": lesson["advice"],
                        "evaluation": evaluation, "assumptions": assumptions})
    return {
        "evaluation_version": 1,
        "artifact_type": "extraction_review_evaluation",
        "protocol_id": PROTOCOL["protocol_id"],
        "acquisition_id": record["acquisition_id"],
        "reviewer": copy.deepcopy(reviewer),
        "review_basis": "Original extraction and cited trajectory messages; no source-revision validity assessment.",
        "source_validity": "not_assessed",
        "rating_values": copy.deepcopy(PROTOCOL["rating_values"]),
        "rubric_definitions": copy.deepcopy(PROTOCOL["rubric_definitions"]),
        "outcome_definitions": copy.deepcopy(PROTOCOL["assumption_outcome_definitions"]),
        "lesson_outcome_definitions": copy.deepcopy(PROTOCOL["lesson_outcome_definitions"]),
        "issue_definitions": copy.deepcopy(PROTOCOL["issue_definitions"]),
        "lessons": lessons,
    }


def export_evaluation(package_dir, output_path, reviewer):
    draft = build_evaluation_draft(load_acquisition(package_dir), reviewer)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(_json_bytes(draft))
    return draft


def _rows_by_id(rows, originals, field, path):
    if not isinstance(rows, list):
        raise ValueError(f"{path}: expected a list")
    indexed = dict()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(field), str):
            raise ValueError(f"{path}: missing string {field}")
        identifier = row[field]
        if identifier in indexed:
            raise ValueError(f"{path}: duplicate ID {identifier}")
        indexed[identifier] = row
    if set(indexed) != {row[field] for row in originals}:
        raise ValueError(f"{path}: IDs must match every original under this parent")
    return indexed


def _validate_judgment(evaluation, message_count, assumption=False):
    fields = ["outcome", "issue_codes", "reason", "reviewer_evidence_message_indices"]
    if assumption:
        fields.append("rubric")
    _fields(evaluation, fields, "evaluation")
    outcomes = PROTOCOL["assumption_outcome_definitions" if assumption else "lesson_outcome_definitions"]
    outcome = evaluation["outcome"]
    if outcome == "pending":
        raise ValueError("evaluation: pending rows cannot be imported")
    if not isinstance(outcome, str) or outcome not in outcomes:
        raise ValueError("evaluation.outcome: unknown outcome")
    _text(evaluation["reason"], "evaluation.reason", nullable=False)
    issues = evaluation["issue_codes"]
    if (not isinstance(issues, list)
            or any(not isinstance(issue, str) or issue not in PROTOCOL["issue_definitions"] for issue in issues)
            or len(set(issues)) != len(issues)):
        raise ValueError("evaluation.issue_codes: expected distinct known codes")
    if (outcome == "usable_as_extracted" and issues) or (outcome != "usable_as_extracted" and not issues):
        raise ValueError("evaluation: usable rows require no issues; other outcomes require an issue code")
    indices = evaluation["reviewer_evidence_message_indices"]
    if (not isinstance(indices, list)
            or any(type(index) is not int or not 0 <= index < message_count for index in indices)
            or len(set(indices)) != len(indices)):
        raise ValueError("evaluation: reviewer citations must be distinct in-range message indices")
    if not assumption:
        return
    rubric = evaluation["rubric"]
    _fields(rubric, PROTOCOL["rubric_definitions"], "evaluation.rubric")
    if any(rating not in PROTOCOL["rating_values"] for rating in rubric.values()):
        raise ValueError("evaluation.rubric: expected yes, no or uncertain for every criterion")
    quality = [value for key, value in rubric.items() if key != "repository_behaviour"]
    if outcome == "usable_as_extracted" and any(value != "yes" for value in rubric.values()):
        raise ValueError("evaluation: usable_as_extracted requires all six ratings to be yes")
    if outcome == "needs_repair" and "no" not in quality:
        raise ValueError("evaluation: needs_repair requires an identified quality defect rated no")
    if outcome == "uncertain" and "uncertain" not in rubric.values():
        raise ValueError("evaluation: uncertain requires an uncertain criterion")
    if outcome == "context_only" and rubric["repository_behaviour"] != "no":
        raise ValueError("evaluation: context_only requires repository_behaviour=no")


def _evaluate(record, review):
    required = ["evaluation_version", "artifact_type", "acquisition_id", "reviewer", "review_basis",
                "source_validity", "rating_values", "rubric_definitions", "outcome_definitions",
                "issue_definitions", "lessons"]
    optional = ["protocol_id", "lesson_outcome_definitions", "original_review_sha256", "summary"]
    if not isinstance(review, dict):
        raise ValueError("review: expected an object")
    _fields(review, required + [key for key in optional if key in review], "review")
    if type(review["evaluation_version"]) is not int or review["evaluation_version"] != 1:
        raise ValueError("review: expected evaluation_version 1")
    if review["acquisition_id"] != record["acquisition_id"]:
        raise ValueError("review: acquisition_id mismatch")
    if review["artifact_type"] not in ["extraction_review_evaluation", "extraction_review_evaluation_example"]:
        raise ValueError("review: unknown artifact_type")
    if review["artifact_type"].endswith("_example") and record["metadata"]["purpose"] != "development":
        raise ValueError("review: examples are restricted to development acquisitions")
    if review.get("protocol_id", PROTOCOL["protocol_id"]) != PROTOCOL["protocol_id"]:
        raise ValueError("review: protocol_id mismatch")
    if "original_review_sha256" in review:
        digest = review["original_review_sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("review: invalid legacy original_review_sha256")
    for key in ["rating_values", "rubric_definitions", "outcome_definitions", "issue_definitions"]:
        protocol_key = "assumption_outcome_definitions" if key == "outcome_definitions" else key
        if not _same(review[key], PROTOCOL[protocol_key]):
            raise ValueError(f"review.{key}: changed evaluation protocol")
    if "lesson_outcome_definitions" in review and not _same(
            review["lesson_outcome_definitions"], PROTOCOL["lesson_outcome_definitions"]):
        raise ValueError("review.lesson_outcome_definitions: changed evaluation protocol")
    _validate_reviewer(review["reviewer"])
    _text(review["review_basis"], "review.review_basis", nullable=False)
    if review["source_validity"] != "not_assessed":
        raise ValueError("review: extraction evaluation does not establish source validity")

    bank = copy.deepcopy(record)
    bank.update(bank_version=1, artifact_type="evaluated_extraction_bank", reviewer=copy.deepcopy(review["reviewer"]),
                protocol_id=PROTOCOL["protocol_id"], source_validity="not_assessed")
    summary = {
        "original_lessons_evaluated": len(record["lessons"]),
        "original_assumptions_evaluated": sum(len(lesson["assumptions"]) for lesson in record["lessons"]),
        "assumption_outcomes": {key: 0 for key in PROTOCOL["assumption_outcome_definitions"]},
    }
    lesson_counts = {key: 0 for key in PROTOCOL["lesson_outcome_definitions"]}
    ratings = {key: {value: 0 for value in PROTOCOL["rating_values"]} for key in PROTOCOL["rubric_definitions"]}
    issues = {key: 0 for key in PROTOCOL["issue_definitions"]}
    lessons = _rows_by_id(review["lessons"], record["lessons"], "lesson_id", "lessons")
    for lesson in bank["lessons"]:
        row = lessons[lesson["lesson_id"]]
        _fields(row, ["lesson_id", "original_advice", "evaluation", "assumptions"], "lesson")
        if row["original_advice"] != lesson["advice"]:
            raise ValueError("lesson: original advice changed")
        _validate_judgment(row["evaluation"], record["message_count"])
        lesson["evaluation"] = copy.deepcopy(row["evaluation"])
        lesson_counts[row["evaluation"]["outcome"]] += 1
        assumptions = _rows_by_id(row["assumptions"], lesson["assumptions"], "assumption_id", "assumptions")
        for assumption in lesson["assumptions"]:
            candidate = assumptions[assumption["assumption_id"]]
            _fields(candidate, ["assumption_id", "original", "evaluation"], "assumption")
            if not _same(candidate["original"], _original(assumption)):
                raise ValueError("assumption: original content changed")
            evaluation = candidate["evaluation"]
            _validate_judgment(evaluation, record["message_count"], assumption=True)
            assumption["evaluation"] = copy.deepcopy(evaluation)
            summary["assumption_outcomes"][evaluation["outcome"]] += 1
            for key, value in evaluation["rubric"].items():
                ratings[key][value] += 1
            for issue in evaluation["issue_codes"]:
                issues[issue] += 1
    if "summary" in review and not _same(review["summary"], summary):
        raise ValueError("review.summary: does not match recomputed original-candidate counts")
    summary.update(acquisition_id=record["acquisition_id"], protocol_id=PROTOCOL["protocol_id"],
                   purpose=record["metadata"]["purpose"], reviewer=copy.deepcopy(review["reviewer"]),
                   source_validity="not_assessed", lesson_outcomes=lesson_counts,
                   criterion_ratings=ratings, assumption_issue_counts=issues)
    return bank, summary


def _write_import(output_dir, files):
    output = Path(output_dir).resolve()
    if output.exists():
        for name, content in files.items():
            if not (output / name).is_file() or (output / name).read_bytes() != content:
                raise FileExistsError(f"Refusing to overwrite changed evaluation artifact: {output / name}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".evaluate-", dir=output.parent) as temporary:
        staging = Path(temporary) / "evaluation"
        staging.mkdir()
        for name, content in files.items():
            (staging / name).write_bytes(content)
        if output.exists():
            raise FileExistsError(f"Output appeared while importing evaluation: {output}")
        staging.rename(output)


def import_evaluation(package_dir, review_path, output_dir):
    """Validate a complete review, retain all originals, and save an auditable report."""
    record_path = Path(package_dir) / "record.json"
    record_bytes = record_path.read_bytes()
    record = load_acquisition(package_dir)
    if record_path.read_bytes() != record_bytes:
        raise ValueError("record changed while loading acquisition")
    review_bytes = Path(review_path).read_bytes()
    review = parse_extraction(review_bytes.decode("utf-8"))
    bank, summary = _evaluate(record, review)
    protocol_bytes = _json_bytes(PROTOCOL)
    manifest = {"import_version": 1, "acquisition_id": record["acquisition_id"],
                "record_sha256": _sha256(record_bytes), "evaluation_sha256": _sha256(review_bytes),
                "protocol_sha256": _sha256(protocol_bytes)}
    evaluation_id = "eval-" + _sha256(_json_bytes(manifest))
    manifest["evaluation_id"] = evaluation_id
    bank["evaluation_id"] = summary["evaluation_id"] = evaluation_id
    report = ["# Extraction evaluation", "", f"Acquisition: `{record['acquisition_id']}`",
              f"Evaluation: `{evaluation_id}`", f"Purpose: {summary['purpose']}",
              f"Reviewer: {review['reviewer']['id']} ({review['reviewer']['type']}); "
              f"independent: {review['reviewer']['independent']} (self-reported).", "",
              "This evaluates extraction quality. Source validity is not assessed.",
              "All original candidates are retained; no rewriting, splitting or review merging is applied.", "",
              f"Original lessons: {summary['original_lessons_evaluated']}",
              f"Original assumptions (denominator): {summary['original_assumptions_evaluated']}", "",
              "| Assumption outcome | Count |", "|---|---:|"]
    report.extend(f"| {key} | {count} |" for key, count in summary["assumption_outcomes"].items())
    report.extend(["", "Counts describe this single review. Uncertain, context-only and repair rows remain in the denominator.",
                   "Reviewer identity and independence are declarations, not authenticated claims.",
                   "The manifest fingerprints the acquisition record, exact submitted review and saved protocol.", ""])
    files = {"evaluation.input.json": review_bytes, "evaluated_bank.json": _json_bytes(bank),
             "summary.json": _json_bytes(summary), "report.md": "\n".join(report).encode("utf-8"),
             "protocol.json": protocol_bytes, "acquisition.record.json": record_bytes}
    manifest["artifacts"] = {name: _sha256(content) for name, content in files.items()}
    files["manifest.json"] = _json_bytes(manifest)
    _write_import(output_dir, files)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    draft = commands.add_parser("draft", help="Export a new pending evaluation form")
    draft.add_argument("--package", required=True, type=Path)
    draft.add_argument("--output", required=True, type=Path)
    draft.add_argument("--reviewer-id", required=True)
    draft.add_argument("--reviewer-type", required=True, choices=["human", "human_ai_assisted", "ai"])
    draft.add_argument("--note", required=True)
    draft.add_argument("--independent", action="store_true", help="Self-report independence; default false")
    ingest = commands.add_parser("import", help="Validate a completed evaluation and produce a bank/report")
    ingest.add_argument("--package", required=True, type=Path)
    ingest.add_argument("--review", required=True, type=Path)
    ingest.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "draft":
            export_evaluation(args.package, args.output, {"id": args.reviewer_id, "type": args.reviewer_type,
                              "independent": args.independent, "note": args.note})
            print(f"Pending evaluation written to {args.output.resolve()}")
        else:
            summary = import_evaluation(args.package, args.review, args.output_dir)
            print(f"Evaluated {summary['original_assumptions_evaluated']} original assumptions in {args.output_dir.resolve()}")
            print("Source validity: not assessed. Reviewer type: " + summary["reviewer"]["type"])
    except (ValueError, OSError) as error:
        parser.exit(2, f"Cannot {args.command} evaluation: {error}\n")


if __name__ == "__main__":
    main()
