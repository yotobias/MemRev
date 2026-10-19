# 09: Harness and two mechanisms

**Status:** done
**Blocked by:** 02
**Estimate:** ~80k tokens

## What to build
A mechanism author can plug a maintenance mechanism into the harness and run it over a memory bank and revision pair. The harness never exposes labels or provenance and records each mechanism's decisions and cost. Two mechanisms ship: no maintenance and file-change invalidation.

Covers stories 34, 35, 37. Decisions V7.

## Acceptance criteria
- [x] The mechanism interface receives a memory bank, a revision pair and repository access, and returns one decision per lesson: keep, recheck, flag or withhold.
- [x] A test proves that a mechanism cannot reach labels or the constructed-case mapping through the harness.
- [x] `run-mechanism` records decisions and cost (checks executed, wall time, tokens) per mechanism and pair.
- [x] No maintenance keeps every lesson; file-change invalidation flags lessons whose supporting files changed between S and T.

## Notes

Built by an AI agent (Claude Code), test-first on seam N1 (`tests/test_harness.py`).

**Command**
- `uv run memrev --run <run-dir> run-mechanism <name> --repository django/django --source <S> --target <T>`, or `run-mechanism <name> --pair <pair_id>`. Names: `no-maintenance`, `file-change-invalidation`. Prints decision counts per decision and the cost line (checks executed, wall time, tokens). Exit 2 with a message on an unknown mechanism, a pair that is not recorded, a pair with an exclusion, an unknown repository, S or T not in the clone, or a mechanism answer that is not exactly one valid decision per lesson; nothing is recorded in those cases. Giving both `--pair` and any of the three, or only some of the three, is also exit 2.
- The memory bank for a run is every imported lesson with that repository and `source_revision == S`.

**Layout**
- `src/memrev/harness.py`: `Decision`, `RevisionPair`, `MechanismView`, `CostMeter`, `Mechanism` protocol, the two mechanisms, the `MECHANISMS` registry, `run_mechanism`, and the read functions `recorded_decisions` and `recorded_cost`. The harness owns its own `SCHEMA` (tables `mechanism_decisions`, `mechanism_costs`) and applies it itself, so `store.py` is untouched.
- `Repository.changed_files(S, T)`: `git diff --name-only --no-renames`, so a rename counts as both the old and the new path.
- To add a mechanism: write a class with `decide(view) -> {lesson_id: Decision}` and add it to `MECHANISMS`.

**Label isolation (V7, V29)**
- `MechanismView` holds only lessons (the bank schema, no provenance), the `RevisionPair`, a `Repository` on the clone, `supporting_files` per lesson and a `CostMeter`. It never holds the `RunStore`, its connection or the run directory path.
- The test plants `lesson_labels` and `constructed_cases` tables with a sentinel string, runs a spy mechanism, and walks every object reachable from the view: no sqlite connection or cursor, no `RunStore`, no sentinel, no path under the run directory. Leaking the store into the view was checked to make this test fail.
- This guards the harness API, not a hostile mechanism: Python code can still open any file it likes. Mechanisms are our own code and reviewed.

**Cost**
- Wall time is measured by the harness around `decide`. Checks executed and tokens are counted by the mechanism through `view.cost.count_checks(n)` / `view.cost.count_tokens(n)`. When a mechanism later gets the check runner (05) or the LLM client (04) through the view, wrap them so they count automatically. Both shipped mechanisms run no checks and use no tokens.
- Rerunning a mechanism on the same pair replaces its decisions and cost row (resumable, no duplicates).

**Decisions made while building** (small, not grilled)
- A lesson with no known supporting files is kept by file-change invalidation: there is nothing to invalidate it on.
- File-change invalidation answers `flag`, not `withhold`, matching the ticket text.
- Decisions and costs are keyed by `(mechanism, repository, S, T)`, the natural key of a revision pair, so they do not depend on 02's pair ids.

**Wired to 02 (revision pairs)**, follow-up after 02, 03 and 09 merged
- `harness._require_runnable` (called first in `_build_view`) finds the `(repository, S, T)` among `store.revision_pairs(repository)` and refuses it if it is missing or if any exclusion, from any stage, has subject `pair <pair_id>` (e.g. the 05 drift guard). The message names the stage, reason and detail.
- `--pair <pair_id>` resolves through `harness.pair_by_id` (uses `store.revision_pair`). The CLI accepts either `--pair` alone or all three of `--repository/--source/--target`.
- Name clash: `harness.RevisionPair` is the minimal `(repository, S, T)` value in the view; `store.RevisionPair` (the full recorded row) is imported in `harness.py` as `RecordedPair`. The view still gets only the minimal one, so `version`, instance ids and `target_role` stay out of mechanisms' reach.
- `mechanism_decisions` / `mechanism_costs` keep the `(mechanism, repository, S, T)` key; no join to `pair_id`. No `--all-pairs` loop yet.
- Tests record pairs with `RunStore.add_revision_pair` (helper `_record_pair` in `tests/test_harness.py`), since the tiny repo's commits can share a committer timestamp (no "later" target) and the `pairs` stage itself is covered in `tests/test_pairs.py`.

**Wired to 03 (assumptions)**
- `harness._supporting_files` now reads `Assumptions(store).reviewed()` (status `accepted`) and takes `harness.file_part` of each code pointer: strips a `::symbol` suffix and a `:12` or `:12-20` line suffix. Pending and rejected assumptions don't count; a lesson with no accepted assumptions has no supporting files and is kept. Uncheckable but accepted assumptions do count.
- The stopgap table `lesson_supporting_files` and `harness.add_supporting_files` are gone. Old run databases may still hold that table; nothing reads it.
- Tests seed assumptions through `seed-assumptions` and decide them through `review-export` / `review-import` (helper `_review_assumptions`).
- Review state is not a label, so feeding reviewed pointers into the view does not break V7.

**After 08 (variant bank)**: `_build_view` should accept the bank to run over (original or variant) and read only the bank's lesson fields, never the constructed-case mapping.

