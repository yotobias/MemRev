"""Seam N2 (slow, opt-in): known checks at one real django 4.0 revision pair in the real SWE-bench image.

Enable with MEMREV_DOCKER=1 and MEMREV_DJANGO_REPO=<django clone>, with Docker running:

    MEMREV_DOCKER=1 MEMREV_DJANGO_REPO=/path/to/django uv run pytest tests/test_docker_n2.py -v -s

The pair is the fixture lesson fixture-django-001: S = django__django-13809's base commit (runserver
has no --skip-checks), T = django__django-13925's base commit (the fix for 13809 added it). Both run
in S's image (swebench/sweb.eval.x86_64.django_1776_django-13809), pulled on first use (~1.15 GB,
amd64 only; Rosetta on Apple Silicon). Expect several minutes.
"""

import os
import time
from pathlib import Path

import pytest

from memrev.check_runner import Check, Environment, Outcome
from memrev.checks import SANITY_SETS
from memrev.docker_runner import DockerCheckRunner

pytestmark = pytest.mark.skipif(
    not (os.environ.get("MEMREV_DOCKER") == "1" and os.environ.get("MEMREV_DJANGO_REPO")),
    reason="slow seam N2: set MEMREV_DOCKER=1 and MEMREV_DJANGO_REPO=<django clone>, with Docker running",
)

S = "bef6f7584280f1cc80e5e2d80b7ad073a93d26ec"  # django__django-13809
T = "0c42cdf0d2422f4c080e93594d5d15381d6e955e"  # django__django-13925
NO_SKIP_CHECKS = Check(
    "python -c \"from django.core.management.commands.runserver import Command; "
    "assert '--skip-checks' not in Command().create_parser('manage.py', 'runserver').format_help()\"",
    "django.core.management.commands.runserver.Command.add_arguments",
)
SKIP_CHECKS_TEST = Check(
    "./tests/runtests.py --verbosity 2 --settings=test_sqlite --parallel 1 "
    "admin_scripts.tests.ManageRunserver.test_skip_checks",
    "runserver --skip-checks",
)


@pytest.fixture(scope="module")
def runner():
    real = DockerCheckRunner()
    yield real
    real.close()


@pytest.fixture(scope="module")
def environment() -> Environment:
    return Environment("django/django", "4.0", "django__django-13809", Path(os.environ["MEMREV_DJANGO_REPO"]))


def timed(runner, check, revision, environment):
    clock = time.perf_counter()
    result = runner.run(check, revision, environment, 1)
    print(f"\n{revision[:12]} {check.command[:60]}: {result.outcome} in {time.perf_counter() - clock:.1f}s "
          f"({result.detail})")  # fmt: skip
    return result


@pytest.mark.parametrize("revision", [S, T])
@pytest.mark.parametrize("command", SANITY_SETS["django/django"])
def test_the_django_sanity_set_passes_at_S_and_T(runner, environment, revision, command):
    result = timed(runner, Check(command, command), revision, environment)

    assert result.outcome is Outcome.PASS, result.output[-2000:]


def test_a_probe_on_runserver_skip_checks_passes_at_S_and_fails_on_its_target_at_T(runner, environment):
    at_s = timed(runner, NO_SKIP_CHECKS, S, environment)
    at_t = timed(runner, NO_SKIP_CHECKS, T, environment)

    assert at_s.outcome is Outcome.PASS, at_s.output[-2000:]
    assert at_t.outcome is Outcome.FAIL_ON_TARGET, at_t.output[-2000:]


def test_a_test_added_after_S_is_out_of_scope_at_S_and_passes_at_T(runner, environment):
    at_s = timed(runner, SKIP_CHECKS_TEST, S, environment)
    at_t = timed(runner, SKIP_CHECKS_TEST, T, environment)

    assert at_s.outcome is Outcome.OUT_OF_SCOPE, at_s.output[-2000:]
    assert at_t.outcome is Outcome.PASS, at_t.output[-2000:]
