# 09: Harness and two mechanisms

**Status:** ready-for-agent
**Blocked by:** 02
**Estimate:** ~80k tokens

## What to build
A mechanism author can plug a maintenance mechanism into the harness and run it over a memory bank and revision pair. The harness never exposes labels or provenance and records each mechanism's decisions and cost. Two mechanisms ship: no maintenance and file-change invalidation.

Covers stories 34, 35, 37. Decisions V7.

## Acceptance criteria
- [ ] The mechanism interface receives a memory bank, a revision pair and repository access, and returns one decision per lesson: keep, recheck, flag or withhold.
- [ ] A test proves that a mechanism cannot reach labels or the constructed-case mapping through the harness.
- [ ] `run-mechanism` records decisions and cost (checks executed, wall time, tokens) per mechanism and pair.
- [ ] No maintenance keeps every lesson; file-change invalidation flags lessons whose supporting files changed between S and T.

## Notes
