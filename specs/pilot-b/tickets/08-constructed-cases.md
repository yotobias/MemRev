# 08: Constructed cases

**Status:** ready-for-agent
**Blocked by:** 04, 06
**Estimate:** ~130k tokens

## What to build
A researcher can generate constructed stale lessons and matched controls for each revision pair, gate them by execution, send them through the same review and sign-off as natural cases, and build a blinded variant memory bank.

Covers stories 27–33. Decisions V4, V5, V6, V29, V30.

## Acceptance criteria
- [ ] Candidates are drafted by the LLM from real behaviour changes in the S..T diff; only the advice is written, the repository is never modified.
- [ ] A pair with no candidate is recorded as "no behaviour change found".
- [ ] A constructed stale lesson is kept only if its check passes 3/3 at S and fails 3/3 at T; others are dropped and counted as "gate failed".
- [ ] Each kept stale lesson gets one matched control, drafted the same way (same file or symbol area, similar length and type, passes 3/3 at S and T); stale lessons without one are counted as "no matched control".
- [ ] Constructed stale lessons and controls go through the review CSV and label sign-off like natural assumptions.
- [ ] The variant memory bank uses opaque ids, the same schema as natural lessons and no provenance field; only the scorer can read the mapping.

## Notes
