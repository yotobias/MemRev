# Limitations carried into a new main-3 extraction batch

These concern the source trajectories, irrespective of which extractor/reviewer is used. They are separate from the earlier Codex-session extraction results.

- V46/V47 select 16 tasks, including six outside SWE-bench Verified: django-12589, django-16910, sympy-14774, sympy-18057, scikit-learn-10949 and scikit-learn-25638. Pilot B must reconcile its older Verified-only/same-version rules and validate source/target environments. Supplied target records are candidates, not accepted pairs.
- Lane R's 2026-11-16 shared report identifies clear upstream-fix recall in 10/16 tasks, unclear recall in 2, no recall in 3, and no recorded reasoning in 1. This aggregate is reported, not independently reclassified by Lane N. Fresh extraction/review contexts do not remove contamination from the source trajectories.
- `final_workspace.json` describes a previous replay, not a filesystem snapshot. django-14792 submitted only three patch-header lines; django-16910 omitted test edits from its submitted patch. Applying submitted patches alone does not reconstruct every final agent workspace.
- Trajectories record test-expectation edits in django-16910 and sympy-18057. Passing output afterward does not establish success on the unchanged test suite.
- Source SHAs identify original base commits. Observations after edits are attributed separately; they must not be assumed valid at the base commit.
- Lane R reports $0.66 for the source agent run. New extraction/review costs belong to their own run; unknown usage is not zero.
- Extraction review judges candidate quality against recorded evidence. No new repository validity checks, sharing assessment, task-success evaluation or Pilot B acceptance is implied by an automated export.

Source records and decisions: `pilot-a/CHANGES.md`, V46–V50 in `docs/decisions.md`. No gold material is included in the delivery.
