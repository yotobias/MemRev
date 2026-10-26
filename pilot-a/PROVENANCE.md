# From a raw extraction to a reviewable acquisition package

This is the step after `validate_extraction`. It preserves where each candidate lesson came from and gives it an identity before review. It does not establish whether the lesson is useful or whether an assumption holds at any revision. Continue with [evaluation-only review](EVALUATION.md), which supersedes the original edit/split review workflow (V40–V41).

## Run the development example

From the MemRev repository root, with the existing virtual environment:

```bash
PYTHONPATH=src .venv/bin/python -m memrev.provenance \
  --trajectory pilot-a/fixtures/test/full_trajectory_example.traj.json \
  --extraction pilot-a/fixtures/test/gpt-6-high_test_lessons_102526.json \
  --metadata pilot-a/fixtures/test/gpt-6-high_test_lessons_102526.metadata.json \
  --output-dir runs/acquisitions/astropy-manual-102526
```

`PYTHONPATH=src` selects the local source package without changing Lane R's current non-packaged uv configuration. The output lives inside MemRev under `runs/acquisitions/`, covered by the existing `runs/` ignore rule (V39). Keep it separate from the benchmark repository being tested. External output directories are also supported. This command uses no model API, Docker, or gold data. The existing curated `extraction_v2.json` remains the independent regression fixture.

If you have the exact saved prompt used for an extraction, add `--prompt /path/to/submitted_prompt.txt`. The command checks its rendered trajectory and saves its bytes and hash. Do not pass a regenerated prompt unless it is actually the one used: a matching trajectory alone cannot prove provenance. For this browser-generated example the exact submitted prompt remains unknown.

## What is written

```text
astropy-manual-102526/
  record.json
  inputs/
    trajectory.json
    extraction.json
    metadata.json
    prompt.txt       # only when supplied
```

`record.json` contains the original lesson/assumption content, assigned IDs, original list positions, metadata, message count, and input fingerprints. Snapshot paths are relative to the package so a teammate can move the whole directory. Original absolute paths are retained for local traceability, but are not used to form IDs.

Each input is read once. The bytes that are parsed are the bytes that are hashed and saved. SHA-256 identifies those bytes; it does not prove that a model produced them or that their statements are true. Keep snapshots and the record unchanged. The script refuses to reuse a directory with changed frozen artifacts, but these are ordinary files, not filesystem-enforced immutable storage.

Acquisition preparation creates only the record and input snapshots. When review is wanted, export an evaluation form separately using `memrev.evaluation draft`; see [EVALUATION.md](EVALUATION.md). Repeating preparation checks frozen artifacts and leaves any existing review files alone. It no longer creates or requires the obsolete action-based `review.json` (V45). A changed response, run, metadata file or prompt requires a new output directory. If metadata alone is corrected, the occurrence IDs remain the same in the new package; review decisions are not automatically copied between packages.

## Metadata and unknowns

Copy the example metadata JSON for a new extraction and fill it from trusted run records. `extraction_run_id` identifies the extraction attempt; do not reuse it for an independently repeated model call just because its output happens to match. `agent_run_id` identifies the coding-agent run that produced the trajectory. They are different activities.

The task ID in this example matches `trajectory.instance_id`. Repository metadata, source SHA, agent-run ID, exact extractor provider/model, tokens, cost and exact prompt are unavailable and remain null. The filename's `gpt-6-high` label is retained as `reported_label`, not promoted to an exact model identifier. The trajectory's own model statistics belong to the coding agent and are not extraction usage or cost.

`purpose: development` permits these unknowns and lists them in `unknown_metadata`. `purpose: pilot_a` requires core provenance: task, repository, full source SHA, agent-run ID, extractor provider/model ID, and prompt. This is a completeness check, not certification that the SHA exists, the task belongs to the selected dataset, or the provider actually served that model. Extraction usage/cost may still be unknown and remain listed. Pilot B has its own import and source-validity requirements.

## Why these IDs work for the research

The acquisition ID hashes an identity-version marker, extraction-run ID, trajectory hash and raw-response hash. Lesson and assumption IDs append their original zero-based positions, for example:

```text
acq-<digest>/lesson/0
acq-<digest>/lesson/0/assumption/1
```

Repreparing identical inputs gives identical IDs. Moving the files or correcting descriptive metadata does not change them. Altering raw bytes (even whitespace) or the extraction-run ID creates new IDs, so preserve the raw response and edit only the review draft.

These identify occurrences, not meanings. Two assumptions with identical wording in different lessons still have different IDs. That distinction is necessary to measure the difference between assumption occurrences and distinct scoped assumptions during the sharing review. Grouping by repository, symbol, predicate and scope happens later; neither string equality nor matching IDs establishes semantic equivalence. These IDs are also separate from Pilot B's content hashes.

The evaluation importer retains these original IDs and all original candidates. A future repair stage would need separate parent/child lineage for splits; repair is not part of primary evaluation.

## How to review

Use [EVALUATION.md](EVALUATION.md) for the current form, rubric, commands and consistency rules. Read each original statement alongside its cited messages in `inputs/trajectory.json`. Rate its quality, record an outcome and explain defects without supplying replacements. Keep uncertainty explicit. The original candidate remains in the bank and denominator even if it needs repair or only provides context.

For example, if lesson 0, assumption 1 combines independent behaviors, mark the atomicity defect and explain it. Splitting the claim is a separate transformation, not required reviewer work. Evidence from a patched installed package must not become a claim that the assumption passes at the source SHA.

## What this enables and what follows

Lane N can review reproducibly and retain the link to the original model response. Lane R can later receive assumption IDs, scoped statements and proposed checks and return C0/C1/Ca results against the same identities. The source SHA remains separate from the workspace described in each assumption. Source-validity labels, manual-vs-executed methods and sharing groups are not inferred here.

Evaluation import, offline sharing/reporting and a draft Pilot B export are implemented. Follow [START_HERE.md](START_HERE.md) for the execution order. Team agreement, actual reviews/checks and production data remain pending. This Astropy package remains development data.
