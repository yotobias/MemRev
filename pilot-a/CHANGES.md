# Pilot A change log

Every deviation from `clusters.csv` or from the settings in `pilot-a/plan/Plan_v2.md` Section 4, with date and reason. Newest last.

Lane N reads this file. Entries never name gold-patch content, test names or test files of the 19 pilot tasks; those details stay in `env/gold_gate.jsonl` and `env/gold_gate_logs/` (Lane R only).

## 2026-10-22: selection frozen

`clusters.csv` written by `pilot-a/scripts/build_clusters.py`: the 19 tasks of `pilot-a/plan/Kickoff.md` Section 5, unchanged. The script checks `kind` against `data/lite_task_file_overlap.csv`, that every task edits its cluster's file, that no two selected tasks share a same-PR group, and that exactly 22686/22711 and 3359/3362 have identical issue text. Same-PR siblings left out: 22706 (with 22711), 16953 (with 16342), 3481 (with 3359), 32450 (with 14016).

Data notes, no effect on the selection: in `SWEContextBench_Relationship.parquet`, `django__django-28147` carries two PRs (11383, 11587) and joins the group of both; the PR URL for `scikit-learn__scikit-learn-13241` is an `/issues/` link and is read as `/pull/13241`.

## 2026-10-22: instance file stricter than the handoff

`instances/<set>/instances.jsonl` also drops `FAIL_TO_PASS` and `PASS_TO_PASS` (the handoff names only `hints_text`, `patch`, `test_patch`). mini-swe-agent reads only `instance_id`, `problem_statement` and `image_name`; the test names come from the test patch and Lane N may open this file.

## 2026-10-22: smoke task is `pallets__flask-4992`, outside the 19 and outside the pilot's repositories

Lane N builds the segmenter on the smoke trajectory, so the smoke task must not prime the review of any cluster. First choice `psf__requests-2674` (no shared edited file with any Lite task) was replaced the same day because it is the same library as R1 (`adapters.py` works with R1's `models.py`). `pallets__flask-4992` edits `src/flask/config.py`, shares no file with any Lite task, and its repository is not in the pilot. Fingerprint clean; gold gate passes (F2P 1/1, P2P 18/18). Its run is not a pilot run and produces no notes.

## 2026-10-22: backbone model and run settings

Decided by the user: the backbone (agent and extractor, pinned for the project) is `claude-sonnet-5-5`; pipeline tests such as the smoke run use `claude-haiku-5-5`. Both are in litellm's price table (1.106.2), so the $3 cost limit works.

Departures from the run command in v2 Section 4 and the Lane R handoff:
- No temperature. Current Claude models reject non-default sampling parameters; the shipped config has `drop_params: true`. All runs use the provider's default sampling, as v2 Section 4 provides for this case.
- No `-c` option. `mini-extra swebench` replaces the default config when `-c` is given, so the handoff's `-c model.model_kwargs.temperature=0` would have run without the shipped `swebench.yaml` (prompts, step and cost limits, 60 s timeout, `BASH_ENV`). The model is passed with `-m`. Command in `pilot-a/scripts/run_agent.sh`.
- Prompt caching: the shipped config sets no `set_cache_control`, so every step is billed for the full history. Left as shipped for the smoke run; token counts from it decide whether to enable it for the 19 runs (it changes cost, not what the model sees).

## 2026-10-22: `mcp` added to the lockfile; smoke-1 failed before any model output

`runs/claude-haiku-5-5/smoke-1` ended with `ModuleNotFoundError: No module named 'mcp'` on the first model call (cost $0, empty patch): litellm 1.106.2 imports `mcp` on every completion that passes tools, without declaring the dependency. `mcp` 2.3.0 was added to `pyproject.toml`/`uv.lock`; mini-swe-agent and litellm versions unchanged. smoke-1 is kept as a record; the smoke run was repeated as `smoke-2`.

## 2026-10-22: smoke-2 result; prompt caching stays as shipped

`runs/claude-haiku-5-5/smoke-2`: `Submitted` after 4 model calls, $0.0014, patch 1,369 characters; trajectory format `mini-swe-agent-1.1`, full outputs in `extra.raw_output`, parallel tool calls observed (two commands in step 1). 11.0k of 16.5k input tokens were cache reads although the config sets no `set_cache_control`: caching happens without it, so the config stays as shipped for the 19 runs. The trajectory goes to Lane N for the segmenter (not a pilot run, no notes).

## 2026-10-22: gold gate runs without reinstall and without patch rewriting

Test commands: official SWE-bench Lite `eval_script` test line for experience tasks; the SCB harness command for related tasks. Unlike both harnesses, the gate does not run `pip install -e .` before testing (agent runs and probes use the image as it is) and does not rewrite `e.message` to `str(e)` as the SCB harness does.

Two departures from the SCB command, both for sympy related tasks (16342, 16946): sympy 1.5's test helpers call `py.test.mark`, which the image's pytest no longer has, so pytest cannot collect the files; the gate uses sympy's own `bin/test -C --verbose`, as official SWE-bench does for sympy. For 16342 the full run of its test files (several hundred P2P tests, some of sympy's slowest) exceeds the 30 min cap; it was gated on its F2P tests only (`--f2p-only`, `bin/test -k`), so its P2P result is not recorded.

## 2026-10-22: gold gate result, all 19 + smoke pass

Every task's gold patch passes all its F2P tests (`env/gold_gate.jsonl`, latest `pass` line per task). Notes: `psf__requests-2148` first failed 9/10 because one F2P test that calls the live httpbin.org service got HTTP 502; it passed 10/10 on rerun. Its tests depend on an external service, and the agent's run may meet the same flakiness. P2P not fully passing (informational, does not gate): matplotlib 22482 (193/194) and 22686 (85/87), requests 3359 (64/67, 3 not found in output).

## 2026-10-22: derived images for five related tasks (decided: use them)

Approved by the user on 2026-10-22. `instances/main/instances.jsonl` was rebuilt (no run had used it) and points the five tasks below to `pilot-a/<owner>.<repo>-<n>:built`; probes for these tasks use the same images.

Rebuilt the same day, before any run used them: `docker commit` had stored the build command as the images' default command and `BASH_ENV` as an image variable. The build now runs without `-e` and commits with `CMD ["/bin/bash"]`, so each derived image has its original's exact configuration (command, working directory, environment). Fingerprints and gold gate re-run on the new images, with identical results; the earlier derived images were deleted.

The jiayuanz3 images build the package and then run a history-cutoff step whose `git clean -fdx` deletes everything untracked, including compiled extensions. Fingerprints of all 19 images (`env/<id>.json`) show five unusable as shipped:

| Task | Problem in the shipped image | Rebuild |
|---|---|---|
| scikit-learn-12622, 15093, 25637 | `import sklearn` fails (no compiled extensions); gate `inconclusive` | 158 s, 208 s, 262 s |
| matplotlib-22686 | `import matplotlib` fails (`_c_internal_utils` missing) | 51 s |
| matplotlib-22482 | meson non-editable install: imports from `site-packages`, so edits in `/testbed` have no effect (tested: an appended attribute is invisible) | 52 s |

The SCB harness repairs the same state before grading (`_python_rebuild_command`, then `docker commit` to a temporary image). Rebuilding exceeds the agent's 60 s command timeout, so the agent cannot repair it itself. `pilot-a/scripts/build_derived.sh` runs the SCB rebuild (editable install for 22482) and saves `pilot-a/<owner>.<repo>-<n>:built`; build artefacts left untracked (only meson's `subprojects/.wraplock`) are hidden through `.git/info/exclude`, so they cannot enter an agent patch. On all five derived images: package imports from `/testbed`, edits are visible, `git status` clean, 0 future commits, gold gate passes. Proposed: agent runs and probes for these five tasks use the derived image; `clusters.csv` keeps the original image name, the instance file carries the derived one.

Not affected: all eight swebench experience images, and the sympy, requests and django related images (pure Python). No image exposes commits after `base_commit` other than the swebench mode-only commit.

## 2026-10-22: moved to the team repository; agent runs on hold

Lane R's work was pushed to branch `pilot-a/laneR` of the team repository `yotobias/MemRev` (public; literature PDFs, proposal drafts and personal files left out). That repository's decisions V11/V12 and ADR 0001 take lessons from SWE-bench Verified django, sympy and scikit-learn tasks so that Pilot B can pair them with later revisions; only 1 of the 19 tasks here (`django__django-14017`) is in Verified, and two clusters (matplotlib, requests) are outside those repositories. ADR 0001's premise that SWE-ContextBench data is unreleased no longer holds (it is on Hugging Face under MIT). The 19 runs wait until the team decides the task source; the pipeline is reusable either way.

## 2026-10-24: tasks come from SWE-bench Verified (user decision)

Pilot A runs on base tasks from the full SWE-ContextBench that are in SWE-bench Verified, in django, sympy or scikit-learn (team decisions V11, V12), and that have related tasks; the related tasks are kept as links for later pilots. The full SWE-ContextBench experience set contains all 500 Verified tasks; its Lite subset, used for the earlier list, is built on SWE-bench Lite. The 19-task list of 2026-10-22 is superseded (only `django__django-14017` qualifies); candidates: 64 base tasks with 105 related tasks. Steps 2 to 5 are redone for the new list; the pipeline is reused. To be recorded as a numbered decision in the team's `docs/decisions.md`.

## 2026-10-24: task list re-selected, 16 tasks in 5 clusters (user decision)

Team decisions V31 (task source) and V32 (this selection) in `docs/decisions.md`. Candidates: 64 Verified base tasks with related tasks (django 41, sympy 17, scikit-learn 6). File-level clusters are too small (at most 4 tasks share a file), so the user chose clusters in two modules, `django/db/models/` (17 candidates) and `sympy/printing/` (4), over a single django cluster of all 17 (one repository only) and over widening to Verified tasks without related tasks (changes the task-source rule). Inside the modules one rule applies: a candidate is selected iff its fix shares an edited file or sub-package with another candidate.

| Cluster | Shared code | Tasks |
|---|---|---|
| D1 | `django/db/models/expressions.py` | django 15161, 15382, 15930, 16082 |
| D2 | `django/db/models/sql/` | django 10554, 11555, 14122 |
| D3 | `django/db/models/fields/` | django 11400, 11999, 15629, 16493 |
| D4 | `django/db/models/base.py` | django 12209, 13964 |
| S1 | `sympy/printing/pycode.py` | sympy 14976, 16766, 22914 |

Left out by the rule (no shared file or sub-package in the module): django 11603, 13363, 14017, 16560; sympy 15976. Related tasks are not run in Pilot A (confirmed by the user); `clusters.csv` lists them in `related_ids` (30 links) and has only base-task rows, so the image, gate and instance scripts see only the 16. All 16 use official SWE-bench images. `build_clusters.py` now reads SWE-bench Verified and the full SWE-ContextBench files, checks that every task edits its cluster's code, that no candidate editing a cluster's code is left out, one task per same-PR group, and no identical issue texts. Same-PR groups now cover all SWE-ContextBench tasks; PR URLs are compared lowercased (the full set spells `briannesbitt/Carbon` both ways).

## 2026-10-24: images and fingerprints of the 16 tasks; scripts switched to Verified

All 16 official SWE-bench images pulled and fingerprinted (`env/<id>.json`): `base_commit` present, HEAD is base plus the mode-only "SWE-bench" commit with no content change, no other commits reachable, working tree clean, package imports from `/testbed`. Python 3.6 to 3.11 depending on the django version. No derived images needed. `clusters.csv` gained a `base_commit` column (read by `pull_images.sh`, which used the Lite-only overlap file). `gold_gate.py` now takes official data from SWE-bench Verified and the full SWE-ContextBench files, and also checks that the SWE-ContextBench issue text equals the official one; `build_instances.py` reads the full SWE-ContextBench files.

## 2026-10-24: gold gate passes for all 16; new instance file

Gold gate (`env/gold_gate.jsonl`, git-ignored): every task's official fix passes all its F2P tests and all its P2P tests, with no non-Python files in the fix and nothing reinstalled; no task replaced. Commands: the official SWE-bench Verified `eval_script` test line. `instances/main/instances.jsonl` rebuilt for the 16 tasks (same fields as before, official images); the never-used 19-task file is kept as `instances/main-lite19/`.

## 2026-10-24: superseded images deleted (user decision)

The 19 images of the superseded list and the 5 derived images built from them were deleted from WSL Docker; image storage went from 72.7 GB to 40.3 GB (layers shared with the 16 new django and sympy images stay). The derived images can be rebuilt with `build_derived.sh`; the fingerprints in `env/` remain as records. Kept: the smoke image (`pallets__flask-4992`) and other images outside both lists.

## 2026-10-25: Lane N raw extraction contract v2

Implemented the user-requested contract revision (V33–V35). Full indexed trajectories replace mandatory per-phase extraction; phase labels never gate verification. The prompt now includes structured scope, symbol/file, predicate, kind and failed-step origin. Null denotes unknown detail, and `no_evidence` with empty indices retains unsupported candidates without assigning a source-validity verdict. Missing evidence and a cited unverified assertion are distinct.

`load_extraction` reads strict JSON; `validate_extraction` validates v2 fields and original message indices without changing the response or judging truth. The raw format rejects unknown fields. The original unversioned development response remains unchanged; a separate hand-authored Astropy fixture demonstrates v2 and is not a production result. Formatting and extraction tests: 54 passed.

The contract is in `specs/pilot-a-extraction/spec.md`. IDs, task/run provenance and the six-field Pilot B JSONL export remain separate pipeline work. B's exact export key names are still pending ticket 01, and B's own assumption extraction/source checks are unchanged. No model runs, gold inspection, or C0/C1/Ca evaluations were performed in this step.

## 2026-10-25: provenance packages and pending review drafts

Implemented V36–V38 after the user requested the next step. `memrev.provenance` validates the raw response, assigns deterministic occurrence IDs, snapshots input bytes and hashes, records operator-supplied metadata and explicit unknowns, and creates a separate pending review draft. Repreparing the same package preserves human review edits; changed frozen artifacts require a new output directory. Outputs live outside Git checkouts.

Prepared the user's development response `gpt-6-high_test_lessons_102526.json`: 5 lessons and 17 assumptions in `../pilot-a-artifacts/astropy-manual-102526/`. Its model filename label is unverified; source SHA, repository metadata, agent-run ID, exact extractor model, usage/cost and exact prompt remain unknown. The curated regression fixture had already been restored and was preserved. All 69 formatting, extraction and provenance tests pass; generated snapshot hashes were checked independently.

See `PROVENANCE.md` and ticket 02 for the workflow. Review import/sign-off, split-child IDs, C0/C1/Ca checks, sharing and Pilot B export remain later work. This package is development data and every review row is pending. No model calls or gold inspection were performed.

## 2026-10-25: evaluation-only review export and import

Implemented V40–V41 following the user's concern that reviewer-written replacements can bias extraction evaluation. Primary review now records six rubric ratings, an outcome, issue codes, reasons and reviewer evidence pointers without changing original text. The legacy action-based draft remains for compatibility; use `memrev.evaluation draft` and `import` as described in `EVALUATION.md`.

Imports verify acquisition snapshots and original candidates, reject incomplete or inconsistent reviews, preserve reviewer type and self-reported independence, and retain every original candidate in an evaluated bank. Exact review bytes, protocol/record snapshots, recomputed counts, a report and a hash manifest are saved together. Changed imports require a new output directory. There is no automatic repair, review merging, or source-validity sign-off.

The existing AI evaluation imported unchanged under `runs/acquisitions/astropy-manual-102526/evaluations/ai-codex/`: 5 lessons, 17 assumptions; 7 usable, 6 needing repair, 2 uncertain and 2 context-only. This remains AI-attributed development data. A pending form with placeholder reviewer details is ready in the acquisition directory. Artifacts are inside MemRev and gitignored, as requested in V39.

Validation: 106 tests pass (37 evaluation tests plus the prior 69), and both new CLI commands ran on the development package. Freeze the development rubric with the team before production review. Human evaluation, selected-task acquisition, revision-specific checks, sharing analysis/reporting and Pilot B's separate lesson export remain. No model calls, gold inspection or benchmark execution were performed.

## 2026-10-25: offline handoff while human review is deferred

At the user's request, implemented the remaining Lane N interface plumbing without requiring any human trajectory review (V42–V44). `memrev.handoff build` combines verified acquisition packages and optional explicit evaluations, preserves all candidates, prepares Lane R requests and pending validity returns, validates later validity/sharing submissions, produces status/count reports, and exports original advice in a proposed six-field Pilot B JSONL with exclusions and review-status sidecars. A review is not required merely to exercise the export; A does not gate B, and B performs its own assumption review/checks.

`sample` prepares a deterministic 30% sample by group, rounded up, with all members and a separate private primary partition. The recipient receives only `blind/`, including portable trajectory evidence. `compare` measures changes in member sets independent of group names, retains reviewer attribution and requires gold-exposure disclosure. No automatic semantic grouping or adjudication is performed.

All wire contracts remain proposed for team alignment. Missing work is pending, setup errors cannot become target contradictions, superseded assumptions remain eligible for sharing, and negatives at checked workspaces do not erase intermediate observations. Evidence references and hashes are declarations; the importer does not open gold evidence or certify executions. Production acquisition metadata must match the frozen selection; development fixtures cannot count as production task coverage.

Current local demonstration: `runs/handoffs/astropy-design-v2/` contains 5 lessons and 17 assumptions with no evaluation imported, 51 pending validity cells and 17 pending grouping rows. Five lessons are excluded from B's draft for missing provenance. A separate `astropy-with-ai-example/` collection reuses the existing AI example without any new review. Outputs remain gitignored.

Validation: 149 tests pass, including 43 new tests covering synthetic completed inputs and the all-pending path. The six proposed B keys are documented in `HANDOFF.md` and linked from B ticket 01 without marking that ticket complete. No paid calls, gold inspection, real check execution or new human judgments. Research work, real Lane R/B integrations and final contract agreement remain separate from this completed implementation slice.

## 2026-10-25: repository cleanup and Lane R readiness audit

Implemented user-requested cleanup (V45). Removed tracked generated egg-info metadata, the redundant rendered transcript fixture, the placeholder package greeting and obsolete action-review generation. Added ignore rules for build/test outputs. Acquisition preparation now snapshots only; `memrev.evaluation draft` explicitly generates the current review format. Existing packages and review edits remain compatible. The trajectory module's hardcoded fixture demo is now an explicit-input CLI that refuses to overwrite a prompt.

Preserved historical research material: moved the original browser-exported kickoff HTML into `plan/archive/`, and moved the development acquisition's action draft and rewriting examples into its ignored `archive/`. Removed the obsolete `astropy-design-v1` bundle only after verifying its manifest and confirming no extra files. Retained raw fixtures, input snapshots, current handoff bundles, generated prompt provenance and decision history. `START_HERE.md` and the fixture index explain the active layout.

Lane R audit: all 16 selected task IDs match the sanitized instance file, no gold/hint/test-label fields are present there, and all 16 fingerprint files exist. The local venv's four checked runtime packages match locked versions. Docker access is denied even outside the tool sandbox, `.env` is absent, and local uv differs from the original recorded toolchain. Image availability and provider access remain unverified. `env.sh` now selects an existing local or original WSL environment while honoring overrides; the WSL setup script fails clearly on native Linux and preserves its external-venv default on WSL.

The launcher exists, but the installed agent saves trajectories/submitted patches and cleans up containers without full workspace capture. Capture must precede cleanup to preserve untracked files and Ca evidence; the actual validity-check runner also remains unimplemented. See `RUN_READINESS.md` for the distinction between basic launch prerequisites, full-batch workspace preservation and later validity work. No paid calls, containers, image pulls or gold inspections were performed.

Validation: 150 offline tests pass; shell syntax and environment-override behavior checked. The current all-pending handoff rebuilt byte-for-byte after cleanup; `git diff --check` passes.
