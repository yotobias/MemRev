# 04: Offline Lane N handoff and reporting

**Status:** done
**Blocked by:** 02, 03 (done)
**Estimate:** one implementation session

## Scope

V42–V44: make the remaining Lane N interfaces demonstrable without human review. No real agent or model calls, Docker execution, gold inspection, invented metadata, automatic semantic grouping, or production sign-off. Lane R still owns real execution; Pilot B still owns its importer and final wire-schema agreement.

## Acceptance criteria

- [x] Build a portable multi-acquisition bundle from verified originals with optional, explicitly supplied reviews; reject duplicates and stale/tampered inputs.
- [x] Generate all-original-assumption Lane R requests and pending C0/C1/Ca returns. Validate supplied returns, attribution and evidence references without opening gold material or executing commands. Setup failures never become contradictions; intermediate observations remain distinct from unsupported-at-all-times claims.
- [x] Export pending sharing rows; import explicit groups with reasons, compatible normalized repository/symbol/predicate/scope and validity support. Retain excluded/uncertain/pending originals; count cross-task sharing separately from repeated occurrences in one task.
- [x] Prepare a deterministic 30%-of-groups sample with no primary grouping in the recipient file, and compare a later regrouping by partitions, not arbitrary group names.
- [x] Export original advice to proposed six-field Pilot B JSONL, with missing metadata exclusions, review-status sidecars, portable trajectory pointers and explicit draft status. No review is required merely to exercise the export.
- [x] Report pending and completed work, original denominators, extraction cost known/unknown coverage, selection coverage and design decisions still awaiting agreement. Do not label an unfinished study complete.
- [x] Provide a documented CLI, a reproducible fixture-based demonstration and tests exercising later completed inputs without claiming human review.
- [x] Keep outputs under ignored `runs/`; unchanged rebuilds are safe and changed artifacts require a fresh output directory.

## Notes

Owner: Codex. Proposed interfaces are documented in `pilot-a/HANDOFF.md`. Freeze their semantics with Lane R and Pilot B before production use. No human trajectory review is requested in this ticket.

Implemented `memrev.handoff` (`build`, `sample`, `compare`), with validity, sharing and artifact helpers in separate small modules. The user-facing entry point remains one command. New tests first failed on the absent module, then drove pending/completed round trips, provenance/ID checks, source-selection guards, superseded/intermediate labels, safe reuse, portable pointers and sampling/comparison.

Validation: `PYTHONPATH=src .venv/bin/python -m pytest -q` — 149 passed (43 new handoff tests). Also ran `build` against the real saved development package with no evaluation and separately with the existing AI example. `runs/handoffs/astropy-design-v2/` is the current all-pending demonstration: 5 lessons, 17 assumptions, 51 pending cells, 17 pending grouping rows, 5 explicit B exclusions for missing provenance. No new human/AI trajectory judgments, paid calls or benchmark executions were performed. The superseded `astropy-design-v1/` snapshot was later verified unchanged and removed during V45 cleanup.

Remaining outside this ticket: team acceptance of the proposed contracts, paid extraction automation if desired, Lane R's actual workspace/check runner, real human judgments and groups, agent/check/container cost aggregation, the final research report and Pilot B's own importer. Completing this implementation ticket does not complete the study.
