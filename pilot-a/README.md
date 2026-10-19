# Pilot A: experience acquisition and source validity

Part 1 of the pilot plan. A fixed agent and backbone model attempt the selected base tasks; we record trajectories, source commits, generated patches, relevant workspace states and execution environments, and turn the outcome into lessons.

This folder is the workspace for Pilot A. It has no spec yet: start with step 1 of the workflow in the [root README](../README.md) (grill the open decisions, record them in [docs/decisions.md](../docs/decisions.md)), then write `specs/pilot-a/spec.md`.

## What Pilot B expects from Pilot A

Pilot B reads lessons as a JSONL file, one lesson per line (decision V1):

| Field | Meaning |
|-------|---------|
| lesson id | Unique id for the lesson |
| lesson text | The advice as the agent wrote it |
| task id | SWE-bench Verified instance id the lesson came from |
| repository | e.g. `django/django` |
| source revision | Commit SHA the lesson was written at |
| trajectory pointer | Path or URL to the recorded trajectory (may be empty for fixtures) |

Extra fields are ignored by Pilot B. The exact field names are fixed in Pilot B ticket 01; check there before producing output.

Lessons should come from SWE-bench Verified Python instances in django, sympy or scikit-learn (decisions V11, V12), so that Pilot B can pair them with later revisions in the same SWE-bench version.

## Open decisions to grill first

- Which agent and backbone model, and how many runs per task.
- One lesson per task or several (lesson granularity).
- Lessons from failed attempts: in or out for the pilot.
- What counts as "supported by the historical repository" versus "depends only on the agent's unmerged edits", and how that is recorded.
- How the manual review of shared assumptions across lessons is done and by whom.
