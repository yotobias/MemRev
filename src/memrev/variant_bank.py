"""Variant memory banks: one per revision pair, the bank a mechanism runs over with `--bank variant`.

A variant bank holds lessons in the lesson-bank schema under opaque ids, with no provenance field
(V29). Next to it, each lesson's supporting files (from accepted assumptions, computed when the bank
is built) so the harness can fill a `MechanismView` without knowing what is behind an opaque id.
The harness reads only this module. What sits behind each opaque id is the constructed-case mapping
(`memrev.constructor.variant_entries`), which only the scorer reads.
"""

from __future__ import annotations

from collections.abc import Mapping

from memrev.store import Lesson, RunStore

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
