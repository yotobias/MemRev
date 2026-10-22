# Pilot A implementation plan: experience acquisition and source validity

Status: draft v2 for team discussion, 2026-10-20. Supersedes the 2026-10-19 draft (`archive/Pilot_A_Plan.md`, kept unchanged). Section 12 lists every change and the finding that motivated it.
Scope: Pilot A of `docs/Final_Proposal_Tex.md` ("Experience acquisition and source validity"). This document is self-contained; the later pilots are planned after Pilot A reports.

## 1. What Pilot A must deliver

Pilot A runs one fixed agent on a small set of real tasks, turns the runs into notes, and inspects what those notes rely on. Its outputs are:

1. **Run records**: for each task, the trajectory (every command and observation), the source commit, the agent's patch, the final workspace state, the execution environment fingerprint, and whether the patch passed the task's tests.
2. **Notes** extracted from each run, from steps that worked and steps that failed, each split into *advice* and the *claims* the advice relies on, with a pointer to the trajectory step that supports each claim.
3. **Source validity** per claim: supported by the historical repository (true at the source commit or in the official fix), or true only because of the agent's own unmerged edits.
4. A **manual review of sharing**: how often independently acquired notes rely on the same claim under compatible scope, counted without treating surface similarity as equivalence, and compared against the rate in a small control set of unrelated tasks.
5. The counts that the later cost comparison needs: notes, claim occurrences, distinct scoped claims.

The pilot answers the first half of RQ1 (do notes contain checkable repository claims?) and gives the first estimate for RQ2 (do claims recur?). A negative answer is a result, and it is the go/no-go for building anything.

## 2. What has been verified (2026-10-19, re-verified 2026-10-20)

| Item | Finding | Consequence |
|---|---|---|
| SWE-ContextBench dataset (HF `jiayuanz3/SWEContextBench`) | Released under MIT in `data/*.parquet`: Experience (1,007 rows), Related (362 rows, 357 distinct tasks), Lite variants (300 / 99), and `SWEContextBench_Relationship.parquet` (362 rows, 360 distinct pairs: `related_instance_id`, `experience_instance_id`, `related_pr_url`, `related_issue_url`, `experience_pr_url`, `experience_issue_url`). Columns are the SWE-bench schema. Lite is all Python, 12 repositories. | Usable as-is. Counts differ from the paper (1,100 / 376); cite the released figures. The PR URL columns are the authority for the same-PR rule in Section 3. |
| Same-PR tasks | SWE-ContextBench builds many "related" tasks by splitting one pull request into several issues. In Lite, 26 of 99 related tasks share a PR with their experience task, 28 with some experience task (the Relationship link can point elsewhere: 32450 is linked to 14017 but carries PR 14016), and 16 related-related pairs have byte-identical patches. **All 27 distinct same-commit pairs in Lite are the same PR or code-identical.** | "Same-commit pairs" do not exist as a category of distinct tasks. Selection applies the same-PR rule (Section 3). |
| Official SWE-bench Lite (HF `SWE-bench/SWE-bench_Lite`, split `test`) | Same 300 instance ids as the SCB Lite experience file; `base_commit`, `patch`, `test_patch`, `problem_statement` identical 300/300; `FAIL_TO_PASS`/`PASS_TO_PASS` 299/300 (sympy-13177 differs, not selected). Carries `image`, `eval_script`, `log_parser`, `eval_type`. | Experience tasks are graded against this dataset, not the SCB parquet. |
| Context pool / trajectories | The GitHub repo ships the 300 Lite experience runs as Claude Code 2.0.67 session transcripts (`cases/SWEContextBench Lite Past Experience/`, 300 `.jsonl`, 126 MB, model `claude-sonnet-4-5-20250929`). Filenames are session ids; the leading "summary" record can describe a different task. The full 1,007 set and related-task runs are not released. | Not used as a note source in Pilot A. Embargoed for reviewers (Section 9). Noted as a same-model contamination risk if that backbone is chosen. |
| SWE-ContextBench code (`github.com/jiayuanz3/SWEContextBench`, last commit 2026-09-21, **no licence file**) | `evaluation.sh {run_id} lite` wraps a fork of the SWE-bench harness (`swebench_memory/harness/run_evaluation.py`) and pulls `jiayuanz3/swecontextbench:base`. `environment.yml` is a saved GitHub HTML page, so dependencies are undocumented. The harness removes each instance image after evaluation unless `run_evaluation.py` gets `--no-remove-instance-image`; `evaluation.sh` does not pass it. `psf__requests-2344` is special-cased (tests run one per container, 30 s cap) because its 2014 tests call httpbin.org. `cases/SWEContextBench Lite/` holds the 99 related-task JSONs (schema above plus `pull_number`, `issue_numbers`). | Evaluates patches for related tasks. We call `run_evaluation.py` directly with `--no-remove-instance-image` and keep our own dependency list (WP0). |
| Docker images, related tasks | Docker Hub `jiayuanz3/swecontextbench`, 358 tags (357 tasks + `base`), pattern `<owner>.<repo>-<number>`, linux/amd64, 0.8 to 2.0 GB compressed (requests 0.8, sympy 1.2, sklearn 1.3, django 1.2 to 1.3, matplotlib 1.9 to 2.0), about 3 GB on disk. `/testbed` is at `base_commit` with a clean tree (checked on one image). Python version varies by task (2344: 3.6.15). | Container exists for every Lite related task. Budget 3 to 4 GB disk per image. |
| Docker images, experience tasks | `docker.io/swebench/sweb.eval.x86_64.<instance_id with __ replaced by _1776_>:latest`, lowercased, linux/amd64, 1.0 to 3.1 GB compressed, up to 6.7 GB on disk. `/testbed` HEAD is **one commit above** `base_commit`: an author "SWE-bench" commit that changes file modes only (checked on two images). | Record and diff against `base_commit`, never HEAD. Gold patches apply on top of it. |
| Gold patches | In-image check with gold + test patch: `psf__requests-3362` passes (1/1), `scikit-learn__scikit-learn-25638` passes (10/10). **`psf__requests-2344` cannot pass**: its gold adds `raise InvalidURL(e.message)` (Python 2 only) and the image runs Python 3.6. | 2344 is excluded. Every selected task's gold is validated in WP0 (gold gate) before any agent run. |
| mini-swe-agent | v2.4.6 (2026-07-23, MIT, Python ≥3.10). `mini-extra swebench --subset <name or directory> --split <split> --workers N -o <dir>`: `--subset` goes straight to `datasets.load_dataset`, which accepts a **directory** containing the jsonl, not a file path. An instance's `image_name` (or `docker_image`) field overrides the image. Shipped `config/benchmarks/swebench.yaml`: `step_limit 250`, `cost_limit 3` (USD, checked before each call, so a run can overshoot by one step), `cwd /testbed`, **60 s** command timeout, one new `bash -c` subshell per command with `BASH_ENV=/root/.bashrc` (activates the testbed env in both image families; verified), `parallel_tool_calls: true` (one message may carry several commands, executed in order), prompt renders `{{task}}` = `problem_statement` only, default `model_name` `anthropic/claude-sonnet-4-5-20250929`, **no temperature set and no seed option** (both go through `-c model.model_kwargs.*`). Outputs over 10,000 characters are shown to the model as head 5,000 + tail 5,000, but the full text is kept in the trajectory (`extra.raw_output`). Container started with `--rm` and `sleep 2h`. Writes `<id>/<id>.traj.json`, `preds.json`, `exit_statuses_<time>.yaml`, `minisweagent.log`. Re-running into an existing `-o` skips instances already in `preds.json` unless `--redo-existing`. An unregistered model raises at the first call unless `cost_tracking: ignore_errors`, in which case cost is 0 and only the step limit applies. | Fixed agent with a small surface. The final workspace must be rebuilt from `base_commit` + `model_patch` because the container is discarded. Each experiment uses a fresh `-o` directory. |
| SWE-bench harness | PyPI `swebench` 5.0.2 (Python ≥3.10): `swebench eval lite -p preds.json --run-id <id> -j N` (the name `lite` is resolved by the harness loader); Docker required; recommends x86_64, 16 GB RAM, 120 GB disk. A local file works only if its rows carry `image`, `eval_script`, `log_parser`, `eval_type`. | Task outcomes for experience tasks against the official Lite dataset; related tasks go through the SCB harness. |
| Related literature code | Subtask-Level Memory: not released. EvoArena SWE-Chain-Evo: dataset on HF (mostly Go), code "to be released", no licence. | No dependency. |
| Local machine | Windows 11, 8 cores, 31 GB RAM, 522 GB free on C:. **Docker exists only inside WSL2** (Ubuntu 24.04, Docker 29.1.3, Compose v5, Buildx; 942 GB free; WSL sees 16 GB RAM by default; no `uv` or `pip` in WSL yet). Git 2.49 on Windows, 2.43 in WSL; `uv` on Windows; `gh` authenticated. Windows clones of django/matplotlib/sklearn/sphinx fail checkout with "Filename too long". Git Bash rewrites `/root/...` arguments to `wsl -e docker` as Windows paths unless `MSYS_NO_PATHCONV=1`. | Run agent, harness, clones and probes inside WSL. Add `%USERPROFILE%\.wslconfig` with `[wsl2] memory=24GB`. |
| LLM API keys | None configured in the environment. | Blocking for the agent runs; decision in Section 9, with a date. |

## 3. Task selection: make sharing possible without manufacturing it

The proposal says 10–20 base tasks from a few repositories. The selection targets tasks that work in the **same files of the same repository**, where shared claims are plausible, and lets the review decide whether they actually share any. Two rules keep this honest:

- **Same-PR rule.** Two tasks are the same task if their gold patches are byte-identical, or if the PR URL of one (from `SWEContextBench_Relationship.parquet`, or `pull_number` in the case JSON) equals the PR URL of the other. At most one member of a same-PR group is selected; where the group contains an experience task, that one is kept. SWE-ContextBench's "same-commit pairs" are all same-PR groups, so there is no separate same-commit category. Tasks that share issue text but sit at different commits with different fixes (22686/22711, 3359/3362) are distinct tasks and are flagged as `same_text=true` in `clusters.csv`.
- **Control set.** One experience task per repository that shares no edited file with any Lite task (`partners = 0` in `lite_task_file_overlap.csv`), chosen mechanically as the lowest instance number. Sharing between control notes and between controls and cluster notes gives the base rate against which the cluster rate is read.

Scripts: `scripts/data_prep/inspect_scb.py` (downloads the parquet files), `scripts/data_prep/clusters.py` → `pilot_a/data/lite_task_file_overlap.csv`, plus a new `scripts/data_prep/same_pr.py` that writes the same-PR groups to `pilot_a/data/same_pr_groups.csv`. Over the 399 Lite tasks, 263 share an edited file with at least one other task; 36 of the 44 file clusters of three or more tasks survive the same-PR rule.

A third property is recorded but not optimised for: whether a task has a chronologically later related task in the benchmark (git ancestry of `base_commit`s in `pilot_a/data/revision_pairs/`; 73 distinct ordered pairs among the 100 distinct Lite pairs). It is listed in the "Why" column below for information; it played no part in choosing or ranking clusters, which were chosen by cluster size after the same-PR rule.

### 3.1 Proposed selection (19 cluster tasks in 5 clusters, 5 controls, 5 optional)

| Cluster | Repo / file | Tasks | Removed by the same-PR rule | Why |
|---|---|---|---|---|
| K1 | scikit-learn `sklearn/utils/validation.py` | 10949, 12622, 15093, 25637 | (replaces the old K1: 25578, 25634, 25635 were all PR 25638) | Four distinct PRs on one validation module; 12622 and 15093 are later related tasks of 10949 |
| M1 | matplotlib `lib/matplotlib/widgets.py` | 22482, 22686, 22711 | 22706 (PR 22711) | 22686 is a later revision of 22711's issue text (`same_text`) |
| S1 | sympy `sympy/sets/sets.py`, `fancysets.py` | 16342, 16946, 16988 | 16953 (= 16342) | 16988 precedes the other two in git |
| R1 | requests `requests/models.py`, `utils.py` | 2148, 3359, 3362 | 3481 (= 3359); 2344 (gold cannot pass) | Small library, API-level claims likely; 3362 precedes 3359; 3359 shares issue text with 3362 (`same_text`) |
| D1 | django `query_utils.py`, `sql/query.py` | 21204, 34570, 35356, 14016, 14017, 16910 | 32450 (PR 14016) | Largest cluster; three ordered pairs inside it (21204→16910, 34570→16910, 16910→35356) |
| C (controls) | one per repo | sklearn 10297, matplotlib 23964, sympy 11400, requests 2674, django 10914 | — | Mechanical rule, Section 3; no shared file with any Lite task |
| S2 (optional) | sympy `sympy/printing/latex.py` | 11897, 14774, 15059, 15609, 19235 | none | The only original cluster with no same-PR member; printing claims are very concrete |

D2 (`migrations/operations/models.py`) is dropped: after removing 34525 (PR 16820) and one of 28862/28916, two tasks remain. `psf__requests-863` (requests 0.14, 2012) is a possible fourth R1 member if its image and gold pass the gate.

Related tasks (jiayuanz3 images, `image_name` field): 12622, 15093, 25637, 22482, 22686, 16342, 16946, 3359, 21204, 34570, 35356, and in the optional set 15059, 19235. Experience tasks (swebench images, official Lite grading): 10949, 22711, 16988, 2148, 3362, 14016, 14017, 16910, the five controls, and in the optional set 11897, 14774, 15609. The `kind` column of `lite_task_file_overlap.csv` is the authority.

Ground rule from the proposal: tasks are chosen for *plausible* overlap, never pre-screened by looking at whether their notes would share a claim. The selection above is fixed in `pilot_a/clusters.csv` (columns: `instance_id, cluster, kind, image, same_text, same_pr_group, role ∈ {cluster, control, optional}`) before any agent run, and any later change to it is logged with a reason.

## 4. Running the agent (WP2)

- **Agent and model**: mini-swe-agent 2.4.6 pinned in a `uv` lockfile; one backbone model for the whole project (decision, Section 9); `step_limit 250`, `cost_limit 3` as shipped. Nothing in the agent's prompt is changed. Temperature is passed explicitly, `-c model.model_kwargs.temperature=0`, where the provider accepts it; if the provider rejects or ignores it, that is recorded in the run record and the model's default sampling is used for all runs. The model must be in litellm's price table (checked in WP0); `cost_tracking` stays at its default.
- **Instance directory**: `pilot_a/instances/<set>/instances.jsonl` (one directory per run set, nothing else in it) built by `scripts/pilot_a/build_instances.py` from the parquet files: SWE-bench schema plus `image_name`. The `hints_text`, `patch` and `test_patch` fields are stripped from the file the agent reads; only `problem_statement` reaches the prompt. Run: `mini-extra swebench --subset pilot_a/instances/<set> --split train --workers 2 -o pilot_a/runs/<model>/<run>` with a fresh `-o` per run (never `--redo-existing` into an old one).
- **Repeated runs**: 1 run for all tasks first; 3 runs per task if budget allows. mini-swe-agent has no seed; repeated runs at temperature 0 differ only by provider nondeterminism, and they measure within-task variance, not sharing across independently acquired notes. Section 7 reports them separately.
- **Outcome**: `swebench eval lite -p preds.json --run-id <run> -j 2` for experience tasks; `run_evaluation.py --no-remove-instance-image` from the SCB fork for related tasks; store `resolved`, `FAIL_TO_PASS` and `PASS_TO_PASS` results per run. Empty submissions and `LimitsExceeded` exits are recorded as `resolved=false` with the exit status kept.
- **Gold gate (WP0)**: before any agent run, apply gold + test patch in every selected image and run its `FAIL_TO_PASS`; a task whose gold does not pass is replaced from the same file cluster and the replacement logged. Results in `pilot_a/env/gold_gate.jsonl`.
- **Final workspace**: fresh container from the task image, `git apply` the `model_patch`, then record `git diff --stat <base_commit>`, untracked files the patch would miss (the agent's reproduce scripts are informative), and the output of the agent's own last test command re-run (the last trajectory action classified `verify` by the segmenter, Section 5).
- **Environment fingerprint**: image digest, `git rev-parse HEAD` and `base_commit`, `python --version` in the testbed env, `pip freeze` hash, captured once per image by `scripts/pilot_a/fingerprint.sh`.
- **Isolation**: every run in its own container; no memory of any kind is given to the agent. Pilot A produces notes; it does not use them. Runs must finish inside the 2-hour container lifetime; a run that hits it is recorded and rerun once.

Cost: 24 tasks (19 + 5 controls) × 1 run × ≤ \$3 cost limit ≈ \$72 worst case; 3 runs ≈ \$216; the optional five add \$15 per run. Extraction (Section 5) is a fraction of that. Disk: about 3 to 7 GB per image on disk, roughly 130 GB for 29 images.

## 5. Extracting notes and claims (WP3)

**Unit of a note.** A trajectory is first segmented into phases using the four categories of Subtask-Level Memory (*analyse*, *reproduce*, *edit*, *verify*), but by a fixed rule on the commands rather than by the agent's own prompt, and keeping repository detail rather than stripping it, since the claims are the object of study. The rule, implemented in `scripts/pilot_a/segment.py` and shipped with a labelled edge-case file:

- Each tool call is one action; a message with several tool calls contributes its actions in order. A command chained with `&&`, `;` or `|` is split and each part classified; the action takes the class of its last part that is not *analyse*.
- *edit*: the part matches a write pattern (`sed -i`, `>`/`>>`/`tee` to a path under the repository, `python`/heredoc that opens a repository file for writing, `git apply`, `patch`, `git checkout -- <path>`, `cp`/`mv` whose target is under the repository), and the path is tracked at `base_commit`. The same patterns on an untracked path are *reproduce*.
- *verify*: `pytest`, `python -m pytest`, `tox`, the repository's own test runner (`runtests.py`, `bin/test`), or `python <file>` where `<file>` is a test file under the repository.
- *reproduce*: creating or running a script that is not a repository file (`python repro.py`, `python -c`), including a reproduce script that itself calls pytest.
- *analyse*: `cat`, `sed -n`, `head`, `tail`, `grep`, `find`, `ls`, `git log`, `git diff`, `git status`, `pip show`, and anything unclassified. `pip install` is *environment* and is logged but does not start a phase.
- A phase ends when the next action has a different class. A single *analyse* action between two *edit* actions does not end the edit phase. Each phase that ends in an observable outcome (a reproduction that runs, a test that passes or fails, an edit that is undone by a later *edit* on the same path) becomes one candidate note; phases with no outcome are merged into the next one. Failed phases produce notes too, marked `from_failed_step=true`.

**Extractor.** An LLM call with structured output receives the task description, the phase's commands and the full observations (`extra.raw_output`, not the elided text the agent saw), and the agent's patch. It does **not** receive the harness outcome; `resolved` is joined to the notes afterwards for reporting only. It returns:

```
note:   {note_id, run_id, phase, from_failed_step, advice}
claims: [{claim_id, statement, symbol, file, predicate,
          scope: {inputs, config, env},
          evidence_steps: [step ids whose observation shows the claim],
          kind: "repo_behaviour" | "procedure" | "environment"}]
```

Rules the prompt enforces, in the spirit of the proposal:
- Separate *advice* ("handle the missing-user case explicitly") from *claims* ("`get_user(None)` returns `None` on this backend").
- A claim without an `evidence_steps` pointer is kept but marked `unsupported`; the extractor may not invent evidence.
- Do not strip repository-specific detail: file, symbol and observed values stay in the claim. Abstraction is the advice's job.
- The extractor sees nothing the agent did not see: no gold patch, no `test_patch`, no `hints_text`, no other task, no test outcome.
- The extractor uses the same model as the agent, so the notes are what that agent could itself have written. To bound what one extractor misses, a 20% sample of phases is re-extracted with a second model and the claim-level recall of the primary extractor against the union is reported.

**Human review (the actual Pilot A work).** Two reviewers independently go through every note with a rubric: is each claim (a) specific enough to check, (b) actually supported by the cited step, (c) scoped correctly, (d) a repository-behaviour claim rather than a general procedure? Disagreements are adjudicated (half a day budgeted); agreement (Cohen's κ, computed per claim on the four rubric items) is reported. Reviewers may split or reword claims but must log every change. Reviewers do not open gold patches, test patches, hints, or the public SCB transcripts during WP3.

## 6. Source validity (WP4)

For each claim the reviewers decide where it is true:

| True at source `base_commit` (C0) | True after the official fix (C1 = C0 + gold patch) | True in the agent's final workspace (Ca = C0 + agent patch) | Label |
|---|---|---|---|
| yes | yes | not needed | `repo_history` (pre-existing behaviour) |
| yes | no | not needed | `repo_history_superseded` (true before the fix, changed by it) |
| no | yes | not needed | `repo_history` (behaviour introduced by the merged fix) |
| no | no | yes | `agent_edit_only` (true only in the agent's unmerged patch) |
| no | no | no | `unsupported` (written wrong) |
| no | no | undefined | `agent_edit_only?` (Ca undefined: empty submission, patch does not apply, or claim depends on an untracked file the rebuild lacks); reported separately |
| any cell is a setup failure | | | `inconclusive` |

Ca is not needed for the first three rows because a claim true at C0 or C1 is about repository history whatever the agent later did to its workspace. Claims of kind `environment` (e.g. "pytest must be run with `-p no:cacheprovider` here") are labelled on C0 only and reported as their own group; whether they count towards the thresholds is decision 4 in Section 9. C1 uses the gold `patch` only, never the `test_patch`; the C1 column is the proposal's "supported by the historical repository" read to include the merged fix, and that reading is stated in the report.

**How a cell is decided.** Where an existing pytest node at C0 or a probe of ≤30 lines can answer the claim, it is run inside the task's own image (note the image's Python version; 3.6 for some requests images):

```
docker run --rm -v $PWD/pilot_a/probes:/probes:ro <image> bash -lc \
  'cd /testbed && git apply /probes/<patch-or-none>.diff; python -m pytest -q -x -p no:cacheprovider <node or /probes/<claim_id>.py>'
```

with `<patch>` = nothing for C0, the gold `patch` for C1, the `model_patch` for Ca; 600 s timeout; setup/collection errors recorded separately from assertion failures; exit code and output hash stored in `validity.jsonl` with `method=probe`. Probes call the real symbol; mocking the function under test is disallowed. Where no cheap probe exists, the reviewer decides from the trajectory observation and the two diffs and records `method=manual` with a reason. The share of `manual` cells is reported, because it bounds how much of the pilot's validity labelling is reproducible; if it exceeds 50% the sharing counts of Section 7 are reported with and without manual-labelled claims.

Only `repo_history` claims are eligible for carrying forward to later revisions. The `agent_edit_only` share is itself a result: it measures how much of what an agent "learns" is about code that never existed in the repository.

## 7. Sharing review (WP5)

- Reviewers group `repo_history` claims by **(repository, symbol, predicate, scope)**. Two claims are the same only if all four match; "`get_user`" vs "`get_cached_user`", or the same symbol under different backends, are different claims. Symbols are normalised to `module.qualname` at C0; predicates come from a fixed vocabulary (`returns`, `raises`, `accepts`, `mutates`, `calls`, `type_is`, `default_is`, `other`) written down before review starts; scopes are compared field by field and are compatible when neither contradicts the other.
- Each grouping records a reason, so it can be withdrawn.
- Report, per repository and overall: number of notes; claim occurrences; distinct scoped claims; distinct claims that occur in ≥2 notes; and, separately, (i) ≥2 notes from *different tasks in different PRs* (the case that matters later), (ii) ≥2 notes from tasks flagged `same_text`, (iii) ≥2 runs of the same task, and (iv) the same counts over the control tasks. Threshold (b) in Section 10 uses (i) only.
- A second reviewer re-groups a 30% sample of claim groups (sampled by group, all member claims included) blind; the disagreement rate (groups changed / groups sampled) is reported as the matching-precision baseline that any automatic grouping will later be measured against.
- Uncertainty: the Section 10 percentages are reported with a cluster bootstrap (resampling clusters, 1,000 draws), because claims within a cluster are not independent.

## 8. Work packages

| WP | Title | Outputs | Effort | Owner |
|---|---|---|---|---|
| 0 | Environment | WSL setup script (uv, Docker check, `.wslconfig`); `uv` lockfile (`mini-swe-agent==2.4.6`, `swebench==5.0.2`, `datasets`, `pandas`, `pyarrow`); clone of the SCB harness with our own `requirements.txt` for it; API key in `.env` (git-ignored); litellm price-table check and one temperature-0 call; image pull script for the 24 (+5) images; **gold gate** for every selected task in both harnesses; smoke test = one full agent run on one task, harness evaluation of its patch, one probe run at C0 and C1 | 2 days | user |
| 1 | Instance files | `pilot_a/instances/<set>/instances.jsonl` with `image_name`; `pilot_a/clusters.csv` (the fixed selection, with `same_pr_group`, `same_text`, `role`); `pilot_a/data/same_pr_groups.csv` | 0.5 day | user |
| 2 | Agent runs + outcomes | `runs/<model>/<run>/<id>/<id>.traj.json`, `preds.json`, harness results, workspace records, env fingerprints | 2 days wall-clock, mostly unattended | user |
| 3 | Note and claim extraction | phase segmenter with edge-case file, extractor prompt (versioned), `notes_raw.jsonl`, `claims_raw.jsonl`, second-model sample, then reviewed versions; rubric; κ; adjudication log | 4.5 days incl. review and adjudication | Nicholas + Johnny |
| 4 | Source validity | `validity.jsonl` with C0/C1/Ca per claim; probe scripts; share of manual cells; about 3 container runs per probed claim on the WSL machine | 2.5 days | OCEAN + user |
| 5 | Sharing review | claim groups with reasons; the counts of Section 7 incl. controls; blind re-grouping sample; bootstrap | 2 days | Robin + Nicholas |
| 6 | Report | `pilot_a/report.md`: checkable share, source-validity split, sharing counts (i)–(iv), failed-step notes, cost per task, examples of good and bad notes; recommendation on the claim family to pursue and on which tasks' notes to carry into the revision study | 1 day | user |

## 9. Decisions needed from the team

1. **Backbone model** for agent and extractor (one model, pinned for the whole project), the second extractor model for the 20% sample, and the budget for 1 vs 3 runs. **Needed by the end of week 0; nothing after WP1 can start without the API key.** If `claude-sonnet-4-5` is chosen, note that the public SCB transcripts for all 13 selected experience tasks (8 cluster tasks and the 5 controls) come from the same model.
2. Accept the **5 clusters (19 tasks) + 5 controls** or add S2.
3. **Reviewers**: two for notes/claims (WP3), two for sharing (WP5). Nicholas appears in both; rule: a WP5 reviewer does not group claims from clusters whose notes they reviewed in WP3 (split clusters between the two WP5 reviewers accordingly). Reviewers do not read gold patches, test patches, hints or the public transcripts until WP4, and WP4 reviewers who have seen gold patches do not do WP5 grouping for those clusters.
4. Whether `environment`-kind claims count towards the Section 10 thresholds or are logged only.
5. The **go/no-go thresholds** (Section 10) are fixed, without "~", at the week-1 meeting, before WP3 starts and before anyone has read extractor output beyond the 3 smoke-test trajectories.

## 10. Timeline and go/no-go

| Week | Milestones |
|---|---|
| 0 | Backbone decision and API key; WP0 incl. gold gate |
| 1 | WP1; smoke run; all 24 tasks run once; harness outcomes; extractor prompt drafted on 3 trajectories; thresholds fixed |
| 2 | WP3 extraction + review complete; WP4 source validity for all claims |
| 3 | WP5 sharing review; extra runs if budgeted; WP6 report; team meeting |

Placeholders to fix in week 1 (the proposal's X and Y): continue to the revision study if (a) at least 30% of reviewed notes carry ≥1 `repo_history` claim that is checkable, (b) at least 15% of distinct scoped claims occur in notes from ≥2 different tasks in different PRs, **and** that rate exceeds the control-set rate by its bootstrap interval, and (c) the sharing-review disagreement rate is at most 20%, so that "same claim" is a well-defined notion. A pre-registered secondary analysis recounts (b) restricted to API return/exception behaviour claims; it is reported alongside the primary count whatever the primary result, and does not replace it.

## 11. Storage layout

```
pilot_a/
  data/                                  parquet files, lite_pairs.csv, lite_task_file_overlap.csv, same_pr_groups.csv
  data/revision_pairs/                   git-ancestry tables for the later revision study
  instances/<set>/instances.jsonl        one directory per run set (mini-swe-agent needs a directory)
  clusters.csv                           the fixed selection
  env/<image>.json                       digest, HEAD, base_commit, python, pip-freeze hash
  env/gold_gate.jsonl                    gold + test patch result per task
  runs/<model>/<run>/<instance_id>/<instance_id>.traj.json
  runs/<model>/<run>/preds.json, exit_statuses_*.yaml, eval/results.json
  workspaces/<run_id>/{diff.stat, untracked.txt, last_test.log}
  notes_raw.jsonl, claims_raw.jsonl      extractor output, never edited
  notes_second.jsonl                     second-model sample
  notes.jsonl, claims.jsonl              after review, with change log
  probes/<claim_id>.py, probes/*.diff
  validity.jsonl                         {claim_id, C0, C1, Ca, label, method, reviewer, reason}
  sharing/groups.jsonl, sharing/blind_sample.jsonl, sharing/bootstrap.json
  report.md
```

Everything lives outside any checked-out repository; one run id per experiment; nothing is overwritten.

## 12. Change log, v1 (2026-10-19) → v2 (2026-10-20)

Sources: the 2026-10-19 audit (A, by fact or flaw number) and the 2026-10-20 review of that audit (R, by section). Items marked "both" were raised by the audit and confirmed by the review.

| # | Section | Change | Motivated by |
|---|---|---|---|
| 1 | 3, 3.1 | Same-PR rule added; K1 replaced by the `validation.py` cluster; 22706, 16953, 3481, 32450 removed; D2 dropped; "same-commit pairs" category removed | A blocker 1, flaw 1; R §4 (all 27 same-commit pairs are same-PR), R §6 items 1–3 |
| 2 | 3, 3.1, 7, 10 | Control set of five unrelated tasks; threshold (b) must beat the control rate | R §6 item 5 |
| 3 | 3.1, 4 | `psf__requests-2344` excluded (gold is Python-2 code in a Python 3.6 image); 2148 added to R1 | A fact 46, blocker 3; R §5 item 1 (cause corrected) |
| 4 | 3.1, 7 | `same_text` flag for 22686/22711 and 3359/3362; counted separately, not as duplicates | R §4, §5 item 3 |
| 5 | 3 | Ordered-pair information stated as informational only; counts corrected to 73 / 100 distinct; D1 has three ordered pairs among the surviving six (was "three" of four with 32450) | A facts 40, 44, flaw 11 |
| 6 | 2, 4, 11 | `--subset` takes a directory; instances live in `pilot_a/instances/<set>/` | A fact 17 (both) |
| 7 | 2, 4 | Experience tasks graded with `swebench eval lite` against the official dataset | A fact 27 (both); R §8 (`lite` resolved by the harness loader) |
| 8 | 2, 4, 8 | SCB harness called directly with `--no-remove-instance-image`; own dependency list because `environment.yml` is HTML; no licence noted | A fact 29 (both) |
| 9 | 2, 4, 6 | Diff and fingerprint against `base_commit`, not HEAD (mode-only "SWE-bench" commit) | A fact 15 (both); R §5 item 6 (severity) |
| 10 | 2, 4 | Timeout 60 s; image sizes corrected; 2-hour container lifetime; re-run skip behaviour; unregistered-model behaviour | A facts 11, 20, 23, 25; R §3 |
| 11 | 4, 9 | Temperature passed explicitly; "seeds" renamed repeated runs and described as a variance measure | A flaw 9; R §5 item 10 |
| 12 | 4, 8 | Gold gate in WP0 for every selected task | A blocker 3, missing pieces |
| 13 | 5 | Extractor no longer receives the harness outcome; reads full `raw_output` | A assumption 8, flaw 5; R §5 item 11 |
| 14 | 5 | Segmentation rule made concrete (classes, chained commands, multiple tool calls, edge-case file) | A flaw 6 (confirmed: `parallel_tool_calls: true`) |
| 15 | 5 | Subtask-Level Memory citation reworded; second-model 20% re-extraction to bound extractor misses | A flaw 7; R §5 item 12 |
| 16 | 6 | Ca-undefined row; environment claims handled explicitly; C1 reading of the proposal stated; manual-share cap | A flaw 4, flaw 10; R §5 items 7–8 |
| 17 | 7 | Sharing key definitions (symbol normalisation, predicate vocabulary, scope compatibility); 30% sample unit; cluster bootstrap | A flaw 8, missing pieces |
| 18 | 2, 9 | Public SCB transcripts recorded, embargoed for reviewers, same-model risk noted | A fact 6, blocker 4; R §6 item 7 |
| 19 | 9 | Blinding rules rewritten so they bind the human reviewers; backbone decision given a date | A flaw 5, flaw 12 |
| 20 | 10 | Thresholds without "~", fixed in week 1; "narrow and re-count" turned into a pre-registered secondary analysis | A flaw 8; R §6 item 6 |
| 21 | 8 | WP0 at 2 days (harness installs, uv in WSL, gold gate); WP3 adjudication time; WP4 container load noted | A flaw 12, assumption 13 |
| 22 | 2 | Distinct counts (357 related tasks, 360 pairs); Git Bash path-conversion note | R §6 items 10–11, §8 |
