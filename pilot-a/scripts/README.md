# Pilot A, Lane R scripts

Run everything inside WSL from the project root. Python scripts run in the project venv:
`source pilot-a/scripts/env.sh` once per shell, then `uv run --locked python -I pilot-a/scripts/<script>.py`
(`--locked` refuses to run if `uv.lock` is out of date instead of silently re-resolving).
Outputs go to `pilot-a/`; nothing is overwritten (see `pilot-a/CHANGES.md` for deviations).
Do not edit a shell script while it runs: bash reads scripts as it goes, so the running copy
executes garbled lines (happened once with `build_derived.sh`).

Shared code: `naming.py` (image name and derived tag rules; `build_derived.sh` repeats the tag
rule in bash). Parser test: `uv run --locked python pilot-a/scripts/test_gold_gate.py`.

| Order | Script | Does | Writes |
|---|---|---|---|
| 0 | `setup_wsl.sh` | installs uv 0.12.21, creates `%USERPROFILE%\.wslconfig` (24 GB) if missing, `uv sync --locked` into `~/.venvs/paper2027-pilot-a`, Docker check | venv |
| 1 | `pilot-a/pilot-a/scripts/data_prep/inspect_scb.py pilot-a/data` | downloads the SCB parquet files (not in the repo) | `pilot-a/data/*.parquet` |
| 2 | `build_clusters.py pilot-a/data pilot-a` | same-PR groups over all Lite tasks; writes and checks the frozen 19-task list | `pilot-a/data/same_pr_groups.csv`, `pilot-a/clusters.csv` |
| 3 | `pull_images.sh [id ...]` | pulls each image in `clusters.csv`, calls `fingerprint.sh` | `pilot-a/env/<id>.json`, `<id>.pip-freeze.txt` |
| 3 | `fingerprint.sh <id> <image> <base_commit>` | digest, HEAD vs base, future commits, Python, package import check, pip-freeze hash | `pilot-a/env/<id>.json` |
| 3b | `build_derived.sh <id> <image>` | rebuilds the compiled package in an image whose build was wiped by the history cutoff; saves `pilot-a/<id>:built` | local Docker image |
| 4 | `gold_gate.py [--derived] [--f2p-only] [id ...]` | gold `patch` + `test_patch`, runs the tests, F2P/P2P per test. `--derived` uses `pilot-a/<id>:built` where present; `--f2p-only` restricts sympy `bin/test` to the F2P tests (needed for 16342) | `pilot-a/env/gold_gate.jsonl`, `gold_gate_logs/` |
| 5 | `build_instances.py main` / `smoke <id>` | mini-swe-agent instance file without patch, test, hint or test-name fields; uses a derived image where one exists | `pilot-a/instances/<set>/instances.jsonl` |
| 6–7 | `run_agent.sh <set> <model> <run> [workers]` | runs mini-swe-agent with the shipped config (no `-c`, no temperature), key from `.env`, fresh output directory | `pilot-a/runs/<model>/<run>/` incl. `run_meta.json` |

**Lane N:** do not open `pilot-a/env/gold_gate_logs/`, `pilot-a/env/gold_gate.jsonl` (test names) or the
parquet files (gold patches). `pilot-a/instances/` and the fingerprints are safe.
