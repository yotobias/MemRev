"""Harness: runs a maintenance mechanism over a memory bank and a revision pair.

The harness hands a mechanism a `MechanismView` and nothing else. The view is
built from lessons, the revision pair, git access to the repository clone and
each lesson's supporting files. It never holds the run store, its database
connection or its path, so labels and the constructed-case mapping are out of
a mechanism's reach. Only the scorer reads those.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping, Protocol

from memrev.repository import Repository
from memrev.store import Lesson, RunError, RunStore

STAGE = "run-mechanism"

SCHEMA = """
CREATE TABLE IF NOT EXISTS mechanism_decisions (
    mechanism TEXT NOT NULL,
    repository TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    target_revision TEXT NOT NULL,
    lesson_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    PRIMARY KEY (mechanism, repository, source_revision, target_revision, lesson_id)
);
CREATE TABLE IF NOT EXISTS mechanism_costs (
    mechanism TEXT NOT NULL,
    repository TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    target_revision TEXT NOT NULL,
    checks_executed INTEGER NOT NULL,
    wall_time_seconds REAL NOT NULL,
    tokens INTEGER NOT NULL,
    ran_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (mechanism, repository, source_revision, target_revision)
);
-- Interim input until ticket 03 lands: replace with the file part of each
-- reviewed assumption's supporting code pointers, then drop this table.
CREATE TABLE IF NOT EXISTS lesson_supporting_files (
    lesson_id TEXT NOT NULL,
    path TEXT NOT NULL,
    PRIMARY KEY (lesson_id, path)
);
"""


class Decision(StrEnum):
    KEEP = "keep"
    RECHECK = "recheck"
    FLAG = "flag"
    WITHHOLD = "withhold"


@dataclass(frozen=True)
class RevisionPair:
    """The minimal revision-pair value a mechanism sees: repository, S and T."""

    repository: str
    source_revision: str
    target_revision: str


@dataclass
class CostMeter:
    """What a mechanism spends beyond wall time; the harness measures wall time itself."""

    checks_executed: int = 0
    tokens: int = 0

    def count_checks(self, n: int = 1) -> None:
        self.checks_executed += n

    def count_tokens(self, n: int) -> None:
        self.tokens += n


@dataclass(frozen=True)
class Cost:
    checks_executed: int
    wall_time_seconds: float
    tokens: int


@dataclass(frozen=True)
class MechanismView:
    """Everything a mechanism may use. Label-free by construction."""

    lessons: tuple[Lesson, ...]
    pair: RevisionPair
    repository: Repository
    supporting_files: Mapping[str, frozenset[str]]
    """Repository paths each lesson relies on, by lesson id; a lesson may have none."""
    cost: CostMeter = field(default_factory=CostMeter)


class Mechanism(Protocol):
    def decide(self, view: MechanismView) -> Mapping[str, Decision]:
        """Return one decision per lesson id in `view.lessons`."""


class NoMaintenance:
    def decide(self, view: MechanismView) -> Mapping[str, Decision]:
        return {lesson.lesson_id: Decision.KEEP for lesson in view.lessons}


class FileChangeInvalidation:
    """Flag a lesson when any of its supporting files changed between S and T."""

    def decide(self, view: MechanismView) -> Mapping[str, Decision]:
        changed = view.repository.changed_files(view.pair.source_revision, view.pair.target_revision)
        return {
            lesson.lesson_id: Decision.FLAG
            if view.supporting_files.get(lesson.lesson_id, frozenset()) & changed
            else Decision.KEEP
            for lesson in view.lessons
        }


MECHANISMS: dict[str, Mechanism] = {
    "no-maintenance": NoMaintenance(),
    "file-change-invalidation": FileChangeInvalidation(),
}


def _ensure_schema(store: RunStore) -> None:
    store.conn.executescript(SCHEMA)


def _build_view(store: RunStore, pair: RevisionPair) -> MechanismView:
    path = store.repositories().get(pair.repository)
    if path is None:
        raise RunError(f"unknown repository {pair.repository} (map it with `init --repo`)")
    repository = Repository(path)
    for role, revision in (("source", pair.source_revision), ("target", pair.target_revision)):
        if not repository.has_commit(revision):
            raise RunError(f"{role} revision {revision} not in repository {pair.repository}")
    lessons = tuple(
        lesson
        for lesson in store.lessons()
        if lesson.repository == pair.repository and lesson.source_revision == pair.source_revision
    )
    return MechanismView(
        lessons=lessons,
        pair=pair,
        repository=repository,
        supporting_files=_supporting_files(store, [lesson.lesson_id for lesson in lessons]),
    )


def add_supporting_files(store: RunStore, lesson_id: str, paths: list[str]) -> None:
    """Record repository paths a lesson relies on (interim input until ticket 03)."""
    _ensure_schema(store)
    with store.conn:
        store.conn.executemany(
            "INSERT OR IGNORE INTO lesson_supporting_files (lesson_id, path) VALUES (?, ?)",
            [(lesson_id, path) for path in paths],
        )


def _supporting_files(store: RunStore, lesson_ids: list[str]) -> dict[str, frozenset[str]]:
    _ensure_schema(store)
    files: dict[str, set[str]] = {lesson_id: set() for lesson_id in lesson_ids}
    for lesson_id, path in store.conn.execute("SELECT lesson_id, path FROM lesson_supporting_files"):
        if lesson_id in files:
            files[lesson_id].add(path)
    return {lesson_id: frozenset(paths) for lesson_id, paths in files.items()}


@dataclass(frozen=True)
class MechanismRun:
    decisions: dict[str, Decision]
    cost: Cost


def run_mechanism(store: RunStore, name: str, pair: RevisionPair) -> MechanismRun:
    mechanism = MECHANISMS.get(name)
    if mechanism is None:
        raise RunError(f"unknown mechanism {name!r}; known: {', '.join(sorted(MECHANISMS))}")
    view = _build_view(store, pair)
    started = time.perf_counter()
    decisions = _validated(name, view, mechanism.decide(view))
    cost = Cost(view.cost.checks_executed, time.perf_counter() - started, view.cost.tokens)
    _record(store, name, pair, decisions, cost)
    return MechanismRun(decisions, cost)


def _validated(name: str, view: MechanismView, answer: Mapping[str, str]) -> dict[str, Decision]:
    expected = {lesson.lesson_id for lesson in view.lessons}
    missing, unknown = expected - set(answer), set(answer) - expected
    if missing or unknown:
        raise RunError(
            f"mechanism {name} must decide every lesson exactly once "
            f"(missing: {sorted(missing)}, unknown: {sorted(unknown)}); nothing recorded"
        )
    allowed = {str(d) for d in Decision}
    invalid = {lesson_id: d for lesson_id, d in answer.items() if str(d) not in allowed}
    if invalid:
        raise RunError(
            f"mechanism {name} returned decisions outside {sorted(allowed)}: {invalid}; nothing recorded"
        )
    return {lesson_id: Decision(str(d)) for lesson_id, d in answer.items()}


def _record(store: RunStore, name: str, pair: RevisionPair, decisions: dict[str, Decision], cost: Cost) -> None:
    key = (name, pair.repository, pair.source_revision, pair.target_revision)
    where = "mechanism = ? AND repository = ? AND source_revision = ? AND target_revision = ?"
    _ensure_schema(store)
    with store.conn:
        store.conn.execute(f"DELETE FROM mechanism_decisions WHERE {where}", key)
        store.conn.executemany(
            "INSERT INTO mechanism_decisions VALUES (?, ?, ?, ?, ?, ?)",
            [(*key, lesson_id, str(decision)) for lesson_id, decision in decisions.items()],
        )
        store.conn.execute(
            "INSERT OR REPLACE INTO mechanism_costs (mechanism, repository, source_revision, target_revision, "
            "checks_executed, wall_time_seconds, tokens) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (*key, cost.checks_executed, cost.wall_time_seconds, cost.tokens),
        )


def recorded_cost(
    store: RunStore, mechanism: str, repository: str, source_revision: str, target_revision: str
) -> Cost | None:
    _ensure_schema(store)
    row = store.conn.execute(
        "SELECT checks_executed, wall_time_seconds, tokens FROM mechanism_costs WHERE mechanism = ? "
        "AND repository = ? AND source_revision = ? AND target_revision = ?",
        (mechanism, repository, source_revision, target_revision),
    ).fetchone()
    return Cost(*row) if row else None


def recorded_decisions(
    store: RunStore, mechanism: str, repository: str, source_revision: str, target_revision: str
) -> dict[str, str]:
    _ensure_schema(store)
    rows = store.conn.execute(
        "SELECT lesson_id, decision FROM mechanism_decisions WHERE mechanism = ? AND repository = ? "
        "AND source_revision = ? AND target_revision = ? ORDER BY lesson_id",
        (mechanism, repository, source_revision, target_revision),
    )
    return dict(rows)
