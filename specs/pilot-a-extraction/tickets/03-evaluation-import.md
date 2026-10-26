# 03: Evaluation-only review export and import

**Status:** done
**Blocked by:** 02

## Scope

Implement V40–V41: export blank evaluation forms and import completed evaluations against verified acquisition inputs. Preserve original candidates and reviewer attribution. No assumption rewriting, final labels, sharing, multi-review adjudication or Pilot B bank export.

## Acceptance criteria

- [x] Blank forms contain the original lesson/assumption IDs and text, the versioned six-criterion rubric, and pending outcomes; no replacement fields.
- [x] The importer verifies input hashes and reconstructs the acquisition record from snapshots before accepting a review.
- [x] Missing, duplicated, foreign or moved-to-another-lesson IDs, modified originals, invalid citations, changed rubric definitions, pending rows and inconsistent outcomes fail before output is written.
- [x] AI, human and AI-assisted human attribution remains explicit; importing AI review never claims human review or source-validity sign-off.
- [x] The bank retains every original lesson and assumption, including context-only, needs-repair and uncertain rows. Summaries are recomputed over the original denominator.
- [x] Imports preserve the exact review input, generate a bank/report with input hashes, and refuse destructive replacement of an existing import.
- [x] The existing evaluation-only AI example imports as development data without editing it.
- [x] Tests cover successful round trips, provenance failures, malformed reviews, attribution, denominator preservation and safe repeated imports.

## Notes

Owner: Codex. Use `runs/acquisitions/<run>/evaluations/<review-name>/` for imports. This development protocol must be frozen with the team before production reviews. Importing one review does not implement a merge/adjudication policy.

Implemented in `src/memrev/evaluation.py` and `evaluation_protocol.json`; acquisition verification is shared with provenance preparation. See `pilot-a/EVALUATION.md` for commands and reviewer instructions. Existing AI example imported to `runs/acquisitions/astropy-manual-102526/evaluations/ai-codex/` without changing the submitted review: 17 assumptions retained (7 usable, 6 repair, 2 uncertain, 2 context-only). Created `evaluation.pending.json` with placeholder reviewer details for the user's next review. All run artifacts are gitignored.

Validation: `PYTHONPATH=src .venv/bin/python -m pytest -q` — 106 passed, including 37 evaluation tests. New tests first failed on the missing module, then passed after implementation. Also exercised both CLI commands against the real development package. No model calls, benchmark execution, gold inspection or source-validity labels.
