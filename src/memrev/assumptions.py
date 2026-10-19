"""Assumptions in the run store: the record, its content hash, review state and staleness.

Every assumption has a stable `assumption_id` and a content `assumption_hash` over the
reviewable fields. Downstream records (evidence, labels, scores) are keyed to
`(assumption_id, assumption_hash)`. When an edit changes the hash, `Assumptions.update_content`
marks the rows of every registered downstream table that carry the old hash as stale.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from memrev.store import RunStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS assumptions (
    assumption_id TEXT PRIMARY KEY,
    lesson_id TEXT NOT NULL,
    statement TEXT NOT NULL,
    assumption_type TEXT NOT NULL,
    scope TEXT NOT NULL,
    code_pointers TEXT NOT NULL,          -- JSON list of strings
    check_command TEXT NOT NULL,
    asserted_target TEXT NOT NULL,
    assumption_hash TEXT NOT NULL,
    origin TEXT NOT NULL,                 -- seed | extract | construct
    status TEXT NOT NULL DEFAULT 'pending',
    reviewer_id TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS assumption_versions (
    assumption_id TEXT NOT NULL,
    assumption_hash TEXT NOT NULL,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    superseded_at TEXT,
    PRIMARY KEY (assumption_id, assumption_hash)
);
CREATE TABLE IF NOT EXISTS review_decisions (
    assumption_id TEXT NOT NULL,
    assumption_hash TEXT NOT NULL,
    decision TEXT NOT NULL,               -- accepted | edited | rejected
    status TEXT NOT NULL,                 -- the assumption's status after the decision
    reviewer_id TEXT NOT NULL,
    decided_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Downstream tables whose rows go stale when an assumption's hash changes.
# Each table must have the columns `assumption_id TEXT`, `assumption_hash TEXT` and
# `stale INTEGER NOT NULL DEFAULT 0`. Tickets that add evidence, labels or scores
# append their table name here (or call `register_downstream`).
DOWNSTREAM_TABLES: list[str] = []


def register_downstream(table: str) -> None:
    if table not in DOWNSTREAM_TABLES:
        DOWNSTREAM_TABLES.append(table)


class AssumptionType(StrEnum):
    """The five checkable assumption types (V16), plus uncheckable."""

    SYMBOL_EXISTS = "symbol exists"
    SIGNATURE = "signature"
    RETURN_RAISE = "return/raise behaviour"
    CONFIG_DEFAULT = "config or default value"
    NAMED_TEST_PASSES = "named test passes"
    UNCHECKABLE = "uncheckable"

    @property
    def checkable(self) -> bool:
        return self is not AssumptionType.UNCHECKABLE


class ReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"  # reviewed: enters the labelled set
    REJECTED = "rejected"


@dataclass(frozen=True)
class AssumptionContent:
    """The reviewable fields; the content hash is computed over exactly these."""

    statement: str
    assumption_type: AssumptionType
    scope: str
    code_pointers: tuple[str, ...]
    check_command: str
    asserted_target: str

    @property
    def hash(self) -> str:
        canonical = json.dumps(
            [
                self.statement,
                str(self.assumption_type),
                self.scope,
                list(self.code_pointers),
                self.check_command,
                self.asserted_target,
            ],
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Assumption:
    assumption_id: str
    lesson_id: str
    content: AssumptionContent
    origin: str
    status: ReviewStatus
    reviewer_id: str | None

    @property
    def hash(self) -> str:
        return self.content.hash

    @property
    def reviewed(self) -> bool:
        return self.status is ReviewStatus.ACCEPTED


_COLUMNS = (
    "assumption_id, lesson_id, statement, assumption_type, scope, code_pointers, "
    "check_command, asserted_target, origin, status, reviewer_id"
)


def _row_to_assumption(row) -> Assumption:
    (aid, lesson_id, statement, atype, scope, pointers, command, target, origin, status, reviewer) = row
    content = AssumptionContent(
        statement, AssumptionType(atype), scope, tuple(json.loads(pointers)), command, target
    )
    return Assumption(aid, lesson_id, content, origin, ReviewStatus(status), reviewer)


class Assumptions:
    """Assumption access on a run store. Creates its tables on first use."""

    def __init__(self, store: RunStore):
        self.store = store
        self.conn = store.conn
        self.conn.executescript(SCHEMA)

    def all(self) -> list[Assumption]:
        rows = self.conn.execute(f"SELECT {_COLUMNS} FROM assumptions ORDER BY rowid")
        return [_row_to_assumption(r) for r in rows]

    def reviewed(self) -> list[Assumption]:
        """Accepted assumptions: the ones that enter the labelled set."""
        return [a for a in self.all() if a.reviewed]

    def get(self, assumption_id: str) -> Assumption | None:
        row = self.conn.execute(
            f"SELECT {_COLUMNS} FROM assumptions WHERE assumption_id = ?", (assumption_id,)
        ).fetchone()
        return _row_to_assumption(row) if row else None

    def for_lesson(self, lesson_id: str) -> list[Assumption]:
        return [a for a in self.all() if a.lesson_id == lesson_id]

    def add(self, lesson_id: str, content: AssumptionContent, origin: str) -> Assumption | None:
        """Add a pending assumption to a lesson; returns None if the lesson already has this content."""
        if any(a.hash == content.hash for a in self.for_lesson(lesson_id)):
            return None
        n = len(self.for_lesson(lesson_id)) + 1
        assumption_id = f"{lesson_id}#{n}"
        while self.get(assumption_id) is not None:
            n += 1
            assumption_id = f"{lesson_id}#{n}"
        with self.conn:
            self.conn.execute(
                "INSERT INTO assumptions (assumption_id, lesson_id, statement, assumption_type, scope, "
                "code_pointers, check_command, asserted_target, assumption_hash, origin) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (assumption_id, lesson_id, *self._content_values(content), origin),
            )
            self._record_version(assumption_id, content.hash)
        return self.get(assumption_id)

    def update_content(self, assumption_id: str, content: AssumptionContent) -> bool:
        """Replace an assumption's content. If the hash changes, the assumption returns to pending
        and every downstream row carrying the old hash is marked stale. Returns whether it changed."""
        current = self.get(assumption_id)
        if current is None:
            raise KeyError(assumption_id)
        if current.hash == content.hash:
            return False
        with self.conn:
            self.conn.execute(
                "UPDATE assumptions SET statement = ?, assumption_type = ?, scope = ?, code_pointers = ?, "
                "check_command = ?, asserted_target = ?, assumption_hash = ?, status = 'pending', "
                "reviewer_id = NULL, reviewed_at = NULL WHERE assumption_id = ?",
                (*self._content_values(content), assumption_id),
            )
            self.conn.execute(
                "UPDATE assumption_versions SET superseded_at = datetime('now') "
                "WHERE assumption_id = ? AND assumption_hash = ?",
                (assumption_id, current.hash),
            )
            self._record_version(assumption_id, content.hash)
            self._mark_downstream(assumption_id, stale_hash=current.hash, current_hash=content.hash)
        return True

    def record_decision(self, assumption_id: str, decision: str, status: ReviewStatus, reviewer_id: str) -> None:
        """Store a reviewer's decision and set the assumption's review status."""
        with self.conn:
            self.conn.execute(
                "UPDATE assumptions SET status = ?, reviewer_id = ?, reviewed_at = datetime('now') "
                "WHERE assumption_id = ?",
                (str(status), reviewer_id, assumption_id),
            )
            self.conn.execute(
                "INSERT INTO review_decisions (assumption_id, assumption_hash, decision, status, reviewer_id) "
                "SELECT assumption_id, assumption_hash, ?, ?, ? FROM assumptions WHERE assumption_id = ?",
                (decision, str(status), reviewer_id, assumption_id),
            )

    def is_stale(self, assumption_id: str, assumption_hash: str) -> bool:
        """True if `assumption_hash` is not the assumption's current hash (it was edited since)."""
        current = self.get(assumption_id)
        return current is None or current.hash != assumption_hash

    # Internals -----------------------------------------------------------

    @staticmethod
    def _content_values(content: AssumptionContent) -> tuple:
        return (
            content.statement,
            str(content.assumption_type),
            content.scope,
            json.dumps(list(content.code_pointers)),
            content.check_command,
            content.asserted_target,
            content.hash,
        )

    def _record_version(self, assumption_id: str, assumption_hash: str) -> None:
        self.conn.execute(
            "INSERT INTO assumption_versions (assumption_id, assumption_hash) VALUES (?, ?) "
            "ON CONFLICT(assumption_id, assumption_hash) DO UPDATE SET superseded_at = NULL",
            (assumption_id, assumption_hash),
        )

    def _mark_downstream(self, assumption_id: str, stale_hash: str, current_hash: str) -> None:
        existing = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in DOWNSTREAM_TABLES:
            if table not in existing:
                continue
            self.conn.execute(
                f"UPDATE {table} SET stale = (assumption_hash != ?) "
                "WHERE assumption_id = ? AND assumption_hash IN (?, ?)",
                (current_hash, assumption_id, stale_hash, current_hash),
            )
