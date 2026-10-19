# 06: Label sign-off and lesson labels

**Status:** ready-for-agent
**Blocked by:** 05
**Estimate:** ~80k tokens

## What to build
A reviewer can sign off proposed labels through a CSV, with only the allowed changes. Final assumption labels then roll up into lesson labels. If a second reviewer labels a sample, agreement is reported.

Covers stories 22, 24, 25, 26. Decisions V19, V22, V26.

## Acceptance criteria
- [ ] `label-export` / `label-import` round trip with a required reviewer id.
- [ ] Allowed actions: accept, downgrade to inconclusive, send back for a rewritten check (which returns the assumption to review and rerun). A direct flip between supported within scope and contradicted is rejected.
- [ ] Lesson label: contradicted if any assumption is contradicted, supported within scope only if all are, otherwise inconclusive and excluded from metrics.
- [ ] Lessons with no checkable assumption stay in the bank, are counted, and get no lesson label.
- [ ] With a second reviewer's file for a sample, agreement is reported and disagreements become inconclusive.

## Notes
