# 05: Running checks and proposing labels

**Status:** ready-for-agent
**Blocked by:** 02, 03
**Estimate:** ~120k tokens

## What to build
A researcher can run the drift guard on each revision pair and then the check of every reviewed assumption at S and T, 3 times each. Every execution is stored as evidence, and a label is proposed by fixed rules. All runs go through a check-runner interface; this ticket ships a fake runner, the real Docker runner comes in 07.

Covers stories 7, 8, 18, 19, 20, 21, 23. Decisions V3, V14, V15, V20, V21, V27.

## Acceptance criteria
- [ ] The check-runner interface returns pass, fail on the asserted target, harness error, or out of scope, plus raw evidence.
- [ ] The drift guard runs a fixed sanity test set 3 times at S and T; a pair whose sanity tests break or disagree, or whose image or checkout is unavailable, is dropped as "environment unavailable" before any assumption check.
- [ ] Each assumption's check runs 3 times at S; unless all 3 pass, the assumption is recorded as invalid at S and not run at T.
- [ ] Eligible checks run 3 times at T: 3/3 pass → supported within scope; 3/3 fail on the asserted target → contradicted; disagreement or harness error → inconclusive with reason; missing fixture or backend → inconclusive with reason "out of scope at T".
- [ ] Every execution is stored as evidence (revision, command, exit status, output excerpt, run index, time), keyed to the assumption hash.
- [ ] Rerunning the stage reuses evidence for unchanged assumptions.
- [ ] Tests (seam N1) use the fake runner with scripted outcomes.

## Notes
