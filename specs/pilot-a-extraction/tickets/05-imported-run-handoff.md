# 05: Imported trajectories and LLM-reviewed handoff

**Status:** done
**Blocked by:** 04 (done)
**Owner:** Codex, for Johnny

Implement V48–V50 using the imported main-3 run. No paid calls, trajectory command execution or gold inspection are needed.

## Acceptance criteria

- [x] Audit all selected tasks against run metadata, instance-file hash and replay reports; reject mismatched input and preserve source bytes.
- [x] Prepare full-trajectory prompts and an inventory in an immutable, portable bundle.
- [x] Allow explicitly disclosed assistant-session extraction with unknown serving-model metadata, without weakening other production provenance requirements.
- [x] Extract and evaluate all 16 trajectories, with AI attribution and no invented execution labels; preserve uncertain/defective candidates.
- [x] Build a portable six-field B draft containing complete source provenance and all task coverage, with review and readiness sidecars.
- [x] Document AI review policy, current task status, replay/contamination limitations and remaining B acceptance decisions.
- [x] Test input rejection, repeatability, provenance and production AI-review handoff; run the existing suite.

## Remaining research work (not gates on delivering the B draft)

- [ ] R: execute scoped C0/C1/Ca checks with evidence and reconstruct Ca by replay where required.
- [ ] N: complete evidence-backed sharing analysis and report agreement if independent regrouping is performed.
- [ ] B: reconcile V46's non-Verified tasks and target environments with its older selection rules; accept the six-field interface and test its importer.
- [ ] Team: report contamination, actual costs, exclusions and uncertainty in the final pilot findings.

## Notes

Reviews in this session are AI-only and non-independent. A workspace report is a declaration of a previous replay, not a captured filesystem or a new validity check.

Completed 2026-11-17: 16 lessons, 32 assumptions, 16 AI evaluations; 31 assumptions usable and 1 context-only. All 16 lessons are exported with no missing tasks or provenance exclusions. Delivery: `runs/pilot-a/main-3/pilot-b-delivery.zip` (gitignored), with file hashes and portable trajectory pointers. Validation: 161 tests passed; synthetic gold-gate parser tests passed without reading gold artifacts. See [the handoff guide](../../../pilot-a/MAIN3_HANDOFF.md) and [current task list](../../../pilot-a/TASKS.md).
