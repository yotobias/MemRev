# Pilot A task list

Updated 2026-11-18. Current contract ticket: [07 — Lane R return contract](../specs/pilot-a-extraction/tickets/07-lane-r-return-contract.md).

**Current objective: fully complete Pilot A before the final handoff to B.** Use [COMPLETION_CHECKLIST.md](COMPLETION_CHECKLIST.md) for exact verification steps, owners, evidence and completion criteria. Software/interface readiness alone is not study completion.

## Completed

- [x] Merge Lane R into Lane N; preserve V33–V45 and revised selection V46/V47.
- [x] Import all 16 main-3 trajectories and replay reports; verify selected IDs, sources, image names and instance-file hash.
- [x] Prepare full-trajectory extraction prompts and immutable input packages.
- [x] Apply supervisor-approved LLM review policy (V48); human review is optional for the pilot.
- [x] Extract 16 focused lessons and retain all 32 original assumptions.
- [x] Complete/import 16 explicitly non-independent AI evaluations: 31 usable assumptions, 1 context-only.
- [x] Build the B draft with all 16 lessons, complete task coverage and no export exclusions.
- [x] Package portable provenance, review evidence, replay caveats and verification-command references.
- [x] Implement configurable API extraction and separate-model review with offline planning, persistent attempts, resume and automatic delivery packaging ([ticket 06](../specs/pilot-a-extraction/tickets/06-automated-model-workflow.md)).
- [x] Freeze the preliminary Lane R execution profile, staged work order, private evidence format and return recording/validation/import commands ([contract](LANE_R_CONTRACT.md)).

## Optional replacement API batch — decide before validity work

The existing collection remains the approved preliminary execution target. If the team chooses an API batch for the primary findings, complete these steps and freeze its new collection before R checks it; do not mix results across batches.

- [ ] Choose extractor/reviewer providers and distinct model IDs; configure credentials and request limits.
- [ ] Run the offline plan and one-task live smoke using [AUTOMATION.md](AUTOMATION.md).
- [ ] Resume all 16 tasks in the new run directory; inspect status, usage, reviews and delivery caveats.
- [ ] Report the API batch separately from the earlier assistant-session preliminary results; complete its validity/sharing analysis before the final handoff.

## Handoff actions

- [ ] Johnny: share `runs/pilot-a/main-3/lane-r-execution-v1.zip` with R. It includes a source snapshot so unpushed code does not block contract validation.
- [ ] R: validate the untouched pending return, then execute one scoped C0/C1 check and record/import its result as the live contract smoke test. Report any runner incompatibility before scaling up.
- [ ] Johnny: after the completion checklist and report are finished, send B the final package; publish the code/documentation changes through the team workflow. The current `pilot-b-delivery.zip` remains preliminary.
- [ ] B owner: confirm six-field schema and demonstrate importing the draft with its relative trajectory pointers.
- [ ] B owner/team: reconcile V46's six non-Verified tasks and target environments with B's older Verified-only/same-version specification. Record accepted pairs and exclusions explicitly.

## Remaining Pilot A research — required before the requested final handoff

- [ ] Team: assign an execution owner with working Docker and recorded image access; freeze the primary collection and review/grouping protocol.
- [ ] R: execute the 62 scheduled preliminary C0/C1 assessments; assess Ca only when both are contradicted. Retain all rows and private evidence under the frozen collection/profile; no execution results exist yet.
- [ ] R: verify reconstructed final workspaces on the check host; use the command index instead of waiting for a phase segmenter.
- [ ] N: import results and complete evidence-backed cross-task grouping. Current state: 96 pending validity cells, 32 pending sharing rows.
- [ ] N/R: perform the planned 30% regrouping check in a separate reviewer context and report disagreement/exposure; if there are no eligible groups, document why it is not applicable. Same-session self-review is not independent agreement.
- [ ] Team: finalize findings, costs, exclusions and uncertainty, including Lane R's reported contamination and the extraction model/procedure deviation.
- [ ] N/R: write `pilot-a/report.md` with answers to the research questions and links to the frozen evidence; verify the final public package and archive hashes.

There is no outstanding mandatory human trajectory-review task. AI review changes who judges extraction quality; it does not supply missing execution evidence or finish Pilot B's implementation.
