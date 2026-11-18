# Handoff: do Lane R's trajectories work with Lane N's tools?

**Historical compatibility exercise:** completed on Lane R before this merge. The current user authorized processing the imported run on Lane N; use [MAIN3_HANDOFF.md](../MAIN3_HANDOFF.md) and [TASKS.md](../TASKS.md). The worktree-specific permissions and paths below describe that earlier exercise.

Written 2026-11-16 for a fresh Claude session. Self-contained: notes from earlier sessions are not available.

## Goal

Find out whether Lane N's tooling (branch `pilot-a/laneN`, commit `bcc2309`, by Johnny) accepts the 16 trajectories of Lane R's run `main-3` as they are, from loading through the handoff bundle, and list every place it does not. The outcome is a **compatibility report** the user can send to Johnny. You test and report; Johnny owns his code.

## Who you work for

Ocean, Lane R of Pilot A in the team repo `yotobias/MemRev` (public). Ocean wants to learn while the work is done: before each step say in a few plain sentences what happens and why; explain each new tool or concept once, briefly; after each step say what the output shows. Short, no lectures, no quizzes.

## Background you need

- Pilot A: one coding agent (mini-swe-agent 2.4.6, Claude Sonnet 5.5) attempted 16 SWE-bench bug-fix tasks; every step is recorded in a trajectory (`.traj.json`). Lane N turns trajectories into **lessons** (advice) with **assumptions** (checkable statements about the code); Lane R later runs **checks** of each assumption in three code states: C0 (the code at the task's commit), C1 (after the official fix), Ca (the agent's final workspace).
- **Lane N stays blind** to the official fixes and to whether the agent's patches are right, so its review cannot be biased. Never copy into the worktree, the report or any message: `pilot-a/env/gold_gate.jsonl`, `pilot-a/env/gold_gate_logs/` (incl. `recall_main-3.csv`), `pilot-a/data/*.parquet`. Everything in `pilot-a/runs/claude-sonnet-5-5/main-3/` is safe.
- Lane R's clone: `C:\Users\semap\Documents\Uni\MSc\MemRev` (WSL: `/mnt/c/Users/semap/Documents/Uni/MSc/MemRev`), branch `pilot-a/laneR`. Its status and decisions: `pilot-a/README.md`, `pilot-a/CHANGES.md` (newest last). Leave this checkout on its branch: work in a separate worktree.
- The run, per task: `pilot-a/runs/claude-sonnet-5-5/main-3/<id>/<id>.traj.json` and `final_workspace.json`; for the run: `preds.json` (submitted patches), `run_meta.json` (versions, images, hashes). Task metadata (repo, `base_commit`): `pilot-a/instances/main/instances.jsonl`.
- Known quirks of this run, so they are not mistaken for tool bugs: sympy-14774 has no reasoning recorded; in django-14792 the submitted patch is cut to 3 header lines and in django-16910 a test edit is missing from it (`final_workspace.json` holds the real final state); reasoning in 10 tasks recalls upstream fixes.

## Lane N's tools in one paragraph

Read `pilot-a/START_HERE.md` (runbook) and `pilot-a/HANDOFF.md` (interfaces) on the Lane N branch. The pipeline per task: `python -m memrev.trajectory` renders an extraction prompt from a trajectory; an LLM's JSON answer is saved by hand (no paid driver exists); `python -m memrev.provenance` validates trajectory + extraction + metadata into an *acquisition*; `python -m memrev.handoff build` combines acquisitions into a bundle with `lane-r/requests.json` and `lane-r/validity.pending.json` (what Lane R must answer) and a Pilot B draft. Metadata fields are validated in `src/memrev/provenance.py` (`_validate_metadata`).

## Rules

- **Ask the user first** before any paid model call, any commit or push, any change to Johnny's branch, and deleting anything. Patching Johnny's code locally to test a fix is fine; report the diff, do not commit it.
- Write outputs only under the worktree's `runs/compat/` (git-ignored there).
- Shell: run Docker-free Python work in WSL. From Git Bash: `MSYS_NO_PATHCONV=1 wsl -e bash -lc '...'`; PowerShell 5.1 strips inner quotes passed to `wsl`. A Windows `python - <<'EOF'` heredoc turns `\t`/`\n` inside string literals into real tabs and newlines: write files with the Write/Edit tools instead.

## Steps

### 1. Worktree and environment

```bash
cd /mnt/c/Users/semap/Documents/Uni/MSc/MemRev
git fetch origin
git worktree add ../MemRev-laneN origin/pilot-a/laneN   # detached checkout of Johnny's branch
cd ../MemRev-laneN
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/memrev-laneN"   # venv on the Linux side, not /mnt/c
export PATH="$HOME/.local/bin:$PATH" PYTHONPATH="$PWD/src"
uv sync --locked && uv run --locked python -m pytest -q
```

Done when the worktree is at `bcc2309`, `uv sync --locked` succeeded without regenerating `uv.lock`, and pytest has run, with every failure listed with its cause.

### 2. Johnny's offline demo

Run START_HERE step 2 as written. Done when `runs/handoffs/demo/report.md` shows 5 lessons, 17 assumptions, 51 pending validity cells and 17 pending sharing decisions (the expected result; all 5 lessons excluded from the B draft is also expected).

### 3. Render all 16 trajectories

For each of the 16 trajectories, `python -m memrev.trajectory --trajectory <path> --output runs/compat/prompts/<id>.txt`. Compare each rendered prompt with the trajectory against this table (counts from Lane R's own scan: assistant messages, tool calls, assistant messages with non-empty reasoning):

| Task | Steps | Commands | Steps with reasoning |
|---|---|---|---|
| django__django-11276 | 7 | 8 | 2 |
| django__django-11555 | 5 | 6 | 2 |
| django__django-12209 | 5 | 6 | 2 |
| django__django-12589 | 5 | 6 | 2 |
| django__django-14792 | 13 | 14 | 6 |
| django__django-15382 | 4 | 5 | 1 |
| django__django-15930 | 5 | 6 | 2 |
| django__django-16910 | 11 | 12 | 5 |
| scikit-learn__scikit-learn-10949 | 7 | 8 | 2 |
| scikit-learn__scikit-learn-25638 | 5 | 6 | 2 |
| sympy__sympy-14774 | 4 | 5 | 0 |
| sympy__sympy-14976 | 5 | 6 | 1 |
| sympy__sympy-15976 | 7 | 8 | 4 |
| sympy__sympy-16766 | 5 | 6 | 1 |
| sympy__sympy-18057 | 12 | 13 | 2 |
| sympy__sympy-20801 | 5 | 6 | 1 |

Done when all 16 render, and for every task the prompt contains every command, every command output and every reasoning summary of the trajectory (spot-read at least three prompts in full, one per repository). A count that differs from the table is a finding to explain (Lane R's count or Johnny's renderer), not automatically a bug. Also note the prompt sizes in tokens or characters: the longest task decides whether one extraction call fits.

### 4. Metadata from Lane R's run records

Write one metadata file per task under `runs/compat/metadata/`, filled from `run_meta.json` and `instances.jsonl`: `purpose` `pilot_a`, `agent_run_id` `main-3`, `task_id`, `repository` (`owner/repo`), `source_revision` = the task's `base_commit`; `extraction_run_id`, `extractor` and the prompt reference describe an extraction that has not happened yet. Done when the table of `_validate_metadata` fields is complete: for each field, where its value comes from in Lane R's records, or "missing" with what would supply it.

### 5. Provenance and handoff build: stop and ask

`memrev.provenance` needs a real extraction JSON. Ask the user whether to extract one short task for real (for example sympy-14976, about 6 steps; a single Sonnet call, cents) by submitting the rendered prompt and saving the answer as plain JSON. With approval: run `memrev.provenance` with `--prompt`, then `memrev.handoff build` on that acquisition, and read `lane-r/requests.json` and `lane-r/validity.pending.json`. Without approval: skip to step 6. Done when either the bundle is built and read, or the user declined.

### 6. Fit of the Lane R return contract

Compare HANDOFF.md's "Proposed Lane R return contract" (outcome, method, assessor, `workspace`, evidence, execution) with what Lane R can supply: C0 and C1 from the task image at `base_commit` (C1 = official fix applied), Ca from `final_workspace.json` (replay of the trajectory in a fresh container of the image in `run_meta.json`; `replay_files`, `untracked_after_replay`, `tracked_diff_same`). Done when every contract field is marked "Lane R can supply as is", "needs a new Lane R output" (say which) or "needs agreement with Johnny" (say the question).

### 7. Report

Write `runs/compat/REPORT.md`: what ran (commit, commands), per-step result, a numbered list of incompatibilities (each: what fails, the evidence, smallest fix, whose side), the step 4 and step 6 tables, and a short paste-ready message to Johnny. No gold material, no test names from the official fixes, nothing about whether agent patches are right. Done when every step above has a recorded result and each incompatibility has an owner. Then tell the user in plain words what works, what does not, and what to ask Johnny; offer to add a dated entry to `pilot-a/CHANGES.md` on the Lane R branch.
