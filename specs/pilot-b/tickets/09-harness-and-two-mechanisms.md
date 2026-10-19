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
- `uv run memrev --run <run-dir> run-mechanism <name> --repository django/django --source <S> --target <T>`. Names: `no-maintenance`, `file-change-invalidation`. Prints decision counts per decision and the cost line (checks executed, wall time, tokens). Exit 2 with a message on an unknown mechanism, an unknown repository, S or T not in the clone, or a mechanism answer that is not exactly one valid decision per lesson; nothing is recorded in those cases.
- The memory bank for a run is every imported lesson with that repository and `source_revision == S`.

**Layout**
- `src/memrev/harness.py`: `Decision`, `RevisionPair`, `MechanismView`, `CostMeter`, `Mechanism` protocol, the two mechanisms, the `MECHANISMS` registry, `run_mechanism`, and the read functions `recorded_decisions` and `recorded_cost`. The harness owns its own `SCHEMA` (tables `mechanism_decisions`, `mechanism_costs`, `lesson_supporting_files`) and applies it itself, so `store.py` is untouched.
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

**To wire after 02 merges (revision pairs)**
- `run-mechanism` takes the pair as `--repository/--source/--target`. After 02, look the pair up in 02's pair table in `harness._build_view` and refuse a pair that was not recorded (or excluded). Optionally add `--pair <id>` as a shortcut, and an `--all-pairs` loop. Keep the `(repository, S, T)` key in `mechanism_decisions` / `mechanism_costs`, or join it to 02's pair id.
- If 02 also adds a method to the end of `Repository`, the merge conflict with `changed_files` is just "keep both".

**To wire after 03 merges (assumptions)**
- Replace the body of `harness._supporting_files` with: for each lesson, the file part of the supporting code pointers of its reviewed assumptions (strip any `::symbol` or `:line` suffix). Then delete `lesson_supporting_files` from the harness schema and `add_supporting_files`, and change the file-change test to seed assumptions through 03's seed CSV instead.
- Only reviewed assumptions' pointers should feed the view; review state is not a label, so this does not break V7.

**After 08 (variant bank)**: `_build_view` should accept the bank to run over (original or variant) and read only the bank's lesson fields, never the constructed-case mapping.

