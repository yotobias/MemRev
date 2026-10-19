# 07: Real Docker check runner

**Status:** ready-for-agent
**Blocked by:** 05
**Estimate:** ~120k tokens

## What to build
The real implementation of the check-runner interface: it runs checks inside the SWE-bench Docker image for the pair's repository and version, at the requested revision, and turns test output into the runner's outcomes. One slow, opt-in test proves it on a real django pair.

Covers seam N2. Decisions V14, ADR 0001.

**Requires:** Docker Desktop installed on the machine that runs this ticket. SWE-bench images run under emulation on Apple Silicon and are slow; a Linux x86 machine is preferred.

## Acceptance criteria
- [ ] The runner obtains the SWE-bench image for a (repository, version) and reports "environment unavailable" if it can't.
- [ ] It checks out the requested revision in a disposable container and runs the check command.
- [ ] Test results are parsed into pass, fail on the asserted target, harness error, or out of scope.
- [ ] A slow test, skipped unless explicitly enabled, runs one known check at one real django revision pair and gets the expected outcome at S and T.
- [ ] The time per check run is recorded so it can be reported.

## Notes
