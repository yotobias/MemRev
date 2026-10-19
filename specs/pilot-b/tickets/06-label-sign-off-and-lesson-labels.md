# 06: Label sign-off and lesson labels

**Status:** done
**Blocked by:** 05
**Estimate:** ~80k tokens

## What to build
A reviewer can sign off proposed labels through a CSV, with only the allowed changes. Final assumption labels then roll up into lesson labels. If a second reviewer labels a sample, agreement is reported.

Covers stories 22, 24, 25, 26. Decisions V19, V22, V26.

## Acceptance criteria
- [x] `label-export` / `label-import` round trip with a required reviewer id.
- [x] Allowed actions: accept, downgrade to inconclusive, send back for a rewritten check (which returns the assumption to review and rerun). A direct flip between supported within scope and contradicted is rejected.
- [x] Lesson label: contradicted if any assumption is contradicted, supported within scope only if all are, otherwise inconclusive and excluded from metrics.
- [x] Lessons with no checkable assumption stay in the bank, are counted, and get no lesson label.
- [x] With a second reviewer's file for a sample, agreement is reported and disagreements become inconclusive.

## Notes

Built by an AI agent (Claude Code), test-first on seam N1 (`tests/test_labels.py`, 28 tests).

**Commands**
- `memrev --run <dir> label-export <out.csv>`: one row per current proposed label of an accepted assumption (stale labels and labels of rejected or pending assumptions are left out). Columns `assumption_id, lesson_id, pair_id, target_revision, statement, proposed_label, reason, runs_at_T, decision, check_command, asserted_target, final_label, reviewer_id, hash`. `runs_at_T` lists the three outcomes from `evidence`. `decision` is pre-filled from an existing final label (`accept` or `inconclusive`), so re-importing an untouched export changes nothing.
- `memrev --run <dir> label-import <csv> --reviewer <id>`: `decision` is `accept`, `inconclusive` (downgrade), `rewrite`, the proposed label itself (same as accept), or empty (not signed off yet). Any other label is a flip and rejects the whole file (V19), naming the allowed actions. Like `review-import`, the file must hold every row exactly once, and any bad row rejects the file (exit 2). A row whose `hash` is not the assumption's current hash is refused ("export again"). Prints `label-import: A accepted, D downgraded, S sent back, U unchanged, N not signed off (reviewer X)`, then one line per sent-back assumption with its hash change.
- `rewrite`: the reviewer writes the new `check_command` and/or `asserted_target` in the row. Other rows of the same assumption may repeat the new check or keep the old one; two different rewrites are refused, and so is a changed check without `rewrite`. The import calls `Assumptions.update_content` (new hash, status pending, old evidence/proposed/final labels stale) and records review decision `sent back`. Every row of that assumption counts as sent back. Next steps: `review-export`/`review-import` to accept it, then `check` to rerun, then sign off again.
- `memrev --run <dir> label-import <csv> --reviewer <id> --second`: a second reviewer's sample (V26). Rows may be missing, and empty decisions are skipped. Each sampled row needs a first sign-off by another reviewer. `rewrite` is refused, and so are flips. Prints `label-agreement: K of N sampled labels agree (P%) (second reviewer X)` and one `disagree ...` line per disagreement. A disagreement makes the final label `inconclusive` with reason `reviewers disagree`, and it stays that way if the first reviewer signs off again.
- `memrev --run <dir> lesson-labels`: prints lessons in the bank, lessons with no checkable assumption (kept, not scored), lesson labels per revision pair by label, and the number of (lesson, pair) still awaiting a check or sign-off.

**Readers (for tickets 08 and 10)**: `memrev.labels.LabelStore(store)`
- `final_labels(include_stale=False) -> list[FinalLabel]` and `final_label(assumption_id, assumption_hash, pair_id)`. `FinalLabel` fields: `assumption_id, assumption_hash, pair_id, target_revision, proposed_label, proposed_reason, reviewer_label, action ('accepted'|'downgraded'), reviewer_id, second_label, second_reviewer_id, label, reason, stale`, plus `.key`. **`label` is the final label**; `reason` is '' unless inconclusive, and then it is the proposed reason, `downgraded by reviewer`, or `reviewers disagree`.
- Table `final_labels`, PK `(assumption_id, assumption_hash, pair_id)`, registered with the staleness hook (`register_downstream("final_labels")` at import of `memrev.labels`; `cli.py` imports it through `signoff`).
- `lesson_labels() -> list[LessonLabel]`: `lesson_id, pair_id, label, assumptions` (tuple of `(assumption_id, assumption_hash)` it was derived from), `.scored` (False for inconclusive). `scored_lesson_labels()` gives only the ones that enter metrics. `lessons_without_checkable_assumption() -> list[lesson_id]`. `lesson_report()` returns all three lists, including `awaiting` `(lesson_id, pair_id)`.
- `reviewer_agreement() -> (agreeing, sampled)` over current final labels.
- The pure rule is `memrev.labeller.lesson_label(labels)`.
- Lesson labels are not stored. They are derived from current final labels on every read, so an edit never leaves a stale lesson label behind.

**Decisions made while building** (small, not grilled)
- A lesson's assumptions for its lesson label are its checkable ones that are not rejected. A pending one (e.g. sent back) holds the label back. An assumption invalid at S counts as inconclusive, so the lesson can be contradicted by another assumption but never supported (V22 "supported only if all are", taken literally). If all of them are invalid at S, the lesson is inconclusive and not scored.
- A lesson gets a label only at drift-kept pairs of its source, and only when every one of its assumptions there has a final label (or is invalid at S). Until then it is "awaiting check or sign-off" and has no label, not inconclusive.
- A lesson with no checkable assumption: no assumptions at all, only uncheckable ones, or only rejected ones.
- Agreement is reported as raw percent agreement on the final label (no kappa). A second reviewer may downgrade but not send back, so the sample cannot change assumptions.

