# Pilot A: status page

Start here for Pilot A. This page says what the pilot is about, what has been done and what comes next. The detailed plan and the decision log are linked at the end.

## What Pilot A asks

Coding agents can save lessons from tasks they solved and reuse them later. Our project splits each lesson into *advice* and the concrete *claims* about the code that the advice relies on (for example "`get_user()` returns `None` for a missing id"), so that only affected claims need rechecking after the code changes (see the top-level `README.md`).

Pilot A is the first step. It asks: **when one fixed agent solves real bugs, do the lessons from its runs contain concrete, checkable claims about the repository, and do lessons from different tasks rely on the same claim?** It has no pass or fail threshold; a low count is a result. The project decides how to continue after Pilots A and B together.

## How it works

1. **Tasks.** 10 to 20 real bug-fix tasks from SWE-bench Verified (django, sympy, scikit-learn) that SWE-ContextBench links to later related tasks, grouped in clusters whose fixes touch the same code, so shared claims are *possible*; the review decides whether they exist. The list is frozen in `clusters.csv` (being re-selected; the earlier 19-task list from SWE-ContextBench Lite is superseded).
2. **Agent runs.** One AI coding agent (mini-swe-agent, model Claude Sonnet 5.5) attempts each task once, inside a Docker container that holds the repository at the commit where the bug existed. Every step it takes is recorded (the "trajectory").
3. **Notes and claims.** Each trajectory is cut into phases; an LLM writes one note per phase (advice plus claims, each pointing to the step that shows it), and a person checks every claim.
4. **Validity.** For each claim: is it true in the original code, after the official fix, or only in the agent's own edits? Small test scripts ("probes") answer this where possible.
5. **Sharing.** Claims are grouped by hand (same repository, function, behaviour and conditions) to count how often different tasks rely on the same claim.
6. **Report.** Counts, examples, costs, exclusions.

## Who does what

The work is split into two lanes so that the people judging the notes never see the official fixes:

| Lane | Does | Person |
|---|---|---|
| **R** (runs and environment) | steps 1, 2 and 4: environment, agent runs, probes; the only lane that opens the official fixes | Ocean |
| **N** (notes and review) | steps 3 and 5: segmenting, note extraction, reviewing claims, grouping | Johnny |

If you might ever review notes (Lane N), do not open `env/gold_gate.jsonl`, `env/gold_gate_logs/` or the files in `data/` that end in `.parquet`, and do not look up the tasks' pull requests or issues on GitHub (a task id such as `django__django-14016` is the PR number): all of these reveal the official fixes or their tests.

## Progress (updated 2026-10-22)

| Step | Lane | Status |
|---|---|---|
| 1. Linux environment (WSL, Docker, Python packages locked) | R | done |
| 2. Freeze the task list, with checks against duplicates | R | **redo**: tasks now come from SWE-bench Verified (decision 2026-10-24, `CHANGES.md`) |
| 3. Download the task containers and record their fingerprints | R | redo for the new tasks |
| 4. "Gold gate": does the official fix pass its own tests in each container? | R | redo for the new tasks |
| 5. Agent input file (problem statements only) | R | redo for the new tasks |
| 6. Smoke test: one complete agent run on a non-pilot task | R | done (cost $0.0014) |
| 7. The agent runs, then rebuild each final workspace | R | after steps 2 to 5; up to $3 per task |
| 8. Probe runner for the validity labels | R | week 2 |
| Rubric, segmenter, extractor prompt, note review, grouping | N | not recorded here yet |

Cost so far: under $0.01 (smoke runs and test calls).

## Decisions so far (details and reasons in `CHANGES.md`)

- Tasks come from SWE-bench Verified (django, sympy, scikit-learn) with related tasks in SWE-ContextBench, so Pilot B can use the lessons (2026-10-24).
- Agent and extractor model: Claude Sonnet 5.5, fixed for the whole project; Claude Haiku 5.5 for pipeline tests.
- The agent runs with its standard settings, unchanged (no temperature setting, which current Claude models reject).
- Five tasks run in locally repaired containers, because the published ones had their compiled code deleted.
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

Extra fields are ignored by Pilot B. The exact field names are fixed in Pilot B ticket 01; check there before producing output. The team's decisions V11 and V12 ask for lessons from SWE-bench Verified Python instances in django, sympy or scikit-learn; Pilot A's tasks are being re-selected to meet it (decision 2026-10-24 in `CHANGES.md`).

The open decisions the team listed for Pilot A (agent and model, runs per task, lesson granularity, lessons from failed attempts, source validity, sharing review) were taken for Lane R in `plan/Kickoff.md` and `CHANGES.md`; they still need to be recorded as numbered decisions in the team's `docs/decisions.md`.

## What is where

| Path | Contents | Safe for Lane N |
|---|---|---|
| `plan/Kickoff.md` | the plan: pipeline, task list, lanes, timeline, pitfalls | yes |
| `plan/Plan_v2.md` | detailed reference plan (partly outdated; the Kickoff says where) | yes |
| `plan/LaneR_Handoff.md` | where Lane R implementation continues | yes |
| `CHANGES.md` | every decision and deviation, with date and reason | yes |
| `clusters.csv` | the frozen 19-task list | yes |
| `instances/` | what the agent is given (problem statements only) | yes |
| `runs/` | agent trajectories and patches | yes |
| `env/*.json` | container fingerprints | yes |
| `env/gold_gate*` | results of the official-fix check | **no** |
| `data/` | benchmark data; the `.parquet` files contain the official fixes | **no** (`.parquet`) |
| `scripts/` | the Lane R pipeline code and its tests | yes |

The scripts that produce all of this are in `scripts/` (see its `README.md`). Paths on this page are relative to `pilot-a/`.
