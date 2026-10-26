# 01: Versioned extraction prompt and validation

**Status:** done
**Blocked by:** none

## Acceptance criteria

- [x] The prompt describes the v2 contract and distinguishes evidence from repository behaviour and source validity.
- [x] A saved v2 response can be loaded and validated against the original trajectory without mutation.
- [x] Invalid JSON, malformed fields, unsupported versions, and invalid citations fail clearly; missing-evidence candidates are retained explicitly.
- [x] A curated development fixture demonstrates the new contract; the original model response remains unchanged.
- [x] Focused tests pass alongside the existing formatting tests.
- [x] Documentation records the whole-trajectory choice, provenance boundary, and separate Pilot B export.

## Notes

Owner: Codex, implementing the user's requested contract changes. No model calls or gold data are required.

Validation: `.venv/bin/python -m pytest -q tests` — 54 passed. From the repository root, `python3 src/memrev/trajectory.py` loads the curated v2 fixture and prints `Validated 2 lessons using schema version 2`. This demo uses only the standard library and does not call a model.

The original saved model response is unversioned and intentionally fails v2 validation. Generate new responses with the updated prompt or migrate a copy through review; do not overwrite the original. Run provenance/IDs and Pilot B export remain later steps.
