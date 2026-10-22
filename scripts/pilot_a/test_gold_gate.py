"""Parser test for gold_gate.py (and the probe runner that will reuse it).

    uv run --locked python scripts/pilot_a/test_gold_gate.py

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


def test_django():
    r = parse(DJANGO, "django/django")
    assert lookup(r, "test_one (app.tests.MyTests)", "django/django") == "PASSED"
    assert lookup(r, "tests/app/tests.py::MyTests::test_two", "django/django") == "FAILED"  # SCB id, py3.11 output
    assert lookup(r, "test_three (app.tests.MyTests)", "django/django") == "ERROR"
    assert lookup(r, "Check that the docstring name is kept.", "django/django") == "ERROR"
    assert lookup(r, "test_four (app.tests.MyTests)", "django/django") == "XFAIL"
    assert lookup(r, "test_five (app.tests.MyTests)", "django/django") == "MISSING"


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
