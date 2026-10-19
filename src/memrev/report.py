"""The `report` stage: renders the scorer's results as Markdown, with a JSON copy alongside.

Rendering only: every number comes from `memrev.scorer`, which is the one module that reads labels
and the constructed-case mapping.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import fields
from pathlib import Path

from memrev import scorer
from memrev.evidence import Evidence
from memrev.labels import FinalLabel
from memrev.lesson_bank import FIELDS as LESSON_FIELDS
from memrev.store import open_run

TITLE = "# MemRev Pilot B report"
SECTION_TITLES = {
    scorer.Section.NATURAL: "## Natural cases",
    scorer.Section.CONSTRUCTED: "## Constructed cases",
}


def table(rows: list[dict], columns: list[str] | None = None) -> list[str]:
    """A Markdown table of `rows` (dicts with the same keys), or a line saying there is nothing."""
    if not rows:
        return ["(none)"]
    columns = columns or list(rows[0])
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(str(row[c]) for c in columns) + " |" for row in rows]
    return lines


def _section(kind: str, data: dict) -> list[str]:
    lessons = data["lessons"]
    lines = [
        SECTION_TITLES[kind],
        "",
        f"Lessons in the bank: {lessons['in the bank']}; "
        f"without a checkable assumption: {lessons['without a checkable assumption']} (kept, not scored).",
        "",
        "### Assumption labels per repository and assumption type",
        "",
        *table(data["assumption_labels"]),
        "",
        "### Lesson labels per repository (one per lesson and revision pair; inconclusive is not scored)",
        "",
        *table(data["lesson_labels"]),
        "",
        "### Inconclusive assumption labels per reason",
        "",
        *_counts(data["inconclusive_reasons"], "reason"),
        "",
        _agreement(data["reviewer_agreement"]),
        "",
        "### Exclusions per reason",
        "",
        *_counts(data["exclusions"], "reason"),
        "",
        f"### Mechanisms ({BANKS[kind]})",
        "",
        *table([_mechanism_cells(row) for row in data["mechanisms"]]),
        "",
        MECHANISM_NOTE,
        "",
    ]
    if kind == scorer.Section.NATURAL:
        y = data["extraction"]
        lines[2:2] = [
            f"Extraction yield: lessons processed: {y['lessons processed']}, checkable assumptions: "
            f"{y['checkable']}, uncheckable: {y['uncheckable']}, extraction failed: {y['extraction failed']}.",
            "",
        ]
    else:
        lines[2:2] = [", ".join(f"{k}: {v}" for k, v in data["cases"].items()).capitalize() + ".", ""]
    return lines


BANKS = {
    scorer.Section.NATURAL: "original memory bank",
    scorer.Section.CONSTRUCTED: "variant memory bank, constructed lessons only",
}
MECHANISM_NOTE = (
    "Lessons scored: lesson labels other than inconclusive. Kept = keep; rejected = flag or withhold; "
    "a recheck is neither and is counted in its own column. Unnecessary rejection: matched controls "
    "rejected, of matched controls supported within scope (constructed cases only). "
    "Cost: checks are those the mechanism executed plus one per recheck, over the whole run."
)


def _mechanism_cells(row: dict) -> dict:
    unnecessary = row["unnecessary rejection"]
    shown = "n/a" if unnecessary is None else f"{unnecessary['rejected']} of {unnecessary['matched controls']}"
    return dict(row, **{"unnecessary rejection": shown})


def _counts(counts: dict[str, int], name: str) -> list[str]:
    return table([{name: key, "count": n} for key, n in sorted(counts.items())])


def _agreement(agreement: dict) -> str:
    sampled, agreeing = agreement["sampled"], agreement["agreeing"]
    if not sampled:
        return "Reviewer agreement: no second-reviewer sample."
    return f"Reviewer agreement: {agreeing} of {sampled} sampled labels agree ({100 * agreeing / sampled:.0f}%)."


def _llm_cost(rows: list[dict]) -> list[str]:
    shown = [dict(row, cost_usd=f"{row['cost_usd']:.4f}") for row in rows]
    return ["## LLM cost per stage", "", *table(shown), ""]


def render(data: dict, run_dir: Path) -> str:
    lines = [TITLE, "", f"Run: {run_dir}", ""]
    for kind in scorer.Section:
        lines += _section(kind, data[kind])
    lines += _llm_cost(data["llm_cost"])
    return "\n".join(lines)


def cmd_report(args) -> int:
    store = open_run(args)
    data = scorer.score(store)
    text = render(data, store.run_dir)
    out = args.out or store.run_dir / "report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    out.with_suffix(".json").write_text(json.dumps(data, indent=2) + "\n")
    print(text)
    print(f"report written to {out} and {out.with_suffix('.json')}")
    return 0


def _csv_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def write_table(directory: Path, name: str, records: list[dict], columns: list[str]) -> None:
    """`<name>.jsonl` (one JSON object per line) and `<name>.csv` (lists as JSON text) with the same rows."""
    with (directory / f"{name}.jsonl").open("w") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    with (directory / f"{name}.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows({c: _csv_value(record[c]) for c in columns} for record in records)


EXPORT_COLUMNS = {
    "lessons": [*LESSON_FIELDS, "case", "pair_id"],
    "assumptions": [
        "assumption_id", "lesson_id", "statement", "assumption_type", "scope", "code_pointers", "check_command",
        "asserted_target", "assumption_hash", "origin", "status", "reviewer_id", "case",
    ],
    "evidence": [*(f.name for f in fields(Evidence)), "lesson_id", "case"],
    "final_labels": [*(f.name for f in fields(FinalLabel)), "lesson_id", "repository", "assumption_type", "case"],
}  # fmt: skip


def cmd_export(args) -> int:
    store = open_run(args)
    data = scorer.dataset(store)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, columns in EXPORT_COLUMNS.items():
        write_table(args.out, name, data[name], columns)
    print(
        f"export: {len(data['lessons'])} lessons, {len(data['assumptions'])} assumptions, "
        f"{len(data['evidence'])} evidence rows, {len(data['final_labels'])} final labels to {args.out}"
    )
    return 0


def add_parsers(stages: argparse._SubParsersAction) -> None:
    rep = stages.add_parser("report", help="score the run and write the report (Markdown plus JSON)")
    rep.add_argument("--out", type=Path, help="Markdown file to write (default <run>/report.md); JSON goes next to it")
    exp = stages.add_parser("export", help="write lessons, assumptions, evidence and final labels as JSONL and CSV")
    exp.add_argument("out", type=Path, help="directory to write the files into")


COMMANDS = {"report": cmd_report, "export": cmd_export}
