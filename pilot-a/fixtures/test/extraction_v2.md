# Curated extraction v2 fixture

`extraction_v2.json` is hand-authored development data derived from `full_trajectory_example.traj.json` (Astropy). It is not a new model response or a production Pilot A result.

- Lesson 1 cites original source inspection at messages 25, 35, and 37. Its recursive-dispatch assumption preserves the early-return condition visible in message 25. Its advice is derived from those successful inspections, hence `from_failed_step: false`.
- Lesson 2 is procedural advice from the failed build at messages 16–17. It deliberately has no repository-behaviour assumptions, rather than treating a past build failure as a transferable assumption. Message 17 reports return code zero while showing a build failure; `from_failed_step: true` describes that observed failure.
- Null scope fields indicate missing detail, not proof that the environment or configuration is irrelevant.

An earlier unversioned browser response was used during development but is not present in this checkout. The saved `gpt-6-high_test_lessons_102526.json` is a separate v2 response. Never add a version field alone to migrate an older response: migration requires reviewing structured scope, kinds, failed-step origin, and semantic qualifications.
