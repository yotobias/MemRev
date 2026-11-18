# main-3: Lane N handoff to Pilot B

Updated 2026-11-17. **The producer draft is ready to share. B acceptance and Pilot A's validity/sharing findings are still pending.**

## What is ready

- All 16 V47 tasks imported from `runs/trajectories-pilot-A/main-3`; run instance-file hash verified against `instances/main/instances.jsonl`.
- 16 full-trajectory prompts, acquisition packages and AI evaluations.
- 16 focused lessons, 32 original assumptions: AI review rates 31 usable as extracted and 1 context-only. One primary lesson per task was retained; these counts are not exhaustive extraction yield.
- 16 lines exported to `handoff/pilot-b/lessons.draft.jsonl`, with no provenance exclusions or missing tasks.
- Original inputs, hashes, per-item reviews, replay reports and a verification-command index preserved in the delivery.

## Files to send

Send **`runs/pilot-a/main-3/pilot-b-delivery.zip`**. Its root README explains the layout. Unzip it as a whole; JSONL trajectory pointers resolve relative to the JSONL file's directory.

| Inside the delivery | Purpose |
|---|---|
| `handoff/pilot-b/lessons.draft.jsonl` | Six-field lesson bank for B's importer |
| `handoff/pilot-b/status.json` | Per-lesson review attribution and export status |
| `handoff/acquisitions/` | Original trajectories, prompts, metadata, lessons and AI reviews |
| `handoff/report.md` | Coverage and pending-work counts |
| `prepared/` | Run/selection/instance snapshots, original replay reports and inventory |
| `verification_commands.json` | Recorded verification commands for R to inspect/re-run; no phase segmenter needed |
| `readiness.json` | Machine-readable limitations and consumer decisions |
| `manifest.json` | SHA-256 inventory of delivery files |

The current main-3 trajectories and handoff artifacts, including both ZIP packages, are tracked in Git. Pull the branch to obtain them; no separate transfer is needed for this frozen batch. New runs and private execution evidence remain ignored.

## Review and evidence policy

V48 implements the supervisor's approval of LLM pilot reviews without mandatory human sign-off. This batch was extracted and reviewed in the same Codex session: **AI, non-independent**, with exact serving model, tokens and cost unknown. This departs from the previously pinned Sonnet extractor (V49). The saved full prompt was task context; the session also saw this conversation and Lane R's shared summary. No isolated API run or independent agreement is claimed.

The importer checks structure, provenance and review consistency. An accepted extraction is not a source-validity label. All **96 C0/C1/Ca cells and 32 sharing rows remain pending**; no new repository check was executed. B still applies its own source/target checks and 3/3 criteria. Original candidates survive review, including the context-only item.

## Limitations B must see

1. **Selection:** V46/V47 include six tasks outside Verified: django-12589, django-16910, sympy-14774, sympy-18057, scikit-learn-10949 and scikit-learn-25638. B must reconcile its older Verified-only/same-version rules with this selection and the supplied 25 target records. Target fingerprint/import success does not establish B's drift guard.
2. **Possible contamination:** Lane R reports upstream-fix recall in 10/16 tasks, unclear in 2, no recall in 3, and no recorded reasoning in 1. This is a reported aggregate, not a fresh blinded classification. Gold material was not opened during Lane N processing.
3. **Agent workspace:** `final_workspace.json` describes a replay, not a filesystem snapshot. django-14792 submitted only three patch-header lines; django-16910 omitted test edits from its patch. Reconstruct Ca by replay, not patch application alone. No new replay was executed here.
4. **Changed tests:** recorded trajectories include test-expectation edits (django-16910 and sympy-18057). Passing output afterward is not evidence of passing the unchanged test suite.
5. **Source attribution:** the source SHA is the original base commit. Assumptions observed after edits are explicitly marked; B must not assume they passed at S.
6. **Costs:** Lane R reports $0.66 for main-3. Session extraction/review usage is unknown, not zero. No separate paid model calls were launched in this processing step.

## Reproduce preparation and rebuild from saved responses

From the repository root with dependencies installed:

```bash
export PYTHONPATH="$PWD/src"
.venv/bin/python -m memrev.run_import \
  --run-dir runs/trajectories-pilot-A/main-3 \
  --output-dir runs/pilot-a/main-3/prepared
```

This snapshots the full run and writes prompts; it does not call an LLM or execute trajectory commands. Keep the original bytes. Changed inputs need a new output directory.

Saved responses are under `runs/pilot-a/main-3/responses/<task>/`. Each contains `extraction.json`, `metadata.json`, the pending review form, completed `review.ai.json` and review instructions. Acquisitions and evaluations can be reconstructed with the existing provenance/evaluation CLIs; the full workflow is in [START_HERE.md](START_HERE.md).

Rebuild the B draft from the existing acquisitions/reviews:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
from memrev.handoff import build_handoff
p = Path('runs/pilot-a/main-3')
build_handoff(sorted((p / 'acquisitions').iterdir()), p / 'handoff',
              evaluations=sorted((p / 'responses').glob('*/review.ai.json')))
PY
```

## Next owners

**B:** accept the six field names, validate source SHAs, test relative trajectory pointers and reconcile pair/environment rules. B may begin integration with this draft before A's study is complete.

**R:** use frozen collection IDs to execute scoped checks and retain evidence; inspect the verification-command index, including failed/edited-test runs.

**N:** incorporate validity returns, complete scoped sharing, report uncertainty/contamination and any independent regrouping. See [TASKS.md](TASKS.md).
