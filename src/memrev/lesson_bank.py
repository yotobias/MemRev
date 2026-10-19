"""The `import` stage: validate a lesson-bank JSONL file into the run.

The schema is documented in docs/lesson-bank-schema.md.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from memrev.repository import Repository
from memrev.store import ExclusionReason, Lesson, RunStore

STAGE = "import"

FIELDS = (
    "lesson_id",
    "lesson_text",
    "task_id",
    "repository",
    "source_revision",
    "trajectory_pointer",
)
# Fields that must be present and non-empty; trajectory_pointer must be present but may be "".
NON_EMPTY = tuple(f for f in FIELDS if f != "trajectory_pointer")

FULL_SHA = re.compile(r"[0-9a-f]{40}")


class InvalidLesson(Exception):
    """The line is not a valid lesson; the message is the exclusion detail."""


@dataclass
class Rejection:
    subject: str
    reason: ExclusionReason
    detail: str


@dataclass
class ImportSummary:
    accepted: int = 0
    new: int = 0
    rejections: list[Rejection] = field(default_factory=list)

    def rejected_per_reason(self) -> Counter:
        return Counter(r.reason for r in self.rejections)


def _subject(bank: Path, line_no: int, record: object) -> str:
    if isinstance(record, dict) and isinstance(record.get("lesson_id"), str) and record["lesson_id"]:
        return f"lesson {record['lesson_id']}"
    return f"{bank.name} line {line_no}"


def _parse(raw: str) -> dict:
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidLesson(f"not valid JSON: {exc.msg}") from None
    if not isinstance(record, dict):
        raise InvalidLesson("not a JSON object")
    return record


def _validate(record: dict, repositories: dict[str, Repository]) -> Lesson:
    missing = [f for f in FIELDS if f not in record]
    if missing:
        raise InvalidLesson(f"missing field(s): {', '.join(missing)}")
    not_text = [f for f in FIELDS if not isinstance(record[f], str)]
    if not_text:
        raise InvalidLesson(f"field(s) not a string: {', '.join(not_text)}")
    empty = [f for f in NON_EMPTY if not record[f].strip()]
    if empty:
        raise InvalidLesson(f"empty field(s): {', '.join(empty)}")

    lesson = Lesson(**{f: record[f] for f in FIELDS})
    repository = repositories.get(lesson.repository)
    if repository is None:
        raise InvalidLesson(f"unknown repository {lesson.repository!r}")
    if not FULL_SHA.fullmatch(lesson.source_revision):
        raise InvalidLesson(f"source revision {lesson.source_revision!r} is not a full 40-character commit SHA")
    if not repository.has_commit(lesson.source_revision):
        raise InvalidLesson(f"source revision {lesson.source_revision} not present in {lesson.repository}")
    return lesson


def import_bank(store: RunStore, bank: Path) -> ImportSummary:
    """Import every valid lesson; reject the rest with an exclusion. Safe to rerun."""
    repositories = {name: Repository(path) for name, path in store.repositories().items()}
    summary = ImportSummary()
    for line_no, raw in enumerate(bank.read_text().splitlines(), start=1):
        if not raw.strip():
            continue
        record: object = None
        subject = f"{bank.name} line {line_no}"
        try:
            record = _parse(raw)
            subject = _subject(bank, line_no, record)
            lesson = _validate(record, repositories)
            existing = store.lesson(lesson.lesson_id)
            if existing is not None and existing != lesson:
                # The stored lesson stays; this line is what gets excluded.
                subject = f"{bank.name} line {line_no}"
                raise InvalidLesson(f"lesson id {lesson.lesson_id!r} already imported with different content")
        except InvalidLesson as exc:
            rejection = Rejection(subject, ExclusionReason.INVALID_LESSON_INPUT, str(exc))
            store.record_exclusion(STAGE, rejection.subject, rejection.reason, rejection.detail)
            summary.rejections.append(rejection)
            continue
        if existing is None:
            store.add_lesson(lesson, imported_from=str(bank))
            summary.new += 1
        store.clear_exclusion(STAGE, subject)
        summary.accepted += 1
    return summary
