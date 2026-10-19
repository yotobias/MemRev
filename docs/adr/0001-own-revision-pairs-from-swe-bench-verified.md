# 0001 — Build our own revision pairs from SWE-bench Verified

The proposal names SWE-ContextBench (arXiv 2602.08316) as the source of related task sequences, but as of 2026-10-19 its data is not publicly released, and EvoArena's coding split is unreleased and mostly Go. Pilot B therefore builds its own revision pairs from SWE-bench Verified Python instances: S and T are `base_commit`s of two instances in the same repository and SWE-bench version, and S must be a git ancestor of T.

## Considered options

- Wait for SWE-ContextBench data: blocks the pilot on an unanswered email.
- EvoArena SWE-Chain-Evo: unreleased, 82% Go.
- Arbitrary commit pairs with rebuilt environments (Repo2Run, SWE-rebench): more coverage, but environment drift would mix install failures into labels.

## Consequences

- Pairs share one Docker image, which limits how far apart S and T can be.
- The paper must state that the pilot data departs from the proposal's named source.
- If SWE-ContextBench data arrives, its related-task groups can replace or supplement these pairs using the same ancestry and drift checks.
