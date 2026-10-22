# Pilot A kickoff: a first plan for two people

Status: initial plan, 2026-10-20. For current progress read `pilot-a/README.md` first; decisions taken since this plan are in `pilot-a/CHANGES.md`. `pilot-a/plan/Plan_v2.md` is the detailed reference; Section 11 below lists where v2 is out of date, so do not read v2 cover to cover on day one.

## 1. The project in one paragraph

Coding agents can save lessons from tasks they solved and reuse them later. Repositories keep changing, so a saved lesson can quietly become wrong. Our idea is to split each lesson into *advice* and the concrete *claims* about repository behaviour the advice depends on (for example "`get_user()` returns `None` for a missing id"), each with a scope and a pointer to evidence. After a code change only the affected claims are rechecked, and one check serves every lesson that shares the claim. We call this scoped verification reuse. Before building any of it, four small pilots (A to D in `docs/Final_Proposal_Tex.md`) test whether the opportunity exists in real agent experience. Pilot A is the first and the only one planned so far.

## 2. What Pilot A asks and what it hands over

The question: when one fixed agent solves real tasks, do the lessons we extract from its runs contain concrete, checkable claims about the repository, and do lessons from different tasks rely on the same claim?

Deliverables:

1. **Run records** for 19 tasks: the full trajectory, the source commit, the agent's patch, the final workspace, the execution environment.
2. **Notes** extracted from each run (from steps that worked and steps that failed), each split into advice and claims, every claim pointing at the trajectory step that shows it.
3. **Source validity** per claim: true in the repository's history (at the source commit, or after the official fix), or true only because of the agent's own unmerged edits.
4. **Sharing review**: how often notes from different tasks rely on the same claim under compatible scope, judged by hand and never by wording alone.
5. **Counts** for the later cost pilot: notes, claim occurrences, distinct scoped claims. Plus a list of exclusions and inconclusive cases.

Pilot A has no pass or fail threshold. The proposal decides after Pilots A and B together; a low count is a result, not a failure.

## 3. The pipeline in six steps

```
1 select tasks → 2 run agent → 3 segment + extract → 4 label validity → 5 review sharing → 6 report
   (fixed list)    (mini-swe-agent    (script + LLM,      (probes in the      (by hand, with     (counts +
                    in Docker)         then human review)  task's container)   written reasons)   examples)
```

1. **Select tasks.** Already done on paper (Section 5). 19 real GitHub issues from 5 repositories, chosen so that tasks in one cluster edit the same file. That makes shared claims *possible*; the review decides whether they exist.
2. **Run the agent.** mini-swe-agent, one backbone model, default settings, one run per task, each in its own Docker container. The agent sees only the problem statement. No memory of any kind is given to it.
3. **Segment and extract.** A script cuts each trajectory into phases (analyse, reproduce, edit, verify). An LLM call per phase writes one note: advice plus claims plus evidence pointers. A human then checks every claim against a short rubric: specific enough to check, actually supported by the cited step, scoped correctly, about the repository rather than general procedure.
4. **Label validity.** For each claim: is it true at the source commit (C0), after the official fix (C1), in the agent's own final workspace (Ca)? Where a small probe or an existing test can answer, it is run inside the task's image. Otherwise a reviewer decides from the trajectory and the diffs and says so.
5. **Review sharing.** Group claims by (repository, symbol, predicate, scope). Two claims are the same only if all four match. Every grouping records a reason.
6. **Report.** The counts, the validity split, examples of good and bad notes, cost per task, exclusions, and a recommendation on which claim family to pursue.

## 4. The toolbox

| What | What it is | Why we need it | Where |
|---|---|---|---|
| SWE-ContextBench Lite | 300 "experience" + 99 "related" Python bug-fix tasks from 12 repos, SWE-bench schema (`repo`, `base_commit`, `problem_statement`, `patch`, `test_patch`, tests). MIT. | Source of our 19 tasks and their gold patches | Hugging Face `jiayuanz3/SWEContextBench`, parquet files; downloaded by `pilot-a/pilot-a/scripts/data_prep/inspect_scb.py` into `pilot-a/data/` |
| SWE-ContextBench GitHub repo | 99 related-task JSONs, a fork of the SWE-bench harness, and 300 public Claude Code transcripts of the experience tasks. No licence file. | Related-task metadata and harness. **The transcripts are off limits** to anyone doing review (Section 6). | `github.com/jiayuanz3/SWEContextBench` |
| Docker images, two families | One prebuilt image per task with the repo checked out at `base_commit` in `/testbed`. Related tasks: `jiayuanz3/swecontextbench:<owner>.<repo>-<n>`. Experience tasks: `swebench/sweb.eval.x86_64.<owner>_1776_<repo>-<n>`. 3 to 7 GB each on disk. | Agent runs and probes execute inside them | Docker Hub; about 100 GB for 19 images |
| mini-swe-agent 2.4.6 | A small, fixed coding agent (MIT, Python 3.10+). Runs a task with `mini-extra swebench --subset <dir> ... -o <dir>`, writes one trajectory JSON per task and `preds.json` with the patches. | The agent whose experience we study | PyPI `mini-swe-agent`; docs at mini-swe-agent.com |
| WSL2 Ubuntu + Docker | Docker on this machine lives only inside WSL2. Windows cannot even check out django or matplotlib ("Filename too long"). | Everything that touches repositories or containers runs here | Already installed on the user's machine; set `[wsl2] memory=24GB` in `.wslconfig` |
| uv + Python 3.10+ | Package manager and lockfile | Pin `mini-swe-agent==2.4.6`, `datasets`, `pandas`, `pyarrow` | `uv` exists on Windows; install in WSL |
| LLM API key, one backbone model | Same model for the agent and the extractor | Nothing after setup can start without it | **Decision needed** (Section 8). No key is configured yet |
| SWE-bench harness 5.0.2 (optional) | Grades a patch against the task's tests. Experience tasks grade against the official `SWE-bench/SWE-bench_Lite`; related tasks through the SCB fork. | Not required by the proposal for Pilot A; Pilot D needs it. Do it only if time is left. | PyPI `swebench` |
| Our scripts and data | `pilot-a/pilot-a/scripts/data_prep/` (download, file-overlap clusters, git ancestry) and `pilot-a/data/*.csv` | Task selection is reproducible from them | This repository; see `pilot-a/pilot-a/scripts/data_prep/README.md` |

## 5. The 19 tasks

Five clusters, each a set of distinct GitHub issues editing the same file. Tasks from the same pull request have been removed (SWE-ContextBench splits one PR into several "related" issues; those would be the same lesson twice). "Related" tasks use the `jiayuanz3` images, "experience" tasks the `swebench` images.

| Cluster | Repo / file | Tasks (instance number) | Kind |
|---|---|---|---|
| K1 | scikit-learn `sklearn/utils/validation.py` | 10949 | experience |
| | | 12622, 15093, 25637 | related |
| M1 | matplotlib `lib/matplotlib/widgets.py` | 22711 | experience |
| | | 22482, 22686 | related |
| S1 | sympy `sympy/sets/sets.py`, `fancysets.py` | 16988 | experience |
| | | 16342, 16946 | related |
| R1 | requests `requests/models.py`, `utils.py` | 2148, 3362 | experience |
| | | 3359 | related |
| D1 | django `db/models/query_utils.py`, `sql/query.py` | 14016, 14017, 16910 | experience |
| | | 21204, 34570, 35356 | related |

Full ids follow the pattern `scikit-learn__scikit-learn-10949`, `django__django-14016`, `psf__requests-2148`, `matplotlib__matplotlib-22711`, `sympy__sympy-16988`. Two pairs (22686/22711, 3359/3362) share issue text but sit at different commits with different fixes; they are distinct tasks and are flagged `same_text` so their sharing is counted separately. The list is frozen in `pilot-a/clusters.csv` before the first agent run; any change is logged with a reason.

Budget: 19 runs at the agent's default cost cap of $3 is at most about $57, plus a smaller amount for extraction.

## 6. Splitting the work between two people

Two lanes. The rule that makes the split clean: **the Runs lane is the only one that ever opens gold patches; the Notes lane stays blind to them until the report.** Reviewing notes and grouping claims must not be influenced by knowing the official fix.

| | Lane R: Runs and environment | Lane N: Notes and review |
|---|---|---|
| Owns | WSL and Docker setup, uv lockfile, API key wiring; image pulls; gold gate (does the official fix pass its tests in the image?); instance file; the 19 agent runs; final workspaces and environment fingerprints; running probes at C0 / C1 / Ca and recording results; the C1 column of validity | Reading the trajectories; the phase segmenter script; the extractor prompt and its structured output; the review rubric; reviewing every note and claim; writing probes (a probe tests a claim and needs no gold patch); the C0 column of validity where no probe exists; grouping claims for sharing, with reasons |
| Hands over | Trajectories and patches (end of week 1); validity labels (week 3) | Reviewed claims and probe scripts (week 2); claim groups and counts (week 3) |
| Must not | Group claims for sharing (has seen gold) except as the consistency sample below | Open gold patches, test patches, hints, or the public SCB transcripts before the report |
| Report | Cost, environment, run outcomes, validity split | Checkable share, sharing counts, examples |

Consistency check with two people: after N has grouped all claims, R regroups a 30% sample without seeing N's groups and the disagreement rate is reported. R has seen gold patches by then; the report says so. A proper blind second reviewer is a known compromise of a two-person pilot.

Effort, from the detailed plan: about 5 person-days in Lane R, about 6 in Lane N, spread over three weeks because the lanes depend on each other.

## 7. Timeline

| Week | Lane R | Lane N |
|---|---|---|
| 0 | Backbone model chosen, API key in `.env`; WSL + uv + Docker ready; pull images; gold gate on all 19 | Read Section 9 material; study one public SWE-bench trajectory format (not the SCB transcripts); draft the rubric |
| 1 | Instance file; smoke run on one task; all 19 runs; rebuild final workspaces; fingerprints. Hand over trajectories. | Write the segmenter against the smoke trajectory; draft the extractor prompt on 3 trajectories; log segmenter edge cases |
| 2 | Probe runner (one container run per claim per revision); start probing claims as they arrive; C1 cells | Extract notes for all 19 runs; review every claim; write probes for claims that need one; C0 cells where no probe exists. Hand over claims. |
| 3 | Finish validity; 30% regrouping sample; report sections on cost and runs | Sharing review with reasons; counts; report sections on notes and sharing. Joint report and team meeting |

## 8. Decisions needed before week 1

1. **Backbone model** (one model, pinned for the whole project, for both agent and extractor) and who pays for the key. Note: the public SCB transcripts were made with Claude Sonnet 4.5; choosing the same model is allowed but should be recorded.
2. **Accept the 19 tasks** or swap a cluster. The optional sixth cluster (sympy `printing/latex.py`, 5 tasks) is available if budget allows.
3. **Who takes Lane R and who takes Lane N.** Lane R needs comfort with Docker and shell; Lane N needs patience for reading trajectories and writing prompts.
4. **Harness grading of the agent's patches in Pilot A, or deferred to Pilot D.** Cheap, but not required by the proposal.

## 9. What to read first, in order (about two hours)

1. `docs/Final_Proposal_Tex.md`: Motivation, Research Idea, and the Pilot A paragraph. This is the contract.
2. This document.
3. `pilot-a/plan/Plan_v2.md`, Sections 3 to 7 only, as the detailed reference for your lane. Skip Section 2 (verification table) and Section 12 (change log) on first read; use Section 11 of this document to know what in v2 has changed.
4. `Literature_md/SWE_Context_Bench.md`, Section 2: how the tasks were built and why same-PR duplicates exist.
5. `Literature_md/Structurally Aligned Subtask-Level Memory.md`, Sections 3.2 and 3.5: the four phase categories and the extractor idea we borrow (we keep repository detail that they strip).
6. Lane R only: the mini-swe-agent docs page for `mini-extra swebench`. Lane N only: one mini-swe-agent `.traj.json` from any public run, to learn the message format.

## 10. Pitfalls already hit (so you do not hit them again)

- mini-swe-agent's `--subset` wants a **directory** containing the jsonl, not a file path. It has no seed option; pass temperature with `-c model.model_kwargs.temperature=0`. Re-running into an existing output directory skips finished tasks; use a fresh directory per run.
- Every "same-commit pair" in SWE-ContextBench Lite is the same pull request split in two. Never count sharing between them.
- `psf__requests-2344` is excluded: its gold patch is Python 2 code and the image runs Python 3.6, so the official fix cannot pass. Hence the gold gate for every task before any run.
- In the `swebench` images, HEAD is `base_commit` plus one mode-only "SWE-bench" commit. Diff and fingerprint against `base_commit`, never HEAD.
- Clone and run inside WSL. Windows checkouts of django, matplotlib, sklearn and sphinx fail with "Filename too long".
- Git Bash rewrites `/root/...` arguments to `wsl -e docker` as Windows paths; set `MSYS_NO_PATHCONV=1`.
- The SCB harness deletes each task image after grading unless `--no-remove-instance-image` is passed. Its `environment.yml` is a saved web page, not a real file.
- Cost cap: mini-swe-agent checks the $3 limit before each call, so one run can overshoot by a step. Container lifetime is 2 hours.

## 11. Where this plan departs from `pilot-a/plan/Plan_v2.md`

A review on 2026-10-20 compared v2 against the proposal. The proposal is the authority, and the following apply when v2 says otherwise:

- **Kept, v2 was wrong to drop them:** claims true at C0 but changed by the official fix ("superseded") stay in the sharing review and carry their support revision (C0 or C1) in the label. Claims the agent observed in an intermediate workspace state are labelled by what was observed, not written off as "unsupported".
- **No thresholds, no gate.** v2's go/no-go percentages are removed. Pilot A does not gate Pilot B; the proposal decides after A and B.
- **Cut for the first round:** the control set of unrelated tasks, the optional S2 cluster, three repeated runs per task, second-model re-extraction, double review of every note, the bootstrap, the pre-registered secondary analysis, the separate environment-claim track. Each can return later if the first round shows it is needed.
- **Deferred:** harness grading of agent patches (Pilot D), the git-ancestry revision pairs in `pilot-a/data/revision_pairs/` (Pilots B and D).
- **Added to the report:** exclusions, inconclusive cases, and the cost components that Pilot C will need (extraction, probing, container time).

Everything else in v2 Sections 3 to 7 (selection rules, agent settings, segmentation rule, extractor schema, validity table, sharing key) stands and is the reference for the detailed work.
