"""Evidence in the run store: drift-guard runs, check runs, verdicts at S and proposed labels.

Assumption rows are keyed to `(assumption_id, assumption_hash)` and registered as downstream
tables, so an edit of an assumption marks them stale (see `memrev.assumptions`).
"""

from __future__ import annotations

from dataclasses import dataclass

from memrev.assumptions import register_downstream
from memrev.store import RunStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS drift_runs (
    pair_id TEXT NOT NULL,
    side TEXT NOT NULL,                   -- S | T
    revision TEXT NOT NULL,
    command TEXT NOT NULL,
    run_index INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    exit_status INTEGER,
    output_excerpt TEXT NOT NULL,
    detail TEXT NOT NULL,
    ran_at TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    PRIMARY KEY (pair_id, revision, command, run_index)
);
CREATE TABLE IF NOT EXISTS drift_verdicts (
    pair_id TEXT PRIMARY KEY,
    verdict TEXT NOT NULL,                -- kept | dropped
    detail TEXT NOT NULL,
    decided_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS evidence (
    assumption_id TEXT NOT NULL,
    assumption_hash TEXT NOT NULL,
    side TEXT NOT NULL,                   -- S | T
    revision TEXT NOT NULL,
    pair_id TEXT NOT NULL,                -- '' at S: the run at S serves every pair of the source
    command TEXT NOT NULL,
    asserted_target TEXT NOT NULL,
    run_index INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    exit_status INTEGER,
    output_excerpt TEXT NOT NULL,
    detail TEXT NOT NULL,
    ran_at TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    stale INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (assumption_id, assumption_hash, revision, run_index)
);
CREATE TABLE IF NOT EXISTS source_verdicts (
    assumption_id TEXT NOT NULL,
    assumption_hash TEXT NOT NULL,
    revision TEXT NOT NULL,
    verdict TEXT NOT NULL,                -- valid | invalid at S
    detail TEXT NOT NULL,
    stale INTEGER NOT NULL DEFAULT 0,
    decided_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (assumption_id, assumption_hash, revision)
);
CREATE TABLE IF NOT EXISTS proposed_labels (
    assumption_id TEXT NOT NULL,
    assumption_hash TEXT NOT NULL,
    pair_id TEXT NOT NULL,
    target_revision TEXT NOT NULL,
    label TEXT NOT NULL,                  -- supported within scope | contradicted | inconclusive
    reason TEXT NOT NULL,                 -- why inconclusive ('' otherwise)
    stale INTEGER NOT NULL DEFAULT 0,
    proposed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (assumption_id, assumption_hash, pair_id)
);
"""

for _table in ("evidence", "source_verdicts", "proposed_labels"):
    register_downstream(_table)

EXCERPT_CHARS = 2000


def excerpt(output: str) -> str:
    """The tail of a run's output, where errors and test summaries end up."""
    return output if len(output) <= EXCERPT_CHARS else "..." + output[-EXCERPT_CHARS:]


@dataclass(frozen=True)
class DriftRun:
    pair_id: str
    side: str
    revision: str
    command: str
    run_index: int
    outcome: str
    exit_status: int | None
    output_excerpt: str
    detail: str
    ran_at: str
    duration_seconds: float


@dataclass(frozen=True)
class Evidence:
    """One execution of an assumption's check."""

    assumption_id: str
    assumption_hash: str
    side: str
    revision: str
    pair_id: str
    command: str
    asserted_target: str
    run_index: int
    outcome: str
    exit_status: int | None
    output_excerpt: str
    detail: str
    ran_at: str
    duration_seconds: float
    stale: bool


@dataclass(frozen=True)
class SourceVerdict:
    assumption_id: str
    assumption_hash: str
    revision: str
    verdict: str
    detail: str
    stale: bool


@dataclass(frozen=True)
class ProposedLabel:
    assumption_id: str
    assumption_hash: str
    pair_id: str
    target_revision: str
    label: str
    reason: str
    stale: bool


_DRIFT_RUN_COLUMNS = (
    "pair_id, side, revision, command, run_index, outcome, exit_status, output_excerpt, detail, "
    "ran_at, duration_seconds"
)
_EVIDENCE_COLUMNS = (
    "assumption_id, assumption_hash, side, revision, pair_id, command, asserted_target, run_index, "
    "outcome, exit_status, output_excerpt, detail, ran_at, duration_seconds, stale"
)
_VERDICT_COLUMNS = "assumption_id, assumption_hash, revision, verdict, detail, stale"
_LABEL_COLUMNS = "assumption_id, assumption_hash, pair_id, target_revision, label, reason, stale"


class EvidenceStore:
    """Evidence access on a run store. Creates its tables on first use."""

    def __init__(self, store: RunStore):
        self.conn = store.conn
        self.conn.executescript(SCHEMA)

    # Drift guard ---------------------------------------------------------

    def add_drift_run(self, run: DriftRun) -> None:
        with self.conn:
            self.conn.execute(
                f"INSERT OR REPLACE INTO drift_runs ({_DRIFT_RUN_COLUMNS}) VALUES ({_marks(11)})",
                (
                    run.pair_id, run.side, run.revision, run.command, run.run_index, run.outcome,
                    run.exit_status, run.output_excerpt, run.detail, run.ran_at, run.duration_seconds,
                ),
            )  # fmt: skip

    def drift_runs(self, pair_id: str) -> list[DriftRun]:
        rows = self.conn.execute(
            f"SELECT {_DRIFT_RUN_COLUMNS} FROM drift_runs WHERE pair_id = ? ORDER BY rowid", (pair_id,)
        )
        return [DriftRun(*row) for row in rows]

    def set_drift_verdict(self, pair_id: str, verdict: str, detail: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO drift_verdicts (pair_id, verdict, detail) VALUES (?, ?, ?)",
                (pair_id, verdict, detail),
            )

    def drift_verdicts(self) -> dict[str, str]:
        """pair_id -> "kept" or "dropped", for every pair the drift guard has decided."""
        return dict(self.conn.execute("SELECT pair_id, verdict FROM drift_verdicts ORDER BY rowid"))

    # Assumption checks -----------------------------------------------------

    def add_evidence(self, ev: Evidence) -> None:
        with self.conn:
            self.conn.execute(
                f"INSERT OR REPLACE INTO evidence ({_EVIDENCE_COLUMNS}) VALUES ({_marks(15)})",
                (
                    ev.assumption_id, ev.assumption_hash, ev.side, ev.revision, ev.pair_id, ev.command,
                    ev.asserted_target, ev.run_index, ev.outcome, ev.exit_status, ev.output_excerpt,
                    ev.detail, ev.ran_at, ev.duration_seconds, int(ev.stale),
                ),
            )  # fmt: skip

    def evidence(self, assumption_id: str | None = None, include_stale: bool = False) -> list[Evidence]:
        query = f"SELECT {_EVIDENCE_COLUMNS} FROM evidence WHERE (? IS NULL OR assumption_id = ?)"
        if not include_stale:
            query += " AND stale = 0"
        rows = self.conn.execute(query + " ORDER BY rowid", (assumption_id, assumption_id))
        return [_evidence(row) for row in rows]

    def runs_at(self, assumption_id: str, assumption_hash: str, revision: str) -> list[Evidence]:
        rows = self.conn.execute(
            f"SELECT {_EVIDENCE_COLUMNS} FROM evidence WHERE assumption_id = ? AND assumption_hash = ? "
            "AND revision = ? ORDER BY run_index",
            (assumption_id, assumption_hash, revision),
        )
        return [_evidence(row) for row in rows]

    def discard_runs_at(self, assumption_id: str, assumption_hash: str, revision: str) -> None:
        """Remove an incomplete set of runs (an interrupted stage) before running again."""
        with self.conn:
            self.conn.execute(
                "DELETE FROM evidence WHERE assumption_id = ? AND assumption_hash = ? AND revision = ?",
                (assumption_id, assumption_hash, revision),
            )

    def set_source_verdict(self, verdict: SourceVerdict) -> None:
        with self.conn:
            self.conn.execute(
                f"INSERT OR REPLACE INTO source_verdicts ({_VERDICT_COLUMNS}) VALUES ({_marks(6)})",
                (*_values(verdict)[:5], int(verdict.stale)),
            )

    def source_verdicts(self, include_stale: bool = False) -> list[SourceVerdict]:
        where = "" if include_stale else " WHERE stale = 0"
        rows = self.conn.execute(f"SELECT {_VERDICT_COLUMNS} FROM source_verdicts{where} ORDER BY rowid")
        return [SourceVerdict(*row[:5], bool(row[5])) for row in rows]

    def set_proposed_label(self, label: ProposedLabel) -> None:
        with self.conn:
            self.conn.execute(
                f"INSERT OR REPLACE INTO proposed_labels ({_LABEL_COLUMNS}) VALUES ({_marks(7)})",
                (*_values(label)[:6], int(label.stale)),
            )

    def proposed_labels(self, include_stale: bool = False) -> list[ProposedLabel]:
        where = "" if include_stale else " WHERE stale = 0"
        rows = self.conn.execute(f"SELECT {_LABEL_COLUMNS} FROM proposed_labels{where} ORDER BY rowid")
        return [ProposedLabel(*row[:6], bool(row[6])) for row in rows]


def _marks(n: int) -> str:
    return ", ".join("?" * n)


def _values(record) -> tuple:
    return tuple(record.__dict__.values())


def _evidence(row) -> Evidence:
    return Evidence(*row[:14], bool(row[14]))
