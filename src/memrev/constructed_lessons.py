"""Kept constructed lessons: the lesson-bank fields plus the revision pair each was constructed for.

The `check` stage and the label store read these to check and label a constructed lesson at its own
pair only. Nothing here says whether a lesson is a constructed stale lesson or a matched control; that
is the constructed-case mapping in `memrev.constructor`, which only the scorer reads.
"""

from __future__ import annotations

from memrev.store import Lesson, RunStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS constructed_lessons (
    lesson_id TEXT PRIMARY KEY,
    lesson_text TEXT NOT NULL,
    task_id TEXT NOT NULL,
    repository TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    trajectory_pointer TEXT NOT NULL,
    pair_id TEXT NOT NULL
);
"""

_COLUMNS = "lesson_id, lesson_text, task_id, repository, source_revision, trajectory_pointer, pair_id"


class ConstructedLessons:
    """Constructed-lesson access on a run store. Creates its table on first use."""

    def __init__(self, store: RunStore):
        self.conn = store.conn
        self.conn.executescript(SCHEMA)

    def add(self, lesson: Lesson, pair_id: str) -> None:
        with self.conn:
            self.conn.execute(
                f"INSERT OR REPLACE INTO constructed_lessons ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (*_lesson_values(lesson), pair_id),
            )

    def all(self) -> list[tuple[Lesson, str]]:
        """Every kept constructed lesson with the pair id it was constructed for."""
        rows = self.conn.execute(f"SELECT {_COLUMNS} FROM constructed_lessons ORDER BY rowid")
        return [(Lesson(*row[:6]), row[6]) for row in rows]

    def get(self, lesson_id: str) -> tuple[Lesson, str] | None:
        row = self.conn.execute(
            f"SELECT {_COLUMNS} FROM constructed_lessons WHERE lesson_id = ?", (lesson_id,)
        ).fetchone()
        return (Lesson(*row[:6]), row[6]) if row else None


def _lesson_values(lesson: Lesson) -> tuple:
    return (
        lesson.lesson_id,
        lesson.lesson_text,
        lesson.task_id,
        lesson.repository,
        lesson.source_revision,
        lesson.trajectory_pointer,
    )
