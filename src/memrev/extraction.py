"""Stage `extract`: an LLM proposes the assumptions in each lesson; they enter the run as pending."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from memrev.assumptions import AssumptionContent, Assumptions, AssumptionType
from memrev.llm import DEFAULT_MODEL, LLM, AnthropicLLM, LLMClient, LLMFailure, LLMRequest
from memrev.store import ExclusionReason, Lesson, RunStore

STAGE = ORIGIN = "extract"
DEFAULT_LESSON_LIMIT = 30

FIELDS = ("statement", "assumption_type", "scope", "code_pointers", "check_command", "asserted_target")

SCHEMA = {
    "type": "object",
    "properties": {
        "assumptions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "assumption_type": {"type": "string", "enum": [str(t) for t in AssumptionType]},
                    "scope": {"type": "string"},
                    "code_pointers": {"type": "array", "items": {"type": "string"}},
                    "check_command": {"type": "string"},
                    "asserted_target": {"type": "string"},
                },
                "required": list(FIELDS),
                "additionalProperties": False,
            },
        }
    },
    "required": ["assumptions"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You extract the assumptions a lesson relies on. A lesson is a short piece of advice a coding agent \
wrote after a task in a repository, at a given source revision. An assumption is one concrete \
statement about repository behaviour at that revision that the lesson relies on, phrased so that \
running a check at another revision can decide whether it still holds.

Give every assumption exactly one assumption_type:
- "symbol exists": a module, class, function, method, attribute or setting exists at a given path.
- "signature": a callable takes given parameters (names, order, defaults).
- "return/raise behaviour": a callable returns a given value or raises a given exception for a given input.
- "config or default value": a setting, constant or default has a given value.
- "named test passes": a named existing test in the repository passes.
- "uncheckable": the lesson relies on it, but it fits none of the five types above \
(style, intent, process advice, vague claims). Still list it.

For each assumption give:
- statement: one sentence, specific enough to be checked.
- scope: the conditions under which it is stated to hold (files, symbols, backend, configuration).
- code_pointers: repository paths, optionally with ":line" or "::symbol", that support it.
- check_command: one shell command run from the repository root at a revision that exits 0 if and \
only if the assumption holds; prefer an existing test (e.g. "./tests/runtests.py app.tests.Class.test") \
or a short "python -c" probe. Empty for uncheckable assumptions.
- asserted_target: the symbol or behaviour the check tests (e.g. "django.db.models.Q.__or__"). \
Empty for uncheckable assumptions.

List only assumptions the lesson actually relies on; do not invent behaviour the lesson does not \
mention. Return an empty list if there are none.
"""


def make_llm(model: str) -> LLM:
    """The real LLM for a model id. Tests replace this with a fake."""
    return AnthropicLLM(model)


def lesson_prompt(lesson: Lesson) -> str:
    return (
        f"Repository: {lesson.repository}\n"
        f"Source revision: {lesson.source_revision}\n"
        f"Task: {lesson.task_id}\n\n"
        f"Lesson:\n{lesson.lesson_text}\n"
    )


def _assumption_type(raw: str) -> AssumptionType:
    """One of the five types, or uncheckable for anything else (V16)."""
    try:
        return AssumptionType(raw.strip())
    except ValueError:
        return AssumptionType.UNCHECKABLE


def _content(item: dict) -> AssumptionContent:
    if not isinstance(item["code_pointers"], list):
        raise TypeError("code_pointers is not a list")
    return AssumptionContent(
        statement=item["statement"].strip(),
        assumption_type=_assumption_type(item["assumption_type"]),
        scope=item["scope"].strip(),
        code_pointers=tuple(p.strip() for p in item["code_pointers"] if p.strip()),
        check_command=item["check_command"].strip(),
        asserted_target=item["asserted_target"].strip(),
    )


def parse_assumptions(data: dict) -> list[AssumptionContent]:
    """The LLM output as assumption content; raises on output that does not match `SCHEMA`."""
    return [_content(item) for item in data["assumptions"]]


@dataclass
class ExtractionYield:
    lessons_processed: int = 0
    checkable: int = 0
    uncheckable: int = 0
    extraction_failed: int = 0
    lessons_left: int = 0


def extract(store: RunStore, client: LLMClient, limit: int = DEFAULT_LESSON_LIMIT) -> ExtractionYield:
    """Extract from the first `limit` lessons in import order (V17). Reruns hit the output cache."""
    assumptions = Assumptions(store)
    lessons = store.lessons()
    summary = ExtractionYield(lessons_left=max(0, len(lessons) - limit))
    for lesson in lessons[:limit]:
        summary.lessons_processed += 1
        subject = f"lesson {lesson.lesson_id}"
        try:
            request = LLMRequest(SYSTEM_PROMPT, lesson_prompt(lesson), SCHEMA)
            contents = client.call(request, parse_assumptions, subject=subject)
        except LLMFailure as exc:
            store.record_exclusion(STAGE, subject, ExclusionReason.EXTRACTION_FAILED, str(exc))
            summary.extraction_failed += 1
            continue
        store.clear_exclusion(STAGE, subject)
        for content in contents:
            assumptions.add(lesson.lesson_id, content, ORIGIN)
            if content.assumption_type.checkable:
                summary.checkable += 1
            else:
                summary.uncheckable += 1
    return summary


# Command line -----------------------------------------------------------


def add_parsers(stages) -> None:
    ext = stages.add_parser("extract", help="LLM extraction of assumptions from the imported lessons")
    ext.add_argument("--model", default=DEFAULT_MODEL, help=f"model id (default {DEFAULT_MODEL})")
    ext.add_argument(
        "--limit",
        type=_positive_int,
        default=DEFAULT_LESSON_LIMIT,
        help=f"stop after this many lessons (default {DEFAULT_LESSON_LIMIT})",
    )


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError(f"expected a positive number, got {value}")
    return n


def cmd_extract(args: argparse.Namespace) -> int:
    store = RunStore.open(args.run.expanduser().resolve())
    client = LLMClient(make_llm(args.model), store, STAGE)
    summary = extract(store, client, limit=args.limit)
    unpriced = f" (plus {client.unpriced_calls} calls to a model without a price)" if client.unpriced_calls else ""
    print(
        f"extract: {summary.lessons_processed} lessons processed, "
        f"{summary.checkable} checkable assumptions, {summary.uncheckable} uncheckable, "
        f"{summary.extraction_failed} extraction failed, cost ${client.cost_usd:.4f}{unpriced}"
    )
    if summary.lessons_left:
        noun = "lesson" if summary.lessons_left == 1 else "lessons"
        print(
            f"stopped at the lesson limit ({args.limit}): {summary.lessons_left} {noun} not processed; "
            "check the yield, then rerun with a higher --limit to continue"
        )
    return 0


COMMANDS = {"extract": cmd_extract}
