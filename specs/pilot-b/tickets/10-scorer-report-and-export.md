# 10: Scorer, report and export

**Status:** ready-for-agent
**Blocked by:** 06, 08, 09
**Estimate:** ~100k tokens

## What to build
A reader gets one report per run that answers the pilot's questions, and teammates get the dataset as JSONL and CSV. The scorer is the only component that reads labels and the constructed-case mapping.

Covers stories 36, 38, 39, 43. Decisions V22, V23.

## Acceptance criteria
- [ ] Label counts per repository and assumption type, natural and constructed cases always separate.
- [ ] Extraction yield, exclusion counts per exclusion reason, and reviewer agreement where available.
- [ ] Per mechanism: contradicted lessons kept, unnecessary rejection (constructed stale lessons with a matched control only), recheck count in its own column, and cost.
- [ ] Recheck decisions add to cost and count as neither kept nor rejected.
- [ ] `export` writes lessons, assumptions, evidence and final labels as JSONL and CSV.

## Notes
