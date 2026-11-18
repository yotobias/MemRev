# Lane R execution contract v1

Frozen by Lane N on 2026-11-18 for the user-approved preliminary main-3 batch. Profile: `pilot-a-lane-r-execution-v1`. The return remains **`validity_version: 1`** and is compatible with the existing handoff importer. This is the producer's executable specification; it does not claim that Lane R has already accepted or executed it.

## Inputs and schedule

Keep the execution bundle intact. `work_order.json` supplies the collection ID, assumption IDs, statements/scopes, task/source/image identities and trajectory pointers. `handoff/acquisitions/` contains the originals and reviews; `prepared/` contains trajectories and previous replay reports. `validity.pending.json` is the starting return; `receipt.template.json` is an intentionally incomplete recording template.

`runner/` contains the source and dependency-lock snapshot for these commands, so execution-contract validation does not depend on pulling an unpublished branch. From the extracted bundle use `export PYTHONPATH="$PWD/runner/src"` with the existing project environment. Alternatively, run `uv sync --locked` inside `runner/`, then use that environment's Python. This supplies the recording/import tools, not a Docker check runner.

For the current batch there are **32 original rows**, including **31 scheduled assumptions**. First assess the scheduled assumptions at C0 and C1 (**62 initial assessments**). Assess Ca only when both C0 and C1 are `contradicted`. If either is pending or inconclusive, resolve that uncertainty before using Ca for classification. Keep the context-only row and unscheduled Ca cells exactly pending; explain scheduling through the work order rather than inventing a `skipped` outcome.

No new agent run, phase segmenter or human review is required. Checks still need to be authored and executed by R. An old trajectory command or replay report is evidence to inspect, not an assumption check to execute blindly. Original code/structure observations can be checked by inspecting the actual symbol in the identified workspace; do not generalize a finite example into a universal behavioral claim.

## Workspace definitions

| Cell | Required state |
|---|---|
| C0 | Task image's original source at the recorded `base_commit`; record any known image packaging/mode-only difference |
| C1 | C0 plus the official source fix, **without the official test patch**; construction and gold details remain on R |
| Ca | Agent's final workspace reconstructed from the recorded run, including relevant tracked/untracked edits and installation changes |

Use the exact image ID from the work order. Tags such as `latest` alone are insufficient. If unavailable, report the blocker; do not substitute a different environment silently. `final_workspace.json` is a previous replay report, not a captured filesystem. For django-14792 and django-16910, applying the submitted patch alone does not reconstruct Ca. Preserve test-edit caveats, including sympy-18057. Intermediate observations need not hold in the final workspace.

A workspace manifest contains `workspace_version: 1`, `task_id`, `revision` (`C0`, `C1`, `Ca`), `source_revision`, `image_id`, a nonempty `reconstruction` description, and SHA-256 hashes of the tracked diff, untracked-file manifest and environment fingerprint. R computes these from the actual workspace, records serialization details and retains the underlying records in reconstruction evidence. Do not fill them from expected values merely to satisfy validation.

The recorder assigns the shared workspace identifier:

```text
lane-r:<task_id>:<revision>:sha256:<canonical-workspace-manifest-hash>
```

This identifies an asserted reconstructed state; hashing does not itself prove that state was built correctly.

## Results and attribution

| Recorded execution result | Return outcome |
|---|---|
| `pass`, exit code 0 | `supported` |
| `fail_on_asserted_target`, nonzero exit | `contradicted` |
| `setup_error`, `out_of_scope`, `flaky`, `timeout`, `unresolved` | `inconclusive` |
| Not assessed | Leave the complete pending cell unchanged |

Nonzero exit alone is never sufficient for contradiction. Verify that the assertion about the stated behavior failed, rather than collection/setup. A submitted patch or a broad test-suite pass does not establish an individual assumption. Use checks that discriminate the stated behavior under its scope; do not mock the target implementation.

This execution profile uses `method: "execution"`. An LLM may author checks and assess outputs; this does not make repository execution optional. Legacy non-execution `manual` judgments remain supported by the base importer but require a separately agreed profile and separate reporting here.

`assessor` identifies whoever designed/assessed the judgment, not merely the shell. Use the existing `id`, `type`, `independent`, `note` fields. AI assessment is allowed. The template defaults independence to false; set true only with a defensible, disclosed separation from extraction/review. Record model/session information and gold exposure in the note where applicable. No human sign-off is inferred.

If Ca is genuinely unreconstructable after C0/C1 are contradicted, a direct `undefined` Ca declaration is allowed under the base contract: assessor and reason required, method/execution null and evidence empty. A temporary Docker or setup failure is not proof that Ca is undefined. Do not mark an unattempted cell inconclusive merely to make a return look complete.

## Private evidence and public return

R retains check source, output including stdout/stderr and exit information, reconstruction evidence, and the workspace manifest. The recorder copies bytes to `EVIDENCE_ROOT/sha256/<digest>` and adds an execution record linking those artifacts to the collection, assumption and judgment.

Shared evidence entries have only `reference` and `sha256`:

```text
lane-r://sha256/<digest>/<role>
```

The five roles are `workspace`, `check_source`, `output`, `reconstruction`, `execution_record`. N checks references and declarations; R can additionally verify the local files and their hashes. **Do not send the private evidence directory, gold patches or detailed C1 logs to N.** Keep shared reasons concise and gold-blind. Use a generic actual command such as `python /checks/check.py`; do not embed source fixes, gold test names or credentials in shared command/reason fields. The validator does not automatically redact arbitrary text.

The recorder refuses evidence/output paths inside the frozen bundle and verifies prior private evidence before extending a return. Store private working files in a separate directory on R's machine.

## Commands

From the repository root, after installing the locked dependencies:

```bash
export PYTHONPATH="$PWD/src"
```

N prepares the immutable bundle:

```bash
.venv/bin/python -m memrev.lane_r prepare \
  --handoff runs/pilot-a/main-3/handoff \
  --prepared runs/pilot-a/main-3/prepared \
  --output-dir runs/pilot-a/main-3/lane-r-execution-v1
```

On R's machine, extract the supplied execution ZIP, and copy its `validity.pending.json` to a working return file outside the frozen bundle. Copy `receipt.template.json` for each executed check and fill it from the actual execution. Evidence paths are absolute or relative to the receipt file. The recorder automatically supplies the original statement as `asserted_target` and computes private evidence hashes:

```bash
.venv/bin/python -m memrev.lane_r record \
  --bundle PATH_TO_EXECUTION_BUNDLE \
  --return-file returns/validity-000.json \
  --receipt private/receipt-001.json \
  --evidence-root private/evidence \
  --output returns/validity-001.json
```

Use a new output name for each update; feed the previous return into the next command. Existing completed cells cannot be silently replaced. Changed judgments need a separately recorded assessment/version, not last-writer-wins merging. This command records results; **it does not execute the command in the receipt**.

R validates before sending a partial or final return:

```bash
.venv/bin/python -m memrev.lane_r validate \
  --bundle PATH_TO_EXECUTION_BUNDLE \
  --return-file returns/validity-001.json \
  --evidence-root private/evidence
```

Send **only the return JSON and the validator summary** to N. N runs the same validation without `--evidence-root`, then imports using the frozen acquisitions/reviews:

```bash
.venv/bin/python -m memrev.lane_r import \
  --bundle runs/pilot-a/main-3/lane-r-execution-v1 \
  --return-file PATH_TO_R_RETURN.json \
  --output-dir runs/pilot-a/main-3/with-validity-v1
```

Partial returns are valid. `remaining_scheduled_cells` states the remaining work; `stage_complete` means no scheduled assessments are pending, even if some are inconclusive. It does not mean the scientific claims are proven or Pilot A is complete. Unscheduled cells remain pending by design.

## Version and handoff boundary

All returns must retain this exact collection ID and all original assumption IDs. A new API extraction creates a different collection: prepare a new work order and never copy old verdicts onto its new assumptions by position or text similarity. Reuse a check only after verifying its claim/scope correspondence and recording the new assessment explicitly.

The current inputs are preliminary same-session AI extractions/reviews. Their contamination, selection and workspace limitations still apply. The supplied contract resolves format/scheduling ambiguity, not missing check implementations or execution access. R should report any incompatible runner behavior before executing the batch; do not rename fields or invent outcomes locally.

The generic handoff report still labels broader interfaces as proposed. This versioned profile fixes the Lane R execution interface only; it does not certify Pilot B acceptance or require changing the immutable original handoff.
