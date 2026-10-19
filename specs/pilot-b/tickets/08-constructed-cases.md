# 08: Constructed cases

**Status:** done
**Blocked by:** 04, 06
**Estimate:** ~130k tokens

## What to build
A researcher can generate constructed stale lessons and matched controls for each revision pair, gate them by execution, send them through the same review and sign-off as natural cases, and build a blinded variant memory bank.

Covers stories 27–33. Decisions V4, V5, V6, V29, V30.

## Acceptance criteria
- [x] Candidates are drafted by the LLM from real behaviour changes in the S..T diff; only the advice is written, the repository is never modified.
- [x] A pair with no candidate is recorded as "no behaviour change found".
- [x] A constructed stale lesson is kept only if its check passes 3/3 at S and fails 3/3 at T; others are dropped and counted as "gate failed".
- [x] Each kept stale lesson gets one matched control, drafted the same way (same file or symbol area, similar length and type, passes 3/3 at S and T); stale lessons without one are counted as "no matched control".
- [x] Constructed stale lessons and controls go through the review CSV and label sign-off like natural assumptions.
- [x] The variant memory bank uses opaque ids, the same schema as natural lessons and no provenance field; only the scorer can read the mapping.

## Notes

Built by an AI agent (Claude Code), test-first on seam N1 with the fake LLM and the fake check runner only (`tests/test_constructed.py`, 16 tests; plus one migration test in `tests/test_harness.py`). No real API or Docker call was made.

**Commands**
- `memrev --run <dir> construct [--pair ID ...] [--model M] [--runner NAME[=ARG]]`: per drift-kept pair (default: all of them; a named pair the drift guard did not keep is exit 2), the LLM drafts up to 3 stale candidates from the S..T diff, each is gated 3x at S and 3x at T, and each kept one gets controls drafted and gated. Prints `construct: N revision pairs, cost $X`, then `constructed stale lessons kept: K, gate failed: G`, `matched controls: M, no matched control: U`, `no behaviour change found: B` and, if any, `drafting failed: F (rerun to retry)`. The counts are run totals, read from the tables.
- Then the usual route: `review-export`/`review-import` (constructed assumptions appear as pending rows, origin `construct`), `check` (reuses the gate runs, so no new executions), `label-export`/`label-import`.
- `memrev --run <dir> variant-bank [--pair ID ...]`: builds the blinded variant bank per pair from the constructed lessons whose assumption was **accepted** in review. Default: every pair with constructed lessons. Rerun after review changes; it replaces the bank and keeps the opaque ids.
- `memrev --run <dir> run-mechanism NAME --pair ID --bank variant`: runs a mechanism over the pair's variant bank (exit 2 if none was built). `--bank original` is the default and unchanged.
- `lesson-labels` now also prints `constructed lessons: N, per revision pair: ...` on its own line, apart from the natural counts.

**Layout**
- `src/memrev/constructor.py`: both stages, prompts and schemas, `make_llm(model)` (tests monkeypatch `constructor.make_llm`, like `extraction.make_llm`), the gate, control matching, `build_variant_bank`, and the two scorer-only readers `case_records` and `variant_entries`.
- `src/memrev/constructed_lessons.py`: `ConstructedLessons(store)` with `add`, `all()`, `get(id)` → `(Lesson, pair_id)`. No role in it. `check` and `LabelStore` read it.
- `src/memrev/variant_bank.py`: `VariantBank(store)` with `lessons(pair_id)`, `supporting_files(pair_id)`, `replace(...)`. The harness reads only this.
- `Repository.diff(S, T, paths)`: read-only `git diff --no-renames`.
- `checks.py`: an assumption whose lesson is constructed is checked only at the pair it was constructed for (`_lesson_and_pairs`).
- `labels.py`: `LabelStore.constructed_lesson_report()`, same rules as `lesson_report()` (V22) over constructed lessons at their own pair. `lesson_report()` still covers natural lessons only.
- `harness.py`: `--bank`, `harness.BANKS = ("original", "variant")`, `_variant_view`. `_supporting_files` is now public `supporting_files` (the variant bank builder uses it). `mechanism_decisions` and `mechanism_costs` gained a `bank` column (in the primary key); `_ensure_schema` migrates a pre-08 table (rows become `original`). `recorded_decisions` / `recorded_cost` take `bank="original"`.

**Tables and how ticket 10 reads them**
- `constructed_lessons` (`lesson_id, lesson_text, task_id, repository, source_revision, trajectory_pointer, pair_id`): kept constructed lessons only. `task_id` is the pair's source instance, `trajectory_pointer` is empty.
- `constructed_cases` (mapping; read with `constructor.case_records(store, pair_id=None)` → `CaseRecord`): one row per drafted candidate, kept or not. `case_key` is `<pair_id>/stale-<n>` or `<pair_id>/stale-<n>/control-<m>`; `role` is `constructor.STALE` ("constructed stale lesson") or `constructor.CONTROL` ("matched control"); `stale_case_key` links a control to its stale lesson; `lesson_id` / `assumption_id` (`<lesson_id>#1`) are the constructed ids; `status` is `kept`, `gate failed` or `not matched`; `detail` holds the outcomes or the mismatch; `draft` is the LLM's candidate as JSON. A stale lesson has a matched control iff some control row with its `stale_case_key` has status `kept`.
- `variant_mapping` (mapping; read with `constructor.variant_entries(store, pair_id=None)` → `VariantEntry(pair_id, variant_lesson_id, kind, lesson_id)`): `kind` is `constructor.NATURAL` ("natural lesson"), `STALE` or `CONTROL`; `lesson_id` is the natural lesson id or the constructed lesson id. To score a variant-bank decision: `harness.recorded_decisions(store, mech, repo, S, T, bank="variant")` gives opaque ids → join on `variant_entries` → for a constructed lesson take its label from `LabelStore.constructed_lesson_report()`, for a natural one from `lesson_report()` at that pair.
- `variant_salts` (`pair_id, salt`): the secret per pair from which opaque ids and the replacement order derive. Part of the mapping.
- `variant_lessons` (`pair_id` + the six lesson-bank fields) and `variant_supporting_files` (`pair_id, lesson_id, path`): the bank the harness reads. No provenance column (a test checks the column list).
- Exclusions, stage `construct`: subject `constructed cases for pair <pair_id>` with "no behaviour change found" (or "extraction failed" with detail `drafting failed: ...` when the LLM call fails persistently; retried on the next run); subject `candidate <case_key>` with "gate failed (constructed)" or "no matched control". The subjects deliberately avoid `pair <pair_id>`, because the harness refuses any pair with such an exclusion.
- Evidence: gate runs are stored in `evidence` under the candidate's would-be assumption id, so gate-failed candidates also have evidence rows whose `assumption_id` is in no `assumptions` row. Join through `constructed_cases.assumption_id` to tell them apart in the export.

**Blinding (V29) and its test**
- `test_a_mechanism_over_the_variant_bank_sees_no_provenance` walks every object reachable from the view (the `_reachable` helper from `test_harness.py`): no connection or store, no natural or constructed lesson id, none of the words stale/control/constructed/natural/provenance in any string, no run-directory path. Making the opaque id equal to the underlying id was checked to make it fail.
- Opaque ids are `v-` + 16 hex of sha256(salt, pair_id, underlying id), stable across rebuilds. Without the salt, ids could be recomputed from the original bank's lesson ids. Variant lessons are listed in opaque-id order, so position says nothing either.
- What blinding cannot hide: a natural lesson's text is the same in both banks, so a mechanism that also kept the original bank could match texts. Mechanisms get one bank per run, and the harness gives no access to the other.

**Decisions made while building** (small, not grilled)
- Candidates: one LLM call per pair over `git diff S T -- '*.py'`, cut at 60,000 characters with a truncation marker; up to 3 stale candidates per pair (asked in the prompt, not enforced); one control call per kept stale lesson, up to 3 alternatives, best first. The first alternative that matches and passes its gate is the control. An empty `*.py` diff still goes to the LLM, which should return no candidate.
- Control matching (V6 "same file or symbol area, similar length and type"): same assumption type; at least one supporting file in common (file part of the code pointers); lesson text between half and twice the stale lesson's length. Mismatches are not gated (saves executions) and are stored as `not matched`.
- Gates: stale needs 3/3 `pass` at S and 3/3 `fail on asserted target` at T; harness errors, out-of-scope and disagreements fail the gate. A control needs 3/3 `pass` at S and at T. A candidate with uncheckable type or no check command / asserted target fails the gate without running. Failed controls are recorded in `constructed_cases` only; the exclusion counted for the stale lesson is "no matched control" (no extra "gate failed" for controls).
- A constructed lesson has exactly one assumption and is checked and labelled only at its own pair, never at the other targets of its source.
- The variant bank includes every constructed lesson of the pair whose assumption is accepted, matched or not (V6: unmatched ones are reported, and the scorer leaves them out of unnecessary rejection). A control whose stale lesson was rejected in review still enters. A pair with no accepted constructed lesson gets no variant bank.
- Replacement: natural lessons of (repository, S) are ordered by a salted hash; the first k are replaced by the k constructed lessons; if there are more constructed than natural lessons, the rest are added. A constructed lesson takes the task id of the lesson it replaces. Every variant lesson gets an empty trajectory pointer, since only natural lessons have trajectories.
- Supporting files of variant lessons are computed from accepted assumptions when the bank is built and stored with it. Rebuild (`variant-bank`) after editing code pointers in review.
- Constructed lesson ids are neutral (`c-` + hash of the case key), so the review and label CSVs do not show stale versus control. The label CSV still shows the proposed label, which reveals it.
- The lesson text of a constructed lesson is not in the review CSV (only its assumption is), as for natural lessons. It is in `constructed_lessons` and in `constructed_cases.draft`.
- Resumability: a rerun of `construct` redoes every selected pair, but the LLM output comes from the cache and the gate runs are reused from evidence, so nothing is called or executed again and nothing is duplicated.
