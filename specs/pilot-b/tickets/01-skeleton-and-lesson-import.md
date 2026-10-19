# 01: Skeleton and lesson import

**Status:** done
**Blocked by:** none, can start now
**Estimate:** ~70k tokens

## What to build
A researcher can create a run and import a lesson-bank JSONL file into it. Valid lessons are stored in the run's own database; invalid ones are rejected with an exclusion reason and counted. A hand-written django fixture bank ships with the repo so the pipeline can run before Pilot A delivers. This ticket also fixes the lesson-bank field names that Pilot A must produce.

Covers stories 1, 2, 3, 41.

## Acceptance criteria
- [x] A single command-line entry point exists with an `import` stage; the project installs with uv and tests run with pytest.
- [x] Each run has its own SQLite database and work directory, outside any repository checkout.
- [x] The lesson-bank schema (lesson id, lesson text, task id, repository, source revision, trajectory pointer) is documented in the repo; extra fields are ignored.
- [x] Lessons with missing fields, an unknown repository, or a source revision not present in the repository are rejected with exclusion reason "invalid lesson input", and the import prints how many were accepted and rejected per reason.
- [x] Importing the same file twice does not duplicate lessons.
- [x] A django fixture bank of at least 10 hand-written lessons at real django commits is included and imports cleanly.
- [x] pilot-a/README.md is updated with the final field names.

## Notes

Built by an AI agent (Claude Code), test-first on seam N1.

**Commands**
- `uv sync` then `uv run pytest`. Python is pinned to 3.11 (`.python-version`, `requires-python`).
- `uv run memrev --run <run-dir> init --repo django/django=<path-to-clone>`: creates `<run-dir>/run.db` and `<run-dir>/work/`. Rerunning `init` adds or updates repository mappings. `--repo` is repeatable.
- `uv run memrev --run <run-dir> import <bank.jsonl>`: stdout `import: N accepted (M new), K rejected` followed by one `  <reason>: <count>` line per exclusion reason; each rejected line is listed on stderr with its detail.
- Optional fixture check against a real clone: `MEMREV_DJANGO_REPO=<path-to-django-clone> uv run pytest`. Without the variable that test is skipped.

**Layout**
- `src/memrev/cli.py`: the single entry point (console script `memrev`). Stages are subcommands and `--run` is a global option placed before the stage. Add new stages to `COMMANDS`.
- `src/memrev/store.py`: `RunStore` (create/open, schema via `CREATE TABLE IF NOT EXISTS`), `Lesson`, `Exclusion`, and `ExclusionReason`, a StrEnum with every reason code from the spec. Tables: `repositories`, `lessons`, `exclusions` (one row per `(stage, subject)`, upserted).
- `src/memrev/repository.py`: `Repository(path)` git access. It currently has `is_git_repository` and `has_commit`; ticket 02 adds ancestry.
- `src/memrev/lesson_bank.py`: the import stage.
- `tests/conftest.py`: the `tiny_repo` fixture (a real 3-commit git repo in `tmp_path`), `cli` (calls `main([...])` in-process), `run_dir`, `write_bank`, `lesson`.
- Schema doc: `docs/lesson-bank-schema.md`. Fixture bank: `fixtures/django/lessons.jsonl`.

**Decisions made while building** (small, not grilled)
- The repository location is a per-run mapping from name to local clone (`init --repo NAME=PATH`), stored in the run database. Tests point it at the tiny repo.
- `source_revision` must be a full 40-character lowercase SHA. Abbreviated SHAs are rejected so that every stored revision is unambiguous.
- `trajectory_pointer` must be present but may be `""`. The other five fields must be non-empty strings.
- Run isolation: `init` refuses a run directory if it or any parent contains `.git`.
- Exclusion subject: `lesson <id>` when the line has a usable `lesson_id`, otherwise `<bank file name> line <n>`. A lesson id that is re-imported with different content is rejected under its file-and-line subject, and the stored lesson stays. A lesson that is accepted on a later import has its old import exclusion cleared, so exclusion counts don't double-count fixed input.

**Gotchas**
- Git runs with `GIT_NO_LAZY_FETCH=1`. Without it, a blobless or partial clone (`git clone --filter=blob:none`) would go to the network for an unknown SHA instead of failing fast.
- A blobless django clone is enough for import (only commits are needed). Later tickets that read file contents at a revision will trigger blob fetches, or need a full clone.

**Fixture bank SHAs**: 12 lessons, all from SWE-bench Verified django instances in version 4.0 (13809, 13925, 13933, 14017, 14053, 14089, 14122, 14155, 14238, 14315, 14349, 14373). Each `source_revision` is that instance's `base_commit`, taken from the SWE-bench Verified parquet (HF `princeton-nlp/SWE-bench_Verified`, test split). All 12 were verified as present in a local blobless django clone by running the import against it: `MEMREV_DJANGO_REPO=... uv run pytest` gives 0 rejected. Each lesson describes the behaviour before that instance's fix, so the gold patch changes it at a later revision. That makes the lessons useful candidates for contradicted assumptions once ticket 02 pairs them with later 4.0 base_commits.
