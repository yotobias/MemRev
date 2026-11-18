# Automated extraction and review

Run from the repository root on Linux/WSL. The runner automates **prepared trajectories → extraction → separate-model review → validated handoff ZIP**. Lane R's agent runs, repository checks and sharing analysis remain separate. No model runs happen unless `--execute` is supplied.

## 1. Prepare inputs and choose models

Use the existing `runs/pilot-a/main-3/prepared` bundle, or create it from the imported trajectories:

```bash
export PYTHONPATH="$PWD/src"
.venv/bin/python -m memrev.run_import \
  --run-dir runs/trajectories-pilot-A/main-3 \
  --output-dir runs/pilot-a/main-3/prepared

cp pilot-a/config/workflow.example.json runs/pilot-a/main-3-api-config.json
```

Edit the copied configuration. Choose two different model IDs and their LiteLLM provider names; the example providers are editable. Prefer pinned model snapshots when available. Use models that support the full input length and configured output mode. `json_schema` requests strict structured output; `json_object` and `text` are explicit alternatives when a provider lacks schema support. All modes still undergo the same local validation. Unsupported settings fail rather than being silently dropped.

Set the credentials in the environment variables named by `api_key_env`, in your own terminal. The runner does not load `.env` automatically. Do not put keys in the configuration. Optional per-model `temperature` and `reasoning_effort` settings are passed explicitly when present; omit unsupported settings.

`max_calls` counts every started request across both stages and all resumes, including failed/unknown attempts. `max_attempts` bounds attempts per task/stage. Each call has a token limit and timeout. These are request limits, **not a dollar spending guarantee**; use provider-side spending controls if needed. The normal 16-task run needs 32 calls before retries.

## 2. Plan offline

```bash
.venv/bin/python -m memrev.workflow \
  --prepared runs/pilot-a/main-3/prepared \
  --config runs/pilot-a/main-3-api-config.json \
  --limitations pilot-a/MAIN3_LIMITATIONS.md \
  --targets pilot-a/targets.csv \
  --output-dir runs/pilot-a/main-3-api-v1
```

This verifies the prepared hashes, identities and configuration without credentials, API calls or output-directory writes. Placeholder model IDs are permitted for planning but rejected for execution. The limitations note is required; targets are optional. For other datasets, supply the applicable caveats rather than main-3's note.

## 3. Run one task, then resume the full selection

Repeat the command above with:

```bash
  --execute --task django__django-11276
```

Inspect that task's extraction, review and usage. Then repeat the same full command with **`--execute` and without `--task`**. The completed task is verified and reused; it is not called again. Multiple `--task` flags select a subset. A ZIP is created only when the entire prepared selection has completed extraction and review, including valid empty extractions.

## Outputs

| Path under the new output directory | Contents |
|---|---|
| `status.json` | Complete, pending or failed tasks; errors and started-call count |
| `inputs/` | Frozen configuration, implementation hashes, protocol, schemas, dataset caveats and prepared inputs |
| `calls/<task>/<extract-or-review>/<attempt>/` | Exact normalized request, timestamps, raw normalized SDK response, returned model, usage and cost estimate/unknown |
| `tasks/<task>/` | Raw extraction JSON, metadata, pending review form, review prompt and assembled completed review |
| `acquisitions/`, `evaluations/` | Existing validated provenance and evaluation packages |
| `usage.json` | Both stages and all attempts; known estimates and unknown-cost coverage |
| `handoff/` | B lesson bank, review status, report and pending Lane R/sharing forms |
| `pilot-b-delivery.zip`, `.sha256` | Portable delivery with source inputs, model-call evidence and file hashes |

The archive contains prompts, trajectories and model outputs; share through the team's normal research channel. API key values and HTTP headers are not included. New API output directories remain gitignored; only the existing frozen main-3 artifacts are selected for Git tracking. Review the copied `limitations.md` and `handoff/report.md` before sharing. No real model run is included with the implementation tests.

## Failure and resume policy

- Repeating the command with unchanged inputs/settings reuses saved responses and revalidates outputs. Requests are sequential; two processes cannot write the same run concurrently.
- Rate limits, timeouts, connection failures and service-unavailable errors receive bounded retries. Failed attempts remain recorded; timeouts may still have incurred provider charges. Provider error text is suppressed to avoid recording credentials.
- Malformed JSON, invalid IDs/citations, refusal, truncation and inconsistent rubric ratings fail that task. They are not automatically repaired or resampled. Uncertain or unfavorable judgments that pass validation are valid results.
- An interrupted request with no saved result is **unknown**, not assumed uncharged. Inspect provider logs first. `--retry-unknown` permits another bounded attempt and may incur a duplicate charge.
- Changed settings, prompts, source bytes, protocol or implementation need a new run directory and run ID. An existing unrelated directory is never adopted. Keep unsuccessful runs as evidence; do not silently replace candidates or report only favorable attempts.
- Failures produce a nonzero CLI exit code and prevent packaging; other selected tasks still proceed. Successful smoke subsets can exit zero while the full selection remains pending.

## What separate review means

Each stage gets a fresh request. Extraction sees one full trajectory and the frozen extraction prompt. Review sees that trajectory, the original candidates and blank rubric; it does not see old ratings, other tasks or the extraction conversation. The model returns only judgments keyed by IDs; code restores the unchanged originals and supplies attribution.

`reviewer.independent=true` records this separation of contexts, not independent model errors or ground truth. Requested model IDs must differ; identical returned IDs from the same provider are rejected. Provider-reported IDs may still be aliases, so the pipeline does not certify underlying weight snapshots. Shared training knowledge and trajectory contamination remain possible.

The existing assistant-session batch remains a preliminary artifact. Report this new batch separately; the number of lessons is determined by the frozen prompt, not forced to match the earlier 16 lessons or 31/32 review count.

Provider references: [LiteLLM input parameters](https://docs.litellm.ai/docs/completion/input), [structured outputs](https://docs.litellm.ai/docs/completion/json_mode). The adapter uses the version pinned in `uv.lock`; model/provider support must be checked with the chosen model in the one-task smoke run.
