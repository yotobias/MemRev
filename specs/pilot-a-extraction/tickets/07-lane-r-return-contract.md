# 07: Freeze the Lane R return contract

**Status:** done
**Blocked by:** 05 (done)
**Owner:** Codex, for Johnny

## Decisions and scope

The user selected the existing main-3 assistant-session batch for preliminary validity work, kept gold material isolated on Lane R, and approved staged scheduling: usable repository assumptions at C0/C1, Ca only if both are contradicted; retain context-only rows without scheduling them.

Keep validity schema version 1 compatible with the existing handoff importer. Freeze a named execution profile in a separate portable work order. Define exact workspace identifiers, private evidence references, attribution and failure mapping. Provide CLI preparation, recording, validation and import, without pretending to execute checks or accepting replay success as assumption validity.

## Acceptance criteria

- [x] Verify and freeze the handoff/prepared identities; distribute original candidates and replay inputs with a work order and untouched pending return.
- [x] Schedule only usable repository candidates; retain every original row; validate staged Ca eligibility.
- [x] Record completed executions from explicit receipts, preserving source/outputs/reconstruction evidence privately by content hash.
- [x] Reject stale IDs, conflicting cell updates, workspace identity mismatches, invalid outcome mappings and missing/tampered private evidence.
- [x] Validate returns offline on N; optionally verify private evidence on R without copying its contents into shared artifacts.
- [x] Import partial/complete returns into a new handoff using exactly the frozen acquisitions and reviews.
- [x] Create the real preliminary execution bundle and concise instructions, including a receipt template that cannot be mistaken for a completed result.
- [x] Test round trip, failure classifications, privacy boundaries, partial returns, consistency and immutable outputs.

No Docker execution, gold inspection, source-validity claims, paid model calls, pushes or messages to teammates are part of this ticket. R still authors and executes the checks; this ticket removes ambiguity about the inputs and expected returns.

## Completion notes

Implemented `memrev.lane_r prepare/record/validate/import`, the execution profile, and a portable source snapshot. `record` assembles public outcomes from explicit execution receipts and keeps private artifacts content-addressed on R; validation is not proof of check adequacy or execution authenticity.

Validation: **206 tests passed**, including 19 contract tests. Tested the copied CLI against the real 32-row collection: 96 cells remain pending, 62 are initially scheduled, and an all-pending import retains the original collection ID. The pending receipt template cannot produce a completed judgment. Archive integrity, all file hashes and all 32 trajectory pointers were verified.

Delivery: `runs/pilot-a/main-3/lane-r-execution-v1.zip` and `.sha256` (gitignored). The ZIP includes 189 files and a runner source/dependency snapshot so R can validate without waiting for a push. No new validity result was generated. R's next task is a live C0/C1 smoke with an authored scoped check; the execution host must have working Docker/image access.
