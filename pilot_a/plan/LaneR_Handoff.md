# Lane R handoff: where to continue

Updated 2026-10-22 for a fresh session that continues Lane R (runs and environment) of Pilot A. Build-order steps 1 to 6 are done and audited; the next step is 7, the 19 agent runs. Read `pilot_a/plan/Kickoff.md` first if you have not.

## Read in this order

1. `pilot_a/plan/Kickoff.md`, Sections 3 to 7 and 10.
2. This note.
3. `pilot_a/CHANGES.md`: every decision and deviation so far. It overrides `pilot_a/plan/Plan_v2.md` and earlier versions of this note where they differ.
4. `scripts/pilot_a/README.md`: what each script does, in order, and the conventions.
5. Reference only: `pilot_a/plan/Plan_v2.md` Section 4 (final workspace, fingerprint), Section 6 (probe command, validity table), Section 11 (storage layout).
6. The auto-memory files, especially `pilot-a-lane-r-env-findings-2026-10-22.md` and `pilot-a-plan-audit-2026-10-19.md`.

Lane R never shows gold patches, test patches, test names or gate logs to Lane N, and never reads the public SCB transcripts.

## Decisions already taken (do not reopen without the user)

- Backbone, pinned for the project: `claude-sonnet-5-5` (agent and extractor). Pipeline tests use `claude-haiku-5-5`.
- No temperature (current Claude models reject it) and no `-c` option (`mini-extra` replaces the shipped config when `-c` is given). Prompt caching stays as shipped; it happens without `set_cache_control`.
- Five related tasks run on local derived images `pilot-a/<owner>.<repo>-<n>:built` (sklearn 12622, 15093, 25637; matplotlib 22482, 22686), because the shipped images lost their compiled builds. `instances/main` already points to them.
- Smoke task: `pallets__flask-4992` (not a pilot task, not a pilot repository).

## State on 2026-10-22

Done:
- Step 1: WSL has 24 GB; venv `~/.venvs/paper2027-pilot-a` from `uv.lock` (mini-swe-agent 2.4.6, litellm 1.106.2, plus `mcp`, which litellm needs but does not declare).
- Step 2: `pilot_a/clusters.csv`, 19 tasks, all selection rules checked by `build_clusters.py`.
- Step 3: all 19 images pulled (51.6 GB) plus the 5 derived ones; fingerprints in `pilot_a/env/<id>.json`. No image exposes commits after `base_commit`.
- Step 4: gold gate passes for all 19 + smoke (`pilot_a/env/gold_gate.jsonl`, latest line per task).
- Step 5: `pilot_a/instances/main/instances.jsonl` (19) and `pilot_a/instances/smoke/` (flask-4992), without patch, test or test-name fields.
- Step 6: smoke run `pilot_a/runs/claude-haiku-5-5/smoke-2`: Submitted in 4 calls, $0.0014. (`smoke-1` failed on the missing `mcp` package, cost $0, kept as a record.)
- A ponytail audit of `scripts/pilot_a/` found 9 issues; all fixed and verified (see `pilot_a/CHANGES.md`). Parser test: `scripts/pilot_a/test_gold_gate.py`.

On this machine only (a second Lane R machine must recreate them): the derived images (`build_derived.sh`), the downloaded parquet files (`scripts/data_prep/inspect_scb.py`), the venv (`setup_wsl.sh`), and `.env` with the user's `ANTHROPIC_API_KEY` (created by the user; never print, read or echo it).

## Next steps

**On hold (2026-10-22):** the team repository `yotobias/MemRev` decided (its V11, V12, ADR 0001) that lessons come from SWE-bench Verified django/sympy/scikit-learn tasks, so that Pilot B can use them; only 1 of our 19 SWE-ContextBench tasks is in Verified. Do not start step 7 until the team has decided the task source (see `pilot_a/CHANGES.md`). Lane R's work is on branch `pilot-a/laneR` of that repository.

7. **The 19 runs.** Confirm with the user before starting (up to about $57, 1 to 3 hours, unattended), then run it in the background:
   `bash scripts/pilot_a/run_agent.sh main claude-sonnet-5-5 main-1 2`
   Afterwards: read `exit_statuses_*.yaml` and the cost per task from each trajectory's `info.model_stats`. Empty submissions and `LimitsExceeded` are results, not failures. A run killed by the 2 h container limit or by an infrastructure error is rerun once, into a new directory (`main-1-rerun`, with `--filter <instance_id>` added to the `mini-extra` call); never `--redo-existing`, never reuse a directory. Log every rerun in `CHANGES.md`.
   Then rebuild each final workspace into `pilot_a/workspaces/<run_id>/` (script not written yet; spec in v2 Section 4): fresh container from the instance's `image_name`, `git apply` the `model_patch` from `preds.json`, record `git diff --stat <base_commit>` (never HEAD), and re-run the agent's last test command. Note: the agent writes its own submission with `git diff -- <files> > patch.txt`, so files it created (reproduction scripts, new source files) are not in `model_patch`; list them from the trajectory, since they decide whether Ca is defined. "Last test command" means the last action the segmenter classifies as verify; until Lane N's segmenter exists, take the last `pytest` / `runtests.py` / `bin/test` command and say so.
   Hand the trajectories (`pilot_a/runs/claude-sonnet-5-5/main-1/<id>/<id>.traj.json`) to Lane N. Safe for them: trajectories, `preds.json`, `pilot_a/instances/`, fingerprints. Not safe: `pilot_a/env/gold_gate*`, the parquet files. Then tick step 7 in the progress table of `pilot_a/README.md`.
8. **Probe runner** (week 2): one container run per (claim, revision) with the command in v2 Section 6, 600 s timeout, setup errors recorded apart from assertion failures, results appended to `pilot_a/validity.jsonl`. C1 applies the gold `patch` only. Reuse `gold_gate.py`'s `parse` and `lookup` (covered by `test_gold_gate.py`) for test output. For the five derived-image tasks, probe on the derived image.

## Pitfalls found so far (details in the memory file)

- Run Docker and repositories inside WSL. From the Bash tool use `MSYS_NO_PATHCONV=1 wsl -e bash -lc '...'`; PowerShell 5.1 strips inner quotes passed to `wsl`.
- Use `uv run --locked`; re-locking is a deliberate, logged step.
- Never edit a shell script while it runs (bash reads it as it goes; this garbled one image build).
- `docker commit` stores the container's command and `-e` variables in the new image; `build_derived.sh` handles this.
- sympy 1.5 tests cannot run under the images' pytest; use `bin/test`. Django test ids come in three formats; the gold gate's parser handles all of them.
- requests-2148's tests call the live httpbin.org and can fail for external reasons; the agent may meet the same.
- `pilot_a/CHANGES.md` is read by Lane N: no test names, test files or gold content in it.
