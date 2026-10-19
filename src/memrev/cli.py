"""Command-line entry point: `memrev --run <run-dir> <stage> ...`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from memrev import lesson_bank
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


COMMANDS = {"init": cmd_init, "import": cmd_import}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.stage](args)
    except RunError as exc:
        print(f"memrev: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
