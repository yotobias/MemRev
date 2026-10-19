"""Stages `label-export` and `label-import` (the reviewer's sign-off of proposed labels, V19, V26) and
`lesson-labels` (lesson labels derived from the final labels, V22)."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from memrev.assumptions import Assumption, Assumptions, ReviewStatus
from memrev.evidence import EvidenceStore, ProposedLabel
from memrev.labeller import Label
from memrev.labels import ACCEPTED, DOWNGRADED, LabelStore
from memrev.review import _fail, _read_csv
from memrev.store import RunError, RunStore, open_run

EXPORT_COLUMNS = (
    "assumption_id", "lesson_id", "pair_id", "target_revision", "statement", "proposed_label", "reason",
    "runs_at_T", "decision", "check_command", "asserted_target", "final_label", "reviewer_id", "hash",
)  # fmt: skip
IMPORT_COLUMNS = ("assumption_id", "pair_id", "decision", "check_command", "asserted_target", "hash")

# The reviewer fills the `decision` column (V19). Naming the proposed label works like accept,
# naming inconclusive downgrades; any other label would be a flip and is refused.
ACCEPT, REWRITE = "accept", "rewrite"
DECISION_FOR_ACTION = {ACCEPTED: ACCEPT, DOWNGRADED: str(Label.INCONCLUSIVE)}
SENT_BACK, UNCHANGED, NOT_SIGNED = "sent back", "unchanged", "not signed off"
OUTCOMES = (ACCEPTED, DOWNGRADED, SENT_BACK, UNCHANGED, NOT_SIGNED)



@dataclass(frozen=True)
class _Item:
    """One proposed label up for sign-off: a current proposed label of a reviewed assumption."""

    assumption: Assumption
    proposed: ProposedLabel

    @property
    def key(self) -> tuple[str, str]:
        return (self.assumption.assumption_id, self.proposed.pair_id)


def _items(store: RunStore) -> dict[tuple[str, str], _Item]:
    reviewed = {a.assumption_id: a for a in Assumptions(store).reviewed()}
    items = {}
    for p in EvidenceStore(store).proposed_labels():
        a = reviewed.get(p.assumption_id)
        if a is not None and a.hash == p.assumption_hash:
            items[(a.assumption_id, p.pair_id)] = _Item(a, p)
    return items


# label-export -----------------------------------------------------------


def cmd_export(args) -> int:
    store = open_run(args)
    evidence, labels = EvidenceStore(store), LabelStore(store)
    items = _items(store)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for item in items.values():
            a, p = item.assumption, item.proposed
            final = labels.final_label(a.assumption_id, a.hash, p.pair_id)
            runs = evidence.runs_at(a.assumption_id, a.hash, p.target_revision)
            writer.writerow(
                {
                    "assumption_id": a.assumption_id,
                    "lesson_id": a.lesson_id,
                    "pair_id": p.pair_id,
                    "target_revision": p.target_revision,
                    "statement": a.content.statement,
                    "proposed_label": p.label,
                    "reason": p.reason,
                    "runs_at_T": ", ".join(r.outcome for r in runs),
                    "decision": DECISION_FOR_ACTION.get(final.action, "") if final else "",
                    "check_command": a.content.check_command,
                    "asserted_target": a.content.asserted_target,
                    "final_label": final.label if final else "",
                    "reviewer_id": final.reviewer_id if final else "",
                    "hash": a.hash,
                }
            )
    print(f"label-export: {len(items)} proposed labels written to {args.out}")
    return 0


# label-import -----------------------------------------------------------


@dataclass(frozen=True)
class _SignedRow:
    item: _Item
    decision: str  # "" (not signed off), ACCEPTED, DOWNGRADED or REWRITE
    label: str  # the reviewer's label ("" unless accepted or downgraded)
    check: tuple[str, str]  # (check_command, asserted_target) as written in the row


def _decision(raw: str, proposed: str) -> tuple[str, str]:
    """(action, label) for a decision cell; raises ValueError for anything V19 does not allow."""
    if not raw:
        return "", ""
    if raw == REWRITE:
        return REWRITE, ""
    if raw == ACCEPT or raw == proposed:
        return ACCEPTED, proposed
    if raw == Label.INCONCLUSIVE:
        return DOWNGRADED, raw
    if raw in set(Label):
        raise ValueError(
            f'"{raw}" would flip the proposed label "{proposed}"; only {ACCEPT}, {Label.INCONCLUSIVE} or '
            f"{REWRITE} (send the assumption back for a rewritten check and rerun) are allowed"
        )
    allowed = ", ".join(f'"{d}"' for d in (ACCEPT, Label.INCONCLUSIVE, REWRITE))
    raise ValueError(f'decision "{raw}" must be {allowed}, the proposed label, or empty')


def _parse_row(row: dict, items: dict) -> _SignedRow:
    aid, pair_id = (row.get("assumption_id") or "").strip(), (row.get("pair_id") or "").strip()
    item = items.get((aid, pair_id))
    if item is None:
        raise ValueError(f"no proposed label for {aid} on pair {pair_id}")
    if (row.get("hash") or "").strip() != item.assumption.hash:
        raise ValueError(f"{aid} has changed since this file was exported; export again")
    action, label = _decision((row.get("decision") or "").strip().lower(), item.proposed.label)
    check = ((row.get("check_command") or "").strip(), (row.get("asserted_target") or "").strip())
    content = item.assumption.content
    unchanged = check == (content.check_command, content.asserted_target)
    if action == REWRITE and not unchanged and not all(check):
        raise ValueError("a rewritten check needs both check_command and asserted_target")
    if action == REWRITE and unchanged:
        raise ValueError(f"{REWRITE} needs a rewritten check_command or asserted_target")
    return _SignedRow(item, action, label, check)


def _validate(path: Path, rows: list[dict], items: dict, sample: bool = False) -> list[_SignedRow]:
    """Check the whole CSV before anything is applied; raises RunError listing every problem.
    A second reviewer's file is a sample (`sample=True`): rows may be missing."""
    problems, parsed = [], []
    keys = Counter(((r.get("assumption_id") or "").strip(), (r.get("pair_id") or "").strip()) for r in rows)
    duplicates = sorted(k for k, n in keys.items() if n > 1)
    if duplicates:
        problems.append("duplicate rows: " + ", ".join(f"{a} on pair {p}" for a, p in duplicates))
    missing = [] if sample else sorted(set(items) - set(keys))
    if missing:
        problems.append("missing rows: " + ", ".join(f"{a} on pair {p}" for a, p in missing))
    for line_no, row in enumerate(rows, start=2):
        try:
            parsed.append(_parse_row(row, items))
        except ValueError as exc:
            problems.append(f"line {line_no}: {exc}")
    problems += _check_rewrites(parsed)
    _fail(path, problems)
    return parsed


def _check_rewrites(parsed: list[_SignedRow]) -> list[str]:
    """Only a rewrite may change a check, and all rows of one assumption must agree on the rewrite.
    Other rows of a rewritten assumption may repeat the rewritten check or keep the old one."""
    rewrites: dict[str, set] = {}
    for row in parsed:
        if row.decision == REWRITE:
            rewrites.setdefault(row.item.assumption.assumption_id, set()).add(row.check)
    problems = []
    for row in parsed:
        a = row.item.assumption
        if row.decision == REWRITE or row.check == (a.content.check_command, a.content.asserted_target):
            continue
        if a.assumption_id in rewrites:
            rewrites[a.assumption_id].add(row.check)
        else:
            where = f"{a.assumption_id} on pair {row.item.proposed.pair_id}"
            problems.append(f'{where}: only "{REWRITE}" may change the check (check_command, asserted_target)')
    problems += [f"{aid} is rewritten in two different ways" for aid, checks in rewrites.items() if len(checks) > 1]
    return problems


def _send_back(assumptions: Assumptions, row: _SignedRow, reviewer: str) -> str:
    """Rewrite the assumption's check: a new hash, back to pending review, old labels stale. Returns a
    line for the summary."""
    a = row.item.assumption
    command, target = row.check
    assumptions.update_content(a.assumption_id, replace(a.content, check_command=command, asserted_target=target))
    assumptions.record_decision(a.assumption_id, SENT_BACK, ReviewStatus.PENDING, reviewer)
    new_hash = assumptions.get(a.assumption_id).hash
    return f"  {SENT_BACK} {a.assumption_id} (hash {a.hash[:12]} -> {new_hash[:12]})"


def _sign(labels: LabelStore, row: _SignedRow, reviewer: str) -> str:
    """Store the reviewer's final label; returns the outcome for the summary."""
    a, p = row.item.assumption, row.item.proposed
    before = labels.final_label(a.assumption_id, a.hash, p.pair_id)
    if before is not None and (before.reviewer_label, before.action) == (row.label, row.decision):
        return UNCHANGED
    labels.sign(p, row.label, row.decision, reviewer)
    return row.decision


def cmd_import(args) -> int:
    reviewer = args.reviewer.strip()
    if not reviewer:
        raise RunError("--reviewer must not be empty")
    store = open_run(args)
    rows = _read_csv(args.csv, IMPORT_COLUMNS)
    if args.second:
        return _import_second(args.csv, store, rows, reviewer)
    return _import_first(args.csv, store, rows, reviewer)


def _import_first(path: Path, store: RunStore, rows: list[dict], reviewer: str) -> int:
    labels, assumptions = LabelStore(store), Assumptions(store)
    signed = _validate(path, rows, _items(store))
    rewrites = {row.item.assumption.assumption_id: row for row in signed if row.decision == REWRITE}
    outcomes, changes = Counter(), []
    for row in signed:
        if row.item.assumption.assumption_id in rewrites:
            outcomes[SENT_BACK] += 1  # every row of a sent-back assumption waits for the rerun
        elif row.decision:
            outcomes[_sign(labels, row, reviewer)] += 1
        else:
            outcomes[NOT_SIGNED] += 1
    for row in rewrites.values():
        changes.append(_send_back(assumptions, row, reviewer))
    print("label-import: " + ", ".join(f"{outcomes[o]} {o}" for o in OUTCOMES) + f" (reviewer {reviewer})")
    for line in changes:
        print(line)
    return 0


def _import_second(path: Path, store: RunStore, rows: list[dict], reviewer: str) -> int:
    """A second reviewer's sample (V26): report agreement; a disagreement makes the final label inconclusive."""
    labels = LabelStore(store)
    sampled = [row for row in _validate(path, rows, _items(store), sample=True) if row.decision]
    firsts, problems = {}, []
    for row in sampled:
        a, p = row.item.assumption, row.item.proposed
        where = f"{a.assumption_id} on pair {p.pair_id}"
        first = labels.final_label(a.assumption_id, a.hash, p.pair_id)
        if row.decision == REWRITE:
            problems.append(f"{where}: a second reviewer can only accept or downgrade, not {REWRITE}")
        elif first is None:
            problems.append(f"{where} has no first sign-off yet")
        elif first.reviewer_id == reviewer:
            problems.append(f"{where}: {reviewer} signed off this label; a second reviewer must be someone else")
        firsts[row.item.key] = first
    _fail(path, problems)
    disagreements = []
    for row in sampled:
        first = firsts[row.item.key]
        labels.sign_second(first, row.label, reviewer)
        if row.label != first.reviewer_label:
            disagreements.append(
                f"  disagree {first.assumption_id} on pair {first.pair_id}: {first.reviewer_id} "
                f"{first.reviewer_label}, {reviewer} {row.label} -> {Label.INCONCLUSIVE}"
            )
    agree, total = len(sampled) - len(disagreements), len(sampled)
    share = f"{100 * agree / total:.0f}%" if total else "n/a"
    print(f"label-agreement: {agree} of {total} sampled labels agree ({share}) (second reviewer {reviewer})")
    for line in disagreements:
        print(line)
    return 0


# lesson-labels ----------------------------------------------------------


def cmd_lesson_labels(args) -> int:
    store = open_run(args)
    report = LabelStore(store).lesson_report()
    counts = Counter(label.label for label in report.labels)
    print(
        f"lesson-labels: {len(store.lessons())} lessons in the bank, "
        f"{len(report.without_checkable_assumption)} with no checkable assumption (kept, not scored)"
    )
    print(
        "  per revision pair: "
        + ", ".join(f"{label}: {counts[str(label)]}" for label in Label)
        + " (excluded from metrics)"
    )
    print(f"  awaiting check or sign-off: {len(report.awaiting)}")
    constructed = LabelStore(store).constructed_lesson_report()
    n_constructed = len(constructed.without_checkable_assumption) + len(
        {lesson_id for lesson_id, _ in constructed.awaiting} | {label.lesson_id for label in constructed.labels}
    )
    if n_constructed:  # reported apart from natural lessons, never mixed into their counts
        counts = Counter(label.label for label in constructed.labels)
        print(
            f"  constructed lessons: {n_constructed}, per revision pair: "
            + ", ".join(f"{label}: {counts[str(label)]}" for label in Label)
        )
    return 0


# Wiring -----------------------------------------------------------------


def add_parsers(stages: argparse._SubParsersAction) -> None:
    exp = stages.add_parser("label-export", help="write the proposed labels to a sign-off CSV")
    exp.add_argument("out", type=Path, help="CSV file to write")

    imp = stages.add_parser("label-import", help="apply a signed-off label CSV (accept, inconclusive or rewrite)")
    imp.add_argument("csv", type=Path, help="signed-off CSV from label-export")
    imp.add_argument("--reviewer", required=True, help="id of the reviewer who signed off these labels")
    imp.add_argument(
        "--second",
        action="store_true",
        help="the file is a second reviewer's sample: report agreement, disagreements become inconclusive",
    )

    stages.add_parser("lesson-labels", help="derive lesson labels per revision pair from the final labels")


COMMANDS = {"label-export": cmd_export, "label-import": cmd_import, "lesson-labels": cmd_lesson_labels}
