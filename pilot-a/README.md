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

1. **Tasks.** 16 real bug-fix tasks from SWE-bench (django, sympy, scikit-learn), each linked by SWE-ContextBench to at least one *later* related task (a valid revision pair for Pilot B), grouped in 5 clusters by the package directory their fixes touch, so shared claims are *possible*; the review decides whether they exist (team decisions V46, V47). Frozen in `clusters.csv` (2026-11-10); earlier lists are superseded.
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

## Progress (updated 2026-11-10)

| Step | Lane | Status |
|---|---|---|
| 1. Linux environment (WSL, Docker, Python packages locked) | R | done |
| 2. Freeze the task list, with checks against duplicates | R | done: 16 tasks, 5 clusters, 25 forward targets (V46, V47; `CHANGES.md` 2026-11-10); 6 tasks carry over from the old list |
| 3. Download the task containers and record their fingerprints | R | done: 16 base images and 25 target images all usable; 3 scikit-learn targets after the local repair (`CHANGES.md` 2026-11-10) |
| 4. "Gold gate": does the official fix pass its own tests in each container? | R | done: all 16 pass, none replaced; two parser gaps and a missing locale setting fixed on the way |
| 5. Agent input file (problem statements only) | R | done: `instances/main/` (16 tasks) |
| 6. Smoke test: one complete agent run on a non-pilot task | R | done (cost $0.0014) |
| 7. The agent runs, then rebuild each final workspace | R | run `main-3` done 2026-11-10: 16/16 submitted, $0.66, reasoning recorded in 15 of 16; final workspaces rebuilt by replay (2 tasks' submissions miss part of the agent's edits, `CHANGES.md`); handover to Lane N open. Earlier runs `main-1`, `main-2` (old list) kept as records; the model recalls upstream fixes in 10 of those 16 tasks (`CHANGES.md`) |
| 8. Probe runner for the validity labels | R | week 2 |
| Rubric, segmenter, extractor prompt, note review, grouping | N | not recorded here yet |

Cost so far: about $1.98 (smoke runs and test calls, main-1 $0.69, thinking smoke test $0.03, main-2 $0.59, main-3 $0.66).

## Decisions so far (details and reasons in `CHANGES.md`)

- Tasks come from SWE-bench (django, sympy, scikit-learn; Verified no longer required), each with at least one later related task in SWE-ContextBench that forms a valid revision pair, so Pilot B can use the lessons (V46, 2026-11-09). The agent runs only these base tasks; the related tasks are the later targets.
- 16 tasks in 5 clusters by package directory of the fix (`django/db/models/` incl. `sql/`, `django/utils/`, `sympy/printing/`, `sympy/core/`, `sklearn/utils/`): a task is in if its fix edits a file in a directory that another candidate's fix also edits (V47, 2026-11-09).
- Agent and extractor model: Claude Sonnet 5.5, fixed for the whole project; Claude Haiku 5.5 for pipeline tests.
- The agent runs with its standard settings, unchanged (no temperature setting, which current Claude models reject).
- All 16 tasks use the official SWE-bench containers. Three scikit-learn target containers (for later pilots) run in locally repaired copies, as in October.
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

Extra fields are ignored by Pilot B. The exact field names are fixed in Pilot B ticket 01; check there before producing output. The team's decisions V11 and V12 ask for lessons from SWE-bench Verified Python instances in django, sympy or scikit-learn; V46 relaxes this for Pilot A: 10 of its 16 tasks are in Verified, 6 only in full SWE-bench (instance ids have the same form). Pilot B ticket 01 should accept full SWE-bench ids.

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
