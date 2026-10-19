"""Stages `seed-assumptions`, `review-export` and `review-import`: the assumption review CSV round trip."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from memrev.assumptions import Assumption, AssumptionContent, Assumptions, AssumptionType, ReviewStatus
from memrev.store import RunError, RunStore

CONTENT_COLUMNS = (
    "statement",
    "assumption_type",
    "scope",
    "code_pointers",
    "check_command",
    "asserted_target",
)
SEED_COLUMNS = ("lesson_id", *CONTENT_COLUMNS)
# `lesson_id`, `status`, `reviewer_id` and `hash` are informational: review-import ignores them.
REVIEW_COLUMNS = ("assumption_id", "lesson_id", "status", "reviewer_id", "decision", *CONTENT_COLUMNS, "hash")
IMPORT_COLUMNS = ("assumption_id", "decision", *CONTENT_COLUMNS)

POINTER_SEPARATOR = "; "

# The reviewer fills the `decision` column; an export pre-fills it from the current status.
ACCEPT, REJECT = "accept", "reject"
DECISIONS = ("", ACCEPT, REJECT)
ACCEPTED, EDITED, REJECTED, UNCHANGED = OUTCOMES = ("accepted", "edited", "rejected", "unchanged")
DECISION_FOR_STATUS = {ReviewStatus.PENDING: "", ReviewStatus.ACCEPTED: ACCEPT, ReviewStatus.REJECTED: REJECT}


def _open_store(args) -> RunStore:
    return RunStore.open(args.run.expanduser().resolve())


def _read_csv(path: Path, required: tuple[str, ...]) -> list[dict]:
    if not path.is_file():
        raise RunError(f"{path}: no such file")
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise RunError(f"{path.name}: missing column(s) {', '.join(missing)}")
        return list(reader)


def _content(row: dict) -> AssumptionContent:
    """Build assumption content from a CSV row; raises ValueError with a readable message."""
    statement = (row.get("statement") or "").strip()
    if not statement:
        raise ValueError("statement is empty")
    raw_type = (row.get("assumption_type") or "").strip()
    try:
        atype = AssumptionType(raw_type)
    except ValueError:
        allowed = ", ".join(f'"{t}"' for t in AssumptionType)
        raise ValueError(f'assumption_type "{raw_type}" is not one of {allowed}') from None
    pointers = tuple(p.strip() for p in (row.get("code_pointers") or "").split(";") if p.strip())
    return AssumptionContent(
        statement=statement,
        assumption_type=atype,
        scope=(row.get("scope") or "").strip(),
        code_pointers=pointers,
        check_command=(row.get("check_command") or "").strip(),
        asserted_target=(row.get("asserted_target") or "").strip(),
    )


def _fail(path: Path, problems: list[str]) -> None:
    if problems:
        lines = "\n".join(f"  {p}" for p in problems)
        raise RunError(f"{path.name} rejected, nothing was imported:\n{lines}")


# seed-assumptions -------------------------------------------------------


def cmd_seed(args) -> int:
    store = _open_store(args)
    assumptions = Assumptions(store)
    rows = _read_csv(args.seed, SEED_COLUMNS)
    problems, parsed = [], []
    for line_no, row in enumerate(rows, start=2):
        lesson_id = (row.get("lesson_id") or "").strip()
        try:
            if store.lesson(lesson_id) is None:
                raise ValueError(f'lesson "{lesson_id}" is not in the run')
            parsed.append((lesson_id, _content(row)))
        except ValueError as exc:
            problems.append(f"line {line_no}: {exc}")
    _fail(args.seed, problems)
    added = sum(assumptions.add(lesson_id, content, origin="seed") is not None for lesson_id, content in parsed)
    print(f"seed-assumptions: {added} added, {len(parsed) - added} already present")
    return 0


# review-export ----------------------------------------------------------


def cmd_export(args) -> int:
    assumptions = Assumptions(_open_store(args))
    rows = assumptions.all()
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for a in rows:
            c = a.content
            writer.writerow(
                {
                    "assumption_id": a.assumption_id,
                    "lesson_id": a.lesson_id,
                    "status": str(a.status),
                    "reviewer_id": a.reviewer_id or "",
                    "decision": DECISION_FOR_STATUS[a.status],
                    "statement": c.statement,
                    "assumption_type": str(c.assumption_type),
                    "scope": c.scope,
                    "code_pointers": POINTER_SEPARATOR.join(c.code_pointers),
                    "check_command": c.check_command,
                    "asserted_target": c.asserted_target,
                    "hash": a.hash,
                }
            )
    print(f"review-export: {len(rows)} assumptions written to {args.out}")
    return 0


# review-import ----------------------------------------------------------


@dataclass(frozen=True)
class _ReviewedRow:
    assumption_id: str
    decision: str
    content: AssumptionContent


def _validate_review(path: Path, rows: list[dict], known: dict) -> list[_ReviewedRow]:
    """Check the whole CSV before anything is applied; raises RunError listing every problem."""
    problems, parsed = [], []
    ids = Counter((row.get("assumption_id") or "").strip() for row in rows)
    duplicates = sorted(i for i, n in ids.items() if n > 1)
    if duplicates:
        problems.append(f"duplicate assumption ids: {', '.join(duplicates)}")
    missing = sorted(set(known) - set(ids))
    if missing:
        problems.append(f"missing rows for assumption ids: {', '.join(missing)}")
    for line_no, row in enumerate(rows, start=2):
        aid = (row.get("assumption_id") or "").strip()
        decision = (row.get("decision") or "").strip().lower()
        try:
            if aid not in known:
                raise ValueError(f'unknown assumption id "{aid}"')
            if decision not in DECISIONS:
                raise ValueError(f'decision "{decision}" must be "{ACCEPT}", "{REJECT}" or empty')
            content = _content(row)
            if decision == ACCEPT and content.assumption_type.checkable and not (
                content.check_command and content.asserted_target
            ):
                raise ValueError("an accepted checkable assumption needs check_command and asserted_target")
            parsed.append(_ReviewedRow(aid, decision, content))
        except ValueError as exc:
            problems.append(f"line {line_no}: {exc}")
    _fail(path, problems)
    return parsed


def _apply(assumptions: Assumptions, row: _ReviewedRow, before: Assumption, reviewer: str) -> str:
    """Apply one reviewed row; returns its outcome: accepted, edited, rejected or unchanged."""
    edited = assumptions.update_content(row.assumption_id, row.content)
    if row.decision == REJECT and (edited or before.status is not ReviewStatus.REJECTED):
        outcome, status = REJECTED, ReviewStatus.REJECTED
    elif row.decision == ACCEPT and edited:
        outcome, status = EDITED, ReviewStatus.ACCEPTED
    elif row.decision == ACCEPT and before.status is not ReviewStatus.ACCEPTED:
        outcome, status = ACCEPTED, ReviewStatus.ACCEPTED
    elif edited:  # edited without a decision: back to pending until someone accepts it
        outcome, status = EDITED, ReviewStatus.PENDING
    else:
        return UNCHANGED
    assumptions.record_decision(row.assumption_id, outcome, status, reviewer)
    return outcome


def cmd_import(args) -> int:
    reviewer = args.reviewer.strip()
    if not reviewer:
        raise RunError("--reviewer must not be empty")
    assumptions = Assumptions(_open_store(args))
    known = {a.assumption_id: a for a in assumptions.all()}
    reviewed = _validate_review(args.csv, _read_csv(args.csv, IMPORT_COLUMNS), known)
    outcomes = Counter()
    changes = []
    for row in reviewed:
        before = known[row.assumption_id]
        outcome = _apply(assumptions, row, before, reviewer)
        outcomes[outcome] += 1
        if outcome != UNCHANGED:
            after = assumptions.get(row.assumption_id)
            hash_note = f" (hash {before.hash[:12]} -> {after.hash[:12]})" if after.hash != before.hash else ""
            changes.append(f"  {outcome} {row.assumption_id}{hash_note}")
    print("review-import: " + ", ".join(f"{outcomes[o]} {o}" for o in OUTCOMES) + f" (reviewer {reviewer})")
    for line in changes:
        print(line)
    return 0


# Wiring -----------------------------------------------------------------


def add_parsers(stages: argparse._SubParsersAction) -> None:
    seed = stages.add_parser("seed-assumptions", help="load hand-written assumptions from a seed CSV")
    seed.add_argument("seed", type=Path, help=f"CSV with columns {', '.join(SEED_COLUMNS)}")

    exp = stages.add_parser("review-export", help="write all assumptions to a review CSV")
    exp.add_argument("out", type=Path, help="CSV file to write")

    imp = stages.add_parser("review-import", help="apply a reviewed CSV (accept, edit or reject each row)")
    imp.add_argument("csv", type=Path, help="reviewed CSV from review-export")
    imp.add_argument("--reviewer", required=True, help="id of the reviewer who made these decisions")


COMMANDS = {"seed-assumptions": cmd_seed, "review-export": cmd_export, "review-import": cmd_import}
