"""Store: the run's own SQLite database and work directory."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

DB_NAME = "run.db"
WORK_DIR = "work"

SCHEMA = """
CREATE TABLE IF NOT EXISTS repositories (
    name TEXT PRIMARY KEY,
    local_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lessons (
    lesson_id TEXT PRIMARY KEY,
    lesson_text TEXT NOT NULL,
    task_id TEXT NOT NULL,
    repository TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    trajectory_pointer TEXT NOT NULL,
    imported_from TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS exclusions (
    stage TEXT NOT NULL,
    subject TEXT NOT NULL,
    reason TEXT NOT NULL,
    detail TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (stage, subject)
);
"""


class ExclusionReason(StrEnum):
    """Fixed exclusion reason codes (spec, Implementation decisions)."""

    INVALID_LESSON_INPUT = "invalid lesson input"
    NO_TARGET = "no target"
    ANCESTRY_FAILED = "ancestry failed"
    CROSS_VERSION = "cross-version"
    ENVIRONMENT_UNAVAILABLE = "environment unavailable"
    EXTRACTION_FAILED = "extraction failed"
    UNCHECKABLE = "uncheckable"
    INVALID_AT_S = "invalid at S"
    OUT_OF_SCOPE_AT_T = "out of scope at T"
    NO_BEHAVIOUR_CHANGE_FOUND = "no behaviour change found"
    GATE_FAILED = "gate failed (constructed)"
    NO_MATCHED_CONTROL = "no matched control"


@dataclass(frozen=True)
class Exclusion:
    stage: str
    subject: str
    reason: str
    detail: str


class RunError(Exception):
    """A run cannot be created or opened; the message is shown to the researcher."""


def _enclosing_checkout(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


@dataclass(frozen=True)
class Lesson:
    lesson_id: str
    lesson_text: str
    task_id: str
    repository: str
    source_revision: str
    trajectory_pointer: str


class RunStore:
    """One run: `<run_dir>/run.db` plus `<run_dir>/work/`."""

    def __init__(self, run_dir: Path, conn: sqlite3.Connection):
        self.run_dir = run_dir
        self.conn = conn

    @classmethod
    def create(cls, run_dir: Path) -> RunStore:
        checkout = _enclosing_checkout(run_dir)
        if checkout is not None:
            raise RunError(
                f"run directory {run_dir} is inside a repository checkout ({checkout}); "
                "choose a directory outside any checkout"
            )
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / WORK_DIR).mkdir(exist_ok=True)
        store = cls(run_dir, sqlite3.connect(run_dir / DB_NAME))
        store.conn.executescript(SCHEMA)
        return store

    @classmethod
    def open(cls, run_dir: Path) -> RunStore:
        db = run_dir / DB_NAME
        if not db.is_file():
            raise RunError(f"no run at {run_dir} (run `memrev --run {run_dir} init` first)")
        store = cls(run_dir, sqlite3.connect(db))
        store.conn.executescript(SCHEMA)
        return store

    @property
    def work_dir(self) -> Path:
        return self.run_dir / WORK_DIR

    # Repositories -------------------------------------------------------

    def set_repository(self, name: str, local_path: Path) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO repositories (name, local_path) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET local_path = excluded.local_path",
                (name, str(local_path)),
            )

    def repositories(self) -> dict[str, Path]:
        rows = self.conn.execute("SELECT name, local_path FROM repositories ORDER BY name")
        return {name: Path(path) for name, path in rows}

    # Lessons ------------------------------------------------------------

    def add_lesson(self, lesson: Lesson, imported_from: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO lessons (lesson_id, lesson_text, task_id, repository, "
                "source_revision, trajectory_pointer, imported_from) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    lesson.lesson_id,
                    lesson.lesson_text,
                    lesson.task_id,
                    lesson.repository,
                    lesson.source_revision,
                    lesson.trajectory_pointer,
                    imported_from,
                ),
            )

    _LESSON_COLUMNS = "lesson_id, lesson_text, task_id, repository, source_revision, trajectory_pointer"

    def lessons(self) -> list[Lesson]:
        rows = self.conn.execute(f"SELECT {self._LESSON_COLUMNS} FROM lessons ORDER BY rowid")
        return [Lesson(*row) for row in rows]

    def lesson(self, lesson_id: str) -> Lesson | None:
        row = self.conn.execute(
            f"SELECT {self._LESSON_COLUMNS} FROM lessons WHERE lesson_id = ?", (lesson_id,)
        ).fetchone()
        return Lesson(*row) if row else None

    # Exclusions ---------------------------------------------------------

    def record_exclusion(self, stage: str, subject: str, reason: ExclusionReason, detail: str) -> None:
        """Record why `subject` left the pipeline at `stage`; one row per (stage, subject)."""
        with self.conn:
            self.conn.execute(
                "INSERT INTO exclusions (stage, subject, reason, detail) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(stage, subject) DO UPDATE SET reason = excluded.reason, "
                "detail = excluded.detail, recorded_at = excluded.recorded_at",
                (stage, subject, str(reason), detail),
            )

    def clear_exclusion(self, stage: str, subject: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM exclusions WHERE stage = ? AND subject = ?", (stage, subject))

    def exclusions(self) -> list[Exclusion]:
        rows = self.conn.execute("SELECT stage, subject, reason, detail FROM exclusions ORDER BY rowid")
        return [Exclusion(*row) for row in rows]
