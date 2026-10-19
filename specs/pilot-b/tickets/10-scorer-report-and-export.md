# 10: Scorer, report and export

**Status:** done
**Blocked by:** 06, 08, 09
**Estimate:** ~100k tokens

## What to build
A reader gets one report per run that answers the pilot's questions, and teammates get the dataset as JSONL and CSV. The scorer is the only component that reads labels and the constructed-case mapping.

Covers stories 36, 38, 39, 43. Decisions V22, V23.

## Acceptance criteria
- [x] Label counts per repository and assumption type, natural and constructed cases always separate.
- [x] Extraction yield, exclusion counts per exclusion reason, and reviewer agreement where available.
- [x] Per mechanism: contradicted lessons kept, unnecessary rejection (constructed stale lessons with a matched control only), recheck count in its own column, and cost.
- [x] Recheck decisions add to cost and count as neither kept nor rejected.
- [x] `export` writes lessons, assumptions, evidence and final labels as JSONL and CSV.

## Notes
- From 08: the constructed-case mapping (`constructor.case_records`, `constructor.variant_entries`), constructed lesson labels (`LabelStore.constructed_lesson_report()`) and variant-bank decisions (`harness.recorded_decisions(..., bank="variant")`) are described in ticket 08's Notes.

Built by an AI agent (Claude Code), test-first on seam N1 (`tests/test_report.py`, 8 tests). One fixture builds a full small run through the CLI with the fake LLM and the fake check runner: extract (one lesson fails), drift, construct (stale lesson plus matched control on pair 1), review, check, sign-off, variant bank, mechanisms; tests then assert on `report.json`, the Markdown and the exported files.

**Commands**
- `memrev --run <dir> report [--out FILE]`: writes the Markdown report to FILE (default `<run>/report.md`) and the same numbers as JSON next to it (`report.json`), and prints the Markdown. Sections: Natural cases, Constructed cases, LLM cost per stage. JSON top level: `natural`, `constructed`, `llm_cost`.
- `memrev --run <dir> export <out-dir>`: writes `lessons`, `assumptions`, `evidence` and `final_labels`, each as `.jsonl` and `.csv` with the same rows. Lists (code pointers) are JSON text in the CSV. Every row has a `case` column: `natural lesson`, `constructed stale lesson` or `matched control`.

**Layout**
- `src/memrev/scorer.py`: the only module that reads labels and the constructed-case mapping. `score(store) -> dict` (the report numbers) and `dataset(store) -> dict[name, rows]` (the export).
- `src/memrev/report.py`: renders the dict as Markdown, writes the JSON and the export files, and holds both commands. It reads nothing from the store itself.
- `harness.recorded_runs(store)`: new reader listing every recorded `(mechanism, repository, S, T, bank)` run.

**What each number means**
- Assumption labels: current final labels of accepted assumptions, per (repository, assumption type). Inconclusive ones are also counted per reason (`out of scope at T`, `harness error`, `check disagrees with itself`, `downgraded by reviewer`, `reviewers disagree`). "Out of scope at T" appears only there, not in the exclusion table (05 records no exclusion row for it).
- Lesson labels: from `LabelStore.lesson_report()` / `constructed_lesson_report()`, one per (lesson, pair), plus the number still awaiting check or sign-off.
- Extraction yield (natural only): lessons processed = distinct lessons with a logged `extract` call; assumptions with origin `extract` split into checkable and uncheckable (current type, so reviewer edits count); extraction failed = `extract` exclusions. Uncheckable is reported here, not as an exclusion. Seeded assumptions are not part of the yield.
- Exclusions: per reason. Stage `construct` rows count as constructed; a `check` row about a constructed assumption counts as constructed; everything else is natural. The constructed section also has a case line (stale candidates drafted, kept, gate failed, with and without a matched control) from `constructor.case_records`.
- Reviewer agreement: per section, over current final labels that a second reviewer labelled (raw agreement).
- Mechanisms: summed over a mechanism's runs. Natural cases come from original-bank runs; constructed cases from variant-bank runs, joined through `constructor.variant_entries`. Kept = keep; rejected = flag or withhold; recheck is neither (V23). `lessons scored` and `contradicted` use scored lesson labels only (inconclusive and unlabelled lessons are left out, V22).
- Unnecessary rejection (constructed only, V6): over matched controls labelled supported within scope whose stale lesson is in the same variant bank; counts those the mechanism rejected. Shown as `k of n`; `n/a` for natural cases.
- Cost: `cost: checks` = checks the mechanism executed plus one per recheck decision, over the whole run; wall time and tokens summed.

**Decisions made while building** (small, not grilled)
- The variant bank's natural lessons are not scored in the constructed section (they are natural cases, already scored from the original bank). Only its constructed lessons count there.
- The recheck column counts recheck decisions on the section's lessons (all of the original bank; the constructed lessons of the variant bank). The cost column covers the whole run, so for a variant-bank run its rechecks include the natural lessons in that bank. The test pins this (2 rechecks, cost 4 for a 3-lesson variant bank).
- One recheck adds one check to cost. If a later mechanism executes the recheck itself (and counts it through `view.cost`), it would be counted twice; revisit then.
- A matched control whose stale lesson was rejected in review (so not in the variant bank) is left out of unnecessary rejection: there is no matched pair to score.
- `lessons processed` counts lessons with any logged extract call, so it is cumulative over reruns with a growing `--limit`.
- The export includes every assumption (any review status, with `status`), current (not superseded) evidence, including gate runs of candidates that failed the gate (their `lesson_id` is empty, `case` comes from the mapping), and current final labels of accepted assumptions only. Lesson labels are not exported (derived; see the report).
- LLM cost per stage counts API attempts (cache hits left out), failed attempts included, since they can cost tokens.
