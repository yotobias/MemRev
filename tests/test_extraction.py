"""Seam N1: the `extract` stage, driven through the command-line tool with the fake LLM only."""

from pathlib import Path

import pytest

from memrev import llm
from memrev.assumptions import Assumptions, AssumptionType, ReviewStatus
from memrev.llm import FakeLLM, LLMError, Usage
from memrev.store import RunStore

from conftest import lesson, write_bank

VALUE_IS_INT = {
    "statement": "module.VALUE is an int",
    "assumption_type": "return/raise behaviour",
    "scope": "module.py",
    "code_pointers": ["module.py:1"],
    "check_command": "python -c 'import module; assert isinstance(module.VALUE, int)'",
    "asserted_target": "module.VALUE",
}
VALUE_EXISTS = {
    "statement": "module defines VALUE",
    "assumption_type": "symbol exists",
    "scope": "module.py",
    "code_pointers": ["module.py"],
    "check_command": "python -c 'import module; module.VALUE'",
    "asserted_target": "module.VALUE",
}
READABLE = {
    "statement": "module.py is easy to read",
    "assumption_type": "code style",
    "scope": "",
    "code_pointers": [],
    "check_command": "",
    "asserted_target": "",
}


@pytest.fixture
def fake_llm(monkeypatch):
    """Route the extract stage to a fake LLM and make backoff instant (recording the delays)."""
    fake = FakeLLM()
    monkeypatch.setattr(llm, "make_llm", lambda model: fake)
    fake.sleeps = []
    monkeypatch.setattr(llm, "sleep", fake.sleeps.append)
    return fake


@pytest.fixture
def run_with_lessons(cli, run_dir, tiny_repo, tmp_path):
    """A run with `n` imported lessons L1..Ln at the tiny repo's first commit."""

    def make(n: int) -> Path:
        assert cli("--run", str(run_dir), "init", "--repo", f"tiny={tiny_repo.path}").exit_code == 0
        bank = write_bank(
            tmp_path / "bank.jsonl", [lesson("tiny", tiny_repo.commits[0], i) for i in range(1, n + 1)]
        )
        assert cli("--run", str(run_dir), "import", str(bank)).exit_code == 0
        return run_dir

    return make


def assumptions_in(run_dir: Path):
    return Assumptions(RunStore.open(run_dir)).all()


def test_extracted_assumptions_enter_the_run_as_pending_for_review(cli, fake_llm, run_with_lessons):
    run_dir = run_with_lessons(1)
    fake_llm.answer("Lesson number 1:", {"assumptions": [VALUE_IS_INT, VALUE_EXISTS]})

    result = cli("--run", str(run_dir), "extract")

    assert result.exit_code == 0, result.err
    stored = assumptions_in(run_dir)
    assert [(a.lesson_id, a.content.statement) for a in stored] == [
        ("L1", "module.VALUE is an int"),
        ("L1", "module defines VALUE"),
    ]
    first = stored[0]
    assert first.origin == "extract"
    assert first.status is ReviewStatus.PENDING
    assert first.content.assumption_type is AssumptionType.RETURN_RAISE
    assert first.content.code_pointers == ("module.py:1",)
    assert first.content.check_command == VALUE_IS_INT["check_command"]
    assert first.content.asserted_target == "module.VALUE"


def test_an_assumption_outside_the_five_types_is_stored_as_uncheckable_and_counted(
    cli, fake_llm, run_with_lessons
):
    run_dir = run_with_lessons(2)
    fake_llm.answer("Lesson number 1:", {"assumptions": [VALUE_IS_INT, READABLE]})
    fake_llm.answer("Lesson number 2:", {"assumptions": [VALUE_EXISTS]})

    result = cli("--run", str(run_dir), "extract")

    assert result.exit_code == 0, result.err
    readable = next(a for a in assumptions_in(run_dir) if a.content.statement == "module.py is easy to read")
    assert readable.content.assumption_type is AssumptionType.UNCHECKABLE
    assert "2 lessons processed" in result.out
    assert "2 checkable assumptions" in result.out
    assert "1 uncheckable" in result.out
    assert "0 extraction failed" in result.out


def test_extraction_stops_after_the_lesson_limit_and_says_how_many_are_left(cli, fake_llm, run_with_lessons):
    run_dir = run_with_lessons(3)
    fake_llm.answer("Lesson number", {"assumptions": [VALUE_EXISTS]})

    result = cli("--run", str(run_dir), "extract", "--limit", "2")

    assert result.exit_code == 0, result.err
    assert sorted({a.lesson_id for a in assumptions_in(run_dir)}) == ["L1", "L2"]
    assert "2 lessons processed" in result.out
    assert "stopped at the lesson limit (2): 1 lesson not processed" in result.out


def test_the_default_lesson_limit_is_30(cli, fake_llm, run_with_lessons):
    run_dir = run_with_lessons(31)
    fake_llm.answer("Lesson number", {"assumptions": []})

    result = cli("--run", str(run_dir), "extract")

    assert result.exit_code == 0, result.err
    assert len(fake_llm.calls) == 30
    assert "30 lessons processed" in result.out
    assert "stopped at the lesson limit (30): 1 lesson not processed" in result.out


def test_a_failing_call_is_retried_with_growing_backoff_before_it_succeeds(cli, fake_llm, run_with_lessons):
    run_dir = run_with_lessons(1)
    fake_llm.answer(
        "Lesson number 1:",
        LLMError("overloaded"),
        LLMError("overloaded"),
        {"assumptions": [VALUE_EXISTS]},
    )

    result = cli("--run", str(run_dir), "extract")

    assert result.exit_code == 0, result.err
    assert len(fake_llm.calls) == 3
    assert len(fake_llm.sleeps) == 2 and fake_llm.sleeps[1] > fake_llm.sleeps[0] > 0
    assert [a.content.statement for a in assumptions_in(run_dir)] == ["module defines VALUE"]
    assert "0 extraction failed" in result.out


def test_a_persistent_failure_counts_as_extraction_failed_not_uncheckable(cli, fake_llm, run_with_lessons):
    run_dir = run_with_lessons(2)
    fake_llm.answer("Lesson number 1:", LLMError("overloaded"))
    fake_llm.answer("Lesson number 2:", {"assumptions": [READABLE]})

    result = cli("--run", str(run_dir), "extract")

    assert result.exit_code == 0, result.err
    assert "2 lessons processed" in result.out
    assert "0 uncheckable" not in result.out and "1 uncheckable" in result.out
    assert "1 extraction failed" in result.out
    assert [a.lesson_id for a in assumptions_in(run_dir)] == ["L2"]
    exclusions = [(e.stage, e.subject, e.reason) for e in RunStore.open(run_dir).exclusions()]
    assert ("extract", "lesson L1", "extraction failed") in exclusions


def test_output_that_does_not_match_the_assumption_schema_is_retried_then_counted_as_failed(
    cli, fake_llm, run_with_lessons
):
    run_dir = run_with_lessons(1)
    fake_llm.answer("Lesson number 1:", {"assumptions": [{"statement": "VALUE exists"}]})

    result = cli("--run", str(run_dir), "extract")

    assert result.exit_code == 0, result.err
    assert len(fake_llm.calls) > 1
    assert "1 extraction failed" in result.out
    assert assumptions_in(run_dir) == []


def test_a_lesson_that_failed_before_is_no_longer_excluded_once_extraction_succeeds(
    cli, fake_llm, run_with_lessons
):
    run_dir = run_with_lessons(1)
    fake_llm.answer("Lesson number 1:", LLMError("down"))
    cli("--run", str(run_dir), "extract")
    fake_llm.answer("Lesson number 1:",{"assumptions": [VALUE_EXISTS]})

    result = cli("--run", str(run_dir), "extract")

    assert "0 extraction failed" in result.out
    assert RunStore.open(run_dir).exclusions() == []


def test_every_call_is_logged_with_model_tokens_and_cost(cli, fake_llm, run_with_lessons):
    run_dir = run_with_lessons(2)
    fake_llm.usage = Usage(input_tokens=1000, output_tokens=500)
    fake_llm.answer("Lesson number 1:", {"assumptions": [VALUE_EXISTS]})
    fake_llm.answer("Lesson number 2:", {"assumptions": "not a list"}, {"assumptions": []})

    result = cli("--run", str(run_dir), "extract")

    calls = llm.call_log(RunStore.open(run_dir))
    # Sonnet 5.5: $2 per million input tokens, $10 per million output tokens.
    # 1000 * 2 / 1e6 + 500 * 10 / 1e6 = 0.007 per call.
    assert [(c.stage, c.subject, c.model, c.input_tokens, c.output_tokens, c.cost_usd, c.outcome) for c in calls] == [
        ("extract", "lesson L1", "claude-sonnet-5-5", 1000, 500, pytest.approx(0.007), "ok"),
        ("extract", "lesson L2", "claude-sonnet-5-5", 1000, 500, pytest.approx(0.007), "error"),
        ("extract", "lesson L2", "claude-sonnet-5-5", 1000, 500, pytest.approx(0.007), "ok"),
    ]
    assert "cost $0.0210" in result.out


def test_a_rerun_reuses_cached_outputs_without_calling_the_llm_again(cli, fake_llm, run_with_lessons):
    run_dir = run_with_lessons(2)
    fake_llm.answer("Lesson number", {"assumptions": [VALUE_EXISTS]})
    cli("--run", str(run_dir), "extract")
    calls_before = len(fake_llm.calls)

    result = cli("--run", str(run_dir), "extract")

    assert len(fake_llm.calls) == calls_before
    assert "cost $0.0000" in result.out
    assert "2 checkable assumptions" in result.out
    assert len(assumptions_in(run_dir)) == 2
    reruns = llm.call_log(RunStore.open(run_dir))[calls_before:]
    assert [(c.cached, c.cost_usd) for c in reruns] == [(True, 0.0), (True, 0.0)]


def test_the_cache_is_keyed_by_model(cli, fake_llm, run_with_lessons):
    run_dir = run_with_lessons(1)
    fake_llm.answer("Lesson number", {"assumptions": [VALUE_EXISTS]})
    cli("--run", str(run_dir), "extract")

    fake_llm.model = "claude-opus-5-5"
    cli("--run", str(run_dir), "extract", "--model", "claude-opus-5-5")

    assert len(fake_llm.calls) == 2


def test_without_an_api_key_extract_stops_with_a_clear_message_before_any_call(
    cli, run_with_lessons, monkeypatch, tmp_path
):
    run_dir = run_with_lessons(1)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here

    result = cli("--run", str(run_dir), "extract")

    assert result.exit_code == 2
    assert "ANTHROPIC_API_KEY" in result.err
    assert llm.call_log(RunStore.open(run_dir)) == []


def test_failed_calls_are_not_cached(cli, fake_llm, run_with_lessons):
    run_dir = run_with_lessons(1)
    fake_llm.answer("Lesson number 1:", LLMError("down"))
    cli("--run", str(run_dir), "extract")
    fake_llm.answer("Lesson number 1:", {"assumptions": [VALUE_EXISTS]})

    cli("--run", str(run_dir), "extract")

    assert [a.content.statement for a in assumptions_in(run_dir)] == ["module defines VALUE"]
