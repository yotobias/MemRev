# Pilot A main-3 input draft for Pilot B

Open `handoff/pilot-b/lessons.draft.jsonl` (16 lessons), `handoff/pilot-b/status.json` and `handoff/report.md`.
Keep this directory intact: trajectory pointers resolve relative to the JSONL directory.

Reviews are AI-only, same-session and non-independent. Exact serving model and usage/cost are unknown. One focused lesson per task was retained, not exhaustive extraction yield. No fresh repository checks were executed.

Read `readiness.json` and `review_policy.md` for limitations: six non-Verified tasks, reported upstream-fix recall, replay/patch differences, test edits and pending B policy agreement. A has 96 pending validity cells and 32 pending sharing rows. This is a producer draft, not B acceptance or completed research.

`prepared/` preserves run metadata, selection, original trajectories, prompts and replay reports. Replay reports are not captured filesystems. `verification_commands.json` identifies recorded commands for Lane R; some combine edits with checks and must not be blindly executed as probes.

`manifest.json` inventories the SHA-256 of each delivery file. Nested prepared/handoff manifests remain intact. No gold files or credentials are included.
