"""Check runner: runs one check once at one revision inside a pair's environment.

Every execution in the `drift` and `check` stages goes through `CheckRunner.run`. This module
ships the interface and a fake runner with scripted outcomes; the real runner (ticket 07) runs
the check inside the SWE-bench Docker image for the pair's (repository, version) and registers
itself with `register_runner("docker", factory)`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Callable, Protocol

from memrev.store import RunError, RunStore


class Outcome(StrEnum):
    """What one execution of a check says, as decided by the runner."""

    PASS = "pass"
    FAIL_ON_TARGET = "fail on asserted target"  # the check failed or errored on its asserted target
    HARNESS_ERROR = "harness error"  # container, install, timeout, crash, error away from the target
    OUT_OF_SCOPE = "out of scope"  # a fixture or backend the check needs is missing at this revision


@dataclass(frozen=True)
class Check:
    """What to run: a shell command (run from the repository root) and the target it asserts on."""

    command: str
    asserted_target: str


@dataclass(frozen=True)
class Environment:
    """Where to run: the shared environment of one revision pair.

    `instance_id` is the SWE-bench instance whose image is used for both S and T of the pair
    (always the source instance). `repository_path` is the local clone on the host, from which
    the requested revision's source is brought into the container (the image prunes later commits).
    """

    repository: str
    version: str
    instance_id: str
    repository_path: Path


@dataclass(frozen=True)
class RunResult:
    """One execution: the runner's outcome plus the raw evidence behind it."""

    outcome: Outcome
    exit_status: int | None  # None when the command never ran to an exit (e.g. timeout)
    output: str  # raw stdout+stderr; the stage stores an excerpt
    detail: str = ""  # the runner's reason for its outcome, e.g. "ImportError on module.VALUE"


class EnvironmentUnavailable(Exception):
    """The image or the checkout of a revision cannot be obtained; the pair cannot be run at all."""


class CheckRunner(Protocol):
    def run(self, check: Check, revision: str, environment: Environment, run_index: int) -> RunResult:
        """Run `check` once at `revision` (full SHA) in `environment`. `run_index` is 1, 2 or 3.

        Raises EnvironmentUnavailable if the image or the revision's checkout cannot be obtained.
        """

    def close(self) -> None:
        """Release anything held across runs (containers, worktrees). Called once per stage."""


# Fake runner --------------------------------------------------------------


@dataclass
class FakeCheckRunner:
    """Returns scripted outcomes. Script (JSON):

        {"checks": {"<command>": {"<revision>": "<outcome>" | [<outcome per run index>]}},
         "unavailable": ["<revision>", ...],
         "default": "<outcome>"}

    An outcome is an `Outcome` value, or {"outcome": ..., "exit_status": ..., "output": ...}.
    Revisions may be given as a prefix of the SHA. Without a script entry the `default` is used;
    without a default the run is a harness error.
    """

    checks: dict = field(default_factory=dict)
    unavailable: list[str] = field(default_factory=list)
    default: str | None = None

    @classmethod
    def from_file(cls, path: Path) -> FakeCheckRunner:
        try:
            body = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise RunError(f"fake runner script {path}: {exc}") from None
        return cls(body.get("checks", {}), body.get("unavailable", []), body.get("default"))

    def run(self, check: Check, revision: str, environment: Environment, run_index: int) -> RunResult:
        if any(revision.startswith(prefix) for prefix in self.unavailable):
            raise EnvironmentUnavailable(f"fake runner: no checkout of {revision[:12]}")
        scripted = self._scripted(check.command, revision)
        if isinstance(scripted, list):
            scripted = scripted[run_index - 1]
        if scripted is None:
            return RunResult(Outcome.HARNESS_ERROR, None, "fake runner: no scripted outcome", "not scripted")
        if isinstance(scripted, str):
            scripted = {"outcome": scripted}
        outcome = Outcome(scripted["outcome"])
        default_exit = 0 if outcome is Outcome.PASS else 1
        return RunResult(
            outcome,
            scripted.get("exit_status", default_exit),
            scripted.get("output", f"fake {outcome} for {check.command}"),
            scripted.get("detail", ""),
        )

    def _scripted(self, command: str, revision: str):
        for prefix, scripted in self.checks.get(command, {}).items():
            if revision.startswith(prefix):
                return scripted
        return self.default

    def close(self) -> None:
        pass


# Registry -----------------------------------------------------------------

# A factory gets the run store and the text after `=` in `--runner NAME=ARG` (None without `=`).
RunnerFactory = Callable[[RunStore, "str | None"], CheckRunner]
RUNNERS: dict[str, RunnerFactory] = {}


def register_runner(name: str, factory: RunnerFactory) -> None:
    RUNNERS[name] = factory


def _fake_factory(store: RunStore, arg: str | None) -> CheckRunner:
    if not arg:
        raise RunError("the fake runner needs a script: --runner fake=<script.json>")
    return FakeCheckRunner.from_file(Path(arg).expanduser())


register_runner("fake", _fake_factory)


def make_runner(store: RunStore, spec: str) -> CheckRunner:
    """Build the runner named by `--runner NAME[=ARG]`."""
    name, sep, arg = spec.partition("=")
    factory = RUNNERS.get(name)
    if factory is None:
        available = ", ".join(sorted(RUNNERS))
        raise RunError(f'no check runner named "{name}" (available: {available})')
    return factory(store, arg if sep else None)
