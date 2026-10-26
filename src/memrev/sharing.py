"""Explicit scoped grouping and a blinded regrouping sample; no semantic auto-merge."""

import copy
import math
from pathlib import Path

from memrev.evaluation import _validate_reviewer
from memrev.handoff_io import canonical_hash, check_version, exact_rows, json_file, load_bundle, write_bundle
from memrev.provenance import _fields, _json_bytes, _text
from memrev.trajectory import parse_extraction
from memrev.validity import validity_label


def pending_group(identifier):
    return {"assumption_id": identifier, "decision": "pending", "group_id": None, "key": None, "reason": None}


def build_sharing_draft(collection_id, validity, candidates):
    return {"sharing_version": 1, "collection_id": collection_id, "validity_sha256": canonical_hash(validity),
            "reviewer": None, "rows": [pending_group(identifier) for identifier in candidates]}


def validate_sharing(document, collection_id, validity, candidates):
    _fields(document, ["sharing_version", "collection_id", "validity_sha256", "reviewer", "rows"], "sharing")
    check_version(document, "sharing_version")
    if document["collection_id"] != collection_id or document["validity_sha256"] != canonical_hash(validity):
        raise ValueError("sharing: stale collection or validity fingerprint")
    rows = exact_rows(document["rows"], candidates, "sharing.rows")
    if document["reviewer"] is not None:
        _validate_reviewer(document["reviewer"])
    groups = dict()
    counts = {key: 0 for key in ["pending", "group", "exclude", "uncertain"]}
    for identifier, row in rows.items():
        _fields(row, pending_group(identifier), "sharing.row")
        decision = row["decision"]
        if not isinstance(decision, str) or decision not in counts:
            raise ValueError("sharing: unknown decision")
        counts[decision] += 1
        if decision == "pending":
            if row != pending_group(identifier):
                raise ValueError("sharing: pending rows must have empty judgments")
            continue
        if document["reviewer"] is None:
            raise ValueError("sharing: completed judgments require reviewer attribution")
        _text(row["reason"], "sharing.reason", nullable=False)
        if decision != "group":
            if row["group_id"] is not None or row["key"] is not None:
                raise ValueError("sharing: excluded/uncertain rows cannot belong to a group")
            continue
        candidate = candidates[identifier]
        if candidate["evaluation"] is None or candidate["evaluation"]["outcome"] != "usable_as_extracted":
            raise ValueError("sharing: grouped candidates require usable extraction evaluations")
        if candidate["original"]["kind"] != "repo_behaviour":
            raise ValueError("sharing: only repository-behaviour candidates enter this analysis")
        if validity_label(validity[identifier]) not in ["repo_history", "repo_history_superseded"]:
            raise ValueError("sharing: grouped candidates require decided C0/C1 repository support")
        _text(row["group_id"], "sharing.group_id", nullable=False)
        key = row["key"]
        _fields(key, ["repository", "symbol", "predicate", "scope"], "sharing.key")
        for field in ["repository", "symbol", "predicate"]:
            _text(key[field], f"sharing.key.{field}", nullable=False)
        if key["repository"] != candidate["repository"] or key["predicate"] != candidate["original"]["predicate"]:
            raise ValueError("sharing: repository/predicate does not match original candidate")
        _fields(key["scope"], ["inputs", "config", "env"], "sharing.key.scope")
        for field, value in key["scope"].items():
            _text(value, f"sharing.scope.{field}", nullable=False)
        group = groups.setdefault(row["group_id"], {"group_id": row["group_id"], "key": copy.deepcopy(key),
                                                     "members": [], "reasons": {}})
        if group["key"] != key:
            raise ValueError("sharing: members of one group must have the same resolved key")
        group["members"].append(identifier)
        group["reasons"][identifier] = row["reason"]
    summary = {"distinct_groups": len(groups), "grouped_occurrences": counts["group"],
               "groups_in_multiple_lessons": 0, "groups_in_multiple_tasks": 0,
               "groups_in_verified_distinct_prs": 0, "groups_with_repeated_task_occurrences": 0,
               "groups_touching_same_text_tasks": 0}
    for group in groups.values():
        members = [candidates[identifier] for identifier in group["members"]]
        lessons = {member["lesson_id"] for member in members}
        tasks = {member["task_id"] for member in members if member["task_id"] is not None}
        prs = {member["same_pr_group"] for member in members if member["same_pr_group"] is not None}
        summary["groups_in_multiple_lessons"] += len(lessons) > 1
        summary["groups_in_multiple_tasks"] += len(tasks) > 1
        summary["groups_in_verified_distinct_prs"] += len(tasks) > 1 and len(prs) > 1
        summary["groups_with_repeated_task_occurrences"] += any(
            len({member["lesson_id"] for member in members if member["task_id"] == task}) > 1 for task in tasks)
        summary["groups_touching_same_text_tasks"] += any(member["same_text"] for member in members)
        group["members"].sort()
    return {"counts": counts, "summary": summary, "groups": sorted(groups.values(), key=lambda group: group["group_id"]),
            "reviewer": copy.deepcopy(document["reviewer"])}


def export_regrouping(bundle_path, output_dir, seed):
    _text(seed, "sample.seed", nullable=False)
    manifest, files = load_bundle(bundle_path)
    collection = json_file(files, "collection.json")
    sharing = json_file(files, "sharing/summary.json")
    groups = sharing["groups"]
    if not groups or sharing["counts"]["pending"]:
        raise ValueError("sample: finish primary grouping before sampling nonempty groups")
    count = math.ceil(len(groups) * 0.3)
    selected = sorted(groups, key=lambda group: canonical_hash([seed, group["group_id"]]))[:count]
    identifiers = {identifier for group in selected for identifier in group["members"]}
    candidates = {row["assumption_id"]: row for row in collection["candidates"]}
    # Sorting independently of primary groups removes member adjacency as a grouping hint.
    ordered = sorted(identifiers, key=lambda identifier: canonical_hash([seed, identifier]))
    sample_id = "sample-" + canonical_hash([manifest["collection_id"], selected, seed])
    form = {"regrouping_version": 1, "sample_id": sample_id, "reviewer": None,
            "gold_exposure": None, "rows": []}
    blind_files = dict()
    for identifier in ordered:
        candidate = candidates[identifier]
        original = {key: copy.deepcopy(candidate[key]) for key in
                    ["assumption_id", "lesson_id", "advice", "task_id", "repository", "source_revision", "original"]}
        trajectory = f"acquisitions/{candidate['acquisition_id']}/trajectory.json"
        original["trajectory_pointer"] = trajectory
        blind_files[f"blind/{trajectory}"] = files[candidate["trajectory_pointer"]]
        form["rows"].append({"assumption_id": identifier, "original": original,
                             "decision": "pending", "group_id": None, "reason": None})
    reference = {"sample_id": sample_id, "collection_id": manifest["collection_id"], "seed": seed,
                 "fraction": 0.3, "rounding": "ceil", "primary_reviewer": sharing["reviewer"],
                 "primary_groups": selected, "total_primary_groups": len(groups)}
    files = {**blind_files, "blind/regrouping.pending.json": _json_bytes(form), "private/reference.json": _json_bytes(reference),
             "README.md": b"Send only blind/ to the second reviewer. Keep private/ and this package manifest private.\n"
                           b"Freeze the seed before reviewing the sample. Gold exposure must be disclosed on return.\n"}
    write_bundle(output_dir, files, {"sample_id": sample_id, "contract_status": "proposed"})
    return reference


def compare_regrouping(sample_path, response_path, output_dir):
    manifest, files = load_bundle(sample_path)
    pending = json_file(files, "blind/regrouping.pending.json")
    reference = json_file(files, "private/reference.json")
    response_bytes = Path(response_path).read_bytes()
    response = parse_extraction(response_bytes.decode("utf-8"))
    _fields(response, pending, "regrouping")
    check_version(response, "regrouping_version")
    if response["sample_id"] != pending["sample_id"]:
        raise ValueError("regrouping: stale sample_id")
    _validate_reviewer(response["reviewer"])
    if type(response["gold_exposure"]) is not bool:
        raise ValueError("regrouping: disclose gold_exposure as true or false")
    originals = {row["assumption_id"]: row for row in pending["rows"]}
    rows = exact_rows(response["rows"], originals, "regrouping.rows")
    partitions = dict()
    for identifier, row in rows.items():
        _fields(row, originals[identifier], "regrouping.row")
        if canonical_hash(row["original"]) != canonical_hash(originals[identifier]["original"]):
            raise ValueError("regrouping: original candidate changed")
        if row["decision"] not in ["group", "exclude", "uncertain"]:
            raise ValueError("regrouping: all sampled rows must have a completed decision")
        _text(row["reason"], "regrouping.reason", nullable=False)
        if row["decision"] == "group":
            _text(row["group_id"], "regrouping.group_id", nullable=False)
            partitions.setdefault(row["group_id"], set()).add(identifier)
        elif row["group_id"] is not None:
            raise ValueError("regrouping: excluded/uncertain rows cannot have group IDs")
    changed = sum(set(group["members"]) not in partitions.values() for group in reference["primary_groups"])
    total = len(reference["primary_groups"])
    report = {"sample_id": manifest["sample_id"], "groups_sampled": total, "groups_changed": changed,
              "disagreement_rate": changed / total if total else None, "reviewer": response["reviewer"],
              "gold_exposure": response["gold_exposure"], "primary_reviewer": reference["primary_reviewer"],
              "uncertain_occurrences": sum(row["decision"] == "uncertain" for row in rows.values()),
              "contract_status": "proposed", "research_complete": False}
    write_bundle(output_dir, {"report.json": _json_bytes(report), "response.input.json": response_bytes},
                 {"sample_id": manifest["sample_id"]})
    return report
