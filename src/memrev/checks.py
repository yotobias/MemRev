"""Stages `drift` and `check`: the drift guard per revision pair, then each reviewed assumption's
check 3 times at S and (if it passes 3/3 at S) 3 times at every kept target, with proposed labels."""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from memrev.assumptions import Assumption, Assumptions
from memrev.check_runner import (
    Check,
    CheckRunner,
    Environment,
    EnvironmentUnavailable,
    Outcome,
    RunResult,
    make_runner,
)
from memrev.constructed_lessons import ConstructedLessons
from memrev.evidence import DriftRun, Evidence, EvidenceStore, ProposedLabel, SourceVerdict, excerpt
from memrev.labeller import INVALID_AT_S, PASSES_AT_S, Label, source_verdict, target_label
from memrev.store import ExclusionReason, RevisionPair, RunError, RunStore, open_run

RUNS = 3  # V15: every check runs 3 times at S and 3 times at T
DRIFT_STAGE = "drift"
KEPT, DROPPED = "kept", "dropped"

# The fixed sanity test set per repository (V14): stable tests unrelated to any lesson.
# `drift --sanity <file>` replaces it (one command per line), e.g. for a repository not listed here.
_DJANGO_TESTS = "./tests/runtests.py --verbosity 2 --settings=test_sqlite --parallel 1"
SANITY_SETS: dict[str, tuple[str, ...]] = {
    "django/django": (
        f"{_DJANGO_TESTS} utils_tests.test_text",
        f"{_DJANGO_TESTS} utils_tests.test_html",
        f"{_DJANGO_TESTS} utils_tests.test_datastructures",
    ),
}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _timed_run(runner: CheckRunner, check: Check, revision: str, env: Environment, index: int):
    """Run once; returns (result, started_at, duration). EnvironmentUnavailable propagates."""
    started, clock = _now(), time.perf_counter()
    result = runner.run(check, revision, env, index)
    return result, started, time.perf_counter() - clock


def environment_for(store: RunStore, pair: RevisionPair) -> Environment:
    """The pair's shared environment: S's SWE-bench image for both revisions."""
    path = store.repositories().get(pair.repository)
    if path is None:
        raise RunError(f"repository {pair.repository} is not mapped in this run (run `init --repo`)")
    return Environment(pair.repository, pair.version, pair.source_instance, path)


# drift ------------------------------------------------------------------


def _sanity_set(repository: str, override: Path | None) -> tuple[str, ...]:
    if override is not None:
        if not override.is_file():
            raise RunError(f"{override}: no such file")
        commands = tuple(line.strip() for line in override.read_text().splitlines() if line.strip())
        if not commands:
            raise RunError(f"{override}: no sanity commands")
        return commands
    if repository not in SANITY_SETS:
        raise RunError(f"no sanity test set for {repository}; pass one with --sanity <file>")
    return SANITY_SETS[repository]


def _guard_pair(store: RunStore, evidence: EvidenceStore, runner: CheckRunner, pair: RevisionPair, sanity) -> str:
    """Run the sanity set 3 times at S and T; returns "" if the pair is kept, else why it is dropped."""
    env = environment_for(store, pair)
    problems = []
    for side, revision in (("S", pair.source_revision), ("T", pair.target_revision)):
        for command in sanity:
            outcomes = []
            for index in range(1, RUNS + 1):
                try:
                    result, started, duration = _timed_run(runner, Check(command, command), revision, env, index)
                except EnvironmentUnavailable as exc:
                    return f"{side} {revision[:12]}: {exc}"
                evidence.add_drift_run(
                    DriftRun(
                        pair.pair_id, side, revision, command, index, str(result.outcome),
                        result.exit_status, excerpt(result.output), result.detail, started, duration,
                    )
                )  # fmt: skip
                outcomes.append(str(result.outcome))
            if any(o != Outcome.PASS for o in outcomes):
                problems.append(f"{side}: {command}: {', '.join(outcomes)}")
    return "; ".join(problems)


def cmd_drift(args) -> int:
    store = open_run(args)
    evidence = EvidenceStore(store)
    runner = make_runner(store, args.runner)
    decided = evidence.drift_verdicts()
    counts = Counter()
    try:
        for pair in store.revision_pairs():
            if pair.pair_id in decided:
                counts["reused"] += 1
                counts[decided[pair.pair_id]] += 1
                continue
            problem = _guard_pair(store, evidence, runner, pair, _sanity_set(pair.repository, args.sanity))
            verdict = DROPPED if problem else KEPT
            evidence.set_drift_verdict(pair.pair_id, verdict, problem)
            counts[verdict] += 1
            if problem:
                store.record_exclusion(
                    DRIFT_STAGE, f"pair {pair.pair_id}", ExclusionReason.ENVIRONMENT_UNAVAILABLE, problem
                )
                print(f"  dropped pair {pair.pair_id}: {problem}", file=sys.stderr)
    finally:
        runner.close()
    total = counts[KEPT] + counts[DROPPED]
    print(
        f"drift: {total} revision pairs guarded, {counts[KEPT]} kept, {counts[DROPPED]} dropped "
        f"({counts['reused']} reused from an earlier run)"
    )
    return 0


# check ------------------------------------------------------------------

CHECK_STAGE = "check"


class _Checker:
    """Runs (or reuses) one assumption's 3 runs at a revision and turns them into verdicts."""

    def __init__(self, store: RunStore, evidence: EvidenceStore, runner: CheckRunner):
        self.store, self.evidence, self.runner = store, evidence, runner
        self.counts = Counter()

    def outcomes(self, a: Assumption, side: str, revision: str, pair_id: str, env: Environment) -> list[Outcome]:
        """The outcomes of the 3 runs at `revision`; reuses complete earlier evidence for this hash."""
        earlier = self.evidence.runs_at(a.assumption_id, a.hash, revision)
        if len(earlier) == RUNS:
            self.counts[f"reused {side}"] += 1
            return [Outcome(e.outcome) for e in earlier]
        self.evidence.discard_runs_at(a.assumption_id, a.hash, revision)
        check = Check(a.content.check_command, a.content.asserted_target)
        outcomes = []
        for index in range(1, RUNS + 1):
            try:
                result, started, duration = _timed_run(self.runner, check, revision, env, index)
            except EnvironmentUnavailable as exc:  # drift passed, so count it as a harness error
                result = RunResult(Outcome.HARNESS_ERROR, None, str(exc), "environment unavailable")
                started, duration = _now(), 0.0
            self.evidence.add_evidence(
                Evidence(
                    a.assumption_id, a.hash, side, revision, pair_id, check.command, check.asserted_target,
                    index, str(result.outcome), result.exit_status, excerpt(result.output), result.detail,
                    started, duration, False,
                )
            )  # fmt: skip
            outcomes.append(result.outcome)
        return outcomes

    def check_at_source(self, a: Assumption, source: str, env: Environment) -> bool:
        verdict, detail = source_verdict(self.outcomes(a, "S", source, "", env))
        self.evidence.set_source_verdict(SourceVerdict(a.assumption_id, a.hash, source, verdict, detail, False))
        subject = f"assumption {a.assumption_id}"
        if verdict == PASSES_AT_S:
            self.store.clear_exclusion(CHECK_STAGE, subject)
        else:
            self.store.record_exclusion(CHECK_STAGE, subject, ExclusionReason.INVALID_AT_S, detail)
        self.counts[verdict] += 1
        return verdict == PASSES_AT_S

    def check_at_target(self, a: Assumption, pair: RevisionPair, env: Environment) -> None:
        label, reason = target_label(self.outcomes(a, "T", pair.target_revision, pair.pair_id, env))
        self.evidence.set_proposed_label(
            ProposedLabel(a.assumption_id, a.hash, pair.pair_id, pair.target_revision, str(label), reason, False)
        )
        self.counts[str(label)] += 1


def _lesson_and_pairs(store: RunStore, constructed: ConstructedLessons, lesson_id: str):
    """The lesson behind an assumption and the revision pairs to check it at: every pair of a natural
    lesson's source revision, or only the pair a constructed lesson was constructed for."""
    lesson = store.lesson(lesson_id)
    if lesson is not None:
        pairs = store.revision_pairs(lesson.repository)
        return lesson, [p for p in pairs if p.source_revision == lesson.source_revision]
    lesson, pair_id = constructed.get(lesson_id)
    return lesson, [store.revision_pair(pair_id)]


def cmd_check(args) -> int:
    store = open_run(args)
    evidence = EvidenceStore(store)
    drift = evidence.drift_verdicts()
    runner = make_runner(store, args.runner)
    checker = _Checker(store, evidence, runner)
    constructed = ConstructedLessons(store)
    counts = checker.counts
    changed = 0
    try:
        for a in Assumptions(store).reviewed():
            if not a.content.assumption_type.checkable:
                counts["uncheckable"] += 1
                continue
            lesson, pairs = _lesson_and_pairs(store, constructed, a.lesson_id)
            counts["not drift-guarded"] += sum(1 for p in pairs if p.pair_id not in drift)
            kept = [p for p in pairs if drift.get(p.pair_id) == KEPT]
            if not kept:
                counts["no kept pair"] += 1
                continue
            counts["checked"] += 1
            # Every pair of one source shares S's image, so one S run serves them all.
            if checker.check_at_source(a, lesson.source_revision, environment_for(store, kept[0])):
                for pair in kept:
                    checker.check_at_target(a, pair, environment_for(store, pair))
        # Edits and rewrites change constructed assumptions too: decide their gates again (V5, V6).
        from memrev.constructor import redecide_constructed_cases  # constructor builds on this module

        changed = redecide_constructed_cases(store, runner)
    finally:
        runner.close()
    print(
        f"check: {counts['checked']} assumptions checked ({counts['uncheckable']} uncheckable skipped, "
        f"{counts['no kept pair']} without a kept revision pair)"
    )
    print(f"  at S: {counts[PASSES_AT_S]} pass 3/3, {counts[INVALID_AT_S]} invalid at S")
    print("  proposed labels: " + ", ".join(f"{label}: {counts[str(label)]}" for label in Label))
    print(f"  reused evidence: {counts['reused S']} at S, {counts['reused T']} at T")
    if changed:
        print(f"  constructed cases whose gate or control matching changed after edits: {changed}")
    if counts["not drift-guarded"]:
        skipped = counts["not drift-guarded"]
        print(f"  skipped {skipped} assumption-pair(s) whose pair is not drift-guarded yet: run `drift` first")
    return 0


# Wiring -----------------------------------------------------------------

RUNNER_HELP = "check runner NAME[=ARG], e.g. docker, or fake=<script.json> (default: docker)"


def add_parsers(stages: argparse._SubParsersAction) -> None:
    drift = stages.add_parser("drift", help="run the drift guard (sanity tests 3x at S and T) per revision pair")
    drift.add_argument("--runner", default="docker", help=RUNNER_HELP)
    drift.add_argument(
        "--sanity", type=Path, help="file with one sanity test command per line (overrides the built-in set)"
    )

    check = stages.add_parser("check", help="run reviewed assumptions' checks 3x at S and T; propose labels")
    check.add_argument("--runner", default="docker", help=RUNNER_HELP)


COMMANDS = {"drift": cmd_drift, "check": cmd_check}
