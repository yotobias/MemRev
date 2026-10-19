# 02: Revision pairs

**Status:** done
**Blocked by:** 01
**Estimate:** ~80k tokens

## What to build
A researcher can build revision pairs for a repository from SWE-bench Verified metadata. For each source revision, up to 3 targets are chosen in the same SWE-bench version (nearest later instance, middle, furthest), and only targets that S is a git ancestor of are kept. Everything not paired is recorded with its exclusion reason.

Covers stories 4, 5, 6. Decisions V11, V13, V24, ADR 0001.

## Acceptance criteria
- [x] A `pairs` stage loads SWE-bench Verified instances for a repository and records revision pairs in the run.
- [x] S and T are always base_commits in the same repository and SWE-bench version, and S is a git ancestor of T.
- [x] Per source revision at most 3 targets are chosen: nearest, middle and furthest later instance.
- [x] Exclusions are recorded and counted with reasons "no target", "ancestry failed" and "cross-version".
- [x] Tests (seam N1) use a tiny real git repository built in the test with fake instance metadata.

## Notes
- Research: docs/research/swe-bench-verified.md and data/swe-bench-verified-meta.jsonl (django/sympy/scikit-learn metadata, 338 rows). `created_at` is the PR opening date, not the base_commit date; order by committer date of base_commit and confirm with `git merge-base --is-ancestor`. Django 1.11 and 2.2 have one instance each, so they never form a pair. Blob:none clone notes: docs/research/django-clone.md.

Built by an AI agent (Claude Code), test-first on seam N1.

**Command**
- `uv run memrev --run <run-dir> pairs [--meta <meta.jsonl>]`. `--meta` defaults to `data/swe-bench-verified-meta.jsonl`. Stdout: `pairs: N revision pairs from M source revisions, K excluded`, then one `  <reason>: <count>` line per exclusion reason. Each exclusion is listed on stderr with its detail.
- Runs over every repository mapped in the run that has lessons. Rerunning is idempotent (same pair ids, exclusions upserted, outdated ones cleared).
- On the fixture bank against the real django clone: 36 pairs from 12 sources (all 4.0), 0 ancestry failures, 984 cross-version rows, about 6 s. Opt-in test: `MEMREV_DJANGO_REPO=<clone> uv run pytest`.

**Layout**
- `src/memrev/pairs.py`: the stage. `choose_targets` holds the nearest/middle/furthest rule.
- `src/memrev/swe_bench.py`: `Instance` and `load_instances(path, repository)`, plus `DEFAULT_META`.
- `src/memrev/repository.py`: added `is_ancestor(a, b)` and `commit_times(shas)` (committer timestamps; commits missing from the clone are left out).
- `src/memrev/store.py`: table `revision_pairs` and dataclass `RevisionPair` (`pair_id, repository, version, source_revision, target_revision, source_instance, target_instance, target_role`). Methods: `add_revision_pair`, `remove_revision_pair`, `revision_pairs(repository=None)`, `revision_pair(pair_id)`.
- `tests/test_pairs.py`: a `History` helper that builds a real git repo with one-day-apart committer dates and side branches, and writes fake metadata.

**For downstream tickets (05 drift guard, 09 harness)**
- Read pairs with `RunStore.revision_pairs()` or `revision_pair(pair_id)`. Each row already passed the same-version and ancestry checks; it has not yet passed the drift guard.
- `pair_id` is `<S[:12]>..<T[:12]>`, stable across reruns. A pair's SWE-bench image is determined by `(repository, version)`.
- To drop a pair, record an exclusion with your own stage name and subject `pair <pair_id>` (e.g. stage `drift`, reason "environment unavailable"). Don't delete the row: the pairs stage would recreate it on a rerun. Filter on exclusions when reading.
- Lessons belong to a pair when `lesson.repository == pair.repository and lesson.source_revision == pair.source_revision`.

**Decisions made while building** (small, not grilled)
- Source revisions are the distinct source revisions of the run's lessons, not every SWE-bench instance. Pairs exist only where there are lessons to check, so the drift guard never runs on unused pairs.
- A source's version is the version of the instance whose base_commit equals S. A source that is no instance's base_commit is excluded as "no target" (detail says so). The lesson's `task_id` is not used for this.
- "Later" means a strictly later committer timestamp of the base_commit, ties broken by instance id. The middle target is index `len // 2` of the later same-version instances. With 1 later instance the role is `nearest`; with 2 they are `nearest` and `furthest`.
- Targets are chosen first and then checked for ancestry; a chosen target that fails is excluded as "ancestry failed" and not replaced by another instance.
- Exclusion subjects: `source <S>` for "no target", `pair <pair_id>` for "ancestry failed" and "cross-version".
- "cross-version" is recorded once per later-dated instance in another version of the same repository. Earlier instances are not candidates and aren't recorded. Same-version later instances that are not chosen are not recorded either (V24 chooses only 3).

**Open point for the team**
- The cross-version count is large (984 for the 12 fixture sources, since every later django instance outside 4.0 counts). It is honest but will dominate the exclusion table in the report. If the team prefers one row per source (e.g. "N later instances in other versions"), that is a small change in `_PairBuilder._build_for_source`.

**Gotchas**
- An instance whose base_commit is missing from the clone is silently left out of ordering (it can't be dated). With a full-history clone (blobless is fine) all django base_commits are present.
