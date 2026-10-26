# Development fixtures

These inputs exercise Lane N's implementation. They are not selected Pilot A production tasks or human-reviewed study results.

| File under `test/` | Purpose |
|---|---|
| `full_trajectory_example.traj.json` | Full Astropy trajectory, 78 messages; formatter/extraction/provenance tests |
| `message_only_github_issue.traj.json` | Legacy messages-only trajectory, 22 messages; loader/formatter tests |
| `extraction_v2.json` / `.md` | Small curated schema fixture and its rationale |
| `gpt-6-high_test_lessons_102526.json` | Preserved saved browser response, 5 lessons and 17 assumptions |
| `gpt-6-high_test_lessons_102526.metadata.json` | Known provenance and explicit unknowns for that response |

Generated transcripts, rendered prompts, reviews and handoff bundles belong under root `runs/`. The obsolete rendered transcript was removed; tests generate their own temporary output. For example:

```bash
PYTHONPATH=src .venv/bin/python -m memrev.trajectory \
  --trajectory pilot-a/fixtures/test/full_trajectory_example.traj.json \
  --output runs/prompts/astropy-development.txt \
  --extraction pilot-a/fixtures/test/gpt-6-high_test_lessons_102526.json
```

The command refuses to overwrite existing output. This renders today's template; it is not proof of the prompt previously submitted for the saved response. The exact submitted prompt for that response remains unknown.
