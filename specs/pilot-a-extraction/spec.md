# Pilot A extraction contract v2

The raw extractor response needs enough structure for assumption review and sharing analysis, while remaining separate from Pilot B's lesson-bank import. This implements decisions V33–V35 and the user-approved whole-trajectory approach.

## Behaviour

1. A researcher builds a prompt from an indexed full trajectory, loads the response as strict JSON, and validates its structure without changing it.
2. Every response has integer `schema_version: 2` and a `lessons` list. An empty list is valid. Each lesson has nonempty `advice`, `from_failed_step` (boolean or null), and an `assumptions` list, which may be empty.
3. Every assumption has nonempty `statement` and `workspace_context`; nullable nonempty `symbol` and `file`; `predicate`; `kind`; structured `scope`; `evidence_basis`; and `evidence_message_indices`.
4. `predicate` is one of `returns`, `raises`, `accepts`, `mutates`, `calls`, `type_is`, `default_is`, `other`. `kind` is `repo_behaviour`, `procedure`, or `environment`. These are Pilot A fields, not Pilot B's five assumption types.
5. `scope` contains exactly `inputs`, `config`, and `env`, each a nonempty string or null. Null means unspecified/unknown, never unrestricted. Reviewers must resolve relevant unknowns before grouping assumptions as equivalent.
6. `evidence_basis` is `execution_observation`, `code_observation`, `unverified_assertion`, or `no_evidence`. Only `no_evidence` permits an empty citation list, and it requires one. All other categories require at least one original zero-based integer message index. Boolean, duplicate, negative, and out-of-range indices are rejected. Command and observation indices may both be cited; the validator does not infer semantic support from message roles.
7. `from_failed_step` is true when advice draws on at least one failed step, false when its origin is known and none failed, and null when unclear. Failure means an observed failed attempt, not necessarily a nonzero shell exit code. It is not a task-resolution label.
8. All documented fields are required; unknown fields are rejected in the raw v2 response to catch typos. JSON syntax errors, duplicate object keys, and nonstandard constants are rejected on load. File errors retain their original exception type. Validation raises `ValueError` with a field path and returns the same object on success.

## Review and provenance

The prompt requests repository behaviour with explicit branches/conditions rather than run-history summaries masquerading as transferable assumptions. Human review still decides truth, scope, relevance, and evidence support. `no_evidence` records missing support, not a C0/C1/Ca verdict; `unverified_assertion` cites an assertion without treating it as proof.

Keep raw responses immutable. A later pipeline stage assigns lesson/assumption IDs and attaches run ID, task ID, repository, source SHA, trajectory pointer, prompt version/hash, and actual model/cost metadata from trusted records. The LLM does not generate these values. Keep source revision separate from the workspace where evidence was observed; edited or installed-package evidence does not establish source validity.

For manual browser extraction, request a downloadable UTF-8 `extraction.json` file when available, otherwise exactly one fenced `json` code block. Save only the block contents as JSON; the loader remains strict and does not strip Markdown or decode HTML entities. This changes delivery formatting, not the v2 schema.

Whole-trajectory extraction replaces mandatory phase extraction for this implementation. No phase label gates verification. This supersedes the phase requirement in Plan_v2 section 5 and Kickoff step 3; grouping and source-validity review still apply.

Pilot B receives a separate JSONL export, one lesson per line, with its six required provenance/text fields. Exact export key names remain to be agreed in B ticket 01. B performs its own assumption extraction and source-validity checks; A's raw assumptions are not its import schema. B may ignore accompanying extra fields; the raw v2 validator is intentionally stricter.

## Tests and limits

Use a hand-reviewed v2 fixture derived from the existing Astropy development trajectory. Test loading, schema boundaries, missing evidence, nullable details, original index bounds, and preservation of input. Retain the original unversioned model response unchanged; do not silently migrate it.

This slice does not call models, run trajectory commands, assign provenance, export to B, judge semantic validity, or inspect gold fixes. The Astropy fixture is development data, not a selected Pilot A result.

## Provenance package (ticket 02)

Ticket 02 adds provenance assignment after raw validation. `memrev.provenance` owns this step; trajectory loading/formatting/validation stays in `trajectory.py`.

Operator metadata includes an extraction-run ID, purpose (`development` or `pilot_a`), agent-run ID, task ID, repository, source revision, extractor provider/model ID/reported label/method, token counts, cost and notes. Required keys are explicit; unknown optional values use null. The reported model label is not an exact model ID. Agent-run cost is never reused as extraction cost. A source revision, if supplied, must be a full 40- or 64-character hexadecimal Git object ID; its existence/ancestry is not checked here.

Production preparation requires a saved prompt and known task/repository/source, agent run, extractor provider and exact model ID. These are operator assertions: passing completeness checks does not certify selection, source validity, provider provenance or Pilot B eligibility. Development packages retain an `unknown_metadata` list. An optional prompt must contain the same formatted trajectory; this catches an obvious mismatch, but cannot prove which prompt a person actually submitted. Supply only the exact prompt used, never silently reconstruct it from today's template.

An acquisition ID hashes a canonical object containing identity version 1, extraction-run ID, and exact trajectory and response SHA-256 digests. Lesson IDs append `/lesson/<original zero-based index>`; assumption IDs append `/assumption/<original zero-based index>`. Same bytes plus run ID give the same IDs across locations; new raw responses or run IDs create new IDs. Whitespace changes to raw input bytes also change IDs, which is why originals must be preserved. Descriptive metadata corrections do not change occurrence IDs. This differs from Pilot B's content hash and from Pilot A's semantic grouping key.

The output directory contains `record.json` and `inputs/` snapshots of trajectory, response, metadata and optional prompt. The record embeds validated lessons and assumptions with IDs and raw list positions, portable snapshot paths, original paths, SHA-256 digests, message count and explicit unknowns. Outputs are staged in a temporary sibling directory; existing frozen artifacts must match before reuse. Existing review files are preserved. V45 retires ticket 02's action-based draft generation; evaluation forms are exported separately as described below.

V39 permits acquisition packages inside MemRev under gitignored `runs/acquisitions/`, as well as external directories. They must stay separate from benchmark checkouts. Package creation no longer rejects a path solely because it is inside a Git repository; overwrite protections still apply.

## Evaluation-only import (ticket 03)

V40–V41 supersede ticket 02's edit/split proposals as the primary review interface. `memrev.evaluation draft` exports pending evaluations with the original IDs and text; `import` requires every row to be complete. Legacy action files are not consumed or regenerated; the development examples are archived under V45. Repairs, splits and adjudication remain separate work.

The versioned development protocol is `src/memrev/evaluation_protocol.json`. Each assumption receives six yes/no/uncertain ratings: checkable specificity, single behavior, support from original citations, scope, workspace attribution and repository behavior. Outcomes are `usable_as_extracted`, `needs_repair`, `uncertain` and `context_only`. Lesson advice has separate usable/needs-clarification/uncertain outcomes. Every judgment has a reason and valid optional reviewer citations; non-usable outcomes require known issue codes. The exact consistency rules and reviewer instructions are in `pilot-a/EVALUATION.md`. Freeze this protocol with the team before production review.

The importer verifies snapshot hashes and reconstructs the acquisition record. It matches each candidate by ID under its original parent, rejects omitted/duplicated/foreign/moved IDs and modified originals, and checks complete ratings and outcomes against unchanged protocol definitions. Reordered review rows are accepted; bank order follows the original extraction. All original candidates survive, including repair, uncertain and context-only rows. Empty extractions produce zero counts.

Review attribution records an ID, type (`human`, `human_ai_assisted`, `ai`), note and self-reported independence. No identity authentication or human sign-off is inferred. The existing AI example is supported only for development acquisitions and remains AI-attributed. Extraction evaluation never establishes C0/C1/Ca or Pilot B source validity.

Outputs preserve exact review bytes, an evaluated bank, recomputed counts over the original denominator, a readable report, acquisition-record and protocol snapshots, and a hash manifest. Identical imports may reuse their directory; changed output artifacts fail without replacement. The optional legacy draft hash in the AI example is only a retained declaration; the import manifest anchors the verified record and actual review bytes. Multiple reviews are saved separately without automatic merge or consensus.

Tests exercise complete and pending forms, input integrity, ID/text preservation, malformed evaluations, reviewer attribution, original denominators, reordered inputs and safe output reuse. This slice does not perform repair, source checks, cross-task grouping, production acquisition or Pilot B export.

## Offline handoff (ticket 04)

V42–V44 add a collection-level workflow that may run with every human judgment pending. Verified acquisition snapshots and optional explicit evaluations are bundled portably. Collection identities fingerprint original records, reviews and the selected-task list; returned validity/sharing data must match those identities and all original assumption IDs. Partial work uses explicit pending rows rather than omitted candidates.

Lane R receives original assumptions with scope, provenance, evidence indices and pending C0/C1/Ca cells. Completed cells carry method, reviewer attribution, workspace identifier, reason and evidence references with hashes. The importer never reads referenced gold evidence or runs checks; submitted outcomes are assertions by the named assessor. Undefined Ca and intermediate trajectory observations remain distinguishable from disproven repository behavior. Suggested validity categories follow Kickoff's preservation of superseded and intermediate observations; no negative result is called universally unsupported.

Sharing is explicit reviewer work. Grouped members require usable extraction evaluations and support at C0 or C1, including superseded assumptions. Each group uses an explicitly resolved repository/symbol/predicate/scope key and a reason; matching text alone never groups candidates. Reports retain all original rows and separate distinct-task from repeated-task sharing. Sampling uses 30% of groups rounded up, includes every member, and hides the primary partition in a separate private mapping. Comparison matches member sets rather than group labels. No bootstrap or threshold is introduced.

Pilot B receives a draft JSONL with the six proposed field names in V44, original advice and portable trajectory pointers. A sidecar records review status and exclusions. Draft export does not require A review or A validity approval, does not validate Git ancestry or SHA existence, and cannot claim B compatibility until its ticket 01 fixes the contract. Unknown metadata is never fabricated. The bundle report distinguishes development data, software readiness, pending research work and pending contract decisions.

## Handoff cleanup (V45)

The historical ticket 02 action-review draft is no longer generated or required. Acquisition preparation writes only `record.json` and input snapshots; the evaluation CLI separately exports the current review form when requested. Reusing an older package preserves any extra review files. The development package's action draft and rewriting examples are archived, not deleted. Original snapshots, IDs and hashes are unchanged.

`python -m memrev.trajectory` now takes explicit `--trajectory` and `--output` arguments, with optional `--prompt-template` and `--extraction`. It does not silently select the Astropy fixture or overwrite an existing prompt.
