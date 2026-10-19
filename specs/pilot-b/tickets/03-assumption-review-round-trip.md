# 03: Assumption review round trip

**Status:** done
**Blocked by:** 01
**Estimate:** ~70k tokens

## What to build
A reviewer can export the assumptions in a run to a CSV, accept, edit or reject each one, and import the CSV back. Every assumption is identified by a content hash, so an edit invalidates any evidence, labels or scores attached to the old version. Assumptions can be seeded from a hand-written CSV, so this works without the LLM.

Covers stories 14, 15, 16, 17. Decisions V2, V25, V26.

## Acceptance criteria
- [x] The assumption record holds statement, assumption type (one of the five, or uncheckable), scope, supporting code pointers, check command and asserted target, and a content hash over these fields.
- [x] `review-export` writes a CSV; `review-import` reads it back with a required reviewer id.
- [x] Only accepted (or edited and accepted) assumptions are marked reviewed; rejected ones are recorded with the reviewer id.
- [x] A CSV with missing rows or duplicate ids is rejected as a whole with a clear message.
- [x] Every import prints what changed (accepted, edited, rejected, unchanged).
- [x] Editing an assumption gives it a new hash and marks downstream evidence, labels and scores of the old hash as superseded.
- [x] Assumptions can be loaded from a hand-written seed CSV.

## Notes

Built by an AI agent (Claude Code), test-first on seam N1 (`tests/test_review.py`).

**Commands**
- `memrev --run <dir> seed-assumptions <seed.csv>`: columns `lesson_id, statement, assumption_type, scope, code_pointers, check_command, asserted_target`. Every lesson must already be imported. Any bad row rejects the whole file (exit 2, problems per line on stderr). Reseeding the same content is a no-op (`N added, M already present`).
- `memrev --run <dir> review-export <out.csv>`: all assumptions, columns `assumption_id, lesson_id, status, reviewer_id, decision, statement, assumption_type, scope, code_pointers, check_command, asserted_target, hash`. `decision` is pre-filled from the current status (`accept`, `reject` or empty), so re-importing an untouched export changes nothing.
- `memrev --run <dir> review-import <csv> --reviewer <id>`: the reviewer edits the six content columns and sets `decision` to `accept`, `reject` or leaves it empty. `lesson_id`, `status`, `reviewer_id` and `hash` are ignored on import. Prints `review-import: A accepted, E edited, R rejected, U unchanged (reviewer X)` and then one line per changed assumption, with `(hash old -> new)` for edits.

**Layout**
- `src/memrev/assumptions.py`: the store side. `AssumptionType` (five types + `uncheckable`), `ReviewStatus` (`pending`, `accepted`, `rejected`), `AssumptionContent` (the six reviewable fields, `.hash`), `Assumption`, and `Assumptions(store)`. It creates its own tables on first use (`CREATE TABLE IF NOT EXISTS`), so `store.py` is untouched.
- `src/memrev/review.py`: the three stages. It registers itself in `cli.py` via `review.add_parsers(stages)` and `COMMANDS.update(review.COMMANDS)`.

**Assumption record and hash**
- Table `assumptions`: `assumption_id` (stable, `<lesson_id>#<n>`, kept across edits), `lesson_id`, the six content fields (`code_pointers` as a JSON list), `assumption_hash`, `origin` (`seed` here; ticket 04 uses `extract`, ticket 08 `construct`), `status`, `reviewer_id`, `reviewed_at`.
- `assumption_hash` = sha256 hex of the JSON list `[statement, assumption_type, scope, code_pointers, check_command, asserted_target]` after trimming whitespace; code pointers are split on `;` and trimmed, so spacing is not an edit. The hash covers content only, not `lesson_id`, so two lessons can share a hash: **key downstream rows by `(assumption_id, assumption_hash)`**, never by hash alone.
- `assumption_versions`: every hash an assumption has had, with `superseded_at` (NULL for the current one).
- `review_decisions`: append-only history `(assumption_id, assumption_hash, decision, status, reviewer_id, decided_at)`; decision is `accepted`, `edited` or `rejected`. Ticket 06/10 can use it for reviewer agreement.
- Reviewed set = `Assumptions(store).reviewed()` (status `accepted`). Uncheckable assumptions can be accepted too; ticket 05 must skip `not a.content.assumption_type.checkable`.

**Supersession hook (for tickets 05, 06, 10)**
- A downstream table needs columns `assumption_id TEXT`, `assumption_hash TEXT`, `superseded INTEGER NOT NULL DEFAULT 0`, and its name added via `memrev.assumptions.register_downstream("<table>")` (or appended to `DOWNSTREAM_TABLES`).
- `Assumptions.update_content` (called by review-import on any edit) sets `superseded = 1` on rows with the old hash and `superseded = 0` on rows with the new hash, for every registered table that exists. Reverting an edit therefore makes the original evidence current again.
- `Assumptions.is_superseded(assumption_id, hash)` answers the same question without a table: true if the hash is no longer current. Ticket 05 can use it, or simply compare with the current hash, to decide whether stored evidence can be reused.
- An edit also returns the assumption to `pending` unless the same row says `accept`.

**Decisions made while building** (small, not grilled)
- Decision outcomes per row: `reject` with a content or status change is `rejected`; `accept` with a content change is `edited` (and accepted); `accept` on a non-accepted assumption is `accepted`; a content change with an empty decision is `edited` and goes back to `pending`; everything else is `unchanged`. An empty decision on an unchanged row keeps the current status.
- The review CSV must contain every assumption in the run (missing rows rejected), no duplicates and no unknown ids. Accepting a checkable assumption requires a non-empty `check_command` and `asserted_target`.
- Re-importing the same decision under another reviewer is `unchanged` and keeps the original reviewer id.

**For ticket 06:** "send back for a rewritten check" can call `Assumptions.update_content` with the rewritten check (new hash, status pending, old evidence superseded), or `record_decision(id, ..., ReviewStatus.PENDING, reviewer)` if only the status should change.
