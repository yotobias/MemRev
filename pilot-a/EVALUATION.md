# Evaluate an extraction without rewriting it

This follows [acquisition preparation](PROVENANCE.md). The reviewer evaluates the original advice and assumptions against the trajectory. They supply ratings, outcomes, issue codes, reasons and optional extra evidence pointers. They do **not** supply replacement text. Repairing an extraction is a separate intervention; mixing it into evaluation would hide the raw extractor's defects and change the denominator.

This is the development protocol from decisions V40–V41. Agree its criteria, issue vocabulary and outcome rules with the team before production reviews. The implementation checks consistency and provenance; it cannot determine whether a reviewer's judgment is correct.

## Create a blank review

From the MemRev repository root:

```bash
PYTHONPATH=src .venv/bin/python -m memrev.evaluation draft \
  --package runs/acquisitions/astropy-manual-102526 \
  --output runs/acquisitions/astropy-manual-102526/evaluation.mine.json \
  --reviewer-id YOUR_ID \
  --reviewer-type human_ai_assisted \
  --note 'I have seen the AI example; this is my own evaluation.'
```

Replace `YOUR_ID` and the note. Supported types are `human`, `human_ai_assisted` and `ai`; choose the one that describes your process. `--independent` is an explicit self-report and defaults to false. Seeing the AI example should be disclosed; do not describe copied AI judgments as independent human review. Identity and independence are recorded, not authenticated. The command refuses to overwrite an existing form.

**Use the evaluation form above for the primary review.** Acquisition preparation no longer creates the obsolete action-based `review.json`. Existing files are preserved if present; this development package's old draft and rewriting examples were moved into its `archive/` directory during cleanup. The importer does not consume accept/edit/split proposals.

## What to fill in

Keep the IDs, original text, definitions and version fields unchanged. For every lesson, fill its `evaluation`; for every assumption, fill its `evaluation` and all six `rubric` ratings. All rows must be complete before import, but `uncertain` is a legitimate completed judgment. An empty extraction is also valid and produces zero counts.

The six criteria are checkable specificity, one behavior, support from the **original** cited messages, sufficient scope, correct workspace attribution, and whether the statement describes repository behavior. Read their precise definitions embedded in the form. Rate each `yes`, `no` or `uncertain`; do not turn unknown scope into unrestricted scope.

| Assumption outcome | Consistency rule |
|---|---|
| `usable_as_extracted` | All six ratings are `yes`; no issue codes |
| `needs_repair` | At least one of the first five quality criteria is `no`; at least one issue code |
| `uncertain` | At least one criterion is `uncertain`; at least one issue code |
| `context_only` | `repository_behaviour` is `no`; at least one issue code |

Choose the outcome and explain your reasoning. These are necessary consistency rules, not an automatic classification algorithm. For example, a useful environment observation can be `context_only` without being false. A compound repository claim can need repair without the reviewer writing its split replacements. Defects and uncertainty can coexist; explain which determines your outcome.

Lesson advice has its own outcomes: `usable_as_extracted`, `needs_clarification`, or `uncertain`. A usable advice statement can still have defective attached assumptions. Advice outcomes are not derived from assumption counts. Non-usable advice needs an issue code; usable advice has none.

Every evaluation needs a nonempty `reason`. Choose zero or more distinct issue codes from the form's `issue_definitions`, following the rules above. `reviewer_evidence_message_indices` contains distinct zero-based indices into the original trajectory; it can be empty where the reason concerns missing information. Additional citations explain your assessment but do not retroactively repair the original extraction's citations. Workspace checks must distinguish original checkout, agent edits and installed-package code.

If no existing issue code captures a material defect, discuss a protocol revision instead of silently editing definitions. The importer requires the versioned definitions to match. Do not set `source_validity` to anything other than `not_assessed`: this review does not run a check at a repository revision.

## Import a completed review

```bash
PYTHONPATH=src .venv/bin/python -m memrev.evaluation import \
  --package runs/acquisitions/astropy-manual-102526 \
  --review runs/acquisitions/astropy-manual-102526/evaluation.mine.json \
  --output-dir runs/acquisitions/astropy-manual-102526/evaluations/my-review
```

Before writing, the importer verifies acquisition snapshot hashes, reconstructs the record, checks every lesson/assumption ID under its original parent, and compares all original content. Missing, duplicated, foreign, moved or modified candidates fail. Row ordering is irrelevant. It also checks the protocol, reviewer attribution, complete ratings, outcome consistency and citation bounds. This is integrity checking, not cryptographic authentication of the acquisition's author.

The output directory contains:

| File | Role |
|---|---|
| `evaluation.input.json` | Exact submitted review bytes |
| `evaluated_bank.json` | All original lessons/assumptions, original order and provenance, plus their evaluations |
| `summary.json` | Recomputed counts, per-criterion ratings, assumption issue counts and reviewer attribution |
| `report.md` | Readable per-review counts and their limits |
| `acquisition.record.json` | Snapshot of the verified acquisition record |
| `protocol.json` | Complete protocol used for this import, including advice outcome definitions |
| `manifest.json` | Evaluation identity and SHA-256 fingerprints of inputs and generated artifacts |

The source package and review remain unchanged. Importing identical bytes to the same output is safe; any changed artifact requires a new output directory. Keep the whole acquisition package when handing it off, since the record points to its `inputs/` snapshots. `runs/` is gitignored, so sharing code alone does not transfer these artifacts.

The older AI example may omit `protocol_id` and lesson outcome definitions; matching its embedded rubric/assumption-outcome/issue definitions identifies this protocol. Its optional `original_review_sha256` is retained only as a legacy declaration, not checked against an editable action draft. The import manifest instead fingerprints the verified acquisition record and exact evaluation input. If a review supplies `summary`, it must exactly match the three original-count fields used by the existing example; ordinarily omit it and let the importer calculate the report.

## Existing development result and remaining work

`runs/acquisitions/astropy-manual-102526/evaluations/ai-codex/` contains the imported `review.ai.json`: **5 lessons, 17 original assumptions; 7 usable, 6 needing repair, 2 uncertain, 2 context-only.** It remains a non-independent AI evaluation of development data with unknown source/model provenance. These are not human judgments, source-validity labels, or Pilot A production results.

Next, agree the protocol and complete a human evaluation, then exercise the same pipeline on one selected Pilot A agent run with complete provenance. Production work still includes acquiring the selected trajectories, extraction with saved prompts/model usage, revision-specific validity checks coordinated with Lane R, scoped cross-task sharing groups and the planned 30% regrouping review, and the Pilot A report. Preserve the original candidates if a separate repair stage is added.

Human review can be deferred while implementing and discussing interfaces. [HANDOFF.md](HANDOFF.md) documents the offline collection builder, pending Lane R forms, later validity/sharing import, regrouping comparison and draft Pilot B export. None of those preparation steps requires filling out a trajectory review now.

Each reviewer imports into a separate directory; this step does not merge judgments or implement adjudication. A draft six-field Pilot B export is available through `memrev.handoff`; agree its field names with B before production use. B performs its own assumption extraction and source/target checks. Follow [START_HERE.md](START_HERE.md) for commands in order.
