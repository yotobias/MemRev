# 05: Running checks and proposing labels

**Status:** done
**Blocked by:** 02, 03
**Estimate:** ~120k tokens

## What to build
A researcher can run the drift guard on each revision pair and then the check of every reviewed assumption at S and T, 3 times each. Every execution is stored as evidence, and a label is proposed by fixed rules. All runs go through a check-runner interface; this ticket ships a fake runner, the real Docker runner comes in 07.

Covers stories 7, 8, 18, 19, 20, 21, 23. Decisions V3, V14, V15, V20, V21, V27.

## Acceptance criteria
- [x] The check-runner interface returns pass, fail on the asserted target, harness error, or out of scope, plus raw evidence.
- [x] The drift guard runs a fixed sanity test set 3 times at S and T; a pair whose sanity tests break or disagree, or whose image or checkout is unavailable, is dropped as "environment unavailable" before any assumption check.
- [x] Each assumption's check runs 3 times at S; unless all 3 pass, the assumption is recorded as invalid at S and not run at T.
- [x] Eligible checks run 3 times at T: 3/3 pass → supported within scope; 3/3 fail on the asserted target → contradicted; disagreement or harness error → inconclusive with reason; missing fixture or backend → inconclusive with reason "out of scope at T".
- [x] Every execution is stored as evidence (revision, command, exit status, output excerpt, run index, time), keyed to the assumption hash.
- [x] Rerunning the stage reuses evidence for unchanged assumptions.
- [x] Tests (seam N1) use the fake runner with scripted outcomes.

## Notes

Built by an AI agent (Claude Code), test-first on seam N1 (`tests/test_checks.py`, 19 tests).

**Commands**
- `memrev --run <dir> drift [--runner NAME[=ARG]] [--sanity <file>]`: per revision pair, runs every sanity command 3x at S and 3x at T. Kept only if all runs pass. Otherwise, or if the runner raises `EnvironmentUnavailable`, the pair is dropped: exclusion stage `drift`, subject `pair <pair_id>`, reason "environment unavailable", detail like `T: <command>: pass, fail on asserted target, pass`. Stdout: `drift: N revision pairs guarded, K kept, D dropped (R reused from an earlier run)`. A pair that already has a verdict is not rerun.
- `memrev --run <dir> check [--runner NAME[=ARG]]`: for every reviewed (accepted), checkable assumption, runs its check 3x at the lesson's S and, if it passes 3/3 at S, 3x at T of every pair the drift guard kept. Prints counts at S, proposed labels per label, and reused evidence. Pairs without a drift verdict are skipped and counted ("run `drift` first").
- `--runner` defaults to `docker`, which ticket 07 registers. Until then use `--runner fake=<script.json>`.
- Sanity set: `checks.SANITY_SETS` per repository (django: `utils_tests.test_text`, `test_html` and `test_datastructures` via runtests.py; ticket 07/11 should confirm these labels exist in every version). `--sanity <file>` (one command per line) replaces it. A repository with neither is an error.

**Layout**
- `src/memrev/check_runner.py`: the interface (`Outcome`, `Check`, `Environment`, `RunResult`, `EnvironmentUnavailable`, `CheckRunner` protocol), `FakeCheckRunner` and the runner registry (`register_runner`, `make_runner`).
- `src/memrev/labeller.py`: pure rules. `source_verdict(outcomes)` and `target_label(outcomes)`, plus `Label`. Ticket 06 can add lesson-label aggregation here.
- `src/memrev/evidence.py`: `EvidenceStore(store)`, the tables below. It creates them on first use and registers the three assumption tables as downstream (supersession hook from 03).
- `src/memrev/checks.py`: the two stages. `cli.py` wires them like review (`checks.add_parsers`, `COMMANDS.update`).

**Check-runner interface (for ticket 07)**
```python
class CheckRunner(Protocol):
    def run(self, check: Check, revision: str, environment: Environment, run_index: int) -> RunResult: ...
    def close(self) -> None: ...  # called once at the end of each stage (try/finally)

Check(command, asserted_target)       # shell command run from the repository root
Environment(repository, version, instance_id, repository_path)  # instance_id = the pair's SOURCE instance (shared image rule: always S's image)
RunResult(outcome: Outcome, exit_status: int | None, output: str, detail: str = "")
Outcome: "pass" | "fail on asserted target" | "harness error" | "out of scope"
raise EnvironmentUnavailable(msg)     # image or checkout of `revision` cannot be obtained
```
- Register with `register_runner("docker", factory)`, where `factory(store: RunStore, arg: str | None) -> CheckRunner` and `arg` is the text after `=` in `--runner docker=...`. Import the module that registers it from `cli.py` (or `check_runner.py`) so the default `--runner docker` resolves. Callers don't change.
- The runner decides the outcome itself, using the asserted target: errors on the target are "fail on asserted target", everything else that is broken is "harness error", and a missing fixture/backend is "out of scope". The stage only measures the time (`ran_at`, `duration_seconds`) and keeps the last 2000 characters of `output`.
- `revision` is a full SHA. `repository_path` is the host clone, where `git archive <revision>` gets the source. The runner may cache containers per (environment, revision) across calls and release them in `close()`. Drift checks for a pair come first (S runs, then T runs), followed by assumption checks grouped per assumption.
- Image name: look up `instance_id` in the metadata's `image` column. `Environment` doesn't carry it, so the fake needs no metadata.
- During `check`, `EnvironmentUnavailable` is stored as a "harness error" run, since the drift guard already passed. At S that makes the assumption invalid at S (V20 taken literally).

**Tables (for ticket 06/10)**. Read through `EvidenceStore`, which filters `superseded = 0` unless `include_superseded=True`.
- `evidence` (one row per assumption-check execution): `assumption_id, assumption_hash, side (S|T), revision, pair_id ('' at S), command, asserted_target, run_index (1-3), outcome, exit_status, output_excerpt, detail, ran_at (UTC ISO), duration_seconds, superseded`. PK `(assumption_id, assumption_hash, revision, run_index)`. One S run serves all pairs of the source (they share the image).
- `source_verdicts`: `assumption_id, assumption_hash, revision (S), verdict ('passes at S' | 'invalid at S'), detail ('runs at S: ...'), superseded`. Invalid at S is also an exclusion: stage `check`, subject `assumption <id>`, reason "invalid at S". It is cleared if a later version passes at S.
- `proposed_labels`: `assumption_id, assumption_hash, pair_id, target_revision, label ('supported within scope' | 'contradicted' | 'inconclusive'), reason, superseded, proposed_at`. PK `(assumption_id, assumption_hash, pair_id)`. `reason` is '' unless inconclusive, and then one of `Outcome.HARNESS_ERROR` ("harness error"), `DISAGREEMENT` ("check disagrees with itself") or `OUT_OF_SCOPE_AT_T` ("out of scope at T"). The individual outcomes stay in `evidence`.
- `drift_runs` (`pair_id, side, revision, command, run_index, outcome, exit_status, output_excerpt, detail, ran_at, duration_seconds`) and `drift_verdicts` (`pair_id, verdict 'kept'|'dropped', detail`). These are not keyed to assumptions.
- For 06: "send back for a rewritten check" → `Assumptions.update_content`. The new hash has no evidence, so the next `check` runs it, and the old rows are superseded. A rejected assumption keeps its current rows, so join with `Assumptions.reviewed()`.

**Decisions made while building** (small, not grilled)
- Rule order at T: any harness error → inconclusive "harness error"; otherwise mixed outcomes → "check disagrees with itself"; 3/3 pass → supported; 3/3 fail on target → contradicted; 3/3 out of scope → inconclusive "out of scope at T". "Out of scope at T" is a label reason, not an extra exclusion row, so 10 must not count it twice.
- Any non-pass at S (including a harness error) is invalid at S (V20/ticket wording).
- The drift guard needs every sanity run at S and T to pass, so a sanity test broken at S also drops the pair.
- Uncheckable assumptions are skipped and counted on stdout, with no exclusion row (03/04 own that count).
- Reuse: three stored runs for (id, hash, revision) are reused. A partial set (interrupted stage) is discarded and rerun. Labels and verdicts are recomputed from the evidence on every run.
- The supersession hook only fires for tables registered in the process. `cli.py` imports `checks` → `evidence`, so any `review-import` through the CLI marks evidence superseded.

**Fake runner script** (`--runner fake=<script.json>`)
```json
{"checks": {"<command>": {"<revision or SHA prefix>": "pass" | ["pass", "fail on asserted target", "harness error"]}},
 "unavailable": ["<revision prefix>"],
 "default": "pass"}
```
An outcome can also be `{"outcome": ..., "exit_status": ..., "output": ..., "detail": ...}`. Without a script entry and without a default, a run is a harness error.
