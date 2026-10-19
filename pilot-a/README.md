# Pilot A: experience acquisition and source validity

Part 1 of the pilot plan. A fixed agent and backbone model attempt the selected base tasks; we record trajectories, source commits, generated patches, relevant workspace states and execution environments, and turn the outcome into lessons.

This folder is the workspace for Pilot A. It has no spec yet: start with step 1 of the workflow in the [root README](../README.md) (grill the open decisions, record them in [docs/decisions.md](../docs/decisions.md)), then write `specs/pilot-a/spec.md`.

## What Pilot B expects from Pilot A

Pilot B reads lessons as a JSONL file, one lesson per line (decision V1):

| Field name | Meaning |
|------------|---------|
| `lesson_id` | Unique id for the lesson (non-empty string) |
| `lesson_text` | The advice as the agent wrote it (non-empty string) |
| `task_id` | SWE-bench Verified instance id the lesson came from, e.g. `django__django-14089` |
| `repository` | Repository as SWE-bench names it, e.g. `django/django` |
| `source_revision` | Full 40-character commit SHA the lesson was written at (the instance's `base_commit`) |
| `trajectory_pointer` | Path or URL to the recorded trajectory; the key must be present, the value may be `""` |

All six keys are required on every line; extra fields are ignored by Pilot B. These names were fixed in Pilot B ticket 01. The full contract, with an example and the import validation rules, is in [docs/lesson-bank-schema.md](../docs/lesson-bank-schema.md); a working example bank is [fixtures/django/lessons.jsonl](../fixtures/django/lessons.jsonl).

Lessons should come from SWE-bench Verified Python instances in django, sympy or scikit-learn (decisions V11, V12), so that Pilot B can pair them with later revisions in the same SWE-bench version.

## Open decisions to grill first

- Which agent and backbone model, and how many runs per task.
- One lesson per task or several (lesson granularity).
- Lessons from failed attempts: in or out for the pilot.
- What counts as "supported by the historical repository" versus "depends only on the agent's unmerged edits", and how that is recorded.
- How the manual review of shared assumptions across lessons is done and by whom.
