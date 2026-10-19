# Pilot B: assumption applicability across revisions

**Status:** ready-for-agent
**Date:** 19-10-2026

Terms follow [GLOSSARY.md](../../GLOSSARY.md); decisions V1–V32 are in [docs/decisions.md](../../docs/decisions.md); data source per [ADR 0001](../../docs/adr/0001-own-revision-pairs-from-swe-bench-verified.md).

## Problem

Coding agents store lessons and reuse them later, but the repository keeps changing. A lesson can stay textually relevant while the behaviour it assumes is gone. We have no data on how often the assumptions inside agent lessons stop holding across real revisions, and no labelled cases to test a maintenance mechanism against. Without that, Pilot C (selective verification) and Pilot D (effect on later tasks) cannot be evaluated, and the paper's go/no-go criteria cannot be measured.

## Solution

A command-line pipeline that takes a memory bank of lessons written at a source revision S, extracts the checkable assumptions from each lesson, and decides by execution whether each still holds at later target revisions T of the same repository. Every label comes from running a check 3 times in the SWE-bench Docker image shared by S and T, and a human signs it off. Alongside the natural cases, the pipeline builds constructed stale lessons (whose check passes at S and fails at T) and matched controls (whose check passes at both), and mixes them blind into a variant memory bank. A harness runs any maintenance mechanism over the original and variant banks without labels; a scorer compares its decisions with the labels and reports natural and constructed cases separately. Two mechanisms ship: no maintenance and file-change invalidation.

## User stories

Roles: **researcher** runs the pipeline; **reviewer** reviews assumptions and signs off labels; **Pilot A producer** supplies lessons; **mechanism author** writes a maintenance mechanism; **reader** is the supervisor or team reading results.

### Input
1. As a Pilot A producer I want a documented lesson-bank JSONL schema (lesson id, lesson text, task id, repository, source revision, trajectory pointer), so that my output plugs into Pilot B without conversion.
2. As a researcher I want a hand-written fixture memory bank for django, so that I can run Pilot B end to end before Pilot A delivers.
3. As a researcher I want lesson banks validated on import (missing fields, unknown repository, source revision not in the repository), with every rejected lesson reported with its exclusion reason, so that bad input never silently disappears.

### Revision pairs
4. As a researcher I want revision pairs built from SWE-bench Verified instances, where S and T are base_commits in the same repository and SWE-bench version and S is a git ancestor of T, so that every pair is chronologically valid.
5. As a researcher I want, per source revision, up to 3 targets in the same version (nearest later instance, middle, furthest), so that the dataset covers short and long gaps with a fixed policy.
6. As a researcher I want sources with no later instance, failed ancestry checks and cross-version candidates excluded with their exclusion reason, so that exclusions are reportable.
7. As a researcher I want the drift guard to run a fixed sanity test set 3 times at S and at T in the shared image, and drop the pair as "environment unavailable" if unrelated sanity tests break or disagree with themselves, so that install drift never becomes a label.
8. As a researcher I want a missing image or failed checkout to drop the pair as "environment unavailable" before any assumption check runs, so that infrastructure noise stays out of label counts.

### Assumptions
9. As a researcher I want an LLM to extract assumptions from each lesson (statement, assumption type, scope, supporting code pointers, candidate check with its asserted target), so that I don't write them by hand.
10. As a researcher I want assumptions that fit none of the five assumption types recorded as uncheckable and counted, so that extraction yield is measurable.
11. As a researcher I want LLM calls retried with backoff, successful outputs cached, and persistent failures counted as "extraction failed" separately from uncheckable assumptions, so that the yield figure is honest.
12. As a researcher I want every LLM call's model, tokens and cost logged, so that extraction cost can be reported.
13. As a researcher I want the LLM behind a thin interface, so that the model can be swapped.
14. As a reviewer I want extracted assumptions exported to a CSV where I accept, edit or reject each one, and the CSV imported back, so that only reviewed assumptions enter the labelled set.
15. As a reviewer I want a re-imported CSV with missing rows or duplicate ids rejected, and a summary of what changed on every re-import, so that review edits are never lost or doubled.
16. As a researcher I want each assumption identified by a content hash, with evidence, labels and scores keyed to it, so that editing an assumption invalidates everything downstream of it.
17. As a reviewer I want my reviewer id stored on every decision, so that the report can say who decided.

### Checks and labels
18. As a researcher I want each reviewed assumption's check run 3 times at S, and the assumption recorded as invalid at S unless all 3 pass, so that lessons wrong from the start don't count as stale.
19. As a researcher I want eligible checks run 3 times at T, with 3/3 pass proposed as supported within scope and 3/3 fail on the asserted target proposed as contradicted, so that labels come from execution.
20. As a researcher I want a check that disagrees with itself, or fails in the harness or container, proposed as inconclusive with the reason, so that environment problems don't count as contradictions.
21. As a researcher I want an error on the asserted target (e.g. ImportError for a renamed symbol) treated as contradicted, and a missing fixture or backend at T treated as inconclusive with reason "out of scope at T", so that real drift is caught and scope loss is not mislabelled.
22. As a reviewer I want to accept a proposed label, downgrade it to inconclusive, or send the assumption back for a rewritten check and rerun, and never flip supported within scope ↔ contradicted directly, so that every final label rests on an execution.
23. As a researcher I want every check execution stored as evidence (revision, command, exit status, output excerpt, run index, time), so that every label is auditable.
24. As a researcher I want a lesson label derived from its assumptions (contradicted if any is contradicted, supported within scope only if all are, else inconclusive and excluded from metrics), so that per-lesson mechanism decisions can be scored.
25. As a researcher I want lessons with no checkable assumption kept in the bank and counted but not scored, so that the bank stays realistic.
26. As a researcher I want, if a second reviewer reviews a sample, agreement reported and disagreements turned into inconclusive, so that label reliability can be stated.

### Constructed cases
27. As a researcher I want candidate constructed stale lessons drafted by an LLM from real behaviour changes in the S..T diff (advice only, no code mutation), so that stale advice reflects realistic change.
28. As a researcher I want a pair recorded as "no behaviour change found" when its diff yields no candidate, so that constructed-case yield per pair is reportable.
29. As a researcher I want a constructed stale lesson kept only if its check passes 3/3 at S and fails 3/3 at T, with dropped candidates counted, so that every constructed case is demonstrably stale.
30. As a researcher I want each constructed stale lesson paired with one matched control, drafted the same way (same file or symbol area, similar length and type, check passes 3/3 at S and T), so that unnecessary rejection can be measured.
31. As a researcher I want constructed stale lessons without a matched control reported but excluded from the unnecessary-rejection metric.
32. As a reviewer I want constructed stale lessons and matched controls to go through the same CSV review and label sign-off as natural assumptions, so that all cases meet the same standard.
33. As a researcher I want a variant memory bank in which selected lessons are replaced by constructed stale lessons and matched controls, using opaque ids, the same schema and no provenance field, so that a mechanism cannot tell constructed from natural.

### Harness and scoring
34. As a mechanism author I want a mechanism interface that receives a memory bank, a revision pair and repository access but never labels or provenance, and returns one decision per lesson (keep, recheck, flag, withhold), so that my mechanism can be scored.
35. As a mechanism author I want the harness to record each mechanism's cost (checks executed, wall time, tokens), so that cost is comparable.
36. As a researcher I want a recheck decision counted toward cost, scored as neither kept nor rejected, and reported in its own column.
37. As a researcher I want two mechanisms shipped, no maintenance and file-change invalidation, so that the harness is exercised and Pilot C has baselines.
38. As a reader I want natural cases and constructed cases reported separately, so that constructed results don't inflate natural ones.
39. As a reader I want a report with label counts per repository and assumption type, extraction yield, exclusion counts per exclusion reason, reviewer agreement where available, and per-mechanism metrics (contradicted lessons kept, unnecessary rejection, recheck count, cost).

### Running
40. As a researcher I want the pipeline to stop after the first ~30 lessons and print extraction yield, so that the team can decide before scaling.
41. As a researcher I want each run to use its own SQLite database outside the checked-out repository, so that runs don't leak into each other.
42. As a researcher I want stages resumable, reusing cached work whose inputs are unchanged, so that a failed Docker run doesn't redo LLM extraction.
43. As a researcher I want the dataset exportable as JSONL and CSV, so that teammates can inspect it without the code.

## Implementation decisions

- **Language and tooling:** Python 3.11, uv, pytest, SQLite. One command-line entry point with a subcommand per stage. No web UI.
- **Stages** (each reads from and writes to the run database, each resumable):
  1. *import* — validate a lesson-bank JSONL into the run.
  2. *pairs* — load SWE-bench Verified metadata for a repository, build revision pairs (same version, git ancestry, up to 3 targets per source), record exclusions.
  3. *drift* — per pair, run the sanity test set 3× at S and T; drop failing pairs.
  4. *extract* — LLM extraction of assumptions; stops after the configured lesson limit (default ~30) and prints yield.
  5. *review-export* / *review-import* — CSV round trip with reviewer id, hash-based change detection and strict row validation.
  6. *check* — run each reviewed assumption's check 3× at S, then 3× at T for eligible ones; store evidence; propose labels.
  7. *label-export* / *label-import* — sign-off CSV with the allowed transitions only (accept, downgrade to inconclusive, send back).
  8. *construct* — draft constructed stale lessons and matched controls from the S..T diff, run the 3/3 gates, feed them into review and labelling, build the blinded variant bank.
  9. *run-mechanism* — run a named mechanism over a bank and pair; record decisions and cost.
  10. *report* / *export* — scorer joins decisions with labels; writes report and JSONL/CSV exports.
- **Modules:**
  - *Store*: SQLite schema for lessons, revision pairs, assumptions (keyed by content hash), evidence, proposed and final labels, review decisions, constructed-case mapping, mechanism decisions, costs, LLM call log, exclusions with reason codes.
  - *Repository access*: git operations on a local clone (ancestry, diff, file listing at a revision).
  - *Check runner*: interface `run(check, revision, environment) → outcome` where outcome is pass / fail-on-asserted-target / harness-error / out-of-scope plus raw evidence. Real implementation runs inside the SWE-bench image for the (repository, version); a fake implementation returns scripted outcomes.
  - *LLM client*: interface for structured extraction and drafting, with retry/backoff, an output cache keyed by prompt and model, and per-call token and cost logging. Real implementation: Claude Sonnet 5.5 via the Anthropic API. Fake implementation returns canned outputs.
  - *Labeller*: pure rules from evidence to proposed label (3/3 rules, asserted-target rule, invalid at S, lesson-label aggregation).
  - *Constructor*: candidate drafting, 3/3 gates, control matching, variant bank with opaque ids and no provenance.
  - *Harness*: mechanism interface (bank, pair, repository access → decision per lesson); it never loads labels or the constructed-case mapping.
  - *Scorer*: the only component that reads labels and the mapping; produces metrics with natural and constructed reported separately.
- **Lesson-bank JSONL schema** (contract with Pilot A): one object per line with lesson id, lesson text, task id (SWE-bench instance id), repository, source revision (commit SHA), trajectory pointer (path or URL, may be empty for fixtures). Documented in the repo; extra fields are ignored.
- **Lesson-label aggregation:** uncheckable assumptions are ignored when aggregating a lesson label; V22's "all" ranges over the lesson's checkable assumptions (V32).
- **Assumption record:** statement, assumption type (one of five, or uncheckable), scope, supporting code pointers, check (command plus asserted target), content hash over these fields.
- **Exclusion reason codes:** invalid lesson input, no target, ancestry failed, cross-version, environment unavailable, extraction failed, uncheckable, invalid at S, out of scope at T, no behaviour change found, drafting failed, gate failed (constructed), no matched control.
- **Run isolation:** each run has its own database and work directory outside any repository checkout.
- **Revision-pair source:** SWE-bench Verified only (ADR 0001); django first, then sympy and scikit-learn.

## Test decisions

- **Seam N1 (main):** the stages, called as the command-line tool calls them, on fixture data: a tiny real git repository created in the test, the fake check runner and the fake LLM client. Catches all data-deciding logic — pair filtering and target choice, drift guard, invalid at S, 3/3 labelling, asserted-target and out-of-scope rules, label-override limits, lesson-label aggregation, CSV round-trip validation and hash invalidation, constructed-case gates and control matching, blinding of the variant bank, recheck scoring, separate natural/constructed reporting, exclusion counts, resumability. Misses real Docker and real SWE-bench test behaviour, and LLM output quality.
- **Seam N2 (opt-in, slow):** one test that runs a known check at one real django revision pair through the real check runner in the real SWE-bench image. Catches image, mount and checkout plumbing and test-result parsing. Skipped unless explicitly enabled.
- A good test drives a stage and asserts on what the run database or exported files contain afterwards (labels, counts, exclusion reasons, report rows), not on internal function calls.
- LLM extraction quality is not tested automatically; it is measured by reviewer acceptance rates and the extraction-yield stop.
- No existing tests to build on: the repository is empty.

## Out of scope

- Pilot A (running the agent and producing real lessons); Pilot B uses the fixture bank until Pilot A's JSONL arrives.
- Synthetic code mutations in the repository (main.tex "controlled changes").
- Pairs across SWE-bench versions, and rebuilding environments at arbitrary commits.
- Any maintenance mechanism beyond no maintenance and file-change invalidation (Pilot C).
- Effects on downstream agent tasks (Pilot D).
- Automatic test generation for checks; checks come from existing tests or small probes written during extraction and review.
- SWE-ContextBench and EvoArena data (until released).
- A web UI.

## Open points

- The SWE-ContextBench authors have not yet been asked for data (board task memrev-t01).
- Execution speed: SWE-bench images run under emulation on the Apple Silicon Mac; a Linux x86 machine has not been arranged.

## Tickets

1. [01: Skeleton and lesson import](tickets/01-skeleton-and-lesson-import.md)
2. [02: Revision pairs](tickets/02-revision-pairs.md) — blocked by 01
3. [03: Assumption review round trip](tickets/03-assumption-review-round-trip.md) — blocked by 01
4. [04: LLM extraction](tickets/04-llm-extraction.md) — blocked by 03
5. [05: Running checks and proposing labels](tickets/05-checks-and-proposed-labels.md) — blocked by 02, 03
6. [06: Label sign-off and lesson labels](tickets/06-label-sign-off-and-lesson-labels.md) — blocked by 05
7. [07: Real Docker check runner](tickets/07-docker-check-runner.md) — blocked by 05
8. [08: Constructed cases](tickets/08-constructed-cases.md) — blocked by 04, 06
9. [09: Harness and two mechanisms](tickets/09-harness-and-two-mechanisms.md) — blocked by 02
10. [10: Scorer, report and export](tickets/10-scorer-report-and-export.md) — blocked by 06, 08, 09
11. [11: First real django run](tickets/11-first-real-django-run.md) — research, blocked by 04, 07
