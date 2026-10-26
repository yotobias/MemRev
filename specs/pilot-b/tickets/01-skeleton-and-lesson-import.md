# 01: Skeleton and lesson import

**Status:** ready-for-agent
**Blocked by:** none, can start now
**Estimate:** ~70k tokens

## What to build
A researcher can create a run and import a lesson-bank JSONL file into it. Valid lessons are stored in the run's own database; invalid ones are rejected with an exclusion reason and counted. A hand-written django fixture bank ships with the repo so the pipeline can run before Pilot A delivers. This ticket also fixes the lesson-bank field names that Pilot A must produce.

Covers stories 1, 2, 3, 41.

## Acceptance criteria
- [ ] A single command-line entry point exists with an `import` stage; the project installs with uv and tests run with pytest.
- [ ] Each run has its own SQLite database and work directory, outside any repository checkout.
- [ ] The lesson-bank schema (lesson id, lesson text, task id, repository, source revision, trajectory pointer) is documented in the repo; extra fields are ignored.
- [ ] Lessons with missing fields, an unknown repository, or a source revision not present in the repository are rejected with exclusion reason "invalid lesson input", and the import prints how many were accepted and rejected per reason.
- [ ] Importing the same file twice does not duplicate lessons.
- [ ] A django fixture bank of at least 10 hand-written lessons at real django commits is included and imports cleanly.
- [ ] pilot-a/README.md is updated with the final field names.

## Notes

Lane N now supplies a draft producer for interface discussion (V44): `lesson_id`, `lesson_text`, `task_id`, `repository`, `source_revision`, `trajectory_pointer`. See `pilot-a/HANDOFF.md`. This ticket still owns final field-name agreement, valid-repository/source-SHA checks and the real B importer. The draft sidecar distinguishes pending/AI/human extraction review; A review does not silently become B sign-off. This proposal does not mark any acceptance criterion complete.
