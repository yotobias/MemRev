"""Turn one check execution (exit status + output) into a runner outcome (V21).

Two kinds of check command:
- django's `runtests.py`: the test statuses are parsed (a small copy of SWE-bench's
  `parse_log_django`). A failing named test is a fail on the asserted target; a named test that
  does not exist at the revision, or a run where every test is skipped, is out of scope; a test
  erroring on its environment (database, file system) is a harness error.
- anything else (e.g. a `python -c` probe): exit 0 is a pass. A traceback is a fail on the
  asserted target if it is an AssertionError or its message names the target; a missing database
  driver or library is out of scope; any other exception is a harness error. A non-zero exit
  without a traceback is a fail on the target (the check "exits 0 if and only if it holds").
Timeouts (exit 124), missing commands (126/127), signals (>128) and no exit at all are harness
errors in both kinds.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from memrev.check_runner import Outcome

# Exit statuses that mean the command never ran to a verdict.
_HARNESS_EXITS = {124: "timed out", 125: "timeout failed", 126: "command not executable", 127: "command not found"}

# A missing driver, library or backend the check needs: out of scope (V21).
_OUT_OF_SCOPE = (
    re.compile(r"Error loading \S+ module"),
    re.compile(r"Could not find the (GDAL|GEOS) library"),
    re.compile(r"No module named '(psycopg2?|MySQLdb|cx_Oracle|oracledb|PIL|yaml|jinja2|selenium|geoip2|numpy|"
               r"bcrypt|argon2|memcache|pymemcache|pylibmc|redis|tblib|docutils|sqlparse)\b"),
)
# Exceptions raised by the environment rather than by the code under test: harness error.
_ENVIRONMENT_ERRORS = {
    "OperationalError", "InterfaceError", "ConnectionError", "ConnectionRefusedError", "PermissionError",
    "OSError", "IOError", "MemoryError", "TimeoutError", "BrokenPipeError", "KeyboardInterrupt",
}  # fmt: skip
_RUNTESTS_OPTIONS_WITH_VALUE = {"--settings", "--parallel", "-v", "--verbosity", "--start-at", "--start-after",
                                "-k", "--tag", "--exclude-tag", "--shuffle"}  # fmt: skip

_STATUS_LINE = re.compile(r"^(?P<id>.+?) \.\.\. ?(?P<status>.*)$")
_BLOCK_START = re.compile(r"^(?P<kind>ERROR|FAIL): (?P<id>.+)$", re.M)
_RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
_SEPARATOR = re.compile(r"^(=|-){20,}$", re.M)
_IDENTIFIER = re.compile(r"[A-Za-z_]\w*")


def classify(command: str, asserted_target: str, exit_status: int | None, output: str) -> tuple[Outcome, str]:
    """The outcome of one execution of `command`, and a one-line reason for it."""
    if exit_status is None:
        return Outcome.HARNESS_ERROR, "no exit status"
    if exit_status in _HARNESS_EXITS:
        return Outcome.HARNESS_ERROR, f"exit {exit_status}: {_HARNESS_EXITS[exit_status]}"
    if exit_status > 128:
        return Outcome.HARNESS_ERROR, f"exit {exit_status}: killed by signal {exit_status - 128}"
    if "runtests.py" in command:
        return _classify_runtests(command, asserted_target, exit_status, output)
    return _classify_command(asserted_target, exit_status, output)


# Generic commands ---------------------------------------------------------


@dataclass(frozen=True)
class _Exception:
    name: str  # unqualified, e.g. "ImportError"
    line: str  # the exception line, e.g. "ImportError: cannot import name 'x' from 'y'"
    text: str  # the exception line and everything after it (multi-line messages)


def _last_exception(text: str) -> _Exception | None:
    """The exception of the last traceback in `text` (the innermost one of a chain is not wanted:
    Python prints the outermost last)."""
    start = text.rfind("Traceback (most recent call last):")
    if start < 0:
        return None
    for match in re.finditer(r"^(?![ \t])(\S.*)$", text[start:], re.M):
        line = match.group(1)
        if line.startswith("Traceback (most recent call last):"):
            continue
        head = line.split(":", 1)[0].strip()
        if not re.fullmatch(r"[\w.]+", head):
            continue
        return _Exception(head.rsplit(".", 1)[-1], line, text[start + match.start():])
    return None


def _target_names(asserted_target: str) -> set[str]:
    """The names whose mention in an error ties it to the asserted target: the last identifier,
    and the one before it when the last is a dunder (`Q.__or__` -> {"__or__", "Q"})."""
    names = _IDENTIFIER.findall(asserted_target)
    if not names:
        return set()
    picked = {names[-1]}
    if names[-1].startswith("__") and len(names) > 1:
        picked.add(names[-2])
    return picked


def _mentions(text: str, names: set[str]) -> bool:
    return any(re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", text) for name in names)


def _is_out_of_scope(text: str) -> bool:
    return any(pattern.search(text) for pattern in _OUT_OF_SCOPE)


def _classify_exception(exc: _Exception, asserted_target: str) -> tuple[Outcome, str]:
    if _is_out_of_scope(exc.text):
        return Outcome.OUT_OF_SCOPE, f"missing dependency: {exc.line}"
    if exc.name == "AssertionError" or _mentions(exc.line, _target_names(asserted_target)):
        return Outcome.FAIL_ON_TARGET, exc.line
    return Outcome.HARNESS_ERROR, f"error away from the asserted target: {exc.line}"


def _classify_command(asserted_target: str, exit_status: int, output: str) -> tuple[Outcome, str]:
    if exit_status == 0:
        return Outcome.PASS, ""
    exc = _last_exception(output)
    if exc is None:
        return Outcome.FAIL_ON_TARGET, f"exit {exit_status}"
    return _classify_exception(exc, asserted_target)


# django runtests.py -------------------------------------------------------


def _labels(command: str) -> list[str]:
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    after = next((i for i, w in enumerate(words) if w.endswith("runtests.py")), len(words))
    labels, skip = [], False
    for word in words[after + 1:]:
        if skip:
            skip = False
        elif word.startswith("-"):
            skip = word in _RUNTESTS_OPTIONS_WITH_VALUE
        elif not word.isdigit():
            labels.append(word)
    return labels


def _blocks(output: str) -> list[tuple[str, str, str]]:
    """The (kind, test id, body) of every `ERROR:` / `FAIL:` block after the test run."""
    blocks = []
    starts = list(_BLOCK_START.finditer(output))
    for n, match in enumerate(starts):
        end = starts[n + 1].start() if n + 1 < len(starts) else len(output)
        body = output[match.end():end]
        ran = _RAN.search(body)
        blocks.append((match["kind"], match["id"].strip(), body[: ran.start()] if ran else body))
    return blocks


def _statuses(output: str) -> dict[str, str]:
    """test id -> ok | FAIL | ERROR | skipped | unexpected success | expected failure."""
    statuses, pending = {}, None
    for line in output.splitlines():
        if _SEPARATOR.match(line) or _BLOCK_START.match(line):
            break
        match = _STATUS_LINE.match(line)
        status = match["status"].strip() if match else line.strip()
        if match:
            pending = match["id"]
        if pending is None:
            continue
        for known in ("ok", "FAIL", "ERROR", "skipped", "unexpected success", "expected failure"):
            if status == known or (known == "skipped" and status.startswith("skipped")):
                statuses[pending] = known
                pending = None
                break
    return statuses


def _missing_label(body: str, labels: list[str]) -> str | None:
    """The named test (label) that a `_FailedTest` block says does not exist, if any."""
    for module in re.findall(r"No module named '([\w.]+)'", body):
        for label in labels:
            if label == module or label.startswith(module + "."):
                return label
    for attribute in re.findall(r"has no attribute '(\w+)'", body):
        for label in labels:
            if attribute in label.split("."):
                return label
    return None


def _classify_runtests(command: str, asserted_target: str, exit_status: int, output: str) -> tuple[Outcome, str]:
    if not _RAN.search(output):
        exc = _last_exception(output)
        reason = exc.line if exc else f"exit {exit_status}"
        return Outcome.HARNESS_ERROR, f"test runner did not run: {reason}"
    labels = _labels(command)
    harness, failed, missing = [], [], []
    for kind, test_id, body in _blocks(output):
        exc = _last_exception(body)
        if "unittest.loader._FailedTest" in test_id:
            label = _missing_label(body, labels)
            if label:
                missing.append(label)
                continue
            if exc is None:
                harness.append(f"{test_id}: failed to load")
                continue
            outcome, reason = _classify_exception(exc, asserted_target)
            {Outcome.FAIL_ON_TARGET: failed, Outcome.OUT_OF_SCOPE: missing}.get(outcome, harness).append(
                f"{test_id}: {reason}"
            )
        elif kind == "FAIL":
            failed.append(f"{test_id} FAIL")
        elif exc is not None and _is_out_of_scope(exc.text):
            missing.append(f"{test_id}: {exc.line}")
        elif exc is not None and exc.name in _ENVIRONMENT_ERRORS:
            harness.append(f"{test_id}: {exc.line}")
        else:
            failed.append(f"{test_id} ERROR" + (f": {exc.line}" if exc else ""))
    statuses = _statuses(output)
    failed += [f"{test_id} unexpected success" for test_id, s in statuses.items() if s == "unexpected success"]
    if harness:
        return Outcome.HARNESS_ERROR, "; ".join(harness)
    if failed:
        return Outcome.FAIL_ON_TARGET, "; ".join(failed)
    if missing:
        return Outcome.OUT_OF_SCOPE, "named test not found at this revision: " + ", ".join(missing)
    if statuses and all(s == "skipped" for s in statuses.values()):
        return Outcome.OUT_OF_SCOPE, "every test was skipped"
    if exit_status != 0:
        return Outcome.HARNESS_ERROR, f"exit {exit_status} without a failing test"
    return Outcome.PASS, ""
