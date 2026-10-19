# 03: Assumption review round trip

**Status:** ready-for-agent
**Blocked by:** 01
**Estimate:** ~70k tokens

## What to build
A reviewer can export the assumptions in a run to a CSV, accept, edit or reject each one, and import the CSV back. Every assumption is identified by a content hash, so an edit invalidates any evidence, labels or scores attached to the old version. Assumptions can be seeded from a hand-written CSV, so this works without the LLM.

Covers stories 14, 15, 16, 17. Decisions V2, V25, V26.

## Acceptance criteria
- [ ] The assumption record holds statement, assumption type (one of the five, or uncheckable), scope, supporting code pointers, check command and asserted target, and a content hash over these fields.
- [ ] `review-export` writes a CSV; `review-import` reads it back with a required reviewer id.
- [ ] Only accepted (or edited and accepted) assumptions are marked reviewed; rejected ones are recorded with the reviewer id.
- [ ] A CSV with missing rows or duplicate ids is rejected as a whole with a clear message.
- [ ] Every import prints what changed (accepted, edited, rejected, unchanged).
- [ ] Editing an assumption gives it a new hash and marks downstream evidence, labels and scores of the old hash as stale.
- [ ] Assumptions can be loaded from a hand-written seed CSV.

## Notes
