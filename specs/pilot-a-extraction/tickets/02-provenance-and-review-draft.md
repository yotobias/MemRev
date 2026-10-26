# 02: Preserve extraction provenance and prepare review

**Status:** done
**Blocked by:** 01

## Scope

Turn validated raw extraction plus operator-supplied metadata into a portable acquisition package with stable occurrence IDs, immutable input snapshots, and a separate pending review draft. Implement V36–V38. This is preparation for human review, not review sign-off, source-validity evaluation, sharing, or Pilot B export.

## Acceptance criteria

- [x] A CLI prepares a package for the user's saved five-lesson development response.
- [x] Inputs are validated and snapshotted without changing their bytes; each snapshot has a SHA-256 fingerprint.
- [x] IDs are deterministic from extraction-run identity, trajectory/response bytes, and original list positions; moving files or correcting descriptive metadata does not change IDs.
- [x] Unknown metadata remains null; production provenance requires known task/repository/source, agent run, exact extractor model and saved prompt. This checks completeness and syntax, not independent truth or dataset eligibility.
- [x] A mismatching trajectory task ID, malformed metadata, or a prompt containing a different rendered trajectory is rejected.
- [x] Preparing identical inputs twice preserves an existing review draft; changed inputs cannot overwrite an existing package.
- [x] The review draft starts pending, retains original content and IDs, and provides separate places for decisions, reviewer, reason, edits and split proposals.
- [x] Tests exercise saved artifacts, identity stability, input changes, missing metadata and preservation of human work.

## Notes

Owner: Codex, implementing the user's requested next step. Use a new output directory; V39 permits gitignored `runs/acquisitions/` inside MemRev, superseding the original external-directory restriction. No inference calls, gold inspection, automatic review decisions, source-code execution or Pilot B export.

Validation: `PYTHONPATH=src .venv/bin/python -m pytest -q tests` — 69 passed. The CLI prepared 5 lessons and 17 assumptions in `../pilot-a-artifacts/astropy-manual-102526/`. See `pilot-a/PROVENANCE.md` for commands, metadata meaning and the review-draft workflow. The curated fixture had already been restored when work started and was left intact.
