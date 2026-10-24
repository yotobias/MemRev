# Lane R handoff: what to do next

Updated 2026-10-24 for a fresh session continuing Lane R (runs and environment) of Pilot A, working in a clone of the team repository `yotobias/MemRev`, branch `pilot-a/laneR`. This note is self-contained: notes from earlier sessions are not available in a new clone.

## Working style

The user (Ocean, Lane R) wants to learn while the work is done. Before each step, explain in a few plain sentences what happens and why the pilot needs it; explain each new tool or concept once, briefly; after each step, say what the output shows. No lectures, no quizzes. Ask before anything that costs money (agent runs) or is hard to undo (pushes to shared branches, deleting images).

## Read first

1. `pilot-a/README.md`: status page. Keep its progress table current.
2. `pilot-a/CHANGES.md`: every decision and deviation, newest last. Overrides the plans below where they differ.
3. `pilot-a/scripts/README.md`: what each script does and the conventions.
4. `pilot-a/plan/Kickoff.md` (the plan) and `pilot-a/plan/Plan_v2.md` (detailed reference, partly outdated) only as needed.
5. The team repo's `README.md` (workflow), `GLOSSARY.md` (use lesson / assumption / check, not note / claim / probe) and `docs/decisions.md`.

## The decision that sets the next steps (2026-10-24)

The user decided that **Pilot A runs on SWE-bench Verified tasks**: base tasks from the full SWE-ContextBench that are in SWE-bench Verified, in django, sympy or scikit-learn (team decisions V11, V12), and that have related tasks in SWE-ContextBench. The agent runs on the base tasks; the related tasks are not run in Pilot A but are kept as the base-to-related link for later pilots. (Confirm with the user that related tasks are not run before freezing.)

This replaces the earlier 19-task list from SWE-ContextBench *Lite* (built on SWE-bench Lite, not Verified; only `django__django-14017` qualifies under the new rule). Everything except the task list is reused.

Record it in the team's `docs/decisions.md` as the next V-number, and note that ADR 0001's premise ("SWE-ContextBench data not released") is outdated: the data is on Hugging Face (`jiayuanz3/SWEContextBench`, MIT), and its full experience set contains all 500 Verified tasks.

## State

Done and reusable: WSL environment and locked packages (`pyproject.toml`, `uv.lock`), selection checks, fingerprinting, image repair, gold gate, instance builder, run script. Smoke test passed (`pallets__flask-4992`, Claude Haiku 5.5, $0.0014). Decided settings: backbone `claude-sonnet-5-5` (agent and extractor, pinned), `claude-haiku-5-5` for pipeline tests, mini-swe-agent 2.4.6 with its shipped config, no `-c` option, no temperature.

Superseded: `pilot-a/clusters.csv`, `pilot-a/instances/main/`, the fingerprints and gold-gate results of the old 19 tasks, and their Docker images (about 50 GB in WSL; delete after the new list is frozen, ask first).

## Setting up in a fresh clone

- Clone inside a path WSL can reach (`/mnt/c/...` works). All Docker and repository work runs in WSL (Ubuntu 24.04, Docker 29 there; Windows cannot check out django or matplotlib).
- `bash pilot-a/scripts/setup_wsl.sh` (uv 0.12.21, venv `~/.venvs/paper2027-pilot-a`, Docker check). Then `source pilot-a/scripts/env.sh` in each shell and use `uv run --locked`.
- Create `.env` in the repo root with `ANTHROPIC_API_KEY=...` (the user does this; never print or read the key).
- Download the SWE-ContextBench parquet files: `uv run --locked python -I pilot-a/scripts/data_prep/inspect_scb.py pilot-a/data`.
- If the old local folder is still around, `pilot-a/env/gold_gate.jsonl`, `gold_gate_logs/` and `runs/` exist only there (git-ignored); they are records of the old 19 tasks and are not needed for the new selection.

## Next steps

1. **Re-select the tasks (new build step 2).** Candidates: 64 base tasks (django 41, sympy 17, scikit-learn 6) with 105 related tasks. Files edited by at least two candidate fixes (2026-10-24 count, test and doc files excluded):

   | Tasks | File |
   |---|---|
   | 4 | `django/db/models/expressions.py` |
   | 3 | `django/db/models/sql/compiler.py` |
   | 3 | `django/utils/html.py` |
   | 3 | `sympy/printing/pycode.py` |
   | 2 each | `django/db/migrations/loader.py`, `django/db/models/fields/__init__.py`, `django/db/models/base.py`, `django/db/backends/base/schema.py`, `django/core/servers/basehttp.py` |

   File-level clusters are small. Propose to the user how to reach 10 to 20 tasks (team decision V17), for example clusters at module level (`django/db/models/` incl. `sql/`), or widening to all Verified tasks in those files whether or not they have related tasks, and let the user decide. Keep the rules: clusters make shared assumptions possible, never pre-screened by looking at lessons; one task per PR; the list is frozen before any run. Adapt `pilot-a/scripts/build_clusters.py`: its `CLUSTERS` table and its file data (today from `pilot-a/data/lite_task_file_overlap.csv`, which covers SWE-ContextBench Lite only; take edited files from the Verified dataset's `patch` instead). Write the new `pilot-a/clusters.csv`.
2. **Images and fingerprints.** All base tasks use official SWE-bench images (`swebench/sweb.eval.x86_64.<id with __ replaced by _1776_>:latest`, also in the Verified dataset's `image` column). `pull_images.sh` then `fingerprint.sh`; check `import_ok`, `import_from_testbed`, `future_commits` in each `pilot-a/env/<id>.json`. The repaired "derived" images were only needed for SWE-ContextBench related-task images, so they should not be needed now.
3. **Gold gate.** `gold_gate.py` loads `SWE-bench/SWE-bench_Lite` and the SWE-ContextBench *Lite* parquet for experience tasks; switch both to `SWE-bench/SWE-bench_Verified` (it has `eval_script` for all 500 tasks) and the full experience parquet. Run it for all selected tasks; replace any task whose official fix fails, and log it.
4. **Instance file.** `build_instances.py` reads the Lite parquet files; switch to the Verified dataset. Same rule: no patch, test or test-name fields.
5. **The runs.** Ask the user before starting (up to $3 per task). `bash pilot-a/scripts/run_agent.sh main claude-sonnet-5-5 main-1 2` (fresh directory, never reuse one). Then rebuild each final workspace (spec in `Plan_v2.md` Section 4; the agent's patch is its own `git diff` of chosen files, so files it created are missing from it) and hand the trajectories to Lane N (Johnny). Update the status page.
6. **Probe runner** (later): see `Plan_v2.md` Section 6; reuse `gold_gate.py`'s parser (tested by `test_gold_gate.py`).
7. **Team alignment before a pull request:** record Pilot A's decisions as V-numbers; decide with the team whether the Lane R code moves into the shared `src/memrev` package and whether to switch from Python 3.12 to the team's 3.11; align document terms with `GLOSSARY.md`.

## Pitfalls already paid for

- From Git Bash: `MSYS_NO_PATHCONV=1 wsl -e bash -lc '...'`. PowerShell 5.1 strips inner quotes passed to `wsl`.
- `mini-extra swebench -c X` replaces the whole shipped config; pass the model with `-m`. Current Claude models reject `temperature`. litellm 1.106.2 needs `mcp` (already in the lockfile). Prompt caching happens without config.
- `--subset` needs a directory containing `instances.jsonl`; a run into an existing output directory skips finished tasks.
- swebench images have HEAD = `base_commit` + one mode-only "SWE-bench" commit: diff against `base_commit`, never HEAD. No image exposes later commits.
- SWE-bench django test names come in three formats (incl. docstring lines); sympy tests need `bin/test`, not pytest; the gold gate's parser handles all of them.
- Some test suites call live web services (requests' httpbin.org) and can fail for external reasons.
- Never edit a shell script while it runs (bash reads it as it goes). `docker commit` saves the container's command and `-e` variables into the image.
- Lane N (Johnny) stays blind to official fixes: `pilot-a/CHANGES.md` and other shared documents never name test names, test files or fix content; gold-gate results stay git-ignored. The team repo is public.
- Commit messages follow the team convention (`pilot-a laneR: <imperative>`); no pushes to `main`.
