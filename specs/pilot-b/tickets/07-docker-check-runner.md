# 07: Real Docker check runner

**Status:** in-progress
**Blocked by:** 05
**Estimate:** ~120k tokens

## What to build
The real implementation of the check-runner interface: it runs checks inside the SWE-bench Docker image for the pair's repository and version, at the requested revision, and turns test output into the runner's outcomes. One slow, opt-in test proves it on a real django pair.

Covers seam N2. Decisions V14, ADR 0001.

**Requires:** Docker Desktop installed on the machine that runs this ticket. SWE-bench images run under emulation on Apple Silicon and are slow; a Linux x86 machine is preferred.

## Acceptance criteria
- [x] The runner obtains the SWE-bench image for a (repository, version) and reports "environment unavailable" if it can't. (verified against a stand-in docker; real pull pending N2)
- [x] It checks out the requested revision in a disposable container and runs the check command. (verified against a stand-in docker; real image pending N2)
- [x] Test results are parsed into pass, fail on the asserted target, harness error, or out of scope. (verified on django-shaped output; real output pending N2)
- [ ] A slow test, skipped unless explicitly enabled, runs one known check at one real django revision pair and gets the expected outcome at S and T.
- [x] The time per check run is recorded so it can be reported. (the stage stores `duration_seconds` per run; the N2 test also prints it)

## Notes
- Research: docs/research/swe-bench-docker.md. The image's /testbed is reset to the instance's base_commit and later commits are pruned, so T cannot be checked out inside S's image: bring T's source in from the host (`git archive T` or a bind-mounted worktree) and reinstall (`pip install -e .`). Images are amd64-only (~1.15 GB each): always `--platform linux/amd64`, Rosetta on. The dataset's `image`, `log_parser` and `eval_script` fields are in data/swe-bench-verified-meta.jsonl (image + log_parser). Django ≥4.2 test ids look like `test_x (module.Class.test_x)`; some ids are a docstring's first line.

### Status 2026-10-19 (AI agent, Claude Code): built, N2 not yet run

Docker was not running on the build machine, so everything below is verified without a daemon. **Remaining: run the N2 test once Docker Desktop runs (Rosetta on), fix what it shows, then set this ticket to `done`.**

```
MEMREV_DOCKER=1 MEMREV_DJANGO_REPO=/path/to/django-clone uv run pytest tests/test_docker_n2.py -v -s
```
It pulls `swebench/sweb.eval.x86_64.django_1776_django-13809:latest` (~1.15 GB) on first use. Then it checks, in that one image, S = bef6f758 (django__django-13809) and T = 0c42cdf0 (django__django-13925, which contains the fix for 13809):
- the three sanity commands of `checks.SANITY_SETS["django/django"]` pass at S and T;
- a `python -c` probe asserting runserver has no `--skip-checks` passes at S and is "fail on asserted target" at T;
- `admin_scripts.tests.ManageRunserver.test_skip_checks` (added by the fix) is "out of scope" at S and passes at T. This last expectation relies on how unittest reports a missing test method under py3.8 (`_FailedTest` + "has no attribute"); if the real output differs, adjust `outcomes._missing_label`.

**Verified without Docker** (`tests/test_outcomes.py`, 17 tests; `tests/test_docker_runner.py`, 16 tests; seam N1-style, with a stand-in for the docker CLI at the process boundary and the real git):
- Environment unavailable when the docker binary is missing, the daemon is down, the instance has no `image` in the metadata, the image can't be pulled, the revision is missing from the host clone, or the revision doesn't install. A failed install is remembered per (image, revision) and not retried; its container is removed.
- Pull only if `docker image inspect` misses; always `--platform linux/amd64`. The image name is the metadata's `image` column for `Environment.instance_id` (S's instance).
- T's source really comes from `git archive <revision>` on the host clone (checked on the tar fed to `docker exec -i`). Also checked by hand: `git archive` works on the blobless django clone (45 MB tar per revision, fetches blobs over the network, a few seconds).
- One container per (image, revision), reused for the 3 runs, `git reset --hard && git clean -fdq` before each run; at most `containers` (default 4) alive, least recently used removed; `close()` removes all. A run that hangs (subprocess timeout) or hits a docker daemon error is a harness error and its container is replaced.
- `--runner docker` resolves through the CLI (`cli.py` imports `docker_runner`). `drift` with an unavailable docker drops every pair as "environment unavailable".
- Sanity set: `tests/utils_tests/test_text.py`, `test_html.py`, `test_datastructures.py`, `tests/runtests.py` and `tests/test_sqlite.py` exist at the base commit of every one of the 231 django instances in data/swe-bench-verified-meta.jsonl (all versions 1.11-5.0; `git ls-tree` on the clone). No change needed. Whether they pass in every image is for N2/ticket 11.

**Not verified**: anything inside a real container (conda activation, `pip install -e .` after swapping the source, django's real runtests output, run times under emulation).

**Layout**
- `src/memrev/docker_runner.py`: `DockerCheckRunner(settings, process)`, `DockerSettings`, `parse_settings`, registration. Settings via `--runner docker=KEY=VALUE,...` with keys `docker` (binary), `meta` (metadata JSONL, default data/swe-bench-verified-meta.jsonl), `timeout` (seconds per check run, default 900), `containers` (default 4).
- `src/memrev/outcomes.py`: `classify(command, asserted_target, exit_status, output) -> (Outcome, detail)`, pure.

**How a revision gets into the container**: `docker run -d --rm --platform linux/amd64 --label memrev=check-runner <image> sleep infinity`; then one `docker exec -i` gets the tar on stdin, deletes everything in /testbed except `.git`, extracts, commits it inside the container (`memrev <sha>`, so resets go back to it) and runs the install (`INSTALL[repository]`, django: `python -m pip install -e .`, as in SWE-bench, which may need network for build isolation). S is loaded the same way as T, so both go through one code path. Checks run as `{ source /opt/miniconda3/bin/activate && conda activate testbed && cd /testbed && timeout -k 10 <timeout> bash -c '<command>'; } 2>&1` with `LANG=LC_ALL=C.UTF-8`.

**Outcome rules** (decisions made while building, small, not grilled)
- Exit 124 (timeout), 125-127 (not found / not executable), >128 (signal, e.g. a segfault under emulation) and no exit: harness error.
- `runtests.py` commands: statuses parsed like SWE-bench's `parse_log_django` (both `test_x (mod.Class)` and the 4.2+ `test_x (mod.Class.test_x)` forms; docstring ids are resolved through the `FAIL:`/`ERROR:` blocks). No `Ran N tests` line: harness error. A `FAIL` or an `ERROR` in a real test: fail on asserted target, except environment exceptions (OperationalError, OSError, PermissionError, ...) which are harness errors and missing drivers/libraries which are out of scope. A `_FailedTest` for a named label that doesn't exist at the revision ("No module named" / "has no attribute" on a label component): **out of scope** (the check's test is missing, like a missing fixture; V21). A `_FailedTest` that fails to import something else: fail on target if it names the target, else harness error. Every test skipped: out of scope. Precedence: harness error > fail on target > out of scope > pass.
- Other commands: exit 0 pass. With a traceback: missing driver/library (`Error loading X module`, GDAL/GEOS, `No module named` a known optional dependency) out of scope; AssertionError or an exception line naming the target's last identifier (plus the class for a dunder) fail on target; anything else (e.g. settings not configured) harness error. Non-zero exit without a traceback: fail on target.
- The pytest and sympy parsers are not ported (Pilot B is django-only); a pytest command falls under "other commands".
