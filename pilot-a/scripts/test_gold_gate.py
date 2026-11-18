"""Parser test for gold_gate.py (and the probe runner that will reuse it).

    uv run --locked python pilot-a/scripts/test_gold_gate.py

Synthetic lines in the exact formats seen in the gate logs; no names from pilot tasks
(Lane N may read this file).
"""
from gold_gate import lookup, parse

PYTEST = """\
tests/test_x.py::TestA::test_alpha PASSED           [ 10%]
tests/test_x.py::TestA::test_beta[a b-Err] FAILED [ 20%]
PASSED tests/test_y.py::test_gamma
FAILED tests/test_y.py::test_delta - AssertionError: boom
"""
DJANGO = """\
test_one (app.tests.MyTests) ... ok
test_two (app.tests.MyTests.test_two) ... FAIL
test_three (app.tests.MyTests)
Check that the docstring name is kept. ... ERROR
test_four (app.tests.MyTests) ... expected failure
test_six (app.tests.MyTests) ... test_seven (app.tests.MyTests) ... ok
"""
SYMPY = """\
sympy/sets/tests/test_x.py[4]
test_ok ok
test_fail F
test_xfail f
test_err E
"""


def test_pytest():
    r = parse(PYTEST, "psf/requests")
    assert lookup(r, "tests/test_x.py::TestA::test_alpha", "psf/requests") == "PASSED"
    assert lookup(r, "tests/test_x.py::TestA::test_beta[a b-Err]", "psf/requests") == "FAILED"
    assert lookup(r, "tests/test_y.py::test_gamma", "psf/requests") == "PASSED"
    assert lookup(r, "tests/test_y.py::test_delta", "psf/requests") == "FAILED"
    assert lookup(r, "tests/test_y.py::test_absent", "psf/requests") == "MISSING"
    # some images force colour: ANSI codes around status and test name
    c = parse("\x1b[32mPASSED\x1b[0m tests/test_z.py::\x1b[1mtest_coloured[a b]\x1b[0m\n", "psf/requests")
    assert lookup(c, "tests/test_z.py::test_coloured[a b]", "psf/requests") == "PASSED"
    # SWE-bench lists parametrized names cut at the first space; match only if all continuations agree
    t = parse("PASSED t.py::test_p[a b]\nPASSED t.py::test_q[x one]\nFAILED t.py::test_q[x two]\n", "psf/requests")
    assert lookup(t, "t.py::test_p[a", "psf/requests") == "PASSED"
    assert lookup(t, "t.py::test_q[x", "psf/requests") == "MISSING"


def test_django():
    r = parse(DJANGO, "django/django")
    assert lookup(r, "test_one (app.tests.MyTests)", "django/django") == "PASSED"
    assert lookup(r, "tests/app/tests.py::MyTests::test_two", "django/django") == "FAILED"  # SCB id, py3.11 output
    assert lookup(r, "test_three (app.tests.MyTests)", "django/django") == "ERROR"
    assert lookup(r, "Check that the docstring name is kept.", "django/django") == "ERROR"
    assert lookup(r, "test_four (app.tests.MyTests)", "django/django") == "XFAIL"
    assert lookup(r, "test_five (app.tests.MyTests)", "django/django") == "MISSING"
    # test_six printed no status (runner crashed later); the "ok" belongs to test_seven
    assert lookup(r, "test_six (app.tests.MyTests)", "django/django") == "MISSING"
    assert lookup(r, "test_seven (app.tests.MyTests)", "django/django") == "PASSED"


def test_sympy():
    r = parse(SYMPY, "sympy/sympy")
    for name, want in [("test_ok", "PASSED"), ("test_fail", "FAILED"), ("test_xfail", "XFAIL"), ("test_err", "ERROR")]:
        assert lookup(r, name, "sympy/sympy") == want                                  # official bare name
        assert lookup(r, f"sympy/sets/tests/test_x.py::{name}", "sympy/sympy") == want  # SCB id
    assert lookup(r, "test_absent", "sympy/sympy") == "MISSING"


if __name__ == "__main__":
    for t in [test_pytest, test_django, test_sympy]:
        t()
    print("parser tests passed")
