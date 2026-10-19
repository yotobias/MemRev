# 04: LLM extraction

**Status:** ready-for-agent
**Blocked by:** 03
**Estimate:** ~100k tokens

## What to build
A researcher can run extraction over the imported lessons. An LLM proposes the assumptions in each lesson, which then flow into the review CSV from ticket 03. Extraction stops after a configurable number of lessons (default 30) and prints the extraction yield, so the team can decide before scaling.

Covers stories 9, 10, 11, 12, 13, 40. Decisions V2, V9, V16, V17, V28.

## Acceptance criteria
- [ ] The LLM sits behind a thin interface with a real implementation (Claude Sonnet 5.5 via the Anthropic API, key from a git-ignored .env) and a fake one for tests.
- [ ] Calls retry with backoff; successful outputs are cached by prompt and model so reruns don't call the API again.
- [ ] Every call's model, input and output tokens and cost are logged in the run.
- [ ] Extracted assumptions are typed as one of the five assumption types; anything else is stored as uncheckable and counted.
- [ ] Persistent LLM failures are counted as "extraction failed", separate from uncheckable.
- [ ] The stage stops after the lesson limit and prints yield: lessons processed, checkable assumptions, uncheckable, extraction failed, cost.
- [ ] Tests use the fake LLM only.

## Notes
