# Lane R readiness and remaining work

Audit of this checkout, 2026-10-25. **Lane R is not complete. Its basic trajectory launcher exists; final-workspace capture and the validity-check runner are unfinished.** No agent run, paid call, image pull, gold-gate execution or gold-file inspection was performed in this audit.

## Already present

- Frozen selection: 16 tasks in 5 clusters.
- `instances/main/instances.jsonl`: exactly those 16 unique IDs. A key-only audit found no patch, test-patch, hint or F2P/P2P fields.
- All 16 fingerprint JSON files exist. This does not establish local Docker image availability.
- Preparation/image scripts and `scripts/run_agent.sh`.
- The original Lane R handoff reports successful image preparation, gold gates and a smoke run on Ocean's machine. These are historical reported results, not fresh local validation.
- Root `.venv` has mini-swe-agent 2.4.6, litellm 1.106.2, datasets 5.1.0 and mcp 2.3.0, each matching a version in `uv.lock`.

## Before any paid trajectory run

| Item | Observed here | Next action |
|---|---|---|
| Docker | Socket permission denied, including outside the tool sandbox | Fix access on the intended host, then verify the daemon and images. An access failure does not prove images are missing. |
| Credentials | Repository `.env` is absent; no credential contents were read | Configure the ignored `.env` on the run host and verify account/model access. |
| Python environment | Root `.venv` exists; old hardcoded WSL venv is absent | Resolved in `env.sh`: respect an override, otherwise use an existing local or original WSL venv. |
| uv | Local 0.4.24 versus 0.12.21 recorded in the original setup | Align tooling and confirm `uv sync --locked` before launch. Compatibility was not established by this audit. |
| Images | Fingerprints exist; Docker access prevents local inspection | Verify all 16 selected images and their intended fingerprints on the actual run host. |
| Budget | No batch started | Authorize paid runs explicitly. The $3 per-task stopping threshold can be exceeded by the final call; 16 × $3 is an approximate planning amount, not a guaranteed cap. |

Use `source pilot-a/scripts/env.sh` on Linux or WSL. `setup_wsl.sh` configures Windows-side settings and is not the native-Linux setup entry point. On native Linux, select the environment, align uv, run `uv sync --locked`, and configure Docker separately.

After prerequisites and budget authorization, the existing launcher is:

```bash
bash pilot-a/scripts/run_agent.sh main claude-sonnet-5-5 main-1 2
```

The model name is the recorded project configuration, not a fresh provider-availability check. Outputs go to `pilot-a/runs/<model>/<run>/`; every run needs a fresh name. The launcher records metadata, checks images and invokes the shipped agent configuration. It does not preserve the full final workspace.

## Before the full research batch

**Capture the final workspace before container cleanup.** The installed 2.4.6 batch runner saves trajectories and submitted patches. Its default Docker environment uses `--rm`, has a two-hour lifetime and stops containers during cleanup. Submission instructions limit the patch to selected source files and exclude reproduction/helper scripts. Applying that patch afterward cannot guarantee recovery of untracked files, other edits, installed-package changes or the full environment.

Lane R needs a capture/reconstruction mechanism covering tracked changes relative to base, relevant untracked files, workspace identity and environment changes. Validate it on a disposable synthetic or non-pilot case before the batch. Avoid including API credentials in saved images/artifacts. This is needed for reliable Ca evidence even though a basic trajectory can be generated without it.

The older plan's instruction to reconstruct afterward is incomplete unless the necessary inputs were captured first. Neither this repo's launcher nor the inspected installed runner contains that capture hook. A submitted patch is not a complete workspace snapshot.

## Can follow initial trajectory collection

- **Validity-check runner:** execute agreed checks at C0/C1/Ca, distinguish asserted-target failures from setup failures, and retain evidence. Lane N's `validity.py` validates returns; it does not run checks.
- **Interface agreement:** settle workspace identifiers, evidence storage and return semantics using [HANDOFF.md](HANDOFF.md). Detailed gold evidence stays with R. No trajectory review is required to discuss these fields.
- **Production extraction and review:** N can format/extract available trajectories; human evaluation and sharing can be scheduled later.
- **Reporting:** aggregate actual agent/check/container costs, complete sharing consistency review and finalize Pilot B's contract/importer.

The immediate dependency is operational access plus workspace preservation, not filling in Lane N review forms. The full validity runner can be developed while extraction proceeds.
