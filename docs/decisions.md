# Decisions

Every design decision for MemRev, newest round last. Each entry lists the question, the decision and where it was made. Terms follow [GLOSSARY.md](../GLOSSARY.md). Decisions that are hard to reverse also get an ADR in [adr/](adr/).

## Pilot B — grilling session, 2026-10-19

| # | Topic | Decision |
|---|-------|----------|
| V1 | Input from Pilot A | Pilot B reads a lesson-bank file in a fixed JSONL schema (lesson text, source revision, task id, trajectory pointer), defined now. Until Pilot A delivers, B runs on a small hand-written fixture bank. |
| V2 | Assumption extraction | Pilot B extracts assumptions (statement, scope, supporting code pointers, candidate check) from each lesson with an LLM. A human accepts or edits each one in a CSV; only reviewed assumptions enter the labelled set. |
| V3 | Labels | The label (supported within scope / contradicted / inconclusive) comes from executing a check at the target revision, signed off by a human. Setup and environment failures map to inconclusive. LLM judgements are never ground truth. |
| V4 | Constructing stale lessons | Constructed stale lessons change only the advice, based on a real behaviour change between S and T. No synthetic code mutations in Pilot B. |
| V5 | Validity gate | A constructed stale lesson counts only if its check passes at S and fails at T. Both executions are stored as evidence; candidates that don't flip are dropped and counted. |
| V6 | Matched controls | Each constructed stale lesson gets one matched control (same file or symbol area, similar length and type, check passes at S and T). Unmatched stale lessons are reported but excluded from the unnecessary-rejection metric. |
| V7 | Deliverable | Pilot B delivers the labelled dataset (natural cases and constructed cases reported separately) and a harness that runs any maintenance mechanism without labels; only the scorer sees labels. Two mechanisms ship: no maintenance, and file-change invalidation. |
| V8 | Stack | Python 3.11 with uv, pytest, SQLite for storage, command-line tools only, no web UI. |
| V9 | LLM provider | Claude Sonnet 5.5 via the Anthropic API, behind a thin interface so the model can be swapped. Tokens and cost of every call are logged. |
| V10 | Repo workflow | Work on branch `pilot-b`, merged into `main` by PR. Specs and tickets live in `specs/`. |
| V11 | Data source | Build revision pairs from SWE-bench Verified Python instances in the same repository, checked with git ancestry. Swap in SWE-ContextBench groups if its data becomes available. See [ADR 0001](adr/0001-own-revision-pairs-from-swe-bench-verified.md). |
| V12 | Repositories | django, sympy and scikit-learn; django first as the end-to-end slice. |
| V13 | Target revisions | T is the `base_commit` of a later instance in the same repository and same SWE-bench version. Cross-version pairs are excluded from the pilot. |
| V14 | Environments | Reuse the SWE-bench Docker image per (repository, version). The drift guard runs a fixed sanity test set at S and T and drops pairs where unrelated tests break. |
| V15 | Flaky checks | Every check runs 3 times at S and 3 times at T; a check that disagrees with itself is labelled inconclusive. |
| V16 | Assumption types | Checkable assumptions are limited to: symbol exists, signature, return/raise behaviour for a given input, config or default value, named test passes. Everything else is recorded as an uncheckable assumption and counted. The list may grow after the yield check. |
| V17 | Scale and early stop | Aim for 10–20 base tasks and ~50–100 reviewed assumptions. After the first ~30 lessons, stop and report extraction yield to the team before scaling. |

## Pilot B — spec stress test, 2026-10-19

| # | Topic | Decision |
|---|-------|----------|
| V18 | Test seams | Main seam: the pipeline stages, run on fixture data with a tiny real git repository, a fake check runner and a fake LLM. Plus one opt-in slow test that runs a real check in a real django Docker image. LLM output quality is measured by review, not tests. |
| V19 | Label override limits | The reviewer may accept a label, downgrade it to inconclusive, or send the assumption back for a rewritten check and rerun. Flipping supported within scope ↔ contradicted directly is not allowed. |
| V20 | Must pass at S | A natural assumption is eligible only if its check passes 3/3 at S; otherwise it is recorded as invalid at S and counted. "Passes at S, fails at T" for constructed stale lessons also means 3/3 consistent runs. |
| V21 | Real vs setup failure | Each check declares its asserted target. An error on that target (e.g. ImportError for a renamed symbol) is contradicted. Harness or container errors are inconclusive. A missing fixture or backend at T is inconclusive with reason "out of scope at T". |
| V22 | Lesson labels | A lesson is contradicted if any assumption is contradicted, supported within scope only if all are, otherwise inconclusive and excluded from metrics. Lessons with no checkable assumption stay in the bank, are counted, and are not scored. |
| V23 | Scoring recheck | A recheck decision adds to cost, is scored as neither kept nor rejected, and is reported in its own column. |
| V24 | Choosing T | Per source revision, up to 3 targets in the same version: nearest later instance, middle and furthest. A source with no later instance is excluded with reason "no target". |
| V25 | Edits after labelling | Each assumption has a content hash; evidence, labels and scores are keyed to it, so an edit invalidates everything downstream. A re-imported CSV with missing rows or duplicate ids is rejected; re-import reports what changed. |
| V26 | Reviewers | Every review decision stores a reviewer id. One reviewer suffices for the pilot; if a second reviewer reviews a sample, agreement is reported and disagreements become inconclusive. |
| V27 | Pair-level failures | A missing image, failed checkout, or drift guard that errors or disagrees with itself (it runs 3 times) drops the revision pair with reason "environment unavailable" before any assumption check. |
| V28 | LLM failures | LLM calls retry with backoff; successful outputs are cached. Persistent failures count as "extraction failed", separate from uncheckable assumptions. |
| V29 | Constructed lessons: review and blinding | Matched controls are drafted the same way as constructed stale lessons; both go through the same CSV review and label sign-off. The variant bank uses opaque ids, the same schema and no provenance field; only the scorer holds the mapping. |
| V30 | Nothing to flip | When the S..T diff yields no stale-lesson candidate, the pair is recorded with reason "no behaviour change found", reported next to the drop counts. |

## Pilot A — task source and selection, 2026-10-24

| # | Topic | Decision |
|---|-------|----------|
| V31 | Pilot A task source | Pilot A runs on base tasks from the full SWE-ContextBench that are in SWE-bench Verified, in django, sympy or scikit-learn (V11, V12), and that have related tasks in SWE-ContextBench. The agent runs on the base tasks only; related tasks are kept as links for later pilots. Supersedes Pilot A's earlier list from SWE-ContextBench Lite (built on SWE-bench Lite). ADR 0001's premise no longer holds: SWE-ContextBench data is on Hugging Face (`jiayuanz3/SWEContextBench`, MIT), and its full experience set contains all 500 Verified tasks. |
| V32 | Pilot A clusters | 16 tasks in 5 clusters, frozen in `pilot-a/clusters.csv` before any run: modules `django/db/models/` and `sympy/printing/`; a candidate is selected iff its fix shares an edited file or sub-package of its module with another candidate. One task per PR; never chosen by looking at lessons. Details in `pilot-a/CHANGES.md`. |

## Pilot A — extraction implementation, 2026-10-25

The user requested implementation of the reviewed contract changes. The following record the implementation choices; they do not redefine Pilot B's import schema.

| # | Topic | Decision |
|---|---|---|
| V33 | Extraction unit | Use the full indexed trajectory, as agreed with Lane N, rather than mandatory per-phase extraction. Supersedes the phase requirement in Pilot A Plan_v2 section 5 and Kickoff step 3; phase labels never skip verification. |
| V34 | Raw extraction contract | Version 2 adds structured scope, symbol/file, predicate, kind, and failed-step origin. Unknown details are nullable; missing evidence is represented by `no_evidence` and empty indices, distinct from cited assertions and source-validity labels; see `specs/pilot-a-extraction/spec.md`. |
| V35 | Provenance and handoff | Assign IDs and trusted run provenance outside the LLM response, preserving raw output. Export Pilot B's six-field lesson bank separately after its exact key names are fixed; do not treat A's raw assumptions as B's importer or its reviewed labels. |
| V36 | Acquisition identities | A provenance package identifies one extraction run and its exact trajectory/response bytes. Lesson and assumption IDs identify original occurrences by list position, remain independent of wording changes during review, and do not assert semantic equivalence across lessons. |
| V37 | Unknown provenance | Operator-supplied provenance is kept separate from model output. Development records may retain unknown fields as null; production preparation requires complete core provenance, but completeness is not verification of the source commit, model or task eligibility. |
| V38 | Review preparation | Snapshot inputs and create a separate pending review draft with originals, IDs, reviewer/reason fields and edit/split proposals. Repeated preparation preserves human edits; review sign-off, split-ID assignment and Pilot B export remain subsequent work. |
| V39 | Pilot A artifact location | At the user's request, acquisition packages may live in MemRev's gitignored `runs/acquisitions/` directory. Supersedes ticket 02's outside-all-checkouts restriction for these packages; keep artifacts separate from benchmark checkouts, and retain the existing overwrite protections. |
| V40 | Evaluation before repair | Following the user's concern about reviewer rewriting, implement evaluation-only review with six yes/no/uncertain rubric ratings and explicit outcomes. Supersedes V38's edit/split proposals as the primary evaluation interface; retain original text and all candidates, and keep any later repair or curation separate. |
| V41 | Evaluation imports | Match all original IDs/text to verified acquisition snapshots, require a complete consistent evaluation, and retain AI/human/AI-assisted-human attribution plus self-reported independence. Materialize an evaluated bank and per-review counts without automatic repair, merging, source-validity approval or Pilot B export; the v1 rubric remains a development protocol pending team freeze before production. |
| V42 | Implement before human review | At the user's request, implement the remaining Lane N handoff plumbing using offline fixtures. Real extraction reviews, validity cells and sharing decisions may stay pending. Software readiness does not imply research completion, and test judgments must never be presented as human judgments. |
| V43 | Proposed handoff interfaces | Build a versioned collection from verified acquisitions, optional explicit extraction evaluations, a Lane R validity request/return form, scoped sharing forms, deterministic 30% group sampling and status reports. Returned records must cover their original IDs and match the collection fingerprint; missing work remains pending. These wire contracts and sampling details are proposals for team alignment, not a silently finalized Lane R protocol. |
| V44 | Draft Pilot B export | Propose `lesson_id`, `lesson_text`, `task_id`, `repository`, `source_revision`, `trajectory_pointer` for the six concepts in B ticket 01. Export original advice independently of A review outcomes; report missing/unsupported provenance as exclusions. Output remains explicitly draft, with review status in a sidecar and no assertion that B has accepted it or that a source SHA exists. B ticket 01 still owns final agreement and repository validation. |
| V45 | Handoff cleanup | At the user's request, remove generated build metadata, redundant rendered fixtures and obsolete action-review generation. Acquisition preparation now snapshots only; evaluation forms are an explicit separate command. Preserve original research inputs and prior review examples in an archive, keep historical decisions, and replace the hardcoded trajectory demo with an explicit-input CLI. Lane R's environment selection honors an override and reuses an existing local or original WSL venv. |
