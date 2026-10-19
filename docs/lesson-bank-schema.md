# Lesson-bank schema

The contract between Pilot A (which writes lessons) and Pilot B (which reads them), decision V1. Fixed in Pilot B ticket 01.

A lesson bank is a JSONL file: one JSON object per line, one lesson per object. Blank lines are skipped.

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `lesson_id` | string, non-empty | yes | Unique id for the lesson within the memory bank |
| `lesson_text` | string, non-empty | yes | The advice as the agent wrote it |
| `task_id` | string, non-empty | yes | SWE-bench Verified instance id the lesson came from, e.g. `django__django-14089` |
| `repository` | string, non-empty | yes | Repository as SWE-bench names it, e.g. `django/django` |
| `source_revision` | string, 40 lowercase hex characters | yes | Full commit SHA the lesson was written at (the instance's `base_commit`) |
| `trajectory_pointer` | string, may be `""` | yes (key must be present) | Path or URL to the recorded trajectory; empty for hand-written fixtures |

Extra fields are ignored.

## Example

```json
{"lesson_id": "fixture-django-006", "lesson_text": "OrderedSet defines no __reversed__, so reversed(OrderedSet(...)) raises TypeError.", "task_id": "django__django-14089", "repository": "django/django", "source_revision": "d01709aae21de9cd2565b9c52f32732ea28a2d98", "trajectory_pointer": ""}
```

## Validation on import

`memrev --run <run-dir> import <bank.jsonl>` rejects a line with exclusion reason **invalid lesson input** when:

- it is not a JSON object;
- a field is missing, is not a string, or (except `trajectory_pointer`) is empty;
- `repository` is not mapped to a local clone in the run (`memrev --run <run-dir> init --repo NAME=PATH`);
- `source_revision` is not a full 40-character SHA, or that commit is not present in the local clone;
- `lesson_id` was already imported into the run with different content.

Re-importing a lesson that is already in the run with identical content is a no-op. Every rejected line is stored as an exclusion and listed on stderr; stdout gives the counts per exclusion reason.
