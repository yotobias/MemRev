"""Proposed Lane R return contract. This module never executes or reads a check."""

import copy
import re

from memrev.evaluation import _validate_reviewer
from memrev.handoff_io import check_version, exact_rows
from memrev.provenance import _fields, _text


REVISIONS = ["C0", "C1", "Ca"]
OUTCOMES = ["pending", "supported", "contradicted", "inconclusive", "undefined"]


def pending_cell():
    return {"outcome": "pending", "method": None, "assessor": None, "workspace": None,
            "reason": None, "evidence": [], "execution": None}


def build_validity_draft(collection_id, candidates):
    return {"validity_version": 1, "collection_id": collection_id,
            "rows": [{"assumption_id": identifier, **{revision: pending_cell() for revision in REVISIONS}}
                     for identifier in candidates]}


def _validate_cell(cell, revision):
    _fields(cell, pending_cell(), f"validity.{revision}")
    outcome = cell["outcome"]
    if outcome not in OUTCOMES:
        raise ValueError("validity: unknown outcome")
    if outcome == "pending":
        if cell != pending_cell():
            raise ValueError("validity: pending cells cannot contain completed judgments")
        return
    _validate_reviewer(cell["assessor"])
    _text(cell["reason"], "validity.reason", nullable=False)
    if outcome == "undefined":
        if revision != "Ca" or cell["method"] is not None or cell["execution"] is not None or cell["evidence"] != []:
            raise ValueError("validity: undefined is only for unavailable Ca, with no execution/method/evidence")
        _text(cell["workspace"], "validity.workspace")
        return
    _text(cell["workspace"], "validity.workspace", nullable=False)
    if cell["method"] not in ["manual", "execution"]:
        raise ValueError("validity: expected manual or execution method")
    evidence = cell["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("validity: completed judgments require evidence references")
    for item in evidence:
        _fields(item, ["reference", "sha256"], "validity.evidence")
        _text(item["reference"], "validity.evidence.reference", nullable=False)
        if not isinstance(item["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("validity: evidence requires a SHA-256 declaration")
    execution = cell["execution"]
    if cell["method"] == "manual":
        if execution is not None:
            raise ValueError("validity: manual assessments cannot contain an execution")
        return
    _fields(execution, ["command", "asserted_target", "result", "exit_code"], "validity.execution")
    for field in ["command", "asserted_target"]:
        _text(execution[field], f"validity.execution.{field}", nullable=False)
    code = execution["exit_code"]
    if code is not None and type(code) is not int:
        raise ValueError("validity: exit_code must be an integer or null")
    allowed = {"supported": ["pass"], "contradicted": ["fail_on_asserted_target"],
               "inconclusive": ["setup_error", "out_of_scope", "flaky", "timeout", "unresolved"]}
    if execution["result"] not in allowed[outcome]:
        raise ValueError("validity: execution result does not support the stated outcome")
    if outcome == "supported" and code != 0:
        raise ValueError("validity: a passing execution requires exit_code 0")
    if outcome == "contradicted" and (code is None or code == 0):
        raise ValueError("validity: a failed target check requires a nonzero exit code")


def validate_validity(document, collection_id, candidates):
    _fields(document, ["validity_version", "collection_id", "rows"], "validity")
    check_version(document, "validity_version")
    if document["collection_id"] != collection_id:
        raise ValueError("validity: stale collection_id")
    rows = exact_rows(document["rows"], candidates, "validity.rows")
    for row in rows.values():
        _fields(row, ["assumption_id", *REVISIONS], "validity.row")
        for revision in REVISIONS:
            _validate_cell(row[revision], revision)
    return copy.deepcopy(rows)


def validity_label(row):
    """Conservative per-workspace summary, never a claim about all intermediate states."""
    c0, c1, ca = [row[revision]["outcome"] for revision in REVISIONS]
    if "inconclusive" in [c0, c1]:
        return "inconclusive"
    if "pending" in [c0, c1]:
        return "pending"
    if c0 == "supported" and c1 == "contradicted":
        return "repo_history_superseded"
    if "supported" in [c0, c1]:
        return "repo_history"
    if ca == "supported":
        return "agent_edit_only"
    if ca == "undefined":
        return "agent_workspace_unavailable"
    if ca == "contradicted":
        return "not_supported_in_checked_workspaces"
    return ca  # pending or inconclusive; intermediate observations remain in the original.
