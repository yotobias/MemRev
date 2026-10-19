# Python stack: uv + src layout + pytest, Python 3.11

Tested locally with uv 0.9.18 and python3.11 (3.11.10). Current PyPI: pytest 9.1.1, typer 0.27.3, anthropic 1.15.0.

## Init (verified)

```
cd <MemRev root>
uv init --package --python 3.11 --name memrev --vcs none .     # or a subdir name instead of "."
uv add --dev pytest
uv run memrev          # prints "Hello from memrev!"
uv run pytest -q
```
- `--package` gives the src layout `src/memrev/__init__.py` with `def main()`, plus a `[project.scripts]` entry and the `uv_build` backend.
- **Pass `--vcs none`.** MemRev is already a git repo; without the flag `uv init` may try to `git init` again.
- `uv init` takes the author name/email from git config (here it picked up a gmail address). Edit or remove the `authors` entry if needed.
- It also creates `.python-version` (3.11), `README.md` and `.gitignore`. If the project already has a README, init in place may skip or clash with it. Check the result.

Generated pyproject (the parts to keep):
```toml
[project]
name = "memrev"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
memrev = "memrev.cli:main"      # change from "memrev:main" once cli.py exists

[build-system]
requires = ["uv_build>=0.9.18,<0.10.0"]
build-backend = "uv_build"

[dependency-groups]
dev = ["pytest>=9.1"]
```
Add pytest config:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
  "docker: needs a running Docker daemon and pulled images",
  "llm: calls the real Anthropic API (costs money)",
]
```
Default runs should skip the expensive tests: add `-m "not docker and not llm"` to addopts, and run them explicitly with `uv run pytest -m docker`. Tests import the installed package (`uv run` installs the project editable), so no `sys.path` hacks are needed.

Runtime deps likely needed: `anthropic`, `pydantic` (if using `messages.parse`), `pyarrow` (only if parquet is read at runtime; prefer a committed JSONL). Docker can be driven via `subprocess` calling the `docker` CLI, with no SDK dependency, which is easier to fake in tests. Alternatively the `docker` PyPI package.

Layout suggestion:
```
src/memrev/__init__.py
src/memrev/cli.py          # argparse entry, subcommands -> functions
src/memrev/<module>.py     # one per pipeline stage
tests/test_<module>.py
tests/fixtures/            # fixture memory bank JSONL, trimmed swe-bench meta, sample logs
```

## CLI library: argparse (recommended)

- **argparse**: stdlib with no dependency, and subparsers cover `memrev import`, `memrev pairs`, `memrev extract`, `memrev review export|import`, `memrev check`, `memrev harness`, `memrev score`. Easy to test: `main(argv: list[str] | None = None) -> int`, and tests call `main([...])` directly and assert on the return code and files.
- **typer**: nicer help and type hints, but it adds typer + click + rich. Its test runner (`typer.testing.CliRunner`) is fine too. It's worth it only if the CLI grows large or is used interactively a lot.
- For a research pipeline with about ten subcommands and file-in/file-out stages, argparse is enough and keeps the dependency surface small.

Pattern:
```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memrev")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pairs"); p.add_argument("--meta", type=Path, required=True); p.set_defaults(func=cmd_pairs)
    args = parser.parse_args(argv)
    return args.func(args)
```
with `if __name__ == "__main__": raise SystemExit(main())` in cli.py.

## Misc

- `uv run --no-project --with pyarrow python -I script.py` runs one-off scripts without touching the project env. I used this for the parquet extraction.
- `uv lock` / `uv sync` creates `uv.lock`. Commit it.
