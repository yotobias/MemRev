"""Stages `construct` and `variant-bank`: constructed stale lessons, matched controls and the blinded
variant memory bank per revision pair (V4, V5, V6, V29, V30).

Per drift-kept revision pair, an LLM reads the S..T diff and drafts candidate stale lessons: advice
that relied on behaviour the diff changes, each with one assumption and its check. The repository is
only read, never modified (V4). A candidate is kept only if its check passes 3/3 at S and fails 3/3 on
its asserted target at T (V5, V20); the runs are stored as evidence under the assumption the candidate
would get, so the `check` stage later reuses them. Each kept stale lesson then gets one matched
control, drafted the same way, that passes 3/3 at S and at T (V6).

Kept constructed lessons live in `constructed_lessons` (the lesson-bank schema plus their pair); their
assumptions enter the shared `assumptions` table as pending (origin `construct`), so they go through
`review-export`/`review-import`, `check` and label sign-off like natural ones (V29).

Which constructed lesson is a stale lesson and which a control (`constructed_cases`), and which lesson
sits behind each opaque id of a variant bank (`variant_mapping`, see `memrev.variant_bank`), is the
constructed-case mapping. Only the scorer reads it, through `case_records` and `variant_entries`; the
harness never imports this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from collections import Counter
from dataclasses import dataclass

from memrev.assumptions import Assumption, AssumptionContent, Assumptions, AssumptionType, ReviewStatus
from memrev.check_runner import CheckRunner, Outcome, make_runner
from memrev.checks import KEPT, RUNNER_HELP, _Checker, environment_for
from memrev.constructed_lessons import ConstructedLessons
from memrev.evidence import EvidenceStore
from memrev.harness import file_part, supporting_files
from memrev.llm import DEFAULT_MODEL, LLM, AnthropicLLM, LLMClient, LLMFailure, LLMRequest
from memrev.repository import Repository
from memrev.store import ExclusionReason, Lesson, RevisionPair, RunError, RunStore
from memrev.variant_bank import VariantBank

STAGE = ORIGIN = "construct"
STALE, CONTROL, NATURAL = "constructed stale lesson", "matched control", "natural lesson"
# Status of a case (one drafted candidate).
KEPT_CASE, GATE_FAILED, NOT_MATCHED = "kept", "gate failed", "not matched"

DIFF_PATHS = ("*.py",)  # the diff the LLM sees: Python files only
MAX_DIFF_CHARS = 60_000
MAX_CANDIDATES = 3  # per pair, and controls per stale lesson
LENGTH_RATIO = 2.0  # a control's lesson text is at most this many times longer or shorter

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS constructed_cases (
    case_key TEXT PRIMARY KEY,            -- <pair_id>/stale-<n> or <pair_id>/stale-<n>/control-<m>
    pair_id TEXT NOT NULL,
    role TEXT NOT NULL,                   -- constructed stale lesson | matched control
    stale_case_key TEXT NOT NULL,         -- for a control: its stale lesson's case; else ''
    lesson_id TEXT NOT NULL,              -- the constructed lesson id (kept or not)
    assumption_id TEXT NOT NULL,
    status TEXT NOT NULL,                 -- kept | gate failed | not matched
    detail TEXT NOT NULL,
    draft TEXT NOT NULL                   -- the LLM's candidate as JSON
);
CREATE TABLE IF NOT EXISTS variant_mapping (
    pair_id TEXT NOT NULL,
    variant_lesson_id TEXT NOT NULL,      -- the opaque id in the variant bank
    kind TEXT NOT NULL,                   -- natural lesson | constructed stale lesson | matched control
    lesson_id TEXT NOT NULL,              -- the natural or constructed lesson behind it
    PRIMARY KEY (pair_id, variant_lesson_id)
);
CREATE TABLE IF NOT EXISTS variant_salts (
    pair_id TEXT PRIMARY KEY,
    salt TEXT NOT NULL                    -- secret: opaque ids and the replacement order derive from it
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


def make_llm(model: str) -> LLM:
    """The real LLM for a model id. Tests replace this with a fake."""
    return AnthropicLLM(model)


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
    role: str  # STALE or CONTROL
    stale_case_key: str
    lesson_id: str
    assumption_id: str
    status: str  # KEPT_CASE, GATE_FAILED or NOT_MATCHED
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


def _listing(outcomes) -> str:
    return ", ".join(str(o) for o in outcomes)


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
    return [CaseRecord(*row) for row in rows]


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
            case_key = f"{pair.pair_id}/stale-{n}"
            failure = self._gate(draft, case_key, pair, Outcome.FAIL_ON_TARGET)
            candidate_subject = f"candidate {case_key}"
            if failure:
                self._record_case(case_key, pair, STALE, "", draft, GATE_FAILED, failure)
                self.store.record_exclusion(STAGE, candidate_subject, ExclusionReason.GATE_FAILED, failure)
                continue
            self.store.clear_exclusion(STAGE, candidate_subject)
            self._keep(case_key, pair, draft)
            self._record_case(case_key, pair, STALE, "", draft, KEPT_CASE, "")
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
            case_key = f"{stale_key}/control-{m}"
            mismatch = _mismatch(stale, control)
            if mismatch:
                self._record_case(case_key, pair, CONTROL, stale_key, control, NOT_MATCHED, mismatch)
                problem = f"control-{m}: {mismatch}"
                continue
            failure = self._gate(control, case_key, pair, Outcome.PASS)
            if failure:
                self._record_case(case_key, pair, CONTROL, stale_key, control, GATE_FAILED, failure)
                problem = f"control-{m}: {failure}"
                continue
            self._keep(case_key, pair, control)
            self._record_case(case_key, pair, CONTROL, stale_key, control, KEPT_CASE, "")
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
            return f"runs at S: {_listing(at_s)}"
        at_t = self.checker.outcomes(a, "T", pair.target_revision, pair.pair_id, env)
        if any(o is not expected_at_t for o in at_t):
            return f"runs at S: {_listing(at_s)}; runs at T: {_listing(at_t)} (needs 3/3 {expected_at_t})"
        return ""

    def _keep(self, case_key: str, pair: RevisionPair, draft: Draft) -> None:
        """Store a kept constructed lesson and its assumption (pending review)."""
        lesson_id = constructed_lesson_id(case_key)
        lesson = Lesson(lesson_id, draft.lesson_text, pair.source_instance, pair.repository, pair.source_revision, "")
        ConstructedLessons(self.store).add(lesson, pair.pair_id)
        Assumptions(self.store).add(lesson_id, draft.content, ORIGIN)

    def _record_case(
        self, case_key: str, pair: RevisionPair, role: str, stale_key: str, draft: Draft, status: str, detail: str
    ) -> None:
        lesson_id = constructed_lesson_id(case_key)
        with self.store.conn:
            self.store.conn.execute(
                f"INSERT OR REPLACE INTO constructed_cases ({_CASE_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (case_key, pair.pair_id, role, stale_key, lesson_id, _assumption_id(lesson_id), status, detail,
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
    store = RunStore.open(args.run.expanduser().resolve())
    _ensure_schema(store)
    pairs = _pairs_to_construct(store, args.pair)
    client = LLMClient(make_llm(args.model), store, STAGE)
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
        f"  constructed stale lessons kept: {counts[(STALE, KEPT_CASE)]}, "
        f"gate failed: {counts[str(ExclusionReason.GATE_FAILED)]}"
    )
    print(
        f"  matched controls: {counts[(CONTROL, KEPT_CASE)]}, "
        f"no matched control: {counts[str(ExclusionReason.NO_MATCHED_CONTROL)]}"
    )
    print(f"  no behaviour change found: {counts[str(ExclusionReason.NO_BEHAVIOUR_CHANGE_FOUND)]}")
    if counts[str(ExclusionReason.EXTRACTION_FAILED)]:
        print(f"  drafting failed: {counts[str(ExclusionReason.EXTRACTION_FAILED)]} (rerun to retry)")
    return 0


# variant-bank -------------------------------------------------------------


@dataclass(frozen=True)
class VariantEntry:
    """What sits behind one opaque id of a variant bank. Part of the constructed-case mapping: scorer only."""

    pair_id: str
    variant_lesson_id: str
    kind: str  # NATURAL, STALE or CONTROL
    lesson_id: str  # the natural lesson id, or the constructed lesson id (see `case_records`)


def variant_entries(store: RunStore, pair_id: str | None = None) -> list[VariantEntry]:
    """The opaque-id mapping of the variant banks. For the scorer only."""
    _ensure_schema(store)
    rows = store.conn.execute(
        "SELECT pair_id, variant_lesson_id, kind, lesson_id FROM variant_mapping "
        "WHERE (? IS NULL OR pair_id = ?) ORDER BY pair_id, variant_lesson_id",
        (pair_id, pair_id),
    )
    return [VariantEntry(*row) for row in rows]


def _salt(store: RunStore, pair_id: str) -> str:
    """The pair's secret salt, created once, so opaque ids stay stable across rebuilds but cannot be
    recomputed from lesson ids by anyone who has not read the mapping."""
    with store.conn:
        store.conn.execute(
            "INSERT OR IGNORE INTO variant_salts (pair_id, salt) VALUES (?, ?)", (pair_id, secrets.token_hex(16))
        )
    return store.conn.execute("SELECT salt FROM variant_salts WHERE pair_id = ?", (pair_id,)).fetchone()[0]


def _digest(salt: str, *parts: str) -> str:
    return hashlib.sha256("\0".join((salt, *parts)).encode()).hexdigest()


def _reviewed_constructed(store: RunStore, pair_id: str) -> list[tuple[Lesson, str]]:
    """The pair's kept constructed lessons whose assumption was accepted in review, with their role."""
    roles = {r.lesson_id: r.role for r in case_records(store, pair_id) if r.status == KEPT_CASE}
    accepted = {a.lesson_id for a in Assumptions(store).reviewed()}
    return [
        (lesson, roles[lesson.lesson_id])
        for lesson, pid in ConstructedLessons(store).all()
        if pid == pair_id and lesson.lesson_id in roles and lesson.lesson_id in accepted
    ]


def build_variant_bank(store: RunStore, pair: RevisionPair) -> tuple[int, int] | None:
    """Build the pair's variant bank (V29): the natural bank of (repository, S) with natural lessons
    replaced, in a salted random order, by the pair's reviewed constructed lessons (extra ones are
    added). Every lesson gets an opaque id and an empty trajectory pointer; a constructed lesson takes
    the task id of the lesson it replaces. Returns (lessons, replaced), or None if the pair has no
    reviewed constructed lesson."""
    _ensure_schema(store)
    constructed = _reviewed_constructed(store, pair.pair_id)
    if not constructed:
        return None
    salt = _salt(store, pair.pair_id)
    natural = sorted(
        (l for l in store.lessons() if (l.repository, l.source_revision) == (pair.repository, pair.source_revision)),
        key=lambda l: _digest(salt, "order", l.lesson_id),
    )
    replaced, kept = natural[: len(constructed)], natural[len(constructed) :]
    behind = [(NATURAL, lesson, lesson.task_id) for lesson in kept] + [
        (role, lesson, replaced[i].task_id if i < len(replaced) else lesson.task_id)
        for i, (lesson, role) in enumerate(constructed)
    ]
    entries, bank = [], []
    for kind, lesson, task_id in behind:
        opaque = "v-" + _digest(salt, pair.pair_id, lesson.lesson_id)[:16]
        entries.append(VariantEntry(pair.pair_id, opaque, kind, lesson.lesson_id))
        bank.append(Lesson(opaque, lesson.lesson_text, task_id, pair.repository, pair.source_revision, ""))
    files = supporting_files(store, [e.lesson_id for e in entries])
    VariantBank(store).replace(pair.pair_id, bank, {e.variant_lesson_id: files[e.lesson_id] for e in entries})
    with store.conn:
        store.conn.execute("DELETE FROM variant_mapping WHERE pair_id = ?", (pair.pair_id,))
        store.conn.executemany(
            "INSERT INTO variant_mapping (pair_id, variant_lesson_id, kind, lesson_id) VALUES (?, ?, ?, ?)",
            [(e.pair_id, e.variant_lesson_id, e.kind, e.lesson_id) for e in entries],
        )
    return len(bank), len(replaced)


def cmd_variant_bank(args) -> int:
    store = RunStore.open(args.run.expanduser().resolve())
    wanted = args.pair or list(dict.fromkeys(pid for _, pid in ConstructedLessons(store).all()))
    for pair_id in wanted:
        pair = store.revision_pair(pair_id)
        if pair is None:
            raise RunError(f"{pair_id} is not a recorded revision pair (run `pairs` first)")
        built = build_variant_bank(store, pair)
        if built is None:
            print(f"variant-bank: pair {pair_id}: no reviewed constructed lesson, no variant bank built")
            continue
        size, replaced = built
        n_constructed = len(_reviewed_constructed(store, pair_id))
        print(
            f"variant-bank: pair {pair_id}: {size} lessons; "
            f"{n_constructed} constructed lessons replaced {replaced} natural lessons"
        )
    if not wanted:
        print("variant-bank: no constructed lessons in this run (run `construct` first)")
    return 0


def add_parsers(stages: argparse._SubParsersAction) -> None:
    con = stages.add_parser(
        "construct", help="draft constructed stale lessons and matched controls per drift-kept revision pair"
    )
    con.add_argument("--pair", action="append", help="only this pair id (repeatable; default: every kept pair)")
    con.add_argument("--model", default=DEFAULT_MODEL, help=f"model id (default {DEFAULT_MODEL})")
    con.add_argument("--runner", default="docker", help=RUNNER_HELP)

    var = stages.add_parser(
        "variant-bank", help="build the blinded variant memory bank per pair from reviewed constructed lessons"
    )
    var.add_argument(
        "--pair", action="append", help="only this pair id (repeatable; default: every pair with constructed lessons)"
    )


COMMANDS = {"construct": cmd_construct, "variant-bank": cmd_variant_bank}
