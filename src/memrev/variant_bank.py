"""Stage `variant-bank`: one blinded variant memory bank per revision pair (V29), the bank a mechanism
runs over with `--bank variant`.

A variant bank holds lessons in the lesson-bank schema under opaque ids, with no provenance field.
Next to it, each lesson's supporting files (from accepted assumptions, computed when the bank is
built) so the harness can fill a `MechanismView` without knowing what is behind an opaque id. The
harness reads only `VariantBank`.

What sits behind each opaque id (`variant_mapping`, read with `variant_entries`) and the per-pair
salt the ids derive from (`variant_salts`) are part of the constructed-case mapping: only the
scorer reads them.
"""

from __future__ import annotations

import argparse
import hashlib
import secrets
from collections.abc import Mapping
from dataclasses import dataclass

from memrev.assumptions import Assumptions, supporting_files
from memrev.constructed_lessons import ConstructedLessons
from memrev.constructor import CaseStatus, Role, case_records
from memrev.store import Lesson, RevisionPair, RunError, RunStore, open_run

SCHEMA = """
CREATE TABLE IF NOT EXISTS variant_lessons (
    pair_id TEXT NOT NULL,
    lesson_id TEXT NOT NULL,
    lesson_text TEXT NOT NULL,
    task_id TEXT NOT NULL,
    repository TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    trajectory_pointer TEXT NOT NULL,
    PRIMARY KEY (pair_id, lesson_id)
);
CREATE TABLE IF NOT EXISTS variant_supporting_files (
    pair_id TEXT NOT NULL,
    lesson_id TEXT NOT NULL,
    path TEXT NOT NULL,
    PRIMARY KEY (pair_id, lesson_id, path)
);
CREATE TABLE IF NOT EXISTS variant_mapping (
    pair_id TEXT NOT NULL,
    variant_lesson_id TEXT NOT NULL,      -- the opaque id in the variant bank
    kind TEXT NOT NULL,                   -- natural lesson | constructed stale lesson | matched control
    lesson_id TEXT NOT NULL,              -- the natural or constructed lesson behind it
    PRIMARY KEY (pair_id, variant_lesson_id)
);
CREATE TABLE IF NOT EXISTS variant_salts (
    pair_id TEXT PRIMARY KEY,
    salt TEXT NOT NULL                    -- secret: opaque ids and the replacement order derive from it
);
"""

_COLUMNS = "lesson_id, lesson_text, task_id, repository, source_revision, trajectory_pointer"


class VariantBank:
    """Variant-bank access on a run store. Creates its tables on first use."""

    def __init__(self, store: RunStore):
        self.conn = store.conn
        self.conn.executescript(SCHEMA)

    def lessons(self, pair_id: str) -> list[Lesson]:
        """The pair's variant bank, ordered by opaque id (empty if none was built)."""
        rows = self.conn.execute(
            f"SELECT {_COLUMNS} FROM variant_lessons WHERE pair_id = ? ORDER BY lesson_id", (pair_id,)
        )
        return [Lesson(*row) for row in rows]

    def supporting_files(self, pair_id: str) -> dict[str, frozenset[str]]:
        files: dict[str, set[str]] = {lesson.lesson_id: set() for lesson in self.lessons(pair_id)}
        rows = self.conn.execute(
            "SELECT lesson_id, path FROM variant_supporting_files WHERE pair_id = ?", (pair_id,)
        )
        for lesson_id, path in rows:
            files.setdefault(lesson_id, set()).add(path)
        return {lesson_id: frozenset(paths) for lesson_id, paths in files.items()}

    def replace(self, pair_id: str, lessons: list[Lesson], files: Mapping[str, frozenset[str]]) -> None:
        """Write the pair's variant bank, replacing an earlier one."""
        with self.conn:
            self.conn.execute("DELETE FROM variant_lessons WHERE pair_id = ?", (pair_id,))
            self.conn.execute("DELETE FROM variant_supporting_files WHERE pair_id = ?", (pair_id,))
            self.conn.executemany(
                f"INSERT INTO variant_lessons (pair_id, {_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (pair_id, l.lesson_id, l.lesson_text, l.task_id, l.repository, l.source_revision,
                     l.trajectory_pointer)
                    for l in lessons
                ],
            )  # fmt: skip
            self.conn.executemany(
                "INSERT INTO variant_supporting_files (pair_id, lesson_id, path) VALUES (?, ?, ?)",
                [(pair_id, lesson_id, path) for lesson_id, paths in files.items() for path in sorted(paths)],
            )


# The mapping behind the opaque ids: read by the scorer only ------------------


@dataclass(frozen=True)
class VariantEntry:
    """What sits behind one opaque id of a variant bank. Part of the constructed-case mapping: scorer only."""

    pair_id: str
    variant_lesson_id: str
    kind: Role
    lesson_id: str  # the natural lesson id, or the constructed lesson id (see `constructor.case_records`)


def variant_entries(store: RunStore, pair_id: str | None = None) -> list[VariantEntry]:
    """The opaque-id mapping of the variant banks. For the scorer only."""
    store.conn.executescript(SCHEMA)
    rows = store.conn.execute(
        "SELECT pair_id, variant_lesson_id, kind, lesson_id FROM variant_mapping "
        "WHERE (? IS NULL OR pair_id = ?) ORDER BY pair_id, variant_lesson_id",
        (pair_id, pair_id),
    )
    return [VariantEntry(pid, opaque, Role(kind), lesson_id) for pid, opaque, kind, lesson_id in rows]


# Building a bank ------------------------------------------------------------


def _salt(store: RunStore, pair_id: str) -> str:
    """The pair's secret salt, created once, so opaque ids stay stable across rebuilds but cannot be
    recomputed from lesson ids by anyone who has not read the mapping."""
    with store.conn:
        store.conn.execute(
            "INSERT OR IGNORE INTO variant_salts (pair_id, salt) VALUES (?, ?)", (pair_id, secrets.token_hex(16))
        )
    return store.conn.execute("SELECT salt FROM variant_salts WHERE pair_id = ?", (pair_id,)).fetchone()[0]


def _digest(salt: str, *parts: str) -> str:
    return hashlib.sha256("\0".join((salt, *parts)).encode()).hexdigest()


def _reviewed_constructed(store: RunStore, pair_id: str) -> list[tuple[Lesson, Role]]:
    """The pair's kept constructed lessons whose assumption was accepted in review, with their role."""
    roles = {r.lesson_id: r.role for r in case_records(store, pair_id) if r.status == CaseStatus.KEPT}
    accepted = {a.lesson_id for a in Assumptions(store).reviewed()}
    return [
        (lesson, roles[lesson.lesson_id])
        for lesson, pid in ConstructedLessons(store).all()
        if pid == pair_id and lesson.lesson_id in roles and lesson.lesson_id in accepted
    ]


def build_variant_bank(store: RunStore, pair: RevisionPair) -> tuple[int, int] | None:
    """Build the pair's variant bank (V29): the natural bank of (repository, S) with natural lessons
    replaced, in a salted random order, by the pair's reviewed constructed lessons (extra ones are
    added). Every lesson gets an opaque id and an empty trajectory pointer; a constructed lesson takes
    the task id of the lesson it replaces. Returns (lessons, replaced), or None if the pair has no
    reviewed constructed lesson."""
    store.conn.executescript(SCHEMA)
    constructed = _reviewed_constructed(store, pair.pair_id)
    if not constructed:
        return None
    salt = _salt(store, pair.pair_id)
    natural = sorted(
        (l for l in store.lessons() if (l.repository, l.source_revision) == (pair.repository, pair.source_revision)),
        key=lambda l: _digest(salt, "order", l.lesson_id),
    )
    replaced, kept = natural[: len(constructed)], natural[len(constructed) :]
    behind = [(Role.NATURAL, lesson, lesson.task_id) for lesson in kept] + [
        (role, lesson, replaced[i].task_id if i < len(replaced) else lesson.task_id)
        for i, (lesson, role) in enumerate(constructed)
    ]
    entries, bank = [], []
    for kind, lesson, task_id in behind:
        opaque = "v-" + _digest(salt, pair.pair_id, lesson.lesson_id)[:16]
        entries.append(VariantEntry(pair.pair_id, opaque, kind, lesson.lesson_id))
        bank.append(Lesson(opaque, lesson.lesson_text, task_id, pair.repository, pair.source_revision, ""))
    files = supporting_files(store, [e.lesson_id for e in entries])
    VariantBank(store).replace(pair.pair_id, bank, {e.variant_lesson_id: files[e.lesson_id] for e in entries})
    with store.conn:
        store.conn.execute("DELETE FROM variant_mapping WHERE pair_id = ?", (pair.pair_id,))
        store.conn.executemany(
            "INSERT INTO variant_mapping (pair_id, variant_lesson_id, kind, lesson_id) VALUES (?, ?, ?, ?)",
            [(e.pair_id, e.variant_lesson_id, str(e.kind), e.lesson_id) for e in entries],
        )
    return len(bank), len(replaced)


def cmd_variant_bank(args) -> int:
    store = open_run(args)
    wanted = args.pair or list(dict.fromkeys(pid for _, pid in ConstructedLessons(store).all()))
    for pair_id in wanted:
        pair = store.revision_pair(pair_id)
        if pair is None:
            raise RunError(f"{pair_id} is not a recorded revision pair (run `pairs` first)")
        built = build_variant_bank(store, pair)
        if built is None:
            print(f"variant-bank: pair {pair_id}: no reviewed constructed lesson, no variant bank built")
            continue
        size, replaced = built
        n_constructed = len(_reviewed_constructed(store, pair_id))
        print(
            f"variant-bank: pair {pair_id}: {size} lessons; "
            f"{n_constructed} constructed lessons replaced {replaced} natural lessons"
        )
    if not wanted:
        print("variant-bank: no constructed lessons in this run (run `construct` first)")
    return 0


def add_parsers(stages: argparse._SubParsersAction) -> None:
    var = stages.add_parser(
        "variant-bank", help="build the blinded variant memory bank per pair from reviewed constructed lessons"
    )
    var.add_argument(
        "--pair", action="append", help="only this pair id (repeatable; default: every pair with constructed lessons)"
    )


COMMANDS = {"variant-bank": cmd_variant_bank}
