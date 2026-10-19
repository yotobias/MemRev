"""Final labels in the run store: the reviewer's sign-off of each proposed label.

Rows are keyed to `(assumption_id, assumption_hash, pair_id)` and registered as a downstream table,
so an edit or a rewritten check of an assumption marks its final labels stale (see
`memrev.assumptions`). Read through `LabelStore`, which filters `stale = 0` unless asked otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from memrev.assumptions import Assumption, Assumptions, ReviewStatus, register_downstream
from memrev.checks import KEPT
from memrev.constructed_lessons import ConstructedLessons
from memrev.evidence import EvidenceStore, ProposedLabel
from memrev.labeller import INVALID_AT_S, VALID, Label, lesson_label
from memrev.store import Lesson, RevisionPair, RunStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS final_labels (
    assumption_id TEXT NOT NULL,
    assumption_hash TEXT NOT NULL,
    pair_id TEXT NOT NULL,
    target_revision TEXT NOT NULL,
    proposed_label TEXT NOT NULL,
    proposed_reason TEXT NOT NULL,
    reviewer_label TEXT NOT NULL,         -- the first reviewer's label
    action TEXT NOT NULL,                 -- accepted | downgraded
    reviewer_id TEXT NOT NULL,
    second_label TEXT,                    -- a second reviewer's label, for a sample
    second_reviewer_id TEXT,
    label TEXT NOT NULL,                  -- the final label: reviewer_label unless the reviewers disagree
    reason TEXT NOT NULL,                 -- why inconclusive ('' otherwise)
    stale INTEGER NOT NULL DEFAULT 0,
    decided_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (assumption_id, assumption_hash, pair_id)
);
"""

register_downstream("final_labels")

ACCEPTED, DOWNGRADED = "accepted", "downgraded"
DOWNGRADE_REASON = "downgraded by reviewer"
DISAGREEMENT_REASON = "reviewers disagree"


@dataclass(frozen=True)
class FinalLabel:
    assumption_id: str
    assumption_hash: str
    pair_id: str
    target_revision: str
    proposed_label: str
    proposed_reason: str
    reviewer_label: str
    action: str
    reviewer_id: str
    second_label: str | None
    second_reviewer_id: str | None
    label: str
    reason: str
    stale: bool

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.assumption_id, self.assumption_hash, self.pair_id)


_COLUMNS = (
    "assumption_id, assumption_hash, pair_id, target_revision, proposed_label, proposed_reason, reviewer_label, "
    "action, reviewer_id, second_label, second_reviewer_id, label, reason, stale"
)


def _final(row) -> FinalLabel:
    return FinalLabel(*row[:13], bool(row[13]))


def _settle(label: FinalLabel) -> FinalLabel:
    """Fill in the final label (V19, V26): the first reviewer's label, unless a second reviewer
    disagrees, which makes it inconclusive."""
    if label.second_label is not None and label.second_label != label.reviewer_label:
        return replace(label, label=str(Label.INCONCLUSIVE), reason=DISAGREEMENT_REASON)
    reason = DOWNGRADE_REASON if label.action == DOWNGRADED else label.proposed_reason
    return replace(label, label=label.reviewer_label, reason=reason)


class LabelStore:
    """Final-label access on a run store. Creates its table on first use."""

    def __init__(self, store: RunStore):
        self.store = store
        self.conn = store.conn
        self.conn.executescript(SCHEMA)

    def sign(self, proposed: ProposedLabel, reviewer_label: str, action: str, reviewer_id: str) -> None:
        """Store the first reviewer's sign-off of a proposed label; keeps a second reviewer's label."""
        before = self.final_label(proposed.assumption_id, proposed.assumption_hash, proposed.pair_id)
        second = (before.second_label, before.second_reviewer_id) if before else (None, None)
        self._put(
            FinalLabel(
                proposed.assumption_id, proposed.assumption_hash, proposed.pair_id, proposed.target_revision,
                proposed.label, proposed.reason, reviewer_label, action, reviewer_id, *second, "", "", False,
            )
        )  # fmt: skip

    def sign_second(self, first: FinalLabel, second_label: str, reviewer_id: str) -> FinalLabel:
        """Store a second reviewer's label for a signed-off label; returns the settled final label."""
        settled = _settle(replace(first, second_label=second_label, second_reviewer_id=reviewer_id))
        self._put(settled)
        return settled

    def _put(self, label: FinalLabel) -> None:
        label = _settle(label)
        with self.conn:
            self.conn.execute(
                f"INSERT OR REPLACE INTO final_labels ({_COLUMNS}) VALUES ({', '.join('?' * 14)})",
                (*tuple(label.__dict__.values())[:13], int(label.stale)),
            )

    def reviewer_agreement(self) -> tuple[int, int]:
        """(agreeing, sampled): current final labels that a second reviewer also labelled (V26)."""
        sampled = [f for f in self.final_labels() if f.second_label is not None]
        return sum(f.second_label == f.reviewer_label for f in sampled), len(sampled)

    def final_labels(self, include_stale: bool = False) -> list[FinalLabel]:
        where = "" if include_stale else " WHERE stale = 0"
        rows = self.conn.execute(f"SELECT {_COLUMNS} FROM final_labels{where} ORDER BY rowid")
        return [_final(row) for row in rows]

    def final_label(self, assumption_id: str, assumption_hash: str, pair_id: str) -> FinalLabel | None:
        row = self.conn.execute(
            f"SELECT {_COLUMNS} FROM final_labels WHERE assumption_id = ? AND assumption_hash = ? AND pair_id = ?",
            (assumption_id, assumption_hash, pair_id),
        ).fetchone()
        return _final(row) if row else None

    # Lesson labels (V22), derived on every read so they never outlive an edit ---------

    def lesson_report(self) -> LessonLabelReport:
        """Lesson labels per (lesson, drift-kept revision pair) from the current final labels.

        A lesson's checkable assumptions are its accepted and pending ones (rejected ones are out of the
        dataset). It gets a label at a pair only when none is pending and every one is either invalid at
        S or has a final label there; otherwise the (lesson, pair) is awaiting check or sign-off."""
        pairs = self.store.revision_pairs()
        lessons = [
            (lesson, [p for p in pairs if _same_source(p, lesson)])
            for lesson in self.store.lessons()
        ]  # fmt: skip
        return self._report(lessons)

    def constructed_lesson_report(self) -> LessonLabelReport:
        """The same, for constructed lessons (ticket 08), each at the one pair it was constructed for.
        Kept apart from `lesson_report` so natural and constructed cases are never mixed."""
        constructed = ConstructedLessons(self.store).all()
        return self._report([(lesson, [self.store.revision_pair(pair_id)]) for lesson, pair_id in constructed])

    def _report(self, lessons: list[tuple[Lesson, list[RevisionPair]]]) -> LessonLabelReport:
        assumptions, evidence = Assumptions(self.store), EvidenceStore(self.store)
        source = {(v.assumption_id, v.assumption_hash): v.verdict for v in evidence.source_verdicts()}
        kept = {pair_id for pair_id, verdict in evidence.drift_verdicts().items() if verdict == KEPT}
        report = LessonLabelReport([], [], [])
        for lesson, pairs in lessons:
            checkable = [
                a for a in assumptions.for_lesson(lesson.lesson_id)
                if a.content.assumption_type.checkable and a.status is not ReviewStatus.REJECTED
            ]  # fmt: skip
            if not checkable:
                report.without_checkable_assumption.append(lesson.lesson_id)
                continue
            for pair in pairs:
                if pair is None or pair.pair_id not in kept:
                    continue
                labels = [self._assumption_label(a, pair.pair_id, source) for a in checkable]
                if None in labels:
                    report.awaiting.append((lesson.lesson_id, pair.pair_id))
                    continue
                keys = tuple((a.assumption_id, a.hash) for a in checkable)
                report.labels.append(LessonLabel(lesson.lesson_id, pair.pair_id, str(lesson_label(labels)), keys))
        return report

    def _assumption_label(self, a: Assumption, pair_id: str, source: dict) -> str | None:
        """The assumption's contribution to its lesson label at a pair, or None if not decided yet."""
        if not a.reviewed:
            return None
        verdict = source.get((a.assumption_id, a.hash))
        if verdict == INVALID_AT_S:
            return str(Label.INCONCLUSIVE)
        final = self.final_label(a.assumption_id, a.hash, pair_id) if verdict == VALID else None
        return final.label if final and not final.stale else None

    def lesson_labels(self) -> list[LessonLabel]:
        return self.lesson_report().labels

    def scored_lesson_labels(self) -> list[LessonLabel]:
        """The lesson labels that enter metrics: inconclusive ones are excluded (V22)."""
        return [label for label in self.lesson_labels() if label.scored]

    def lessons_without_checkable_assumption(self) -> list[str]:
        """Lessons kept in the bank and counted, but never labelled or scored (V22)."""
        return self.lesson_report().without_checkable_assumption


def _same_source(pair: RevisionPair, lesson: Lesson) -> bool:
    return (pair.repository, pair.source_revision) == (lesson.repository, lesson.source_revision)


@dataclass(frozen=True)
class LessonLabel:
    lesson_id: str
    pair_id: str
    label: str
    assumptions: tuple[tuple[str, str], ...]  # the (assumption_id, assumption_hash) it was derived from

    @property
    def scored(self) -> bool:
        return self.label != Label.INCONCLUSIVE


@dataclass
class LessonLabelReport:
    labels: list[LessonLabel]
    without_checkable_assumption: list[str]  # lesson ids
    awaiting: list[tuple[str, str]]  # (lesson_id, pair_id) still waiting for a check or sign-off
