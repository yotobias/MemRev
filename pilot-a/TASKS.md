# Pilot A task list

Updated 2026-11-17. Technical ticket: [05 — imported run handoff](../specs/pilot-a-extraction/tickets/05-imported-run-handoff.md).

## Completed

- [x] Merge Lane R into Lane N; preserve V33–V45 and revised selection V46/V47.
- [x] Import all 16 main-3 trajectories and replay reports; verify selected IDs, sources, image names and instance-file hash.
- [x] Prepare full-trajectory extraction prompts and immutable input packages.
- [x] Apply supervisor-approved LLM review policy (V48); human review is optional for the pilot.
- [x] Extract 16 focused lessons and retain all 32 original assumptions.
- [x] Complete/import 16 explicitly non-independent AI evaluations: 31 usable assumptions, 1 context-only.
- [x] Build the B draft with all 16 lessons, complete task coverage and no export exclusions.
- [x] Package portable provenance, review evidence, replay caveats and verification-command references.

## Handoff actions

- [ ] Johnny: send `runs/pilot-a/main-3/pilot-b-delivery.zip` to B; publish the code/documentation changes through the team workflow.
- [ ] B owner: confirm six-field schema and demonstrate importing the draft with its relative trajectory pointers.
- [ ] B owner/team: reconcile V46's six non-Verified tasks and target environments with B's older Verified-only/same-version specification. Record accepted pairs and exclusions explicitly.

## Remaining Pilot A research (does not block sharing B's input draft)

- [ ] R: execute scoped C0/C1/Ca checks and retain evidence under the frozen collection IDs; confirm workspace identifiers and return contract.
- [ ] R: verify reconstructed final workspaces on the check host; use the command index instead of waiting for a phase segmenter.
- [ ] N: import results and complete evidence-backed cross-task grouping. Current state: 96 pending validity cells, 32 pending sharing rows.
- [ ] N/R: if independent regrouping is performed, use a separate reviewer context and report disagreement. Same-session self-review is not independent agreement.
- [ ] Team: finalize findings, costs, exclusions and uncertainty, including Lane R's reported contamination and the extraction model/procedure deviation.

There is no outstanding mandatory human trajectory-review task. AI review changes who judges extraction quality; it does not supply missing execution evidence or finish Pilot B's implementation.
