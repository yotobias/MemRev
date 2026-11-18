# 06: Automated extraction and separate-model review

**Status:** done
**Blocked by:** 05 (done)
**Owner:** Codex, for Johnny

## Scope

The user authorized automation with configurable providers and model IDs to be chosen later. Reuse imported, frozen trajectories. Add an explicit-execution CLI and a shared model client; preserve the current assistant-session batch. No live model calls are part of implementation testing.

Each task uses a fresh extraction request and a fresh review request. Review receives the full indexed trajectory, original candidates and frozen rubric, without previous ratings or this conversation. The runner assembles original fields and attribution; the model supplies only judgments. Separate contexts are a procedural control, not proof of statistically independent errors.

## Acceptance criteria

- [x] Offline planning verifies the prepared bundle and configuration without credentials or model calls.
- [x] Configurable providers/model IDs, explicit execution, request limits and per-call token limits.
- [x] Validate and preserve raw extraction; evaluate every original candidate without rewriting.
- [x] Preserve exact requests, raw responses, returned model/usage and estimated or unknown cost for both stages.
- [x] Resume completed requests, bound transient retries, report failed/uncertain attempts, reject changed inputs/settings and prevent simultaneous runs into one directory.
- [x] Reject malformed/truncated/refused outputs without silently repairing or resampling judgments.
- [x] Generate a portable handoff and archive only after all selected tasks complete; preserve research-pending labels and limitations.
- [x] Offline integration tests cover completion, negative judgments, failures, resume, integrity and client request isolation; document one-task smoke then full run.

## Research boundaries

No agent reruns, Docker/repository checks, gold inspection, validity labeling, sharing inference or reviewer adjudication. Optional existing targets and a limitations note travel with the delivery. The current main-3 contamination and selection caveats must be carried into any new main-3 batch.

## Completion notes

Implemented `memrev.workflow`, a LiteLLM client, wire schemas/judgment assembly, and persistent request helpers. The client uses the already-locked LiteLLM version, now an explicit dependency. Test-first integration coverage includes real package construction with simulated responses, negative reviews, empty extraction, transient failures, interrupted calls, request caps, same-model aliases, tampering, input changes and output-directory locking.

Validation: **187 tests passed** (26 new); `uv lock --locked --offline` passed; offline planning verified all 16 real main-3 tasks and estimated 32 requests before retries. No live API request or new repository check was performed. Provider/model capability testing remains the user's one-task live smoke after configuration.

Runbook: [AUTOMATION.md](../../../pilot-a/AUTOMATION.md). Example configuration: [workflow.example.json](../../../pilot-a/config/workflow.example.json). The main-3 source caveats are carried separately in [MAIN3_LIMITATIONS.md](../../../pilot-a/MAIN3_LIMITATIONS.md).
