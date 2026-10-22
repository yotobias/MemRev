# Pilot A: status page

Start here for Pilot A. This page says what the pilot is about, what has been done and what comes next. The detailed plan and the decision log are linked at the end.

## What Pilot A asks

Coding agents can save lessons from tasks they solved and reuse them later. Our project splits each lesson into *advice* and the concrete *claims* about the code that the advice relies on (for example "`get_user()` returns `None` for a missing id"), so that only affected claims need rechecking after the code changes (see the top-level `README.md`).

Pilot A is the first step. It asks: **when one fixed agent solves real bugs, do the lessons from its runs contain concrete, checkable claims about the repository, and do lessons from different tasks rely on the same claim?** It has no pass or fail threshold; a low count is a result. The project decides how to continue after Pilots A and B together.

## How it works

1. **Tasks.** 19 real bug-fix tasks from 5 Python repositories (scikit-learn, matplotlib, sympy, requests, django), taken from the SWE-ContextBench benchmark. Tasks are grouped in 5 clusters whose fixes touch the same file, so shared claims are *possible*; the review decides whether they exist. The list is frozen in `clusters.csv`.
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
| 2. Freeze the 19-task list, with checks against duplicates | R | done |
| 3. Download the task containers and record their fingerprints; repair 5 broken ones | R | done |
| 4. "Gold gate": does the official fix pass its own tests in each container? | R | done, all 19 pass |
| 5. Agent input file (problem statements only) | R | done |
| 6. Smoke test: one complete agent run on a non-pilot task | R | done (cost $0.0014) |
| 7. The 19 agent runs, then rebuild each final workspace | R | **next**; up to about $57 |
| 8. Probe runner for the validity labels | R | week 2 |
| Rubric, segmenter, extractor prompt, note review, grouping | N | not recorded here yet |

Cost so far: under $0.01 (smoke runs and test calls).

## Decisions so far (details and reasons in `CHANGES.md`)

- Agent and extractor model: Claude Sonnet 5.5, fixed for the whole project; Claude Haiku 5.5 for pipeline tests.
- The agent runs with its standard settings, unchanged (no temperature setting, which current Claude models reject).
- Five tasks run in locally repaired containers, because the published ones had their compiled code deleted.
- The smoke test used a task from outside the pilot (flask), so it cannot bias the review of any cluster.

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

The scripts that produce all of this are in `scripts/pilot_a/` (see its `README.md`).
