"""Command-line entry point: `memrev --run <run-dir> <stage> ...`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from memrev import checks, constructor, docker_runner, extraction, harness, lesson_bank, pairs, report, review, signoff, swe_bench  # noqa: F401  (docker_runner registers "docker")
from memrev.repository import Repository
from memrev.store import RunError, RunStore


def _parse_repo(value: str) -> tuple[str, Path]:
    name, sep, path = value.partition("=")
    if not sep or not name or not path:
        raise argparse.ArgumentTypeError(f"expected NAME=PATH, got {value!r}")
    return name, Path(path).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memrev", description="MemRev Pilot B pipeline")
    parser.add_argument("--run", required=True, type=Path, help="run directory (outside any repository checkout)")
    stages = parser.add_subparsers(dest="stage", required=True)

    init = stages.add_parser("init", help="create a run, or update its repository mapping")
    init.add_argument(
        "--repo",
        action="append",
        default=[],
        type=_parse_repo,
        metavar="NAME=PATH",
        help="map a repository name (e.g. django/django) to a local clone; repeatable",
    )

    imp = stages.add_parser("import", help="validate a lesson-bank JSONL file into the run")
    imp.add_argument("bank", type=Path, help="lesson-bank JSONL file")

    prs = stages.add_parser("pairs", help="build revision pairs for the run's source revisions")
    prs.add_argument(
        "--meta",
        type=Path,
        default=swe_bench.DEFAULT_META,
        help="SWE-bench Verified metadata JSONL (default: data/swe-bench-verified-meta.jsonl)",
    )

    mech = stages.add_parser("run-mechanism", help="run a maintenance mechanism over a revision pair")
    mech.add_argument("mechanism", help=f"mechanism name ({', '.join(sorted(harness.MECHANISMS))})")
    mech.add_argument("--pair", help="pair id of a recorded revision pair (instead of --repository/--source/--target)")
    mech.add_argument("--repository", help="repository name, e.g. django/django")
    mech.add_argument("--source", help="source revision S (full SHA)")
    mech.add_argument("--target", help="target revision T (full SHA)")
    mech.add_argument(
        "--bank",
        choices=harness.BANKS,
        default=harness.ORIGINAL,
        help="original (the imported lessons of S, default) or variant (the pair's blinded variant bank)",
    )

    review.add_parsers(stages)
    extraction.add_parsers(stages)
    checks.add_parsers(stages)
    signoff.add_parsers(stages)
    constructor.add_parsers(stages)
    report.add_parsers(stages)
    return parser


def cmd_init(args) -> int:
    for name, path in args.repo:
        if not Repository(path).is_git_repository():
            raise RunError(f"repository {name}: {path} is not a git repository")
    store = RunStore.create(args.run.expanduser().resolve())
    for name, path in args.repo:
        store.set_repository(name, path)
    print(f"run ready at {store.run_dir}")
    return 0


def cmd_import(args) -> int:
    store = RunStore.open(args.run.expanduser().resolve())
    summary = lesson_bank.import_bank(store, args.bank)
    print(f"import: {summary.accepted} accepted ({summary.new} new), {len(summary.rejections)} rejected")
    for reason, count in sorted(summary.rejected_per_reason().items()):
        print(f"  {reason}: {count}")
    for rejection in summary.rejections:
        print(f"  rejected {rejection.subject}: {rejection.detail}", file=sys.stderr)
    return 0


def cmd_pairs(args) -> int:
    store = RunStore.open(args.run.expanduser().resolve())
    summary = pairs.build_pairs(store, args.meta)
    noun = "source revision" if summary.sources == 1 else "source revisions"
    print(
        f"pairs: {summary.pairs} revision pairs from {summary.sources} {noun}, "
        f"{len(summary.exclusions)} excluded"
    )
    for reason, count in sorted(summary.excluded_per_reason().items()):
        print(f"  {reason}: {count}")
    for subject, reason, detail in summary.exclusions:
        print(f"  excluded {subject} ({reason}): {detail}", file=sys.stderr)
    return 0


def cmd_run_mechanism(args) -> int:
    revisions = (args.repository, args.source, args.target)
    by_id = args.pair is not None and not any(revisions)
    if not by_id and (args.pair is not None or not all(revisions)):
        raise RunError("name the revision pair with either --pair or --repository/--source/--target")
    store = RunStore.open(args.run.expanduser().resolve())
    pair = harness.pair_by_id(store, args.pair) if by_id else harness.RevisionPair(*revisions)
    run = harness.run_mechanism(store, args.mechanism, pair, args.bank)
    bank = " (variant bank)" if args.bank == harness.VARIANT else ""
    print(f"{args.mechanism}: {len(run.decisions)} lessons decided{bank}")
    for decision in harness.Decision:
        print(f"  {decision}: {sum(1 for d in run.decisions.values() if d == decision)}")
    print(
        f"  cost: checks executed: {run.cost.checks_executed}, "
        f"wall time: {run.cost.wall_time_seconds:.3f}s, tokens: {run.cost.tokens}"
    )
    return 0


COMMANDS = {"init": cmd_init, "import": cmd_import, "pairs": cmd_pairs, "run-mechanism": cmd_run_mechanism}
COMMANDS.update(review.COMMANDS)
COMMANDS.update(extraction.COMMANDS)
COMMANDS.update(checks.COMMANDS)
COMMANDS.update(signoff.COMMANDS)
COMMANDS.update(constructor.COMMANDS)
COMMANDS.update(report.COMMANDS)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.stage](args)
    except RunError as exc:
        print(f"memrev: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
