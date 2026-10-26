# Pilot A runbook

Run commands from the repository root on Linux or WSL. The fixture workflow needs no Docker, API key or human review. Real trajectory generation has additional prerequisites; see step 3.

**Status: Lane N's offline tools are implemented; Lane N and Pilot A are not complete.** Production integration, real reviews/checks/grouping and the final report remain. See [completion status and remaining work](README.md#completion-status).

## 1. Set up

Use the Python version in `.python-version` and uv compatible with `uv.lock`.

```bash
export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
uv sync --locked
source .venv/bin/activate
export PYTHONPATH="$PWD/src"
python -m pytest -q
```

Repeat activation and `PYTHONPATH` setup in each new shell. If locked installation fails, align uv/Python with the project setup; do not regenerate the lockfile just to bypass it.

## 2. Run the offline example

Preserve the tracked example's trajectory, extraction and metadata:

```bash
pilot_acquisition=runs/acquisitions/demo
python -m memrev.provenance \
  --trajectory pilot-a/fixtures/test/full_trajectory_example.traj.json \
  --extraction pilot-a/fixtures/test/gpt-6-high_test_lessons_102526.json \
  --metadata pilot-a/fixtures/test/gpt-6-high_test_lessons_102526.metadata.json \
  --output-dir "$pilot_acquisition"

python -m memrev.handoff build \
  --acquisition "$pilot_acquisition" \
  --output-dir runs/handoffs/demo
```

Open `runs/handoffs/demo/report.md`. Expected: **5 lessons, 17 assumptions, 51 pending validity cells and 17 pending sharing decisions**. All five lessons are excluded from the B draft because the fixture lacks required provenance. This is expected.

**Stop here for a software/interface demonstration.** The remaining steps are for real data and later research work.

## 3. Obtain a real trajectory — Lane R

Before launching, confirm Docker access, selected images, credentials, model access and budget. Implement/test final-workspace capture before the full batch; submitted patches alone are insufficient for Ca reconstruction. See [RUN_READINESS.md](RUN_READINESS.md).

Once ready and authorized, the existing launcher is:

```bash
bash pilot-a/scripts/run_agent.sh main claude-sonnet-5-5 main-1 2
```

Use a fresh run name. Lane R supplies trajectories, run metadata and preserved workspaces. Agent outputs live under `pilot-a/runs/`.

## 4. Extract and preserve lessons — Lane N

Replace uppercase placeholders with your paths/IDs. Render the prompt:

```bash
python -m memrev.trajectory \
  --trajectory PATH_TO_TRAJECTORY \
  --output runs/prompts/TASK_RUN_ID.txt
```

Submit that exact prompt to the agreed extractor. Save its response as plain JSON, without Markdown fences. Extraction is currently manual; no paid API batch driver is implemented.

Create metadata using [the fixture metadata](fixtures/test/gpt-6-high_test_lessons_102526.metadata.json) as a template. For production, set `purpose` to `pilot_a` and supply the extraction-run ID, agent-run ID, task, repository, source SHA and actual extractor provider/model. Record extractor usage/cost when known; do not substitute agent-run usage.

```bash
pilot_acquisition=runs/acquisitions/TASK_RUN_ID
python -m memrev.provenance \
  --trajectory PATH_TO_TRAJECTORY \
  --extraction PATH_TO_EXTRACTION_JSON \
  --metadata PATH_TO_METADATA_JSON \
  --prompt runs/prompts/TASK_RUN_ID.txt \
  --output-dir "$pilot_acquisition"
```

This validates structure and creates `record.json` plus input snapshots. Keep those originals unchanged. Use a new directory for changed inputs. Details: [PROVENANCE.md](PROVENANCE.md).

## 5. Review when scheduled — Lane N

To defer review, run `handoff build` as in step 2 and leave forms pending. Otherwise create a form, replacing the reviewer details with accurate attribution:

```bash
python -m memrev.evaluation draft \
  --package "$pilot_acquisition" \
  --output "$pilot_acquisition/evaluation.json" \
  --reviewer-id YOUR_ID --reviewer-type human \
  --note 'Describe your review process here.'
```

Complete ratings, outcomes and reasons using [EVALUATION.md](EVALUATION.md). Use `human_ai_assisted` when applicable. Do not edit original text or IDs. Then import the completed form into a handoff:

```bash
python -m memrev.handoff build \
  --acquisition "$pilot_acquisition" \
  --evaluation "$pilot_acquisition/evaluation.json" \
  --output-dir runs/handoffs/reviewed
```

For multiple acquisitions, repeat `--acquisition` and supply evaluations with repeated `--evaluation`. Keep development and production collections separate.

## 6. Return validity results — Lane R

Send `runs/handoffs/reviewed/lane-r/` together with its sibling `acquisitions/`. Agree the proposed return format before use. Lane R completes `validity.pending.json` from actual checks or documented assessments and saves the return as `runs/returns/validity.json`. The real check runner remains unfinished; the importer does not execute checks.

```bash
python -m memrev.handoff build \
  --acquisition "$pilot_acquisition" \
  --evaluation "$pilot_acquisition/evaluation.json" \
  --validity runs/returns/validity.json \
  --output-dir runs/handoffs/with-validity
```

Preserve the same acquisition/evaluation set on subsequent builds. A changed set or review invalidates earlier returns. Lane N must not open gold patches, gold-test logs, hints or public benchmark transcripts.

## 7. Group assumptions and check consistency

Lane N fills `runs/handoffs/with-validity/sharing/pending.json` with groups and reasons, saving it as `runs/returns/sharing.json`. See [grouping rules](HANDOFF.md#sharing-when-judgments-are-available).

```bash
python -m memrev.handoff build \
  --acquisition "$pilot_acquisition" \
  --evaluation "$pilot_acquisition/evaluation.json" \
  --validity runs/returns/validity.json \
  --sharing runs/returns/sharing.json \
  --output-dir runs/handoffs/grouped

python -m memrev.handoff sample \
  --bundle runs/handoffs/grouped --seed TEAM_AGREED_SEED \
  --output-dir runs/handoffs/sample
```

Sampling requires completed primary grouping and at least one group. Send **only `sample/blind/`** to the second reviewer; keep `private/` and the sample manifest private. They complete the form and disclose gold exposure. Compare the returned form:

```bash
python -m memrev.handoff compare \
  --sample runs/handoffs/sample \
  --response PATH_TO_COMPLETED_REGROUPING_JSON \
  --output-dir runs/handoffs/comparison
```

## 8. Hand over outputs

| Recipient | Files |
|---|---|
| Lane R | `lane-r/` and sibling `acquisitions/` |
| Pilot B | `pilot-b/` and sibling `acquisitions/`, preserving relative paths |
| Research report owner | `report.md`, `report.json`, grouping and comparison outputs |

Pilot B's `lessons.draft.jsonl` uses proposed field names. Check `pilot-b/status.json` for exclusions and review status. Agree the schema with B before production import; a draft export does not require A's human review or certify source validity.

Both output locations (`runs/` and `pilot-a/runs/`) are gitignored: transfer artifacts separately from code. Preserve snapshots and manifests. Identical builds can reuse their output; changed results need a new directory. Form and prompt commands refuse to overwrite files.

For field definitions and design decisions, see [HANDOFF.md](HANDOFF.md). For project status, see [README.md](README.md).
