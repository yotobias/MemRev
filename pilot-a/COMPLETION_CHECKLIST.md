# Complete Pilot A: verification and research checklist

Updated 2026-11-18. **Current objective: finish Pilot A's research analysis before handing the final package to Pilot B.** This guide follows the current first-round plan, not superseded requirements in Plan_v2.

New to the project? Start with [WORKFLOW_OVERVIEW.md](WORKFLOW_OVERVIEW.md): current files and formats, why each matters, and one real lesson traced through the workflow.

Pilot A must answer: **Do the extracted lessons contain checkable repository assumptions? Which hold in repository history versus agent edits? Do different tasks share the same scoped assumptions?** A low count or inconclusive result is reportable; there is no minimum success threshold.

## Starting point: what has actually been verified

| Item | Status |
|---|---|
| Imported main-3 trajectories and extraction/review packages | 16 tasks; 16 focused lessons; 32 original assumptions |
| Extraction review | Same-session AI review: 31 usable, 1 context-only; not independent accuracy measurement |
| Software tests | 206 passed at the last implementation verification |
| Execution bundle and return interface | Hashes/pointers checked; pending return validated and imported with collection ID unchanged |
| Repository validity | No new assumption checks completed; all 96 tracking cells pending |
| Sharing and regrouping | Not performed |
| Fresh separate-model API batch | Runner implemented; no live batch performed |

**Do not repeat completed offline validation as a substitute for running the checks.** The code that records a receipt does not execute its command. R must still author/adapt checks and the execution harness.

## 1. Assign owners and freeze the analysis batch — team/N

- [ ] Assign an **execution owner (R)** with working Linux/WSL, Docker and task-image access. This can be an operator working with an isolated agent; mandatory human trajectory review is not required.
- [ ] Assign an **analysis owner (N)** for imports, scoped grouping and reporting. Keep N blind to official fixes and detailed C1 evidence.
- [ ] Record the chosen collection ID, review protocol and task selection in the final report before running checks.

The user-approved starting batch is the existing preliminary main-3 collection:

```text
collection-702c7aaa7a3c36d6f599e12b477ff5f82d25b40fbce37ce70220483fba32e752
```

Its execution package is `runs/pilot-a/main-3/lane-r-execution-v1.zip`. It includes inputs and a source/dependency snapshot. Keep the extracted bundle immutable; store working returns and private evidence elsewhere.

If the team chooses the new API extraction/review batch as the primary analysis, run [AUTOMATION.md](AUTOMATION.md) **before** starting validity checks, then prepare a new execution bundle. It will have new IDs and possibly different counts. Never copy old verdicts onto new assumptions automatically. The existing batch is permitted under V49; a new API batch is not silently added as a prerequisite for completing it.

**Done when:** there is one named collection for the primary results and an execution owner can access its recorded images. N's current host could not access Docker; that blocker has not been resolved by the offline tests.

## 2. Prove one real check works end to end — R, then N

- [ ] Validate the supplied pending return once on R's machine using [LANE_R_CONTRACT.md](LANE_R_CONTRACT.md). Expect success with scheduled work still pending.
- [ ] Pick one scheduled assumption from `work_order.json`. Read its exact statement, scope and cited trajectory messages.
- [ ] Write a small check against the actual repository symbol. Specify the input/setup and the assertion that distinguishes the stated behavior. Do not mock the target function or treat a broad suite pass as proof of this assumption.
- [ ] Reconstruct C0 and C1 as defined below. Confirm the code imported by the check comes from the intended workspace, not an unrelated installed package.
- [ ] Execute the check separately in both states. Save the check source, stdout/stderr, exit status, workspace reconstruction and environment evidence.
- [ ] Fill a receipt from each actual execution; use `memrev.lane_r record`, then `validate --evidence-root` on R.
- [ ] Send only the return JSON and validation summary to N. N validates without private evidence and imports into a new output directory.
- [ ] Confirm the imported counts match those two assessments and no other pending cells changed.

**Done when:** a real scoped check has completed the repository execution → evidence → receipt → validation → import path. A synthetic test or all-pending import does not satisfy this step.

## 3. Assess the full scheduled set — R

For the current collection: **31 usable assumptions × C0/C1 = 62 initial assessments**. This is not necessarily 62 different scripts. Preserve all 32 rows, including the context-only row.

| Workspace | What R must verify |
|---|---|
| C0 | Original task source at the recorded base commit and exact recorded image ID; document known packaging/mode-only differences |
| C1 | C0 plus the official **source** fix, without the official test patch; gold construction remains private on R |
| Ca | Agent's actual final state reconstructed from the trajectory, including relevant untracked files and installation changes |

For each scheduled assumption:

- [ ] Establish that the check tests the stated behavior under its stated conditions. For a code-structure observation, inspect the actual symbol in the identified workspace; do not substitute brittle keyword presence for the claimed control flow.
- [ ] Keep the check and scope consistent between C0/C1. Record any environment-specific adaptation explicitly.
- [ ] Run C0/C1 and classify each observation using the table below.
- [ ] Run Ca **only if both C0 and C1 are contradicted**, as agreed in V52.
- [ ] Record actual workspace manifests and retain evidence privately; run the return validator before each delivery.
- [ ] Investigate inconclusive cases. If a limitation cannot be resolved, retain the attempted evidence and state the limitation; never convert it to a pass/fail merely to finish.

| What happened | Record |
|---|---|
| The scoped assertion passed | `supported` / `pass`, exit code 0 |
| The assertion about the target behavior failed | `contradicted` / `fail_on_asserted_target`, nonzero exit |
| Setup/import failed, timeout, flakiness, unresolved scope or interpretation | `inconclusive` with the appropriate execution result and evidence |
| Not assessed | Leave the cell exactly `pending` |
| Required Ca is genuinely unreconstructable | Explicit `undefined` Ca declaration under the contract; temporary Docker failure is not enough |

Ca warnings: `final_workspace.json` is a replay report, not a filesystem snapshot. django-14792's submission is truncated; django-16910's submission omits test edits. Test-expectation edits also occur in sympy-18057. Do not assume submitted-patch application reproduces these states, or that passing modified tests establishes the original behavior. If using recorded verification commands to confirm replay, separate edits from verification and retain the observed outcome even when it fails.

**Done when:** `remaining_scheduled_cells` is empty after real assessments, with any irreducible inconclusive/undefined results explained. Unscheduled Ca cells and the context-only row remain pending by design. Do not require all 96 cells to be populated. A failed check is a result; missing execution is unfinished work.

## 4. Import and reconcile validity results — N

- [ ] Validate and import R's final return using `memrev.lane_r import` and the exact frozen bundle. Full commands: [LANE_R_CONTRACT.md](LANE_R_CONTRACT.md).
- [ ] Check counts against R's summary: supported, contradicted, inconclusive, undefined and intentionally pending.
- [ ] Confirm every original assumption remains present and no statement, scope or source identity was rewritten.
- [ ] Report repository-history support, superseded behavior, agent-edit-only behavior and unavailable/uncertain cases separately. Negative final-workspace results do not invalidate a recorded intermediate observation automatically.
- [ ] Use the new bundle's `sharing/pending.json`; its validity fingerprint must match this return.

**Done when:** N has an immutable bundle with the actual validity returns, consistent counts and a fresh sharing form. N need not open gold material to perform these checks.

## 5. Determine cross-task sharing — N, using an attributed reviewer

- [ ] Give the reviewer the original candidates, their evidence and the imported validity summary. LLM review is allowed; record its model/session and process.
- [ ] Complete every sharing row as `group`, `exclude` or `uncertain`, with a reason. Keep all original occurrences in the accounting.
- [ ] Group only usable repository assumptions with decided C0/C1 repository-history support. Keep superseded assumptions eligible. Exclude context-only and agent-edit-only candidates from the primary sharing groups; retain their records.
- [ ] Compare **repository, symbol, predicate and resolved scope**, and the actual behavior. Similar wording alone is insufficient. Unknown scope is not unrestricted scope.
- [ ] Give eligible assumptions with no equivalent another-task occurrence their own singleton groups. Do not omit them from the distinct-assumption denominator.
- [ ] Rebuild with the same acquisitions/reviews, `--validity` and `--sharing`; use the recipe in [HANDOFF.md](HANDOFF.md#sharing-when-judgments-are-available).

**Done when:** no sharing row is pending, every grouping/exclusion/uncertainty has a reason, and counts distinguish recurrence across different tasks/PRs from repeated occurrences within one task. Zero cross-task sharing is a valid finding.

## 6. Check grouping consistency — separate reviewer context

- [ ] Record the sampling seed before inspecting the sample.
- [ ] Run `memrev.handoff sample` on the completed sharing bundle. It selects `ceil(0.30 × group count)` groups with all their members.
- [ ] Give a separate reviewer/model context **only the `blind/` directory**, without primary assignments or `private/reference.json`. Record gold exposure honestly.
- [ ] Have that reviewer regroup the supplied candidates, then run `memrev.handoff compare`.
- [ ] Report changed groups / sampled groups and explain important disagreements. Do not silently rewrite primary groups to make agreement higher.

Commands: [HANDOFF.md](HANDOFF.md#the-30-regrouping-sample). If there are no eligible groups, record this step as not applicable with a zero denominator; do not report 0% disagreement. Skipping an applicable consistency check is a plan deviation requiring an explicit scope decision, not full completion under this checklist.

## 7. Write the final findings and deliver — N + R

Write `pilot-a/report.md`, linking the frozen artifacts. Include:

- [ ] Collection/model/prompt/review procedure, selection and all deviations; state that the existing batch used same-session review and one focused lesson per task, not exhaustive extraction.
- [ ] Task, lesson and assumption counts; extraction-quality outcomes and the share of lessons with at least one usable repository assumption, with explicit denominators.
- [ ] Validity split, missing/unavailable/inconclusive cases and the share of lessons with repository-history-supported assumptions.
- [ ] Distinct scoped assumptions and sharing counts overall and per repository; distinguish different tasks/PRs, same-text cases and within-task repetition. Here “verified distinct PRs” means verified PR membership, not SWE-bench Verified membership.
- [ ] Regrouping results, examples of useful/defective lessons, failed-step origins and limitations of the sampling/review procedure.
- [ ] Agent, extraction/review, check and container costs/time, or explicitly unavailable components. Lane R reported $0.66 for main-3; unknown session usage is not zero.
- [ ] Lane R's reported upstream-fix recall (10 clear, 2 unclear, 3 none, 1 without recorded reasoning), six non-Verified tasks and workspace/test-edit caveats. Do not expose gold contents or private test details.
- [ ] Direct answers to Pilot A's research questions, including what remains uncertain, and implications for Pilot B.

Then package the final lesson bank, source provenance, public reviews/returns, analysis and limitations. Verify archive hashes and relative trajectory pointers. Publish the code through the team workflow and share the gitignored artifacts separately. B still confirms its importer and pair/environment rules; that is a consumer acceptance step, not proof of Pilot A's research conclusions.

**Completion criterion:** all applicable steps above are complete and the report is written. An inconclusive or low-yield finding is acceptable when supported and reported. Missing scheduled work is not. The generic handoff report currently hardcodes `research_complete: false`; it cannot certify study completion automatically. Record completion in the final report/checklist rather than editing immutable machine output to make it look complete.

## Scope boundaries

The current first round does **not** require new phase segmentation, controls, repeated agent runs, double review of every extraction, bootstrap analysis or official harness grading of agent patches. These were removed/deferred in [Kickoff section 11](plan/Kickoff.md) and later decisions. The separate-model API route improves the procedure but does not remove the need for validity/sharing analysis, nor does it remove contamination from the source trajectories.

This document specifies remaining work; it does not report new verification results or authorize a change to the frozen data.
