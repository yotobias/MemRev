"""Harness: runs a maintenance mechanism over a memory bank and a revision pair.

The harness hands a mechanism a `MechanismView` and nothing else. The view is
built from lessons, the revision pair, git access to the repository clone and
each lesson's supporting files. It never holds the run store, its database
connection or its path, so labels and the constructed-case mapping are out of
a mechanism's reach. Only the scorer reads those.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping, Protocol

from memrev.assumptions import Assumptions
from memrev.repository import Repository
from memrev.store import Lesson, RunError, RunStore
from memrev.store import RevisionPair as RecordedPair
from memrev.variant_bank import VariantBank

STAGE = "run-mechanism"

SCHEMA = """
CREATE TABLE IF NOT EXISTS mechanism_decisions (
    mechanism TEXT NOT NULL,
    repository TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    target_revision TEXT NOT NULL,
    lesson_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    bank TEXT NOT NULL DEFAULT 'original',  -- original | variant
    PRIMARY KEY (mechanism, repository, source_revision, target_revision, bank, lesson_id)
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
    bank TEXT NOT NULL DEFAULT 'original',
    PRIMARY KEY (mechanism, repository, source_revision, target_revision, bank)
);
"""


# The memory banks a mechanism can run over: the imported lessons of S, or the pair's variant bank
# (ticket 08), whose lessons carry opaque ids and no provenance.
ORIGINAL, VARIANT = "original", "variant"
BANKS = (ORIGINAL, VARIANT)


class Decision(StrEnum):
    KEEP = "keep"
    RECHECK = "recheck"
    FLAG = "flag"
    WITHHOLD = "withhold"


@dataclass(frozen=True)
class RevisionPair:
    """The minimal revision-pair value a mechanism sees: repository, S and T.

    Not to be confused with `store.RevisionPair` (imported here as `RecordedPair`), the full row
    the pairs stage records. A run only accepts an (S, T) that is a recorded, non-excluded pair.
    """

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
    _add_bank_column(store, "mechanism_decisions")
    _add_bank_column(store, "mechanism_costs")
    store.conn.executescript(SCHEMA)


def _add_bank_column(store: RunStore, table: str) -> None:
    """Migrate a table from before ticket 08 (no `bank` column): its rows are about the original bank.
    The primary key changes too, so the table is rebuilt from SCHEMA."""
    columns = [row[1] for row in store.conn.execute(f"PRAGMA table_info({table})")]
    if not columns or "bank" in columns:
        return
    with store.conn:
        store.conn.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
        store.conn.executescript(SCHEMA)
        listed = ", ".join(columns)
        store.conn.execute(f"INSERT INTO {table} ({listed}) SELECT {listed} FROM {table}_old")
        store.conn.execute(f"DROP TABLE {table}_old")


def pair_by_id(store: RunStore, pair_id: str) -> RevisionPair:
    """The (repository, S, T) of a recorded revision pair, refused if unknown."""
    recorded = store.revision_pair(pair_id)
    if recorded is None:
        raise RunError(f"{pair_id} is not a recorded revision pair (run `pairs` first)")
    return RevisionPair(recorded.repository, recorded.source_revision, recorded.target_revision)


def _require_runnable(store: RunStore, pair: RevisionPair) -> RecordedPair:
    """The recorded pair for (repository, S, T); refused if not recorded or excluded at any stage."""
    recorded = next(
        (
            p
            for p in store.revision_pairs(pair.repository)
            if (p.source_revision, p.target_revision) == (pair.source_revision, pair.target_revision)
        ),
        None,
    )
    if recorded is None:
        raise RunError(
            f"({pair.repository}, {pair.source_revision}, {pair.target_revision}) "
            "is not a recorded revision pair (run `pairs` first)"
        )
    subject = f"pair {recorded.pair_id}"
    for exclusion in store.exclusions():
        if exclusion.subject == subject:
            raise RunError(
                f"{subject} is excluded at stage {exclusion.stage} ({exclusion.reason}): {exclusion.detail}"
            )
    return recorded


def _build_view(store: RunStore, pair: RevisionPair, bank: str = ORIGINAL) -> MechanismView:
    recorded = _require_runnable(store, pair)
    path = store.repositories().get(pair.repository)
    if path is None:
        raise RunError(f"unknown repository {pair.repository} (map it with `init --repo`)")
    repository = Repository(path)
    for role, revision in (("source", pair.source_revision), ("target", pair.target_revision)):
        if not repository.has_commit(revision):
            raise RunError(f"{role} revision {revision} not in repository {pair.repository}")
    if bank == VARIANT:
        return _variant_view(store, recorded, pair, repository)
    lessons = tuple(
        lesson
        for lesson in store.lessons()
        if lesson.repository == pair.repository and lesson.source_revision == pair.source_revision
    )
    return MechanismView(
        lessons=lessons,
        pair=pair,
        repository=repository,
        supporting_files=supporting_files(store, [lesson.lesson_id for lesson in lessons]),
    )


def _variant_view(
    store: RunStore, recorded: RecordedPair, pair: RevisionPair, repository: Repository
) -> MechanismView:
    """The view over the pair's variant bank: opaque ids, the bank schema, files stored with the bank.
    Reads only `memrev.variant_bank`, never the constructed-case mapping."""
    variant = VariantBank(store)
    lessons = tuple(variant.lessons(recorded.pair_id))
    if not lessons:
        raise RunError(f"pair {recorded.pair_id} has no variant bank (run `variant-bank --pair {recorded.pair_id}`)")
    return MechanismView(
        lessons=lessons, pair=pair, repository=repository, supporting_files=variant.supporting_files(recorded.pair_id)
    )


_LINE_SUFFIX = re.compile(r":\d+(-\d+)?$")


def file_part(code_pointer: str) -> str:
    """The repository path of a code pointer: `a/b.py::Cls.meth`, `a/b.py:12` or `a/b.py:12-20` -> `a/b.py`."""
    return _LINE_SUFFIX.sub("", code_pointer.split("::", 1)[0].strip())


def supporting_files(store: RunStore, lesson_ids: list[str]) -> dict[str, frozenset[str]]:
    """Per lesson, the files its accepted (reviewed) assumptions point at; pending and rejected don't count."""
    files: dict[str, set[str]] = {lesson_id: set() for lesson_id in lesson_ids}
    for assumption in Assumptions(store).reviewed():
        if assumption.lesson_id in files:
            files[assumption.lesson_id].update(
                path for path in map(file_part, assumption.content.code_pointers) if path
            )
    return {lesson_id: frozenset(paths) for lesson_id, paths in files.items()}


@dataclass(frozen=True)
class MechanismRun:
    decisions: dict[str, Decision]
    cost: Cost


def run_mechanism(store: RunStore, name: str, pair: RevisionPair, bank: str = ORIGINAL) -> MechanismRun:
    mechanism = MECHANISMS.get(name)
    if mechanism is None:
        raise RunError(f"unknown mechanism {name!r}; known: {', '.join(sorted(MECHANISMS))}")
    if bank not in BANKS:
        raise RunError(f"unknown bank {bank!r}; known: {', '.join(BANKS)}")
    view = _build_view(store, pair, bank)
    started = time.perf_counter()
    decisions = _validated(name, view, mechanism.decide(view))
    cost = Cost(view.cost.checks_executed, time.perf_counter() - started, view.cost.tokens)
    _record(store, name, pair, bank, decisions, cost)
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


_KEY = "mechanism, repository, source_revision, target_revision, bank"
_WHERE = "mechanism = ? AND repository = ? AND source_revision = ? AND target_revision = ? AND bank = ?"


def _record(
    store: RunStore, name: str, pair: RevisionPair, bank: str, decisions: dict[str, Decision], cost: Cost
) -> None:
    key = (name, pair.repository, pair.source_revision, pair.target_revision, bank)
    _ensure_schema(store)
    with store.conn:
        store.conn.execute(f"DELETE FROM mechanism_decisions WHERE {_WHERE}", key)
        store.conn.executemany(
            f"INSERT INTO mechanism_decisions ({_KEY}, lesson_id, decision) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(*key, lesson_id, str(decision)) for lesson_id, decision in decisions.items()],
        )
        store.conn.execute(
            f"INSERT OR REPLACE INTO mechanism_costs ({_KEY}, checks_executed, wall_time_seconds, tokens) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (*key, cost.checks_executed, cost.wall_time_seconds, cost.tokens),
        )


def recorded_cost(
    store: RunStore, mechanism: str, repository: str, source_revision: str, target_revision: str,
    bank: str = ORIGINAL,
) -> Cost | None:
    _ensure_schema(store)
    row = store.conn.execute(
        f"SELECT checks_executed, wall_time_seconds, tokens FROM mechanism_costs WHERE {_WHERE}",
        (mechanism, repository, source_revision, target_revision, bank),
    ).fetchone()
    return Cost(*row) if row else None


def recorded_decisions(
    store: RunStore, mechanism: str, repository: str, source_revision: str, target_revision: str,
    bank: str = ORIGINAL,
) -> dict[str, str]:
    """Lesson id -> decision; for the variant bank the ids are opaque (the scorer maps them)."""
    _ensure_schema(store)
    rows = store.conn.execute(
        f"SELECT lesson_id, decision FROM mechanism_decisions WHERE {_WHERE} ORDER BY lesson_id",
        (mechanism, repository, source_revision, target_revision, bank),
    )
    return dict(rows)
