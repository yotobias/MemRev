# Offline Lane N handoff: implement first, review later

For commands in execution order, use [START_HERE.md](START_HERE.md). This document is the detailed interface reference.

Human review is not required to prepare or exercise this workflow. It builds a **draft interface handoff**, with unfinished judgments explicitly pending. It does not complete Pilot A's research or certify a Pilot B dataset. V42–V44 authorize this implementation approach; the contracts below are proposals to discuss with Lane R and Pilot B.

## Start with the existing development acquisition

From the MemRev root:

```bash
PYTHONPATH=src .venv/bin/python -m memrev.handoff build \
  --acquisition runs/acquisitions/astropy-manual-102526 \
  --output-dir runs/handoffs/astropy-design-v2
```

No review is required or inferred. The builder does not search for `review.ai.json` or human forms; only evaluations explicitly passed with `--evaluation` are imported. It does not contact a model, execute trajectory commands, launch Docker or open gold material. Repeat `--acquisition` to collect multiple packages. Development and production acquisitions must be kept in separate collections.

The current development example has 5 lessons and 17 assumptions. Without an evaluation, all 51 C0/C1/Ca cells and all 17 sharing rows remain pending. All five lessons are excluded from the B draft because required provenance is missing; the exclusions are a useful demonstration of the contract, not evidence of bad lessons. No repository or SHA is guessed from the filename.

Outputs live in gitignored `runs/`. Repeating a command with identical inputs is safe; changed inputs or outputs require a fresh output directory. The entire collection is fingerprinted from verified acquisition records, exact supplied evaluations and the selected-task CSV. Reordering packages does not change the result. Changing a review invalidates the collection identity, so stale judgments cannot silently carry forward.

## Components and files

| Component | What it does | What it leaves to people or another lane |
|---|---|---|
| Acquisition loader | Verifies snapshot hashes, reconstructs records, rejects duplicates, copies original inputs | Accuracy of operator-supplied provenance |
| Collection builder | Combines acquisitions, preserves IDs and all original candidates, attaches optional reviews | Choice of extraction attempts and review protocol |
| Validity contract | Prepares C0/C1/Ca cells and checks returned outcome/evidence consistency | Check authoring, real execution, workspace reconstruction and judgment |
| Sharing contract | Validates explicit scoped groups and counts occurrence/task relationships | Semantic equivalence and normalization judgments |
| Regrouping workflow | Samples groups, hides the primary partition, compares returned member sets | Independent second grouping and disclosure of gold exposure |
| Pilot B draft export | Writes original advice in the proposed six-field schema; reports exclusions | Final schema agreement and B's repository/import checks |
| Status report | Reports counts, pending work, attribution, known/unknown cost coverage and selection coverage | Interpretation and final research report |

```text
handoff/
  collection.json                 original candidates, IDs and optional evaluations
  acquisitions/<acquisition-id>/  portable original snapshots and supplied evaluation
  selection.csv                   frozen task-list snapshot
  lane-r/
    requests.json                 all candidates with original scope/evidence pointers
    validity.pending.json         empty cells for Lane R's return
  validity.input.json             current return, or pending cells when none supplied
  sharing/
    pending.json                  blank grouping form tied to current validity
    input.json                    supplied grouping, or pending rows
    summary.json                  groups, reasons and computed counts
  pilot-b/
    lessons.draft.jsonl            proposed six-field export
    status.json                   attribution, exclusions and export limitations
  report.json / report.md         machine-readable and readable status
  manifest.json                   hashes of all saved artifacts
```

Collection trajectory pointers are relative to the bundle root. Lane R pointers are relative to `lane-r/requests.json`; B pointers are relative to its JSONL. Keep the `acquisitions/` sibling directory when sharing a recipient folder. Original absolute paths in acquisition records are provenance only and are not needed to use the copied snapshots.

## Optional extraction reviews

Later, provide completed evaluation JSON explicitly:

```bash
PYTHONPATH=src .venv/bin/python -m memrev.handoff build \
  --acquisition runs/acquisitions/astropy-manual-102526 \
  --evaluation runs/acquisitions/astropy-manual-102526/review.ai.json \
  --output-dir runs/handoffs/astropy-with-ai-example
```

This uses the existing AI example without performing a new review and retains its AI attribution. The validator is the same as [EVALUATION.md](EVALUATION.md). An acquisition may have one explicitly selected evaluation in a collection; separate reviewers require separate collections or a future adjudication policy. Pending extraction forms cannot be passed as completed evaluations; omit `--evaluation` instead.

Review is not a prerequisite for producing requests or the B draft. Grouping into the proposed primary sharing analysis does require usable extraction judgments and repository-history support. Pending/uncertain/excluded candidates remain in the original denominator.

## Proposed Lane R return contract

Send `lane-r/` plus its referenced `acquisitions/` directory to Lane R for interface discussion. The requests include **all** original candidates, including unreviewed and context candidates; their presence does not authorize or require executing a check for each one. Review eligibility and check scheduling are separate decisions.

`validity.pending.json` contains one row per original assumption ID, with C0, C1 and Ca cells. Keep every row; leave unfinished cells exactly pending. Each completed assessment supplies:

- `outcome`: `supported`, `contradicted`, `inconclusive`, or `undefined` (Ca only).
- `method`: `execution` or `manual`; null for pending/undefined.
- `assessor`: the same id/type/independence/note structure used by extraction review.
- `workspace`: an exact identifiable checkout/container/workspace reference. Agree how this identifies C0, C1 and Ca; a source SHA alone does not identify agent edits or patched installations.
- `reason`: an explanation of the judgment, including setup limitations.
- `evidence`: references with SHA-256 declarations. For execution, retain the check source, outputs and workspace reconstruction evidence on Lane R's side.
- `execution`: for executed checks, `command`, `asserted_target`, `result` and `exit_code`; otherwise null.

Execution result mapping is explicit: `pass` supports `supported`; `fail_on_asserted_target` supports `contradicted`; setup errors, timeouts, flakiness, scope failures and unresolved execution support `inconclusive`. The importer never infers contradiction from a generic nonzero exit. Pass requires zero exit; target failure requires a nonzero exit. If Lane R's runner has different test-result semantics, adapt and agree this proposed contract before using it.

The importer validates declared references and digest syntax but **does not open evidence references, authenticate assessors, execute checks or prove that a workspace matches its name**. Gold patches and detailed C1 evidence stay with Lane R; only the agreed return travels to Lane N. Manual and execution methods, assessor types and the fraction of manual cells are reported separately. Unknown agent/check/container costs are reported as unaggregated, not zero.

Derived summaries preserve `repo_history_superseded`. If C0/C1 are negative and Ca is unavailable, the result is `agent_workspace_unavailable`; if all checked workspaces are negative, it is `not_supported_in_checked_workspaces`. Neither claims that an intermediate trajectory observation never happened. Original workspace context is retained. Pending or inconclusive required cells are never counted as failed checks. Ca can stay pending when C0/C1 already establish repository history.

To ingest a later return:

```bash
PYTHONPATH=src .venv/bin/python -m memrev.handoff build \
  --acquisition PATH_TO_ACQUISITION --evaluation PATH_TO_COMPLETED_EVALUATION \
  --validity PATH_TO_VALIDITY_RETURN \
  --output-dir runs/handoffs/with-validity
```

Use the same acquisition/evaluation set that produced the return. A return with missing, duplicated or foreign assumption IDs, a stale collection ID or inconsistent cells is rejected before output is written.

## Sharing when judgments are available

The updated bundle's `sharing/pending.json` is tied to its exact validity snapshot. For each occurrence choose `group`, `exclude`, `uncertain`, or leave `pending`. Completed rows require reviewer attribution and a reason; group rows additionally require a group ID and resolved key:

```json
{
  "repository": "django/django",
  "symbol": "module.qualname",
  "predicate": "returns",
  "scope": {"inputs": "explicit conditions", "config": "explicit conditions", "env": "explicit conditions"}
}
```

The key is a reviewer-supplied normalization, not a copy of raw strings and not an automatic equivalence test. A group's members must use the same resolved key. Unknown scope must be resolved or kept uncertain; null does not mean unrestricted. Same-key candidates may still be kept in separate groups when their behavior differs. Every member carries a reason.

Grouped candidates need a usable extraction evaluation, repository-behavior kind and C0/C1 repository support. Superseded assumptions remain eligible. Context, uncertain and repair candidates are retained but do not silently enter the primary groups. The grouping reviewer may be AI in a development fixture; the report retains that attribution and never counts it as human sign-off.

Supply the completed or partially completed form with `--sharing PATH` alongside the same `--validity PATH`. Counts distinguish multiple lessons, multiple tasks, frozen-selection distinct PRs, repeated-task occurrences and same-text flags. A group occurring twice within one task is not cross-task sharing. Development task IDs and made-up SHAs do not establish selected-task coverage or trusted PR membership.

## The 30% regrouping sample

After all primary sharing rows are resolved and at least one group exists:

```bash
PYTHONPATH=src .venv/bin/python -m memrev.handoff sample \
  --bundle runs/handoffs/with-sharing \
  --seed TEAM_AGREED_SEED \
  --output-dir runs/handoffs/regrouping-sample
```

The proposed rule samples `ceil(0.30 × group count)` groups, includes every member, and orders candidates independently of the primary groups. Freeze the seed before inspecting the sample. The sample directory contains:

- `blind/`: pending regrouping form and referenced trajectories. **Send only this directory to the second reviewer.**
- `private/reference.json`: primary groups, seed and denominator. Keep this private.
- A private package manifest for integrity checks; do not send it as a substitute for `blind/`.

The second reviewer assigns new group IDs and reasons, or marks an occurrence excluded/uncertain. They must declare `gold_exposure` true or false. Lane R's known prior gold exposure must be disclosed; independence is a declaration, not authenticated by the code. Candidate text and provenance cannot be changed.

```bash
PYTHONPATH=src .venv/bin/python -m memrev.handoff compare \
  --sample runs/handoffs/regrouping-sample \
  --response PATH_TO_RETURNED_REGROUPING_JSON \
  --output-dir runs/handoffs/regrouping-comparison
```

A primary group is unchanged only if its exact member set appears as one returned group. Renaming a group does not create disagreement; splits, merges, exclusions and uncertainty do. Report `groups_changed / groups_sampled`, with reviewer attribution and exposure. This measures consistency within the sampled partition, not recall of sharing with unsampled candidates. It is not automatic adjudication.

## Proposed Pilot B mapping

| Proposed key | Source |
|---|---|
| `lesson_id` | Original occurrence ID |
| `lesson_text` | Original extraction advice, never reviewer replacement text |
| `task_id` | Acquisition metadata |
| `repository` | Acquisition metadata |
| `source_revision` | Acquisition metadata |
| `trajectory_pointer` | Copied trajectory, relative to the JSONL file |

The exporter excludes rows with missing task/repository/source or a repository outside B's documented set; each exclusion has reasons. It does not require A review or source-validity approval, because Pilot A does not gate B and B performs its own extraction/checks. `status.json` records whether advice has an extraction review. It does not check that the SHA exists, ancestry, version compatibility, provider authenticity or B's acceptance policy. B ticket 01 must agree these exact names and perform its own validation. Both reviewed and unreviewed output remains **draft** until then.

## Test and handoff checklist

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_handoff.py -q
```

The tests construct two explicitly synthetic tasks, four lessons, synthetic AI evaluations and manual/execution declarations. They exercise nonempty B export, validity, sharing and regrouping without executing a real check or claiming a human review. The current Astropy command above exercises the all-pending path with real saved development inputs.

For a design meeting, bring `report.md`, this proposed contract and the generated request/return forms. No trajectory review is necessary to discuss those interfaces. Decisions still needed are rubric/repair policy, Lane R evidence/workspace conventions, grouping scope/eligibility and seed, and B's field names/provenance policy.

After agreement, remaining work includes real selected-task runs and preserved workspaces from Lane R, extraction using the existing saved-response path (a paid API client/batch driver is not implemented here), actual review/checks/grouping, cost aggregation beyond extractor metadata, and the final research report. Lane R's real check runner and Pilot B's importer remain their own implementations. This ticket makes those boundaries concrete and testable; it does not claim that the entire research study or those other lanes are finished.
