"""How the Docker check runner turns a check's exit status and output into an outcome (V21).

The outputs below are shaped like real django `runtests.py --verbosity 2` and `python -c` output.
"""

from memrev.check_runner import Outcome
from memrev.outcomes import classify

RUNTESTS = "./tests/runtests.py --verbosity 2 --settings=test_sqlite --parallel 1"
HEADER = """Testing against Django installed in '/testbed/django'
Importing application utils_tests
Found 3 test(s).
Skipping setup of unused database(s): default, other.
System check identified no issues (0 silenced).
"""


def test_runtests_with_every_test_ok_is_a_pass():
    output = HEADER + (
        "test_a (utils_tests.test_text.TestUtilsText) ... ok\n"
        "test_b (utils_tests.test_text.TestUtilsText) ... ok\n"
        "test_c (utils_tests.test_text.TestUtilsText) ... skipped 'needs jinja2'\n"
        "\n----------------------------------------------------------------------\n"
        "Ran 3 tests in 0.012s\n\nOK (skipped=1)\n"
    )

    outcome, _ = classify(f"{RUNTESTS} utils_tests.test_text", "django.utils.text", 0, output)

    assert outcome is Outcome.PASS


def test_runtests_with_a_failing_test_is_a_fail_on_the_asserted_target_naming_the_test():
    output = HEADER + (
        "test_a (utils_tests.test_text.TestUtilsText) ... ok\n"
        "test_b (utils_tests.test_text.TestUtilsText) ... FAIL\n"
        "\n======================================================================\n"
        "FAIL: test_b (utils_tests.test_text.TestUtilsText)\n"
        "----------------------------------------------------------------------\n"
        "Traceback (most recent call last):\n"
        '  File "/testbed/tests/utils_tests/test_text.py", line 10, in test_b\n'
        "    self.assertEqual(1, 2)\n"
        "AssertionError: 1 != 2\n"
        "\n----------------------------------------------------------------------\n"
        "Ran 2 tests in 0.010s\n\nFAILED (failures=1)\n"
    )

    outcome, detail = classify(f"{RUNTESTS} utils_tests.test_text", "django.utils.text", 1, output)

    assert outcome is Outcome.FAIL_ON_TARGET
    assert "test_b (utils_tests.test_text.TestUtilsText)" in detail


def test_django_4_2_test_ids_and_output_between_a_test_and_its_status_are_parsed():
    output = HEADER + (
        "test_a (utils_tests.test_text.TestUtilsText.test_a) ... some printed noise\n"
        "ok\n"
        "Wrap text at a given width. ... FAIL\n"
        "\n======================================================================\n"
        "FAIL: test_wrap (utils_tests.test_text.TestUtilsText.test_wrap)\n"
        "Wrap text at a given width.\n"
        "----------------------------------------------------------------------\n"
        "Traceback (most recent call last):\n"
        '  File "/testbed/tests/utils_tests/test_text.py", line 20, in test_wrap\n'
        "AssertionError: 'a' != 'b'\n"
        "\n----------------------------------------------------------------------\n"
        "Ran 2 tests in 0.010s\n\nFAILED (failures=1)\n"
    )

    outcome, detail = classify(f"{RUNTESTS} utils_tests.test_text", "django.utils.text.wrap", 1, output)

    assert outcome is Outcome.FAIL_ON_TARGET
    assert "test_wrap (utils_tests.test_text.TestUtilsText.test_wrap)" in detail


def test_a_named_test_that_does_not_exist_at_the_revision_is_out_of_scope():
    output = HEADER + (
        "test_skip_checks (unittest.loader._FailedTest) ... ERROR\n"
        "\n======================================================================\n"
        "ERROR: test_skip_checks (unittest.loader._FailedTest)\n"
        "----------------------------------------------------------------------\n"
        "AttributeError: type object 'ManageRunserver' has no attribute 'test_skip_checks'\n"
        "\n----------------------------------------------------------------------\n"
        "Ran 1 test in 0.000s\n\nFAILED (errors=1)\n"
    )
    command = f"{RUNTESTS} admin_scripts.tests.ManageRunserver.test_skip_checks"

    outcome, detail = classify(command, "runserver --skip-checks", 1, output)

    assert outcome is Outcome.OUT_OF_SCOPE
    assert "admin_scripts.tests.ManageRunserver.test_skip_checks" in detail


def test_a_named_test_module_that_cannot_be_found_is_out_of_scope():
    output = HEADER + (
        "test_texts (unittest.loader._FailedTest) ... ERROR\n"
        "\n======================================================================\n"
        "ERROR: test_texts (unittest.loader._FailedTest)\n"
        "----------------------------------------------------------------------\n"
        "ImportError: Failed to import test module: test_texts\n"
        "Traceback (most recent call last):\n"
        '  File "/opt/miniconda3/envs/testbed/lib/python3.8/unittest/loader.py", line 154, in loadTestsFromName\n'
        "    module = __import__(module_name)\n"
        "ModuleNotFoundError: No module named 'utils_tests.test_texts'\n"
        "\n----------------------------------------------------------------------\n"
        "Ran 1 test in 0.000s\n\nFAILED (errors=1)\n"
    )

    outcome, _ = classify(f"{RUNTESTS} utils_tests.test_texts", "django.utils.text", 1, output)

    assert outcome is Outcome.OUT_OF_SCOPE


def test_a_test_module_that_fails_to_import_the_asserted_target_is_a_fail_on_the_target():
    output = HEADER + (
        "test_text (unittest.loader._FailedTest) ... ERROR\n"
        "\n======================================================================\n"
        "ERROR: test_text (unittest.loader._FailedTest)\n"
        "----------------------------------------------------------------------\n"
        "ImportError: Failed to import test module: test_text\n"
        "Traceback (most recent call last):\n"
        '  File "/testbed/tests/utils_tests/test_text.py", line 5, in <module>\n'
        "    from django.utils.text import slugify_unicode\n"
        "ImportError: cannot import name 'slugify_unicode' from 'django.utils.text'\n"
        "\n----------------------------------------------------------------------\n"
        "Ran 1 test in 0.000s\n\nFAILED (errors=1)\n"
    )

    outcome, _ = classify(f"{RUNTESTS} utils_tests.test_text", "django.utils.text.slugify_unicode", 1, output)

    assert outcome is Outcome.FAIL_ON_TARGET


def test_a_test_erroring_in_the_code_under_test_is_a_fail_on_the_target():
    output = HEADER + (
        "test_a (utils_tests.test_text.TestUtilsText) ... ERROR\n"
        "\n======================================================================\n"
        "ERROR: test_a (utils_tests.test_text.TestUtilsText)\n"
        "----------------------------------------------------------------------\n"
        "Traceback (most recent call last):\n"
        '  File "/testbed/django/utils/text.py", line 30, in wrap\n'
        "TypeError: wrap() got an unexpected keyword argument 'width'\n"
        "\n----------------------------------------------------------------------\n"
        "Ran 1 test in 0.001s\n\nFAILED (errors=1)\n"
    )

    outcome, _ = classify(f"{RUNTESTS} utils_tests.test_text", "django.utils.text.wrap", 1, output)

    assert outcome is Outcome.FAIL_ON_TARGET


def test_a_test_erroring_on_the_database_is_a_harness_error():
    output = HEADER + (
        "test_a (backends.tests.Tests) ... ERROR\n"
        "\n======================================================================\n"
        "ERROR: test_a (backends.tests.Tests)\n"
        "----------------------------------------------------------------------\n"
        "Traceback (most recent call last):\n"
        '  File "/testbed/django/db/backends/utils.py", line 84, in _execute\n'
        "django.db.utils.OperationalError: disk I/O error\n"
        "\n----------------------------------------------------------------------\n"
        "Ran 1 test in 0.001s\n\nFAILED (errors=1)\n"
    )

    outcome, _ = classify(f"{RUNTESTS} backends.tests", "django.db.connection", 1, output)

    assert outcome is Outcome.HARNESS_ERROR


def test_runtests_where_every_test_is_skipped_is_out_of_scope():
    output = HEADER + (
        "test_a (postgres_tests.test_array.Tests) ... skipped 'PostgreSQL specific tests'\n"
        "\n----------------------------------------------------------------------\n"
        "Ran 1 test in 0.000s\n\nOK (skipped=1)\n"
    )

    outcome, _ = classify(f"{RUNTESTS} postgres_tests.test_array", "ArrayField", 0, output)

    assert outcome is Outcome.OUT_OF_SCOPE


def test_runtests_that_crashes_before_running_tests_is_a_harness_error():
    output = (
        "Traceback (most recent call last):\n"
        '  File "./tests/runtests.py", line 26, in <module>\n'
        "    from django.test.runner import get_max_test_processes\n"
        "ImportError: cannot import name 'get_max_test_processes' from 'django.test.runner'\n"
    )

    outcome, _ = classify(f"{RUNTESTS} utils_tests.test_text", "django.utils.text", 1, output)

    assert outcome is Outcome.HARNESS_ERROR


def test_a_probe_that_exits_0_is_a_pass():
    assert classify("python -c 'import django'", "django", 0, "")[0] is Outcome.PASS


def test_a_probe_whose_assertion_fails_is_a_fail_on_the_target():
    output = 'Traceback (most recent call last):\n  File "<string>", line 1, in <module>\nAssertionError\n'

    outcome, detail = classify("python -c 'assert False'", "runserver --skip-checks", 1, output)

    assert outcome is Outcome.FAIL_ON_TARGET
    assert "AssertionError" in detail


def test_a_probe_that_cannot_import_the_asserted_target_is_a_fail_on_the_target():
    output = (
        'Traceback (most recent call last):\n  File "<string>", line 1, in <module>\n'
        "ImportError: cannot import name 'slugify_unicode' from 'django.utils.text' "
        "(/testbed/django/utils/text.py)\n"
    )

    outcome, _ = classify(
        "python -c 'from django.utils.text import slugify_unicode'", "django.utils.text.slugify_unicode", 1, output
    )

    assert outcome is Outcome.FAIL_ON_TARGET


def test_a_probe_crashing_away_from_the_asserted_target_is_a_harness_error():
    output = (
        'Traceback (most recent call last):\n  File "<string>", line 1, in <module>\n'
        "django.core.exceptions.ImproperlyConfigured: Requested setting INSTALLED_APPS, but settings "
        "are not configured. You must either define the environment variable DJANGO_SETTINGS_MODULE "
        "or call settings.configure() before accessing settings.\n"
    )

    outcome, _ = classify("python -c 'from django.contrib.auth.models import User'", "User.get_username", 1, output)

    assert outcome is Outcome.HARNESS_ERROR


def test_a_probe_missing_a_database_driver_is_out_of_scope():
    output = (
        'Traceback (most recent call last):\n  File "<string>", line 1, in <module>\n'
        "django.core.exceptions.ImproperlyConfigured: Error loading psycopg2 module: "
        "No module named 'psycopg2'\n"
    )

    outcome, _ = classify("python -c 'import django.db.backends.postgresql.base'", "DatabaseWrapper", 1, output)

    assert outcome is Outcome.OUT_OF_SCOPE


def test_a_probe_that_exits_nonzero_without_a_traceback_is_a_fail_on_the_target():
    outcome, _ = classify("python -c 'import sys; sys.exit(1)'", "Q.__or__", 1, "")

    assert outcome is Outcome.FAIL_ON_TARGET


def test_timeouts_missing_commands_and_signals_are_harness_errors():
    assert classify("python -c 'x'", "x", 124, "")[0] is Outcome.HARNESS_ERROR  # `timeout` expired
    assert classify("pytets", "x", 127, "bash: pytets: command not found")[0] is Outcome.HARNESS_ERROR
    assert classify("python -c 'x'", "x", 139, "")[0] is Outcome.HARNESS_ERROR  # segfault under emulation
    assert classify("python -c 'x'", "x", None, "")[0] is Outcome.HARNESS_ERROR
    assert classify(f"{RUNTESTS} utils_tests", "x", 124, HEADER)[0] is Outcome.HARNESS_ERROR


# Errors away from the target, pytest exit codes, a missing command (review 2026-10-19) ----------


def test_a_test_erroring_away_from_the_asserted_target_is_a_harness_error():
    output = HEADER + (
        "test_a (utils_tests.test_text.TestUtilsText) ... ERROR\n"
        "\n======================================================================\n"
        "ERROR: test_a (utils_tests.test_text.TestUtilsText)\n"
        "----------------------------------------------------------------------\n"
        "Traceback (most recent call last):\n"
        '  File "/testbed/tests/utils_tests/test_text.py", line 12, in setUp\n'
        "KeyError: 'LANG'\n"
        "\n----------------------------------------------------------------------\n"
        "Ran 1 test in 0.001s\n\nFAILED (errors=1)\n"
    )

    outcome, detail = classify(f"{RUNTESTS} utils_tests.test_text", "django.utils.text.wrap", 1, output)

    assert outcome is Outcome.HARNESS_ERROR
    assert "KeyError" in detail


def test_a_test_whose_id_names_the_asserted_target_erroring_is_a_fail_on_the_target():
    output = HEADER + (
        "test_wrap (utils_tests.test_text.TestUtilsText) ... ERROR\n"
        "\n======================================================================\n"
        "ERROR: test_wrap (utils_tests.test_text.TestUtilsText)\n"
        "----------------------------------------------------------------------\n"
        "Traceback (most recent call last):\n"
        '  File "/testbed/tests/utils_tests/test_text.py", line 12, in setUp\n'
        "KeyError: 'width'\n"
        "\n----------------------------------------------------------------------\n"
        "Ran 1 test in 0.001s\n\nFAILED (errors=1)\n"
    )
    target = "utils_tests.test_text.TestUtilsText.test_wrap"

    outcome, _ = classify(f"{RUNTESTS} utils_tests.test_text", target, 1, output)

    assert outcome is Outcome.FAIL_ON_TARGET


def test_pytest_interrupted_internal_error_and_usage_error_are_harness_errors():
    for exit_status, output in (
        (2, "Interrupted: 1 error during collection"),
        (3, "INTERNALERROR> Traceback ..."),
        (4, "ERROR: usage: pytest [options] [file_or_dir]\npytest: error: unrecognized arguments: --nope"),
    ):
        outcome, detail = classify("python -m pytest tests/test_text.py::test_wrap", "wrap", exit_status, output)
        assert outcome is Outcome.HARNESS_ERROR, exit_status
        assert f"pytest exit {exit_status}" in detail


def test_pytest_collecting_no_tests_is_out_of_scope():
    outcome, _ = classify("pytest -k test_wrap tests/test_text.py", "wrap", 5, "collected 0 items\n\nno tests ran")

    assert outcome is Outcome.OUT_OF_SCOPE


def test_pytest_failing_a_test_is_still_a_fail_on_the_target():
    output = "tests/test_text.py F\n\nE       assert 1 == 2\n1 failed in 0.01s\n"

    outcome, _ = classify("pytest tests/test_text.py::test_wrap", "wrap", 1, output)

    assert outcome is Outcome.FAIL_ON_TARGET


def test_the_same_exit_codes_from_a_command_that_is_not_pytest_stay_a_fail_on_the_target():
    for exit_status in (2, 3, 4, 5):
        assert classify("./check_wrap.sh", "wrap", exit_status, "")[0] is Outcome.FAIL_ON_TARGET


def test_a_missing_command_or_script_is_a_harness_error():
    missing_script = "python: can't open file '/testbed/probe_wrap.py': [Errno 2] No such file or directory"
    missing_program = "sh: 1: nosuchtool: command not found"

    assert classify("python probe_wrap.py", "wrap", 2, missing_script)[0] is Outcome.HARNESS_ERROR
    assert classify("nosuchtool --check wrap", "wrap", 1, missing_program)[0] is Outcome.HARNESS_ERROR


def test_a_missing_file_that_the_check_itself_reports_stays_a_fail_on_the_target():
    output = "cat: django/utils/wrap.txt: No such file or directory"

    assert classify("cat django/utils/wrap.txt", "wrap", 1, output)[0] is Outcome.FAIL_ON_TARGET
