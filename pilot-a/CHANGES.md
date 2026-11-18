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

## 2026-10-24: run main-1 finished; trajectories carry no reasoning

`runs/claude-sonnet-5-5/main-1` (git-ignored; `bash pilot-a/scripts/run_agent.sh main claude-sonnet-5-5 main-1 2`, started 17:19 UTC, detached with `setsid nohup`): all 16 tasks `Submitted` with a non-empty patch within 20 minutes; total cost $0.69 ($0.017 to $0.27 per task). 15 tasks took 4 to 7 model calls (5 to 8 commands); django-10554 took 24. Correctness of the patches is not checked yet.

Every assistant message has empty text: no thinking blocks, `reasoning_tokens` 0, about 90 output tokens per call. With the shipped config, Sonnet 5.5 answers with bare tool calls, so a trajectory holds only commands and their outputs. Agents often went straight to the edited function with the first search and did not reproduce the bug. Open (user decision pending): keep main-1 as the pilot run, or run again with reasoning recorded.

## 2026-10-24: smoke test with visible thinking (`smoke-thinking-1`)

Cause of the empty messages in main-1: Sonnet 5.5 thinks adaptively by default (the model decides per call whether to think), and returns thinking and text between tool calls as blank blocks unless `thinking.display` is set ("omitted" is the default). `display: "summarized"` changes visibility only; the raw chain of thought is never returned.

`pilot-a/config/thinking_summarized.yaml` sets `thinking: {type: adaptive, display: summarized}`; `run_agent.sh` takes it as an optional 5th argument, passes `-c swebench.yaml -c <file>` (shipped config kept, merged recursively) and stores the file in `run_meta.json`. Smoke run on `pallets__flask-4992` with Sonnet 5.5: `Submitted`, 3 calls, $0.029; the setting reached the API; the model thought on 1 of 3 calls (589 reasoning tokens, summary recorded in `reasoning_content`, shown by Lane N's parser as "Agent reasoning"); the other calls had 0 reasoning tokens. So main-1 most likely had little hidden thinking, and this setting alone records reasoning only where the model chooses to think.

The recorded reasoning mentions "upstream Flask's actual implementation" and "hidden tests": the model knows the official fix of this public task. Evidence for training-data contamination, to be reported with Pilot A's results.

## 2026-10-24: run main-2 with visible reasoning (user decision: option 1)

`runs/claude-sonnet-5-5/main-2` (git-ignored): same 16 tasks, agent and shipped config as main-1, plus `pilot-a/config/thinking_summarized.yaml` (visibility only). All 16 `Submitted`; $0.59 in total; 87 model calls (main-1: 99). Reasoning summaries recorded in 31 of 87 calls; 3 tasks have none (django 13964, 16493, sympy 16766), and django 10554 and 15629 account for 14. Lane N's parser shows them as "Agent reasoning". main-1 is kept as a record. Correctness of the patches is not checked for either run.

Contamination: in 10 of the 16 tasks the reasoning recalls the upstream fix (for example "recalling the upstream Django fix that handles column type alteration", "trying to recall the exact upstream test case"). The agent's lessons may therefore rest on memory of the official fixes, not on what it observed; Lane N's extractor labels such statements `unverified_assertion`. To be reported with Pilot A's results and raised with the team, since every SWE-bench Verified task predates the model.

## 2026-10-26: parser bug found by a first correctness check

A first trial of checking an agent patch against the official tests (one task of main-2) exposed a parser bug: when Django prints two test names on one line before a single status, and the runner then crashes while printing a subtest description, `gold_gate.py`'s parser gives the status to the wrong test. The gold gate results are not affected. Must be fixed before checking agent patches or running checks. Correctness results are Lane R only and stay out of this file (details in the git-ignored `env/gold_gate_logs/agent/`), so that Lane N reviews lessons without knowing whether the agent's fix was right.

## 2026-11-09: new task source and selection (team decisions V46, V47)

A teammate set four requirements for each task's revision pair (base task at S, a related task at T): same repository; S an ancestor of T; T's environment reconstructable; the code changed between S and T. Checked with GitHub's compare API (ancestry), file blob hashes at S and T (did the files the base fix edits change), and Docker Hub (does the related task's image exist).

Finding: SWE-ContextBench links tasks by topic, not by time. Of its 360 base-to-related links, 116 point forward, 132 backwards (the related task is older), 107 sit at the same commit and 5 are on diverged branches (`data/scb_link_directions.csv`). Only 6 of the 16 V32 tasks had a future target. Dropping the Verified requirement (user decision), 28 SWE-bench base tasks in django, sympy and scikit-learn have at least one forward link; all 45 of their forward links meet requirements 1, 2 and 4, and every target image exists (`data/v46_candidates.csv`, `data/v46_forward_links.csv`). Image existence is not yet "image works": the target images still need a fingerprint check, and the scikit-learn ones the build repair (`build_derived.sh`).

Selection (user decision): 16 of the 28, in 5 clusters by package directory of the fix (listed in V47); the other 12 share no directory with another candidate. Clusters are looser than file level, to be reported as such. 6 of the 16 come from SWE-bench outside Verified (django 12589, 16910; sympy 14774, 18057; scikit-learn 10949, 25638) and lack its hand checks (clear issue text, fair tests). Carried over from V32: django 11555, 12209, 15382, 15930 and sympy 14976, 16766. Runs `main-1` and `main-2` covered the V32 list and are kept as records; a new run of all 16 keeps one run per pilot list.

## 2026-11-10: V47 list frozen

`clusters.csv` rewritten by `scripts/build_clusters.py` for the 16 tasks of V47: clusters D1 `django/db/models/` incl. `sql/` (6), D2 `django/utils/` (2), S1 `sympy/printing/` (4), S2 `sympy/core/` (2), K1 `sklearn/utils/` (2). New column `targets`: each task's forward related tasks from `data/v46_forward_links.csv` (25 in all), the T side of its revision pairs; `related_ids` still lists all SCB links. Neither is run in Pilot A.

The builder now reads full SWE-bench (`SWE-bench/SWE-bench`) instead of Verified: it has all 28 candidates with `eval_script` and `image`, and agrees with Verified on base commit, fix and problem statement for the 17 candidates in both. It fails if a cluster leaves out a candidate whose fix edits a file in its directories, if a directory edited by two candidates' fixes is in no cluster, if a forward link is not an SCB link, or on the old checks (one task per PR, no identical problem statements). All passed; `data/same_pr_groups.csv` regenerated unchanged.

The V32 instance file is kept as `instances/main-v32/` (runs `main-1`, `main-2`); `instances/main/` is rebuilt in step 5.

## 2026-11-10: gold gate reads full SWE-bench; parser bug fixed

`gold_gate.py` loads `SWE-bench/SWE-bench` instead of Verified (needed for the 6 tasks outside Verified). For all 500 Verified tasks the two datasets have identical `eval_script` and `test_patch`, so earlier results are unaffected; the recorded command source is now `swebench_eval_script`.

The parser bug of 2026-10-26 is fixed: when Django prints a second test name on the same line before any status, the first test now gets no status (MISSING) instead of the second test's. A synthetic case was added to `test_gold_gate.py` first (it failed), then the fix (it passes). Re-parsing every saved gate log with the old and the new parser: the 16 gold-gate logs give identical results; only the trial log of 2026-10-26 changes, as intended.

`build_clusters.py` also writes `targets.csv` (the 25 target tasks with image and commit, in the column order `pull_images.sh` reads); `TASKS=pilot-a/targets.csv bash pilot-a/scripts/pull_images.sh` pulls and fingerprints them.

## 2026-11-10: fingerprints, gold gate and instance file for the V47 list

Fingerprints (`env/<id>.json`): all 16 base images (official SWE-bench) have `base_commit`, HEAD = base plus the mode-only commit with no content change, no other commits reachable, clean tree, package imported from `/testbed`. Of the 25 target images, 22 work as shipped; the three scikit-learn targets (12622, 15093, 25637) fail `import sklearn`, as in October, and work after `build_derived.sh` (`pilot-a/<owner>.<repo>-<n>:built`; their fingerprints are of the repaired images). So every task keeps at least one usable target and none drops out (requirement 3 now means "image works", not only "image exists"). The targets were not gold-gated; they are not run in Pilot A. Image storage: 79 GB.

Gold gate (`env/gold_gate.jsonl`, git-ignored): all 16 tasks pass, with all their F2P and P2P tests passing and none missing; no task replaced. All 16 were re-gated with the final gate version. Three gaps in the gate were found and fixed on the way, each with a failing case added to `test_gold_gate.py` first:
- the Django parser bug of 2026-10-26 (fixed above) also hid a sub-test error in one task's P2P tests, which made the next gap visible;
- the gate ran only the official script's test line and missed its `export` lines; four tasks' scripts set a UTF-8 locale, without which a file-reading test fails under Python 3.6. The gate now runs the exports too;
- one image prints coloured pytest output (ANSI codes), which the parser now strips; and SWE-bench lists parametrized test names cut at the first space, which `lookup` now matches when all continuations agree.

Instance file: `instances/main/instances.jsonl`, 16 tasks, official images, fields as before (no patch, test or test-name fields).

## 2026-11-10: run main-3 (the V47 list)

`bash pilot-a/scripts/run_agent.sh main claude-sonnet-5-5 main-3 2 pilot-a/config/thinking_summarized.yaml` (approved by the user). All 16 tasks submitted a non-empty patch; 4 to 13 steps per task; $0.66 in total ($0.015 to $0.092 per task); 4 min 44 s with 2 workers. Trajectories in `runs/claude-sonnet-5-5/main-3/` (git-ignored); `run_meta.json` records versions, image ids and hashes of the instance file and lockfile.

Reasoning summaries are recorded in 15 of 16 trajectories (on 1 to 6 steps each, 195 to 2,803 characters). sympy-14774 has none: the model thinks adaptively and did not think on that 4-step task, and its steps carry no text besides the commands. Not re-run: one run per pilot list, and re-running one task because of its trajectory would select data after seeing it. Lane N gets that trajectory with commands and outputs only.

## 2026-11-10: final workspaces of main-3

`scripts/final_workspace.py` rebuilds each task's final workspace (Plan_v2 Section 4, parts 1 and 2): in one fresh container of the run's image it replays every command of the trajectory in order, as mini-swe-agent ran it; in another it only applies the submitted patch. Results per task in `runs/claude-sonnet-5-5/main-3/<id>/final_workspace.json` (git-ignored, with the run).

The replay is faithful: on all 16 tasks every replayed command returns the exit code recorded in the run (a timeout counts as -1, as in mini-swe-agent). The only untracked file after any replay is the agent's own `patch.txt`, so no file the agent created is missing from a patch. In 14 tasks the replayed and the patched workspace have identical tracked diffs. Two differ, both because of how the agent built its submission:
- django-14792: the agent's submit command was `cat patch.txt | head -3`, so the submitted patch holds only the first three header lines and does not apply; one step earlier `cat patch.txt` had printed the full patch, so the cut looks like an accident (the agent shortened long outputs with `head` throughout). Its edits (4 source files) exist only in the replayed workspace.
- django-16910: the agent changed the expected results of an existing test (it reasoned that the old test passed only by accident) and then built its patch with `git diff -- django`, so that test change is not in the submission; the submitted source change is the same in both. (Corrected 2026-11-16: first recorded as added test lines.)

For probes and validity labels (Ca), the replayed workspace is the agent's final state. Part 3 of the spec (re-run the agent's last verify step) waits for Lane N's segmenter.

## 2026-11-16: decisions renumbered V46, V47

The team decisions of 2026-11-09 (task source, clusters) were first numbered V33 and V34, but branch `pilot-a/laneN` had already used V33 to V45 on 2026-10-25. They are now V46 and V47 (user decision), throughout this branch including the entries above; the content is unchanged. The analysis files were renamed with them: `data/v46_candidates.csv`, `data/v46_forward_links.csv`. Rebuilding with the renamed files gives byte-identical `clusters.csv`, `targets.csv` and `data/same_pr_groups.csv`.

The trajectories of run `main-3` (with `final_workspace.json`, `preds.json`, `run_meta.json`; 16 tasks, 256 KB zipped, no gold material) go to Lane N as a zip sent by the user, since `runs/` is git-ignored.

## 2026-11-16: recall of upstream fixes in main-3 (reviewed by the user)

The recorded reasoning of every main-3 task was read, flagged passages first (words such as "upstream", "recall", "actual fix", a version or ticket number). A passage counts as clear recall when it uses knowledge the agent cannot have from the problem statement or the code at its commit: a later fix, a later version, or code that does not exist at the commit. Each flagged claim was compared with the problem statement, the code in the image and (Lane R only) the official fix; the per-task verdicts are in the git-ignored `env/gold_gate_logs/recall_main-3.csv`.

Result over 16 tasks: clear recall in 10, unclear in 2 (a vague mention, or awareness of a later change without using it), no recall in 3, no reasoning recorded in 1 (sympy-14774). Of the 10, 6 also match the later fix in content (same function, variable or mechanism, absent from the problem statement); 4 rest on wording such as "checking the upstream version" for a change that can be reasoned out. In django-14792 the recalled code (`split_tzname_delta`) does not exist at the task's commit: lessons from that task may describe a later Django version. Same rate as main-2 (10 of 16). To be reported with Pilot A's results and raised with the team.

## 2026-11-16: problem statements of the 6 tasks outside Verified (reviewed by the user)

SWE-bench Verified tasks were checked by people for a clear issue text and fair tests; the 6 tasks from full SWE-bench (django 12589, 16910; sympy 14774, 18057; scikit-learn 10949, 25638) were not. Their problem statements were read (tests were not opened): all 6 state the bug with reproducing code and the expected behaviour. sympy-14774's issue text names the fix itself (the line to change), which fits its short run (4 steps, no reasoning); lessons from it will likely be few. No change to the frozen list.

## 2026-11-16: Lane N compatibility test; repository clean-up (user decision)

Lane N's tools (`pilot-a/laneN` at `bcc2309`, unchanged, tested in a separate worktree) accept the 16 trajectories of main-3: all render completely, metadata from `run_meta.json` and `instances/main/instances.jsonl` passes production validation, and one real extraction (sympy-14976, one Sonnet 5.5 call, about $0.04) gave a full handoff bundle. Blocker: `clusters.csv` on `pilot-a/laneN` is the old task list, so `handoff build` rejects every main-3 acquisition unless `--selection pilot-a/clusters.csv` (V47) is passed. Open with Lane N: which rows and code states Lane R checks, the `workspace` identifier, `assessor.independent`, freezing the bundle before checks. Report kept outside the repository (worktree `MemRev-laneN`, `runs/compat/REPORT.md`); the task brief is `plan/LaneN_Compat_Handoff.md`.

Removed: `scripts/data_prep/clusters.py` and its output `data/lite_task_file_overlap.csv`, the SWE-ContextBench Lite task selection replaced by `build_clusters.py` (V46, V47); recoverable from git history. Fixed script paths written as `pilot-a/pilot-a/scripts/...` in `scripts/README.md`, `scripts/data_prep/README.md`, `plan/Kickoff.md` and `plan/Plan_v2.md`. Fingerprints and instance sets of superseded lists stay as records.
