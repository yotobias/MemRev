# Pilot A: status page

Start here for Pilot A. This page says what the pilot is about, what has been done and what comes next. The detailed plan and the decision log are linked at the end.

For handoff, use [START_HERE.md](START_HERE.md). Before starting paid runs, read [RUN_READINESS.md](RUN_READINESS.md): historical setup results do not imply local Docker/image/API access, and final-workspace capture still needs implementation.

## Completion status

**Pilot A is not complete. Lane N is not complete.** Lane N's current offline implementation slice is implemented and tested; production integration and research work remain.

| Area | Ready now | Still required |
|---|---|---|
| Lane N software | Full-trajectory formatting, extraction validation, provenance/IDs, evaluation forms/import, validity-return validation, sharing/regrouping tools, draft B export and status reports; 150 tests passed | Agree the proposed contracts and exercise them with real Lane R/B inputs. Adapt as needed. Paid extraction automation is optional; saved manual responses already work. |
| Lane N research | Development example and pending forms; an explicitly AI-attributed review example | Extract selected-task lessons, perform human evaluations, author scoped checks where needed, decide sharing groups, interpret results and write the N report sections. |
| Lane R | Frozen selection, sanitized inputs, fingerprints, preparation scripts and basic trajectory launcher | Resolve run-host prerequisites, preserve final workspaces, generate selected-task trajectories and implement actual validity-check execution. |
| Pilot B handoff | Proposed six-field JSONL exporter with exclusions and provenance pointers | Agree final keys/policy, test B's importer against the export and supply real lessons with sufficient provenance. B performs its own assumption review/checks. |

The current demonstration contains **5 lessons and 17 assumptions from development data**. The all-pending bundle has 51 pending validity cells and 17 pending sharing rows. Its five lessons are excluded from the B draft for missing provenance. These are not Pilot A production findings or source-validity results.

## What must happen next

| Order | Owner | Work |
|---|---|---|
| 1 | Team | Agree the extraction rubric/repair policy, Lane R return schema and workspace identifiers, sharing rules/sample seed, and Pilot B field names. Human trajectory review is not needed for this discussion. |
| 2 | R | Confirm Docker/images, credentials/model access, locked tooling and budget on the actual run host. |
| 3 | R | Implement and test capture of the full final workspace before container cleanup; submitted patches omit relevant files. |
| 4 | R + N | Exercise one selected task end to end: generate a trajectory, preserve its workspace, extract lessons and create a complete acquisition package. Then process the remaining selected tasks. |
| 5 | N | Review extracted advice/assumptions and prepare scoped checks without viewing gold material. This work may be deferred while engineering continues. |
| 6 | R + N | R executes checks at C0/C1/Ca and retains evidence; N supplies checks and permitted manual assessments. Import results using the agreed contract. The runner can be developed alongside extraction. |
| 7 | N + R | N groups equivalent scoped assumptions with reasons; R regroups the 30% sample without seeing N's partition and discloses gold exposure. Report disagreements. |
| 8 | Team | Produce counts, examples, exclusions, uncertainty and actual costs; finalize the A report and the agreed B export. Pilot A has no pass/fail threshold gating B. |

Before distributing the implementation, review/commit the local changes through the repository's PR workflow. Generated `runs/` artifacts are gitignored and must be transferred separately or regenerated from the runbook.

## Meeting summary

> Lane N now has a working offline pipeline from recorded trajectories and saved extractions to traceable acquisitions, review forms, Lane R requests, sharing analysis and a draft Pilot B export. The current implementation passed 150 tests, and the repository has a command-by-command runbook. We can demonstrate the interfaces without asking anyone to review trajectories yet. Lane N and Pilot A remain unfinished: we still need contract agreement, real selected-task trajectories with preserved workspaces, actual reviews/checks/grouping and the final report. Teammates should expect runnable tools and proposed interfaces, not a validated production lesson bank.

## What Pilot A asks

Coding agents can save lessons from tasks they solved and reuse them later. Our project splits each lesson into *advice* and the concrete *claims* about the code that the advice relies on (for example "`get_user()` returns `None` for a missing id"), so that only affected claims need rechecking after the code changes (see the top-level `README.md`).

Pilot A is the first step. It asks: **when one fixed agent solves real bugs, do the lessons from its runs contain concrete, checkable claims about the repository, and do lessons from different tasks rely on the same claim?** It has no pass or fail threshold; a low count is a result. The project decides how to continue after Pilots A and B together.

## How it works

1. **Tasks.** 10 to 20 real bug-fix tasks from SWE-bench Verified (django, sympy, scikit-learn) that SWE-ContextBench links to later related tasks, grouped in clusters whose fixes touch the same code, so shared claims are *possible*; the review decides whether they exist. The list is frozen in `clusters.csv`: 16 tasks in 5 clusters, four in django's `db/models` and one in sympy's code printers (the earlier 19-task list from SWE-ContextBench Lite is superseded).
2. **Agent runs.** One AI coding agent (mini-swe-agent, model Claude Sonnet 5.5) attempts each task once, inside a Docker container that holds the repository at the commit where the bug existed. Every step it takes is recorded (the "trajectory").
3. **Lessons and assumptions.** An LLM reads the full indexed trajectory and extracts advice plus scoped assumptions with evidence pointers; a person reviews each assumption. The v2 extraction contract replaces mandatory per-phase extraction (V33–V35; `../specs/pilot-a-extraction/spec.md`).
4. **Validity.** For each claim: is it true in the original code, after the official fix, or only in the agent's own edits? Small test scripts ("probes") answer this where possible.
5. **Sharing.** Claims are grouped by hand (same repository, function, behaviour and conditions) to count how often different tasks rely on the same claim.
6. **Report.** Counts, examples, costs, exclusions.

## Who does what

The work is split into two lanes so that the people judging the notes never see the official fixes:

| Lane | Does | Person |
|---|---|---|
| **R** (runs and environment) | steps 1, 2 and 4: environment, agent runs, probes; the only lane that opens the official fixes | Ocean |
| **N** (notes and review) | steps 3 and 5: full-trajectory lesson extraction, review, check authoring and grouping | Johnny |

If you might ever review notes (Lane N), do not open `env/gold_gate.jsonl`, `env/gold_gate_logs/` or the files in `data/` that end in `.parquet`, and do not look up the tasks' pull requests or issues on GitHub (a task id such as `django__django-14016` is the PR number): all of these reveal the official fixes or their tests.

## Progress (updated 2026-10-25)

| Step | Lane | Status |
|---|---|---|
| 1. Linux environment (WSL, Docker, Python packages locked) | R | completed on original R host; current run-host prerequisites need confirmation |
| 2. Freeze the task list, with checks against duplicates | R | done: 16 tasks from SWE-bench Verified in 5 clusters (team decisions V31, V32; `CHANGES.md` 2026-10-24) |
| 3. Download the task containers and record their fingerprints | R | original R handoff reports all 16 clean; fingerprint files are present, local image availability unverified |
| 4. "Gold gate": does the official fix pass its own tests in each container? | R | original R handoff reports all 16 pass; not rerun in this audit |
| 5. Agent input file (problem statements only) | R | done: `instances/main/` (16 tasks) |
| 6. Smoke test: one complete agent run on a non-pilot task | R | original R handoff reports success (cost $0.0014) |
| 7. Agent runs and final-workspace preservation | R | launcher exists; no selected-task runs here. Resolve local prerequisites and implement capture before container cleanup; see [RUN_READINESS.md](RUN_READINESS.md) |
| 8. Check runner for validity labels | R | not implemented here; Lane N validates return records only |
| Extraction and review | N | formatter, v2 validation, provenance and evaluation import implemented. Offline collection, Lane R forms, validity-return validation, sharing import/regrouping and draft B export now run with human work pending; see [HANDOFF.md](HANDOFF.md). Real selected-task extraction, review, checks and grouping remain pending. |

Original R handoff reports under $0.01 for smoke runs and test calls. The Lane N offline implementation work started no paid model calls or benchmark runs.

## Decisions so far (details and reasons in `CHANGES.md`)

- Tasks come from SWE-bench Verified (django, sympy, scikit-learn) with related tasks in SWE-ContextBench, so Pilot B can use the lessons (2026-10-24). The agent runs only these base tasks; related tasks are kept as links.
- 16 tasks in 5 clusters in `django/db/models/` and `sympy/printing/`: a task is in if its fix shares a file or sub-package with another candidate (2026-10-24).
- Agent and extractor model: Claude Sonnet 5.5, fixed for the whole project; Claude Haiku 5.5 for pipeline tests.
- The agent runs with its standard settings, unchanged (no temperature setting, which current Claude models reject).
- All 16 tasks use the official SWE-bench containers; the locally repaired containers were only needed for the superseded list.
- The smoke test used a task from outside the pilot (flask), so it cannot bias the review of any cluster.

## What Pilot B expects from Pilot A

From the team repository (`yotobias/MemRev`, decision V1): Pilot B reads lessons as a JSONL file, one lesson per line.

| Field | Meaning |
|-------|---------|
| lesson id | Unique id for the lesson |
| lesson text | The advice as the agent wrote it |
| task id | SWE-bench Verified instance id the lesson came from |
| repository | e.g. `django/django` |
| source revision | Commit SHA the lesson was written at |
| trajectory pointer | Path or URL to the recorded trajectory (may be empty for fixtures) |

Extra fields are ignored by Pilot B. Its ticket 01 requires the exact field names to be fixed, but currently specifies only the six concepts above; agree and document the names before producing the export. Pilot A's versioned raw extraction JSON and provenance package are separate formats, not this JSONL bank. `memrev.provenance` attaches occurrence IDs and operator-supplied provenance without inventing unknown metadata; see [PROVENANCE.md](PROVENANCE.md). The team's decisions V11 and V12 ask for lessons from SWE-bench Verified Python instances in django, sympy or scikit-learn; Pilot A's 16 tasks meet it (V31, V32).

For interface discussion, `memrev.handoff` now produces an explicitly **draft** JSONL with proposed keys `lesson_id`, `lesson_text`, `task_id`, `repository`, `source_revision`, `trajectory_pointer` (V44). Original advice is exported independently of A review outcomes; missing required metadata produces recorded exclusions. The accompanying status file retains review attribution. This proposal does not complete B ticket 01 or certify source SHA existence. See [HANDOFF.md](HANDOFF.md) for commands, portability and the design decisions still pending.

The open decisions the team listed for Pilot A (agent and model, runs per task, lesson granularity, lessons from failed attempts, source validity, sharing review) were taken for Lane R in `plan/Kickoff.md` and `CHANGES.md`; they still need to be recorded as numbered decisions in the team's `docs/decisions.md`.

## What is where

| Path | Contents | Safe for Lane N |
|---|---|---|
| `plan/Kickoff.md` | the plan: pipeline, task list, lanes, timeline, pitfalls | yes |
| `plan/Plan_v2.md` | detailed reference plan (partly outdated; the Kickoff says where) | yes |
| `plan/LaneR_Handoff.md` | where Lane R implementation continues | yes |
| `CHANGES.md` | every decision and deviation, with date and reason | yes |
| `clusters.csv` | the frozen 16-task list (related tasks as links, not run) | yes |
| `instances/` | what the agent is given (problem statements only) | yes |
| `runs/` | agent trajectories and patches | yes |
| `env/*.json` | container fingerprints | yes |
| `env/gold_gate*` | results of the official-fix check | **no** |
| `data/` | benchmark data; the `.parquet` files contain the official fixes | **no** (`.parquet`) |
| `scripts/` | the Lane R pipeline code and its tests | yes |

The scripts that produce all of this are in `scripts/` (see its `README.md`). Paths on this page are relative to `pilot-a/`.
