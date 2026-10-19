# 02: Revision pairs

**Status:** ready-for-agent
**Blocked by:** 01
**Estimate:** ~80k tokens

## What to build
A researcher can build revision pairs for a repository from SWE-bench Verified metadata. For each source revision, up to 3 targets are chosen in the same SWE-bench version (nearest later instance, middle, furthest), and only targets that S is a git ancestor of are kept. Everything not paired is recorded with its exclusion reason.

Covers stories 4, 5, 6. Decisions V11, V13, V24, ADR 0001.

## Acceptance criteria
- [ ] A `pairs` stage loads SWE-bench Verified instances for a repository and records revision pairs in the run.
- [ ] S and T are always base_commits in the same repository and SWE-bench version, and S is a git ancestor of T.
- [ ] Per source revision at most 3 targets are chosen: nearest, middle and furthest later instance.
- [ ] Exclusions are recorded and counted with reasons "no target", "ancestry failed" and "cross-version".
- [ ] Tests (seam N1) use a tiny real git repository built in the test with fake instance metadata.

## Notes
- Research: docs/research/swe-bench-verified.md and data/swe-bench-verified-meta.jsonl (django/sympy/scikit-learn metadata, 338 rows). `created_at` is the PR opening date, not the base_commit date; order by committer date of base_commit and confirm with `git merge-base --is-ancestor`. Django 1.11 and 2.2 have one instance each, so they never form a pair. Blob:none clone notes: docs/research/django-clone.md.
