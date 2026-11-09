# Lane R handoff: what to do next

Updated 2026-11-09 (new task selection V33/V34) for a fresh session continuing Lane R (runs and environment) of Pilot A, working in a clone of the team repository `yotobias/MemRev`, branch `pilot-a/laneR`. This note is self-contained: notes from earlier sessions are not available in a new clone.

## Working style

The user (Ocean, Lane R) wants to learn while the work is done. Before each step, explain in a few plain sentences what happens and why the pilot needs it; explain each new tool or concept once, briefly; after each step, say what the output shows. No lectures, no quizzes. Ask before anything that costs money (agent runs) or is hard to undo (pushes to shared branches, deleting images).

## Read first

1. `pilot-a/README.md`: status page. Keep its progress table current.
2. `pilot-a/CHANGES.md`: every decision and deviation, newest last. Overrides the plans below where they differ.
3. `pilot-a/scripts/README.md`: what each script does and the conventions.
4. `pilot-a/plan/Kickoff.md` (the plan) and `pilot-a/plan/Plan_v2.md` (detailed reference, partly outdated) only as needed.
5. The team repo's `README.md` (workflow), `GLOSSARY.md` (use lesson / assumption / check, not note / claim / probe) and `docs/decisions.md`.

## The decisions that set the next steps (2026-11-09, team decisions V33, V34)

Every Pilot A task must form at least one valid **revision pair** for Pilot B: the base task at commit S and a SWE-ContextBench related task at commit T, with (1) the same repository, (2) S an ancestor of T (T is later), (3) T's environment reconstructable, (4) the files the base fix edits changed between S and T. SWE-ContextBench's "related" means related by topic, not later in time: only 116 of its 360 links point forward. SWE-bench Verified is no longer required (V33 supersedes V31). The agent runs on the base tasks only; related tasks are the targets for later pilots.

The selection (V34, supersedes V32): 16 base tasks in 5 clusters by package directory of the fix:

| Cluster | Tasks (instance number) |
|---|---|
| `django/db/models/` incl. `sql/` | django 11555, 12209, 12589, 15382, 15930, 16910 |
| `sympy/printing/` | sympy 14774, 14976, 15976, 16766 |
| `sympy/core/` | sympy 18057, 20801 |
| `sklearn/utils/` | scikit-learn 10949, 25638 |
| `django/utils/` | django 11276, 14792 |

The analysis is in `pilot-a/data/`: `v33_candidates.csv` (the 28 qualifying base tasks), `v33_forward_links.csv` (their 45 forward links with the requirement checks; requirement 3 is only "image exists" so far), `scb_link_directions.csv` (all 360 links). Six tasks carry over from the V32 list (11555, 12209, 15382, 15930, 14976, 16766); six are from SWE-bench outside Verified (12589, 16910, 14774, 18057, 10949, 25638).

## State

Done and reusable: WSL environment and locked packages (`pyproject.toml`, `uv.lock`), selection checks, fingerprinting, image repair (`build_derived.sh`), gold gate, instance builder, run script (optional 5th argument: settings file; `pilot-a/config/thinking_summarized.yaml` records the model's reasoning summaries). Smoke tests passed. Decided settings: backbone `claude-sonnet-5-5` (agent and extractor, pinned), `claude-haiku-5-5` for pipeline tests, mini-swe-agent 2.4.6 with its shipped config plus the thinking settings file, no temperature.

Runs so far (git-ignored, on this machine): `runs/claude-sonnet-5-5/main-1` and `main-2` on the V32 list (16/16 submitted each, $0.69 and $0.59). Kept as records. In 10 of those 16 tasks the model's reasoning recalls the official upstream fix (contamination, `CHANGES.md` 2026-10-24); raise with the team and report.

Correctness results of agent patches are Lane R only: `pilot-a/env/gold_gate_logs/agent/` (git-ignored, incl. `NOTES.md`). Never write which agent patch is right or wrong into shared files.

Superseded: the V32 list (`instances/main-v32/`; its `clusters.csv` is in git history), the Lite 19-task list (`instances/main-lite19/`).

## Setting up in a fresh clone

- Clone inside a path WSL can reach (`/mnt/c/...` works). All Docker and repository work runs in WSL (Ubuntu 24.04, Docker 29 there; Windows cannot check out django or matplotlib).
- `bash pilot-a/scripts/setup_wsl.sh` (uv 0.12.21, venv `~/.venvs/paper2027-pilot-a`, Docker check). Then `source pilot-a/scripts/env.sh` in each shell and use `uv run --locked`.
- Create `.env` in the repo root with `ANTHROPIC_API_KEY=...` (the user does this; never print or read the key).
- Download the SWE-ContextBench parquet files: `uv run --locked python -I pilot-a/scripts/data_prep/inspect_scb.py pilot-a/data`.
- If the old local folder is still around, `pilot-a/env/gold_gate.jsonl`, `gold_gate_logs/` and `runs/` exist only there (git-ignored); they are records of the old 19 tasks and are not needed for the new selection.

## Next steps

1. **Freeze the V34 list (step 2).** Done 2026-11-10 (`CHANGES.md`). Write the new `pilot-a/clusters.csv` (keep the column set; add each task's forward related task(s) as targets) with `build_clusters.py` adapted to V33/V34: the scripts read SWE-bench Verified today; 6 tasks are only in full SWE-bench (`SWE-bench/SWE-bench`, which also has `eval_script` and `image`; check). Keep the old instance set under a new name, as was done for `main-lite19`.
2. **Images and fingerprints (step 3)** for the 10 new base tasks (official `swebench/sweb.eval.x86_64.*` images), **and for the target images** of every task's forward related task(s) (`jiayuanz3/swecontextbench:<owner>.<repo>-<n>`). Requirement 3 means the target image *works*: fingerprint each (`import_ok`, `import_from_testbed`); the scikit-learn targets likely need `build_derived.sh`. A task whose targets all fail drops out; log it.
3. **Gold gate (step 4)** for the 10 new base tasks; switch the experience-task path to full SWE-bench where needed. Replace a task whose official fix fails, from the same cluster or the remaining 12 candidates, and log it.
4. **Instance file (step 5)**, same rules (no patch, test or test-name fields).
5. **Fix the parser bug** in `gold_gate.py` (`CHANGES.md` 2026-10-26; repro in `env/gold_gate_logs/agent/`): add a failing case to `test_gold_gate.py` first, then fix. Needed before any correctness check or probe.
6. **The run (step 7).** Ask the user before starting (cheap so far: about $0.04 per task). One new run of all 16 with the thinking settings file: `bash pilot-a/scripts/run_agent.sh main claude-sonnet-5-5 main-3 2 pilot-a/config/thinking_summarized.yaml` (check the exact arguments in the script). Then rebuild each final workspace (spec in `Plan_v2.md` Section 4) and agree with Johnny (Lane N) how he gets the git-ignored trajectories. Update the status page.
7. **Probe runner** (later): see `Plan_v2.md` Section 6; reuse `gold_gate.py`'s parser.
8. **Team:** raise the contamination finding; before a pull request, decide whether the Lane R code moves into `src/memrev`, whether to switch to Python 3.11, and align terms with `GLOSSARY.md`.

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
