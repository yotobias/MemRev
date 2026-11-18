# Pilot A: status and handoff

New contributors: [WORKFLOW_OVERVIEW.md](WORKFLOW_OVERVIEW.md) maps the existing files/formats and walks through one lesson from trajectory to research results.

Updated 2026-11-18. **Current objective: complete Pilot A before the final B handoff.** Start with [the completion checklist](COMPLETION_CHECKLIST.md) for required verification and research work. [The main-3 handoff](MAIN3_HANDOFF.md) describes the existing preliminary package; [START_HERE.md](START_HERE.md) covers the general workflow.

## Completion status

**Lane N has prepared a Pilot B input draft from all 16 imported main-3 trajectories, with LLM evaluations. Pilot A's validity/sharing study is not complete, and B has not yet accepted the interface or revision-pair policy.**

To regenerate extractions and reviews with separate API model contexts, follow [AUTOMATION.md](AUTOMATION.md). The resumable runner is implemented; model selection and a live smoke/full run remain pending.

| Area | Completed | Remaining |
|---|---|---|
| Lane R | Revised V47 selection; main-3 trajectories and replay reports imported; source instance-file hash matches | Scoped C0/C1/Ca check execution and evidence; replay verification on the check host |
| Lane N | Full-trajectory preparation, 16 acquisition packages, 16 AI reviews, 16 exported lessons with 32 assumptions; no missing selected tasks | Evidence-backed sharing analysis and final research report |
| Review policy | Supervisor-authorized LLM reviews; no mandatory human review (V48) | Keep AI attribution and independence honest; actual execution remains separate |
| Pilot B | Portable draft JSONL, provenance, reviews and limitations | Accept/test six-field import; reconcile V46's six non-Verified tasks and target environments with B's older rules |

The AI review marks **31 assumptions usable as extracted and 1 context-only**. These are extraction-quality judgments. **96 validity cells and 32 sharing rows remain pending.** Review and extraction used the same Codex session; exact serving model and usage/cost are unknown. One focused lesson per task was retained, so this is not an exhaustive extraction-yield estimate.

## What must happen next

1. Assign an execution owner and freeze the primary collection. Follow [COMPLETION_CHECKLIST.md](COMPLETION_CHECKLIST.md).
2. R authors and executes scoped checks using the frozen IDs and return contract, starting with a real C0/C1 smoke. The verification-command index removes any dependency on a phase segmenter.
3. N imports validity results, completes sharing and performs the planned regrouping consistency check.
4. Write the final findings report, including costs, exclusions, uncertainty and contamination. There is no minimum success threshold.
5. The current main-3 artifacts come with the Git checkout. Publish the final public package explicitly when complete; new output directories remain ignored by default. B confirms importer fields, source SHAs and selection/environment rules, including V46's non-Verified tasks.

Lane R reports upstream-fix recall in 10/16 tasks. Replay differs from patch-only reconstruction for django-14792 and django-16910. The imported JSON files describe prior replay results; they are not full workspace archives. See the handoff for these limitations.

## What Pilot A asks

Coding agents can save lessons from tasks they solved and reuse them later. Our project splits each lesson into *advice* and the concrete *claims* about the code that the advice relies on (for example "`get_user()` returns `None` for a missing id"), so that only affected claims need rechecking after the code changes (see the top-level `README.md`).

Pilot A is the first step. It asks: **when one fixed agent solves real bugs, do the lessons from its runs contain concrete, checkable claims about the repository, and do lessons from different tasks rely on the same claim?** It has no pass or fail threshold; a low count is a result. The project decides how to continue after Pilots A and B together.

## How it works

1. **Tasks.** 16 real bug-fix tasks from SWE-bench (django, sympy, scikit-learn), each linked by SWE-ContextBench to at least one *later* related task (a valid revision pair for Pilot B), grouped in 5 clusters by the package directory their fixes touch, so shared claims are *possible*; the review decides whether they exist (team decisions V46, V47). Frozen in `clusters.csv` (2026-11-10); earlier lists are superseded.
2. **Agent runs.** One AI coding agent (mini-swe-agent, model Claude Sonnet 5.5) attempts each task once, inside a Docker container that holds the repository at the commit where the bug existed. Every step it takes is recorded (the "trajectory").
3. **Lessons and assumptions.** An LLM reads the full indexed trajectory and extracts advice plus scoped assumptions with evidence pointers; an attributed LLM reviewer evaluates each assumption. The v2 extraction contract replaces mandatory per-phase extraction (V33–V35; `../specs/pilot-a-extraction/spec.md`).
4. **Validity.** For each claim: is it true in the original code, after the official fix, or only in the agent's own edits? Small test scripts ("probes") answer this where possible.
5. **Sharing.** Claims are grouped through attributed review (same repository, function, behaviour and conditions) to count how often different tasks rely on the same claim.
6. **Report.** Counts, examples, costs, exclusions.

## Who does what

The work is split into two lanes so that the people judging the notes never see the official fixes:

| Lane | Does | Person |
|---|---|---|
| **R** (runs and environment) | steps 1, 2 and 4: environment, agent runs, probes; the only lane that opens the official fixes | Ocean |
| **N** (notes and review) | steps 3 and 5: full-trajectory lesson extraction, review, check authoring and grouping | Johnny |

If you might ever review notes (Lane N), do not open `env/gold_gate.jsonl`, `env/gold_gate_logs/` or the files in `data/` that end in `.parquet`, and do not look up the tasks' pull requests or issues on GitHub (a task id such as `django__django-14016` is the PR number): all of these reveal the official fixes or their tests.

## Progress

The imported run is `runs/trajectories-pilot-A/main-3`. Prepared inputs, responses, acquisitions, evaluations and the handoff live under `runs/pilot-a/main-3/`. The earlier Astropy example remains development data. Lane R reports $0.66 for main-3; extraction/review cost for this assistant session is unknown.

## Decisions so far (details and reasons in `CHANGES.md`)

- Tasks come from SWE-bench (django, sympy, scikit-learn; Verified no longer required), each with at least one later related task in SWE-ContextBench that forms a valid revision pair, so Pilot B can use the lessons (V46, 2026-11-09). The agent runs only these base tasks; the related tasks are the later targets.
- 16 tasks in 5 clusters by package directory of the fix (`django/db/models/` incl. `sql/`, `django/utils/`, `sympy/printing/`, `sympy/core/`, `sklearn/utils/`): a task is in if its fix edits a file in a directory that another candidate's fix also edits (V47, 2026-11-09).
- Recorded agent model: Claude Sonnet 5.5; Claude Haiku 5.5 for earlier pipeline tests. This handoff uses Codex-session extraction/review under V49, a disclosed deviation from the pinned Sonnet extractor.
- main-3 uses the shipped agent configuration plus the recorded summarized-thinking configuration; see run_meta.json.
- All 16 tasks use the official SWE-bench containers. Three scikit-learn target containers (for later pilots) run in locally repaired copies, as in October.
- The smoke test used a task from outside the pilot (flask), so it cannot bias the review of any cluster.

## What Pilot B expects from Pilot A

From the team repository (`yotobias/MemRev`, decision V1): Pilot B reads lessons as a JSONL file, one lesson per line.

| Field | Meaning |
|-------|---------|
| lesson id | Unique id for the lesson |
| lesson text | The advice as the agent wrote it |
| task id | SWE-bench instance id the lesson came from |
| repository | e.g. `django/django` |
| source revision | Commit SHA the lesson was written at |
| trajectory pointer | Path or URL to the recorded trajectory (may be empty for fixtures) |

The producer proposes `lesson_id`, `lesson_text`, `task_id`, `repository`, `source_revision`, `trajectory_pointer`. Exact field-name acceptance and importer validation remain in Pilot B ticket 01. The team's decisions V11 and V12 ask for lessons from SWE-bench Verified Python instances in django, sympy or scikit-learn; V46 relaxes this for Pilot A: 10 of its 16 tasks are in Verified, 6 only in full SWE-bench (instance ids have the same form). B must explicitly reconcile this selection change with its older Verified-only specification.

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
