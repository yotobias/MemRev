# Lane R handoff: what to do next

Updated 2026-10-24 (after the re-selection) for a fresh session continuing Lane R (runs and environment) of Pilot A, working in a clone of the team repository `yotobias/MemRev`, branch `pilot-a/laneR`. This note is self-contained: notes from earlier sessions are not available in a new clone.

**2026-10-25 addendum:** read [RUN_READINESS.md](../RUN_READINESS.md) before launching on the merged checkout. Local prerequisites differ from the original WSL machine. Capture the actual final workspace before cleanup; applying only the submitted patch afterward cannot recover omitted files. `env.sh` now honors an override and reuses an existing local or original WSL environment. The current Lane N contract is in [HANDOFF.md](../HANDOFF.md).

## Working style

The user (Ocean, Lane R) wants to learn while the work is done. Before each step, explain in a few plain sentences what happens and why the pilot needs it; explain each new tool or concept once, briefly; after each step, say what the output shows. No lectures, no quizzes. Ask before anything that costs money (agent runs) or is hard to undo (pushes to shared branches, deleting images).

## Read first

1. `pilot-a/README.md`: status page. Keep its progress table current.
2. `pilot-a/CHANGES.md`: every decision and deviation, newest last. Overrides the plans below where they differ.
3. `pilot-a/scripts/README.md`: what each script does and the conventions.
4. `pilot-a/plan/Kickoff.md` (the plan) and `pilot-a/plan/Plan_v2.md` (detailed reference, partly outdated) only as needed.
5. The team repo's `README.md` (workflow), `GLOSSARY.md` (use lesson / assumption / check, not note / claim / probe) and `docs/decisions.md`.

## The decision that sets the next steps (2026-10-24)

The user decided that **Pilot A runs on SWE-bench Verified tasks**: base tasks from the full SWE-ContextBench that are in SWE-bench Verified, in django, sympy or scikit-learn (team decisions V11, V12), and that have related tasks in SWE-ContextBench. The agent runs on the base tasks; related tasks remain links for later pilots. This was confirmed before the 16-task list was frozen; do not request confirmation again.

This replaces the earlier 19-task list from SWE-ContextBench *Lite* (built on SWE-bench Lite, not Verified; only `django__django-14017` qualifies under the new rule). Everything except the task list is reused.

Record it in the team's `docs/decisions.md` as the next V-number, and note that ADR 0001's premise ("SWE-ContextBench data not released") is outdated: the data is on Hugging Face (`jiayuanz3/SWEContextBench`, MIT), and its full experience set contains all 500 Verified tasks.

## State

Done and reusable: WSL environment and locked packages (`pyproject.toml`, `uv.lock`), selection checks, fingerprinting, image repair, gold gate, instance builder, run script. Smoke test passed (`pallets__flask-4992`, Claude Haiku 5.5, $0.0014). Decided settings: backbone `claude-sonnet-5-5` (agent and extractor, pinned), `claude-haiku-5-5` for pipeline tests, mini-swe-agent 2.4.6 with its shipped config, no `-c` option, no temperature.

Superseded: the old 19-task list (now `instances/main-lite19/`; the old `clusters.csv` is in git history before commit 1e2be93), the fingerprints and gold-gate results of the old 19 tasks; their Docker images were deleted on 2026-10-24.

## Setting up in a fresh clone

- Clone inside a path WSL can reach (`/mnt/c/...` works). All Docker and repository work runs in WSL (Ubuntu 24.04, Docker 29 there; Windows cannot check out django or matplotlib).
- `bash pilot-a/scripts/setup_wsl.sh` (uv 0.12.21, venv `~/.venvs/paper2027-pilot-a`, Docker check). Then `source pilot-a/scripts/env.sh` in each shell and use `uv run --locked`.
- Create `.env` in the repo root with `ANTHROPIC_API_KEY=...` (the user does this; never print or read the key).
- Download the SWE-ContextBench parquet files: `uv run --locked python -I pilot-a/scripts/data_prep/inspect_scb.py pilot-a/data`.
- If the old local folder is still around, `pilot-a/env/gold_gate.jsonl`, `gold_gate_logs/` and `runs/` exist only there (git-ignored); they are records of the old 19 tasks and are not needed for the new selection.

## Next steps

1. **Done 2026-10-24: steps 2 to 5 for the new list.** 16 tasks in 5 clusters (`clusters.csv`; rule and options in `CHANGES.md`; team decisions V31, V32); all images fingerprinted clean; gold gate passes for all 16; `instances/main/` rebuilt (the old one is `instances/main-lite19/`). The scripts now read SWE-bench Verified and the full SWE-ContextBench files. Related tasks are not run (confirmed by the user). The superseded images were deleted the same day.
2. **The runs.** Ask the user before starting (up to $3 per task, so up to $48 for the 16). `bash pilot-a/scripts/run_agent.sh main claude-sonnet-5-5 main-1 2` (fresh directory, never reuse one). Then rebuild each final workspace (spec in `Plan_v2.md` Section 4; the agent's patch is its own `git diff` of chosen files, so files it created are missing from it) and hand the trajectories to Lane N (Johnny). Update the status page.
3. **Probe runner** (later): see `Plan_v2.md` Section 6; reuse `gold_gate.py`'s parser (tested by `test_gold_gate.py`).
4. **Team alignment before a pull request:** record Pilot A's decisions as V-numbers; decide with the team whether the Lane R code moves into the shared `src/memrev` package and whether to switch from Python 3.12 to the team's 3.11; align document terms with `GLOSSARY.md`.

## Pitfalls already paid for

- From Git Bash: `MSYS_NO_PATHCONV=1 wsl -e bash -lc '...'`. PowerShell 5.1 strips inner quotes passed to `wsl`.
- A clone used by both Windows git and WSL git needs `git config core.autocrlf false` and `git config core.eol lf` (then `git rm -rq --cached . && git reset -q --hard`); otherwise WSL git sees every file as changed and could commit Windows line endings. Done in the user's clone `Documents/Uni/MSc/MemRev`.
- `mini-extra swebench -c X` replaces the whole shipped config; pass the model with `-m`. Current Claude models reject `temperature`. litellm 1.106.2 needs `mcp` (already in the lockfile). Prompt caching happens without config.
- `--subset` needs a directory containing `instances.jsonl`; a run into an existing output directory skips finished tasks.
- swebench images have HEAD = `base_commit` + one mode-only "SWE-bench" commit: diff against `base_commit`, never HEAD. No image exposes later commits.
- SWE-bench django test names come in three formats (incl. docstring lines); sympy tests need `bin/test`, not pytest; the gold gate's parser handles all of them.
- Some test suites call live web services (requests' httpbin.org) and can fail for external reasons.
- Never edit a shell script while it runs (bash reads it as it goes). `docker commit` saves the container's command and `-e` variables into the image.
- Lane N (Johnny) stays blind to official fixes: `pilot-a/CHANGES.md` and other shared documents never name test names, test files or fix content; gold-gate results stay git-ignored. The team repo is public.
- Commit messages follow the team convention (`pilot-a laneR: <imperative>`); no pushes to `main`.
