"""Stage `construct`: constructed stale lessons and matched controls per revision pair (V4, V5, V6,
V29, V30). The blinded variant memory bank built from them is `memrev.variant_bank`.

Per drift-kept revision pair, an LLM reads the S..T diff and drafts candidate stale lessons: advice
that relied on behaviour the diff changes, each with one assumption and its check. The repository is
only read, never modified (V4). A candidate is kept only if its check passes 3/3 at S and fails 3/3 on
its asserted target at T (V5, V20); the runs are stored as evidence under the assumption the candidate
would get, so the `check` stage later reuses them. Each kept stale lesson then gets one matched
control, drafted the same way, that passes 3/3 at S and at T (V6).

Kept constructed lessons live in `constructed_lessons` (the lesson-bank schema plus their pair); their
assumptions enter the shared `assumptions` table as pending (origin `construct`), so they go through
`review-export`/`review-import`, `check` and label sign-off like natural ones (V29).

Which constructed lesson is a constructed stale lesson and which a matched control
(`constructed_cases`), and which lesson sits behind each opaque id of a variant bank
(`memrev.variant_bank.variant_entries`), is the constructed-case mapping. Only the scorer reads it,
through `case_records` and `variant_entries`; the harness only reads `variant_bank.VariantBank`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from memrev.assumptions import Assumption, AssumptionContent, Assumptions, AssumptionType, ReviewStatus, file_part
from memrev.check_runner import CheckRunner, Outcome, make_runner
from memrev.checks import KEPT, RUNNER_HELP, _Checker, environment_for
from memrev.constructed_lessons import ConstructedLessons
from memrev.evidence import EvidenceStore
from memrev.labeller import listing
from memrev import llm
from memrev.llm import DEFAULT_MODEL, LLMClient, LLMFailure, LLMRequest
from memrev.repository import Repository
from memrev.store import ExclusionReason, Lesson, RevisionPair, RunError, RunStore, open_run

STAGE = ORIGIN = "construct"


class Role(StrEnum):
    """What a lesson is in the constructed-case mapping (scorer only)."""

    NATURAL = "natural lesson"
    CONSTRUCTED_STALE = "constructed stale lesson"
    MATCHED_CONTROL = "matched control"


class CaseStatus(StrEnum):
    """What became of one drafted candidate."""

    KEPT = "kept"
    GATE_FAILED = "gate failed"
    NOT_MATCHED = "not matched"


DIFF_PATHS = ("*.py",)  # the diff the LLM sees: Python files only
MAX_DIFF_CHARS = 60_000
MAX_CANDIDATES = 3  # per pair, and controls per stale lesson
LENGTH_RATIO = 2.0  # a control's lesson text is at most this many times longer or shorter

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS constructed_cases (
    case_key TEXT PRIMARY KEY,            -- <pair_id>/constructed-stale-<n>[/matched-control-<m>]
    pair_id TEXT NOT NULL,
    role TEXT NOT NULL,                   -- constructed stale lesson | matched control (Role)
    stale_case_key TEXT NOT NULL,         -- for a control: its stale lesson's case; else ''
    lesson_id TEXT NOT NULL,              -- the constructed lesson id (kept or not)
    assumption_id TEXT NOT NULL,
    status TEXT NOT NULL,                 -- kept | gate failed | not matched
    detail TEXT NOT NULL,
    draft TEXT NOT NULL                   -- the LLM's candidate as JSON
);
"""

_ITEM = {
    "type": "object",
    "properties": {
        "lesson_text": {"type": "string"},
        "statement": {"type": "string"},
        "assumption_type": {"type": "string", "enum": [str(t) for t in AssumptionType if t.checkable]},
        "scope": {"type": "string"},
        "code_pointers": {"type": "array", "items": {"type": "string"}},
        "check_command": {"type": "string"},
        "asserted_target": {"type": "string"},
    },
    "required": [
        "lesson_text", "statement", "assumption_type", "scope", "code_pointers", "check_command", "asserted_target",
    ],
    "additionalProperties": False,
}  # fmt: skip


def _list_schema(key: str) -> dict:
    return {
        "type": "object",
        "properties": {key: {"type": "array", "items": _ITEM}},
        "required": [key],
        "additionalProperties": False,
    }


STALE_SCHEMA, CONTROL_SCHEMA = _list_schema("candidates"), _list_schema("controls")

_FIELDS_HELP = """\
For each lesson give:
- lesson_text: the advice, one to three sentences, written like a lesson a coding agent noted after a task.
- statement: the one assumption about repository behaviour the advice relies on, specific enough to check.
- assumption_type: "symbol exists", "signature", "return/raise behaviour", "config or default value" or \
"named test passes".
- scope: the conditions under which it is stated to hold (files, symbols, backend, configuration).
- code_pointers: repository paths, optionally with ":line" or "::symbol", that support it.
- check_command: one shell command run from the repository root that exits 0 if and only if the \
assumption holds; prefer an existing test or a short "python -c" probe.
- asserted_target: the symbol or behaviour the check tests.
Write advice only. Never propose to change the repository.
"""

STALE_SYSTEM = f"""\
You draft constructed stale lessons for a study of whether coding-agent lessons go stale. You get the \
diff between a source revision S and a later target revision T of a repository. Find real behaviour \
changes in the diff (a renamed or removed symbol, a changed signature, a changed return value or \
exception, a changed default or setting). For each, write a lesson as an agent could have written it \
at S: advice that relies on the behaviour as it was at S, so its check passes at S and fails at T. \
Give at most {MAX_CANDIDATES} lessons, each about a different change. Return an empty list if the diff \
changes no behaviour (only comments, docs, tests or formatting).

{_FIELDS_HELP}"""

CONTROL_SYSTEM = f"""\
You draft matched controls for a constructed stale lesson. A matched control is a lesson about the \
same file or symbol area as the stale lesson, of similar length and of the same assumption type, \
whose assumption holds both at S and at T: the diff between them does not change it. Give at most \
{MAX_CANDIDATES} alternatives, best first.

{_FIELDS_HELP}"""


# Records ------------------------------------------------------------------


@dataclass(frozen=True)
class Draft:
    """One drafted lesson with its single assumption."""

    lesson_text: str
    content: AssumptionContent

    @classmethod
    def parse(cls, item: dict) -> Draft:
        if not isinstance(item["code_pointers"], list):
            raise TypeError("code_pointers is not a list")
        try:
            atype = AssumptionType(item["assumption_type"].strip())
        except ValueError:
            atype = AssumptionType.UNCHECKABLE
        content = AssumptionContent(
            statement=item["statement"].strip(),
            assumption_type=atype,
            scope=item["scope"].strip(),
            code_pointers=tuple(p.strip() for p in item["code_pointers"] if p.strip()),
            check_command=item["check_command"].strip(),
            asserted_target=item["asserted_target"].strip(),
        )
        return cls(item["lesson_text"].strip(), content)

    def as_json(self) -> str:
        c = self.content
        return json.dumps(
            {
                "lesson_text": self.lesson_text, "statement": c.statement, "assumption_type": str(c.assumption_type),
                "scope": c.scope, "code_pointers": list(c.code_pointers), "check_command": c.check_command,
                "asserted_target": c.asserted_target,
            },
            ensure_ascii=False,
        )  # fmt: skip

    @property
    def files(self) -> frozenset[str]:
        return frozenset(p for p in map(file_part, self.content.code_pointers) if p)


@dataclass(frozen=True)
class CaseRecord:
    """One drafted candidate and what became of it. Part of the constructed-case mapping: scorer only."""

    case_key: str
    pair_id: str
    role: Role  # CONSTRUCTED_STALE or MATCHED_CONTROL
    stale_case_key: str
    lesson_id: str
    assumption_id: str
    status: CaseStatus
    detail: str
    draft: str


_CASE_COLUMNS = "case_key, pair_id, role, stale_case_key, lesson_id, assumption_id, status, detail, draft"


def _ensure_schema(store: RunStore) -> None:
    store.conn.executescript(SCHEMA_SQL)


def constructed_lesson_id(case_key: str) -> str:
    """A neutral id for a constructed lesson: it says neither its role nor its pair."""
    return "c-" + hashlib.sha256(case_key.encode()).hexdigest()[:16]


def _assumption_id(lesson_id: str) -> str:
    """The id `Assumptions.add` gives the first (and only) assumption of a new lesson."""
    return f"{lesson_id}#1"


def _drafts_subject(pair_id: str) -> str:
    return f"constructed cases for pair {pair_id}"


# The constructed-case mapping: read by the scorer only ------------------------


def case_records(store: RunStore, pair_id: str | None = None) -> list[CaseRecord]:
    """The constructed-case mapping: every drafted candidate, its role and status. For the scorer only."""
    _ensure_schema(store)
    rows = store.conn.execute(
        f"SELECT {_CASE_COLUMNS} FROM constructed_cases WHERE (? IS NULL OR pair_id = ?) ORDER BY rowid",
        (pair_id, pair_id),
    )
    return [
        CaseRecord(key, pid, Role(role), stale_key, lesson_id, aid, CaseStatus(status), detail, draft)
        for key, pid, role, stale_key, lesson_id, aid, status, detail, draft in rows
    ]


# The stage ------------------------------------------------------------------


class _Constructor:
    def __init__(self, store: RunStore, client: LLMClient, runner: CheckRunner):
        self.store, self.client = store, client
        self.checker = _Checker(store, EvidenceStore(store), runner)
        self.counts = Counter()

    def construct_pair(self, pair: RevisionPair) -> None:
        repository = Repository(self.store.repositories()[pair.repository])
        diff = repository.diff(pair.source_revision, pair.target_revision, DIFF_PATHS)
        subject = _drafts_subject(pair.pair_id)
        try:
            drafts = self._draft(STALE_SYSTEM, _stale_prompt(pair, diff), STALE_SCHEMA, "candidates", subject)
        except LLMFailure as exc:
            self.store.record_exclusion(STAGE, subject, ExclusionReason.EXTRACTION_FAILED, f"drafting failed: {exc}")
            self.counts["drafting failed"] += 1
            return
        if not drafts:
            self.store.record_exclusion(
                STAGE, subject, ExclusionReason.NO_BEHAVIOUR_CHANGE_FOUND, "the S..T diff yielded no candidate"
            )
            return
        self.store.clear_exclusion(STAGE, subject)
        for n, draft in enumerate(drafts, start=1):
            case_key = f"{pair.pair_id}/constructed-stale-{n}"
            failure = self._gate(draft, case_key, pair, Outcome.FAIL_ON_TARGET)
            candidate_subject = f"candidate {case_key}"
            if failure:
                self._record_case(case_key, pair, Role.CONSTRUCTED_STALE, "", draft, CaseStatus.GATE_FAILED, failure)
                self.store.record_exclusion(STAGE, candidate_subject, ExclusionReason.GATE_FAILED, failure)
                continue
            self.store.clear_exclusion(STAGE, candidate_subject)
            self._keep(case_key, pair, draft)
            self._record_case(case_key, pair, Role.CONSTRUCTED_STALE, "", draft, CaseStatus.KEPT, "")
            self._match_control(case_key, pair, draft, diff)

    def _match_control(self, stale_key: str, pair: RevisionPair, stale: Draft, diff: str) -> None:
        """Keep the first drafted control that matches the stale lesson and passes 3/3 at S and T."""
        subject = f"candidate {stale_key}"
        try:
            controls = self._draft(
                CONTROL_SYSTEM, _control_prompt(pair, stale, diff), CONTROL_SCHEMA, "controls", subject
            )
        except LLMFailure as exc:
            controls, problem = [], f"drafting failed: {exc}"
        else:
            problem = "no control drafted"
        for m, control in enumerate(controls, start=1):
            case_key = f"{stale_key}/matched-control-{m}"
            mismatch = _mismatch(stale, control)
            if mismatch:
                self._record_case(case_key, pair, Role.MATCHED_CONTROL, stale_key, control, CaseStatus.NOT_MATCHED, mismatch)
                problem = f"matched-control-{m}: {mismatch}"
                continue
            failure = self._gate(control, case_key, pair, Outcome.PASS)
            if failure:
                self._record_case(case_key, pair, Role.MATCHED_CONTROL, stale_key, control, CaseStatus.GATE_FAILED, failure)
                problem = f"matched-control-{m}: {failure}"
                continue
            self._keep(case_key, pair, control)
            self._record_case(case_key, pair, Role.MATCHED_CONTROL, stale_key, control, CaseStatus.KEPT, "")
            self.store.clear_exclusion(STAGE, subject)
            return
        self.store.record_exclusion(STAGE, subject, ExclusionReason.NO_MATCHED_CONTROL, problem)

    def _gate(self, draft: Draft, case_key: str, pair: RevisionPair, expected_at_t: Outcome) -> str:
        """"" if the draft's check passes 3/3 at S and gives `expected_at_t` 3/3 at T, else why not.

        The runs are stored as evidence of the assumption the draft would get, so `check` reuses them."""
        content = draft.content
        if not content.assumption_type.checkable or not content.check_command or not content.asserted_target:
            return "not checkable: needs one of the five assumption types, a check command and an asserted target"
        lesson_id = constructed_lesson_id(case_key)
        a = Assumption(_assumption_id(lesson_id), lesson_id, content, ORIGIN, ReviewStatus.PENDING, None)
        env = environment_for(self.store, pair)
        at_s = self.checker.outcomes(a, "S", pair.source_revision, "", env)
        if any(o is not Outcome.PASS for o in at_s):
            return f"runs at S: {listing(at_s)}"
        at_t = self.checker.outcomes(a, "T", pair.target_revision, pair.pair_id, env)
        if any(o is not expected_at_t for o in at_t):
            return f"runs at S: {listing(at_s)}; runs at T: {listing(at_t)} (needs 3/3 {expected_at_t})"
        return ""

    def _keep(self, case_key: str, pair: RevisionPair, draft: Draft) -> None:
        """Store a kept constructed lesson and its assumption (pending review)."""
        lesson_id = constructed_lesson_id(case_key)
        lesson = Lesson(lesson_id, draft.lesson_text, pair.source_instance, pair.repository, pair.source_revision, "")
        ConstructedLessons(self.store).add(lesson, pair.pair_id)
        Assumptions(self.store).add(lesson_id, draft.content, ORIGIN)

    def _record_case(
        self, case_key: str, pair: RevisionPair, role: Role, stale_key: str, draft: Draft, status: CaseStatus, detail: str
    ) -> None:
        lesson_id = constructed_lesson_id(case_key)
        with self.store.conn:
            self.store.conn.execute(
                f"INSERT OR REPLACE INTO constructed_cases ({_CASE_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (case_key, pair.pair_id, str(role), stale_key, lesson_id, _assumption_id(lesson_id), str(status), detail,
                 draft.as_json()),
            )  # fmt: skip

    def _draft(self, system: str, prompt: str, schema: dict, key: str, subject: str) -> list[Draft]:
        request = LLMRequest(system, prompt, schema)
        return self.client.call(request, lambda data: [Draft.parse(item) for item in data[key]], subject=subject)


def _truncated(diff: str) -> str:
    if len(diff) <= MAX_DIFF_CHARS:
        return diff
    return diff[:MAX_DIFF_CHARS] + f"\n[diff truncated: {len(diff) - MAX_DIFF_CHARS} more characters]\n"


def _stale_prompt(pair: RevisionPair, diff: str) -> str:
    return (
        "Draft constructed stale lessons.\n"
        f"Repository: {pair.repository}\n"
        f"Source revision S: {pair.source_revision}\n"
        f"Target revision T: {pair.target_revision}\n\n"
        f"Diff S..T ({', '.join(DIFF_PATHS)}):\n{_truncated(diff)}"
    )


def _control_prompt(pair: RevisionPair, stale: Draft, diff: str) -> str:
    c = stale.content
    return (
        "Draft matched controls for this constructed stale lesson.\n"
        f"Repository: {pair.repository}\n"
        f"Source revision S: {pair.source_revision}\n"
        f"Target revision T: {pair.target_revision}\n\n"
        f"Stale lesson ({len(stale.lesson_text)} characters):\n{stale.lesson_text}\n"
        f"Its assumption ({c.assumption_type}): {c.statement}\n"
        f"Code pointers: {'; '.join(c.code_pointers)}\n\n"
        f"Diff S..T ({', '.join(DIFF_PATHS)}):\n{_truncated(diff)}"
    )


def _mismatch(stale: Draft, control: Draft) -> str:
    """"" if `control` is matched to `stale` (V6: same file area, same type, similar length), else why not."""
    if control.content.assumption_type != stale.content.assumption_type:
        return f'assumption type "{control.content.assumption_type}" differs from "{stale.content.assumption_type}"'
    if not control.files & stale.files:
        return f"no supporting file in common with the stale lesson ({', '.join(sorted(stale.files)) or 'none'})"
    ratio = len(control.lesson_text) / max(1, len(stale.lesson_text))
    if not 1 / LENGTH_RATIO <= ratio <= LENGTH_RATIO:
        return f"lesson length {len(control.lesson_text)} vs {len(stale.lesson_text)} characters"
    return ""


def _pairs_to_construct(store: RunStore, wanted: list[str] | None) -> list[RevisionPair]:
    kept = {pid for pid, verdict in EvidenceStore(store).drift_verdicts().items() if verdict == KEPT}
    pairs = store.revision_pairs()
    if wanted:
        known = {p.pair_id for p in pairs}
        unknown = [pid for pid in wanted if pid not in known]
        if unknown:
            raise RunError(f"not a recorded revision pair: {', '.join(unknown)} (run `pairs` first)")
        not_kept = [pid for pid in wanted if pid not in kept]
        if not_kept:
            raise RunError(f"not kept by the drift guard: {', '.join(not_kept)} (run `drift` first)")
        pairs = [p for p in pairs if p.pair_id in wanted]
    return [p for p in pairs if p.pair_id in kept]


def _summary(store: RunStore) -> Counter:
    counts = Counter()
    for record in case_records(store):
        counts[(record.role, record.status)] += 1
    for exclusion in store.exclusions():
        if exclusion.stage == STAGE:
            counts[exclusion.reason] += 1
    return counts


def cmd_construct(args) -> int:
    store = open_run(args)
    _ensure_schema(store)
    pairs = _pairs_to_construct(store, args.pair)
    client = LLMClient(llm.make_llm(args.model), store, STAGE)
    runner = make_runner(store, args.runner)
    constructor = _Constructor(store, client, runner)
    try:
        for pair in pairs:
            constructor.construct_pair(pair)
    finally:
        runner.close()
    counts = _summary(store)
    print(f"construct: {len(pairs)} revision pairs, cost ${client.cost_usd:.4f}")
    print(
        f"  constructed stale lessons kept: {counts[(Role.CONSTRUCTED_STALE, CaseStatus.KEPT)]}, "
        f"gate failed: {counts[str(ExclusionReason.GATE_FAILED)]}"
    )
    print(
        f"  matched controls: {counts[(Role.MATCHED_CONTROL, CaseStatus.KEPT)]}, "
        f"no matched control: {counts[str(ExclusionReason.NO_MATCHED_CONTROL)]}"
    )
    print(f"  no behaviour change found: {counts[str(ExclusionReason.NO_BEHAVIOUR_CHANGE_FOUND)]}")
    if counts[str(ExclusionReason.EXTRACTION_FAILED)]:
        print(f"  drafting failed: {counts[str(ExclusionReason.EXTRACTION_FAILED)]} (rerun to retry)")
    return 0


def add_parsers(stages: argparse._SubParsersAction) -> None:
    con = stages.add_parser(
        "construct", help="draft constructed stale lessons and matched controls per drift-kept revision pair"
    )
    con.add_argument("--pair", action="append", help="only this pair id (repeatable; default: every kept pair)")
    con.add_argument("--model", default=DEFAULT_MODEL, help=f"model id (default {DEFAULT_MODEL})")
    con.add_argument("--runner", default="docker", help=RUNNER_HELP)


COMMANDS = {"construct": cmd_construct}
