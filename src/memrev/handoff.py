"""Build an offline, explicitly draft Lane N handoff without requiring human review."""

import argparse
from collections import Counter
import copy
import csv
import io
import json
from pathlib import Path

from memrev.evaluation import _evaluate
from memrev.handoff_io import canonical_hash, write_bundle
from memrev.provenance import _json_bytes, _sha256, load_acquisition
from memrev.sharing import build_sharing_draft, compare_regrouping, export_regrouping, validate_sharing
from memrev.trajectory import parse_extraction
from memrev.validity import OUTCOMES, REVISIONS, build_validity_draft, validate_validity, validity_label


ROOT = Path(__file__).resolve().parents[2]
SELECTION = ROOT / "pilot-a/clusters.csv"
B_FIELDS = ["lesson_id", "lesson_text", "task_id", "repository", "source_revision", "trajectory_pointer"]
B_REPOSITORIES = ["django/django", "sympy/sympy", "scikit-learn/scikit-learn"]


def _load_inputs(acquisitions, evaluations, selection_path):
    if not acquisitions:
        raise ValueError("handoff: supply at least one acquisition")
    selection_bytes = Path(selection_path).read_bytes()
    selected = dict()
    for row in csv.DictReader(io.StringIO(selection_bytes.decode("utf-8"))):
        if not {"instance_id", "base_commit", "cluster", "same_pr_group", "same_text"}.issubset(row):
            raise ValueError("selection: missing required columns")
        if row["instance_id"] in selected:
            raise ValueError("selection: duplicate task")
        selected[row["instance_id"]] = row
    review_inputs = dict()
    for path in evaluations:
        content = Path(path).read_bytes()
        review = parse_extraction(content.decode("utf-8"))
        if not isinstance(review, dict) or not isinstance(review.get("acquisition_id"), str):
            raise ValueError("evaluation: expected acquisition_id")
        identifier = review["acquisition_id"]
        if identifier in review_inputs:
            raise ValueError("handoff: only one explicit evaluation per acquisition; do not silently merge reviewers")
        review_inputs[identifier] = (review, content)
    records, files, fingerprints, review_summaries = {}, {}, {}, {}
    for supplied in acquisitions:
        package = Path(supplied)
        record_bytes = (package / "record.json").read_bytes()
        record = load_acquisition(package)
        if (package / "record.json").read_bytes() != record_bytes:
            raise ValueError("acquisition changed while reading")
        identifier = record["acquisition_id"]
        if identifier in records:
            raise ValueError("handoff: duplicate acquisition")
        metadata = record["metadata"]
        task = selected.get(metadata["task_id"])
        if metadata["purpose"] == "pilot_a":
            if task is None or metadata["source_revision"].lower() != task["base_commit"].lower():
                raise ValueError("handoff: production acquisition must match the frozen task and source revision")
            if metadata["repository"] != task["same_pr_group"].split("#", 1)[0]:
                raise ValueError("handoff: production task/repository mismatch")
        prefix = f"acquisitions/{identifier}"
        files[f"{prefix}/record.json"] = record_bytes
        for artifact in record["artifacts"].values():
            if artifact is None:
                continue
            content = (package / artifact["path"]).read_bytes()
            if _sha256(content) != artifact["sha256"]:
                raise ValueError("acquisition snapshot changed while copying")
            files[f"{prefix}/{artifact['path']}"] = content
        fingerprint = {"record_sha256": _sha256(record_bytes), "review_sha256": None}
        if identifier in review_inputs:
            review, content = review_inputs[identifier]
            record, summary = _evaluate(record, review)
            review_summaries[identifier] = summary
            files[f"{prefix}/evaluation.input.json"] = content
            fingerprint["review_sha256"] = _sha256(content)
        records[identifier] = record
        fingerprints[identifier] = fingerprint
    if set(review_inputs) - set(records):
        raise ValueError("handoff: evaluation supplied for an unknown acquisition")
    purposes = {record["metadata"]["purpose"] for record in records.values()}
    if len(purposes) != 1:
        raise ValueError("handoff: keep development and production acquisitions in separate collections")
    files["selection.csv"] = selection_bytes
    identity = {"collection_version": 1, "acquisitions": dict(sorted(fingerprints.items())),
                "selection_sha256": _sha256(selection_bytes)}
    return dict(sorted(records.items())), review_summaries, selected, files, identity


def _candidates(records, selected):
    candidates = dict()
    for identifier, record in sorted(records.items()):
        metadata = record["metadata"]
        selection = selected.get(metadata["task_id"], {})
        # Do not assign trusted PR membership to development metadata that merely resembles a task ID.
        matches = (selection.get("base_commit") == metadata["source_revision"]
                   and metadata["repository"] == selection.get("same_pr_group", "").split("#", 1)[0])
        for lesson in record["lessons"]:
            for assumption in lesson["assumptions"]:
                original = {key: copy.deepcopy(value) for key, value in assumption.items()
                            if key not in ["assumption_id", "raw_assumption_index", "evaluation"]}
                candidates[assumption["assumption_id"]] = {
                    "assumption_id": assumption["assumption_id"], "lesson_id": lesson["lesson_id"],
                    "acquisition_id": identifier, "advice": lesson["advice"],
                    "task_id": metadata["task_id"], "repository": metadata["repository"],
                    "source_revision": metadata["source_revision"], "agent_run_id": metadata["agent_run_id"],
                    "trajectory_pointer": f"acquisitions/{identifier}/inputs/trajectory.json",
                    "original": original, "evaluation": copy.deepcopy(assumption.get("evaluation")),
                    "reviewer": copy.deepcopy(record.get("reviewer")),
                    "same_pr_group": selection.get("same_pr_group") if matches else None,
                    "same_text": matches and selection.get("same_text", "").lower() == "true",
                }
    return candidates


def _export_b(records):
    lines, status, exclusions = [], [], []
    for identifier, record in sorted(records.items()):
        metadata = record["metadata"]
        for lesson in record["lessons"]:
            reasons = [f"missing_{field}" for field in ["task_id", "repository", "source_revision"]
                       if metadata[field] is None]
            if metadata["repository"] is not None and metadata["repository"] not in B_REPOSITORIES:
                reasons.append("unsupported_repository")
            sidecar = {"lesson_id": lesson["lesson_id"], "purpose": metadata["purpose"],
                       "reviewer": record.get("reviewer"), "extraction_outcome": lesson.get("evaluation", {}).get("outcome", "pending"),
                       "source_validity": "not_certified_by_export", "exclusion_reasons": reasons}
            status.append(sidecar)
            if reasons:
                exclusions.append({"lesson_id": lesson["lesson_id"], "reasons": reasons})
                continue
            row = {"lesson_id": lesson["lesson_id"], "lesson_text": lesson["advice"],
                   "task_id": metadata["task_id"], "repository": metadata["repository"],
                   "source_revision": metadata["source_revision"],
                   "trajectory_pointer": f"../acquisitions/{identifier}/inputs/trajectory.json"}
            # One compact JSON object per line, unlike the indented acquisition files.
            lines.append(json.dumps(row, ensure_ascii=False, allow_nan=False))
    payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    return payload, {"contract_status": "proposed", "fields": B_FIELDS, "exported": len(lines),
                     "excluded": len(exclusions), "exclusions": exclusions, "lesson_status": status,
                     "source_sha_existence_checked": False, "review_required_for_draft_export": False}


def _report(records, reviews, selected, candidates, validity, sharing, pilot_b):
    review_counts = {key: 0 for key in ["pending", "human", "human_ai_assisted", "ai"]}
    assumption_outcomes = Counter()
    lessons = sum(len(record["lessons"]) for record in records.values())
    for identifier, record in records.items():
        review_counts[reviews[identifier]["reviewer"]["type"] if identifier in reviews else "pending"] += 1
        for lesson in record["lessons"]:
            for assumption in lesson["assumptions"]:
                assumption_outcomes[assumption.get("evaluation", {}).get("outcome", "pending")] += 1
    cells = {key: 0 for key in OUTCOMES}
    methods, assessors, labels = Counter(), Counter(), Counter()
    for identifier, row in validity.items():
        label = validity_label(row) if candidates[identifier]["original"]["kind"] == "repo_behaviour" else "context_candidate"
        labels[label] += 1
        for revision in REVISIONS:
            cell = row[revision]
            cells[cell["outcome"]] += 1
            if cell["method"] is not None:
                methods[cell["method"]] += 1
            if cell["assessor"] is not None:
                assessors[cell["assessor"]["type"]] += 1
    costs = [record["metadata"]["extractor"]["cost_usd"] for record in records.values()]
    tasks = {record["metadata"]["task_id"] for record in records.values()}
    observed = {record["metadata"]["task_id"] for record in records.values()
                if record["metadata"]["purpose"] == "pilot_a"}
    per_repository = dict()
    lesson_origins = {"from_failed_step": 0, "not_from_failed_step": 0, "unknown": 0}
    usable_lessons, history_lessons = set(), set()
    for identifier, candidate in candidates.items():
        if (candidate["original"]["kind"] == "repo_behaviour" and candidate["evaluation"] is not None
                and candidate["evaluation"]["outcome"] == "usable_as_extracted"):
            usable_lessons.add(candidate["lesson_id"])
            if validity_label(validity[identifier]) in ["repo_history", "repo_history_superseded"]:
                history_lessons.add(candidate["lesson_id"])
    for record in records.values():
        repo = record["metadata"]["repository"] or "unknown"
        counts = per_repository.setdefault(repo, {"lessons": 0, "assumption_occurrences": 0})
        counts["lessons"] += len(record["lessons"])
        counts["assumption_occurrences"] += sum(len(lesson["assumptions"]) for lesson in record["lessons"])
        for lesson in record["lessons"]:
            flag = lesson["from_failed_step"]
            lesson_origins["unknown" if flag is None else "from_failed_step" if flag else "not_from_failed_step"] += 1
    return {
        "purpose": next(iter(records.values()))["metadata"]["purpose"],
        "contract_status": "proposed", "research_complete": False,
        "acquisitions": len(records), "original_lessons": lessons, "original_assumptions": len(candidates),
        "distinct_task_ids": len(tasks - {None}), "extraction_reviews": review_counts,
        "assumption_evaluation_outcomes": dict(assumption_outcomes), "validity_cells": cells,
        "validity_methods": dict(methods), "validity_assessor_types": dict(assessors), "validity_labels": dict(labels),
        "manual_fraction_of_assessed_cells": methods["manual"] / sum(methods.values()) if methods else None,
        "sharing_decisions": sharing["counts"], "sharing": sharing["summary"], "sharing_reviewer": sharing["reviewer"],
        "pilot_b": {key: pilot_b[key] for key in ["exported", "excluded", "contract_status"]},
        "extraction_cost": {"known_usd": sum(cost for cost in costs if cost is not None),
                            "known_acquisitions": sum(cost is not None for cost in costs),
                            "unknown_acquisitions": sum(cost is None for cost in costs)},
        "other_costs": {"agent_runs": "not_aggregated", "checks": "not_aggregated", "container_time": "not_aggregated"},
        "selection": {"selected_tasks": len(selected), "production_tasks_present": sorted(observed),
                      "production_tasks_missing": sorted(set(selected) - observed),
                      "unselected_task_ids": sorted(tasks - {None} - set(selected))},
        "per_repository": per_repository,
        "lesson_origins": lesson_origins,
        "lessons_with_usable_repository_assumption": len(usable_lessons),
        "lessons_with_reviewed_repository_history_assumption": len(history_lessons),
        "design_decisions_pending": ["Freeze the extraction-review rubric and separate repair policy.",
            "Agree Lane R's validity return fields, evidence storage and workspace identifiers.",
            "Agree scoped grouping eligibility, unknown-scope handling and sampling seed.",
            "Agree Pilot B's six exact field names and provenance/export policy."],
    }


def build_handoff(acquisitions, output_dir, evaluations=(), validity_path=None, sharing_path=None, selection_path=SELECTION):
    records, reviews, selected, files, identity = _load_inputs(acquisitions, evaluations, selection_path)
    collection_id = "collection-" + canonical_hash(identity)
    candidates = _candidates(records, selected)
    draft_validity = build_validity_draft(collection_id, candidates)
    validity_bytes = Path(validity_path).read_bytes() if validity_path is not None else _json_bytes(draft_validity)
    validity_input = parse_extraction(validity_bytes.decode("utf-8"))
    validity = validate_validity(validity_input, collection_id, candidates)
    draft_sharing = build_sharing_draft(collection_id, validity, candidates)
    sharing_bytes = Path(sharing_path).read_bytes() if sharing_path is not None else _json_bytes(draft_sharing)
    sharing_input = parse_extraction(sharing_bytes.decode("utf-8"))
    sharing = validate_sharing(sharing_input, collection_id, validity, candidates)
    b_bytes, pilot_b = _export_b(records)
    report = _report(records, reviews, selected, candidates, validity, sharing, pilot_b)
    report["collection_id"] = collection_id
    collection = {"collection_version": 1, "collection_id": collection_id, "identity": identity,
                  "purpose": report["purpose"], "contract_status": "proposed",
                  "candidates": list(candidates.values())}
    requests = {"request_version": 1, "collection_id": collection_id, "contract_status": "proposed",
                "assumptions": [{**candidate, "trajectory_pointer": "../" + candidate["trajectory_pointer"]}
                                for candidate in candidates.values()],
                "instructions": "All candidates are included, including pending reviews. Run no checks solely because a row exists. "
                    "Lane R owns workspace reconstruction and execution; return outcome/method/assessor/evidence declarations. "
                    "Keep gold patches and detailed C1 evidence private to Lane R. Agree the return contract before production."}
    files.update({"collection.json": _json_bytes(collection), "report.json": _json_bytes(report),
                  "lane-r/requests.json": _json_bytes(requests), "lane-r/validity.pending.json": _json_bytes(draft_validity),
                  "validity.input.json": validity_bytes, "sharing/pending.json": _json_bytes(draft_sharing),
                  "sharing/input.json": sharing_bytes, "sharing/summary.json": _json_bytes(sharing),
                  "pilot-b/lessons.draft.jsonl": b_bytes, "pilot-b/status.json": _json_bytes(pilot_b)})
    files["report.md"] = _markdown_report(report).encode("utf-8")
    files["README.md"] = (
        "# Draft Lane N handoff\n\nSee report.md for pending work and proposed contracts.\n"
        "Send lane-r/ plus the referenced acquisitions/ to Lane R for interface review; gold evidence stays with R.\n"
        "Send pilot-b/ plus acquisitions/ together to Pilot B; trajectory pointers are relative to the JSONL file.\n"
        "Do not distribute the private reference directory from a regrouping sample to its reviewer.\n"
        "These hashes detect changed files; they do not authenticate reviewers or establish scientific validity.\n"
    ).encode("utf-8")
    write_bundle(output_dir, files, {"collection_id": collection_id, "contract_status": "proposed"})
    return report


def _markdown_report(report):
    lines = ["# Lane N draft handoff", "", f"Purpose: **{report['purpose']}**. Contracts: **proposed**.",
             "This is a software/status report, not a completed Pilot A study or a Pilot B acceptance certificate.", "",
             f"Original data: {report['acquisitions']} acquisitions, {report['original_lessons']} lessons, "
             f"{report['original_assumptions']} assumption occurrences.", "",
             "| Stage | Recorded state |", "|---|---|"]
    for label, key in [("Extraction review (acquisitions)", "extraction_reviews"), ("Validity (cells)", "validity_cells"),
                       ("Sharing (occurrences)", "sharing_decisions"), ("Pilot B draft", "pilot_b")]:
        lines.append(f"| {label} | " + ", ".join(f"{name}: {count}" for name, count in report[key].items()) + " |")
    lines.extend(["", f"Distinct reported sharing groups: {report['sharing']['distinct_groups']}.",
                  f"Groups in multiple tasks: {report['sharing']['groups_in_multiple_tasks']}.",
                  f"Known extraction cost: ${report['extraction_cost']['known_usd']:.4f}; "
                  f"unknown for {report['extraction_cost']['unknown_acquisitions']} acquisitions.",
                  "Agent, check and container costs are not aggregated here; unknown costs are not zero cost.",
                  f"Selected production tasks still missing: {len(report['selection']['production_tasks_missing'])}.", "",
                  "No human judgments are inferred. All original candidates remain in the denominator. "
                  "Validity evidence references are recorded but not opened or independently verified.",
                  "Negative results concern only the specified workspaces; intermediate observations remain in original assumptions.",
                  "Pilot B receives original advice, without filtering by A review outcome. Missing provenance is listed in pilot-b/status.json.",
                  "", "Design decisions to agree:", ""])
    lines.extend(f"- {decision}" for decision in report["design_decisions_pending"])
    lines.extend(["", "Research work still requires real selected-task acquisitions, human review, workspace-specific checks, "
                  "sharing judgments, the regrouping comparison and the final report. No threshold gates Pilot B.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Prepare requests, pending forms, draft exports and a status report")
    build.add_argument("--acquisition", required=True, action="append", type=Path)
    build.add_argument("--evaluation", action="append", default=[], type=Path)
    build.add_argument("--validity", type=Path)
    build.add_argument("--sharing", type=Path)
    build.add_argument("--selection", type=Path, default=SELECTION)
    build.add_argument("--output-dir", required=True, type=Path)
    sample = commands.add_parser("sample", help="Prepare a blinded 30%-of-groups regrouping form")
    sample.add_argument("--bundle", required=True, type=Path)
    sample.add_argument("--seed", required=True)
    sample.add_argument("--output-dir", required=True, type=Path)
    compare = commands.add_parser("compare", help="Compare the returned partition with the private primary partition")
    compare.add_argument("--sample", required=True, type=Path)
    compare.add_argument("--response", required=True, type=Path)
    compare.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "build":
            report = build_handoff(args.acquisition, args.output_dir, args.evaluation, args.validity, args.sharing, args.selection)
            print(f"Prepared draft handoff: {report['original_lessons']} lessons, {report['original_assumptions']} assumptions.")
            print(f"Pending extraction reviews: {report['extraction_reviews']['pending']}; "
                  f"B draft rows: {report['pilot_b']['exported']}, exclusions: {report['pilot_b']['excluded']}.")
        elif args.command == "sample":
            report = export_regrouping(args.bundle, args.output_dir, args.seed)
            print(f"Prepared {len(report['primary_groups'])} sampled groups. Send only blind/ to the reviewer.")
        else:
            report = compare_regrouping(args.sample, args.response, args.output_dir)
            print(f"Groups changed: {report['groups_changed']}/{report['groups_sampled']}.")
    except (ValueError, OSError) as error:
        parser.exit(2, f"Cannot {args.command} handoff: {error}\n")
    print(f"Output: {args.output_dir.resolve()}. Contracts remain proposed; research is not signed off.")


if __name__ == "__main__":
    main()
