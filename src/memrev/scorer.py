"""Scorer: the only component that reads labels and the constructed-case mapping (V7, V29).

`score(store)` joins final labels, lesson labels, exclusions, the LLM call log and mechanism decisions
into one plain dict, with natural and constructed cases always under separate keys (V6, V22, V23).
`memrev.report` renders that dict; `export_dataset` writes the dataset for teammates.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from enum import StrEnum

from memrev import constructor, harness, variant_bank
from memrev.assumptions import Assumption, Assumptions, ReviewStatus
from memrev.constructed_lessons import ConstructedLessons
from memrev.constructor import CaseStatus, Role
from memrev.evidence import EvidenceStore
from memrev.extraction import STAGE as EXTRACT_STAGE
from memrev.labeller import Label
from memrev.labels import FinalLabel, LabelStore, LessonLabel, LessonLabelReport
from memrev.llm import call_log
from memrev.store import Exclusion, ExclusionReason, Lesson, RunStore

CONSTRUCT_STAGE = constructor.STAGE



class Section(StrEnum):
    """The report's two sections: natural and constructed cases are never mixed (V7)."""

    NATURAL = "natural"
    CONSTRUCTED = "constructed"

LABELS = tuple(str(label) for label in Label)
AWAITING = "awaiting check or sign-off"


@dataclass(frozen=True)
class _Cases:
    """Which lessons are natural and which are constructed, and where each comes from.

    `kind` holds the lessons that count: natural lessons and the constructed lessons whose case is
    kept now. A constructed lesson whose gate or control matching failed after an edit is in
    `lessons` (it has a repository) but counts nowhere."""

    lessons: dict[str, Lesson]
    kind: dict[str, Section]

    @classmethod
    def of(cls, store: RunStore) -> _Cases:
        lessons = {lesson.lesson_id: lesson for lesson in store.lessons()}
        kind = dict.fromkeys(lessons, Section.NATURAL)
        kept = {r.lesson_id for r in constructor.case_records(store) if r.status == CaseStatus.KEPT}
        for lesson, _pair_id in ConstructedLessons(store).all():
            lessons[lesson.lesson_id] = lesson
            if lesson.lesson_id in kept:
                kind[lesson.lesson_id] = Section.CONSTRUCTED
        return cls(lessons, kind)

    def ids(self, kind: Section) -> list[str]:
        return [lesson_id for lesson_id, k in self.kind.items() if k == kind]

    def counts(self, lesson_id: str) -> bool:
        """False for a constructed lesson whose case is no longer kept."""
        return lesson_id in self.kind or lesson_id not in self.lessons


class Scorer:
    def __init__(self, store: RunStore):
        self.store = store
        self.labels = LabelStore(store)
        self.assumptions = Assumptions(store)
        self.cases = _Cases.of(store)

    def score(self) -> dict:
        reports = {
            Section.NATURAL: self.labels.lesson_report(),
            Section.CONSTRUCTED: _only(self.labels.constructed_lesson_report(), self.cases.ids(Section.CONSTRUCTED)),
        }
        data = {kind: self._section(kind, reports[kind]) for kind in Section}
        data[Section.NATURAL]["extraction"] = self._extraction_yield()
        data[Section.CONSTRUCTED]["cases"] = self._constructed_cases()
        data["llm_cost"] = self._llm_cost()
        return data

    def _section(self, kind: Section, report: LessonLabelReport) -> dict:
        finals = self._current_finals(kind)
        sampled = [final for _, final in finals if final.second_label is not None]
        return {
            "lessons": {
                "in the bank": len(self.cases.ids(kind)),
                "without a checkable assumption": len(report.without_checkable_assumption),
            },
            "assumption_labels": self._assumption_labels(finals),
            "inconclusive_reasons": dict(
                Counter(final.reason for _, final in finals if final.label == Label.INCONCLUSIVE)
            ),
            "lesson_labels": self._lesson_labels(report),
            "reviewer_agreement": {
                "sampled": len(sampled),
                "agreeing": sum(final.second_label == final.reviewer_label for final in sampled),
            },
            "mechanisms": self._mechanisms(kind, report),
            "exclusions": self._exclusions(kind, finals),
        }

    # Labels ---------------------------------------------------------------

    def _reviewed(self, kind: Section) -> dict[str, Assumption]:
        return {
            a.assumption_id: a for a in self.assumptions.reviewed()
            if self.cases.kind.get(a.lesson_id) == kind
        }  # fmt: skip

    def _current_finals(self, kind: Section) -> list[tuple[Assumption, FinalLabel]]:
        """Current final labels of reviewed (accepted) assumptions of one kind of case."""
        reviewed = self._reviewed(kind)
        return [
            (reviewed[final.assumption_id], final) for final in self.labels.final_labels()
            if final.assumption_id in reviewed and reviewed[final.assumption_id].hash == final.assumption_hash
        ]  # fmt: skip

    def _assumption_labels(self, finals: list[tuple[Assumption, FinalLabel]]) -> list[dict]:
        """Final labels per (repository, assumption type)."""
        counts: Counter = Counter()
        for a, final in finals:
            repository = self.cases.lessons[a.lesson_id].repository
            counts[(repository, str(a.content.assumption_type), final.label)] += 1
        groups = sorted({key[:2] for key in counts})
        return [
            {"repository": repo, "assumption_type": atype, **{label: counts[(repo, atype, label)] for label in LABELS}}
            for repo, atype in groups
        ]

    def _lesson_labels(self, report: LessonLabelReport) -> list[dict]:
        """Lesson labels per repository (one per lesson and revision pair), plus those still awaited."""
        counts: Counter = Counter()
        for label in report.labels:
            counts[(self.cases.lessons[label.lesson_id].repository, label.label)] += 1
        for lesson_id, _pair_id in report.awaiting:
            counts[(self.cases.lessons[lesson_id].repository, AWAITING)] += 1
        repositories = sorted({repo for repo, _ in counts})
        return [
            {"repository": repo, **{label: counts[(repo, label)] for label in (*LABELS, AWAITING)}}
            for repo in repositories
        ]

    # Mechanisms (V6, V22, V23) ---------------------------------------------

    def _mechanisms(self, kind: Section, report: LessonLabelReport) -> list[dict]:
        """Per mechanism, summed over its runs: natural cases from the original bank, constructed cases
        from the variant bank (only its constructed lessons; its natural lessons are scored as natural
        cases from the original bank)."""
        labels = {(label.lesson_id, label.pair_id): label for label in report.labels}
        pair_ids = {
            harness.PairKey(p.repository, p.source_revision, p.target_revision): p.pair_id
            for p in self.store.revision_pairs()
        }
        bank = harness.ORIGINAL if kind == Section.NATURAL else harness.VARIANT
        rows: dict[str, dict] = {}
        for run in harness.recorded_runs(self.store):
            pair_id = pair_ids.get(run.pair)
            if run.bank != bank or pair_id is None:
                continue
            decisions = harness.recorded_decisions(self.store, run)
            checked = harness.recorded_checked(self.store, run)
            cost = harness.recorded_cost(self.store, run)
            in_section = self._section_lessons(kind, pair_id, decisions)
            row = rows.setdefault(run.mechanism, _mechanism_row(run.mechanism, kind))
            row["revision pairs"] += 1
            # V23: checks the mechanism ran (whole run), plus one per recheck on the section's lessons, the
            # same lessons as the recheck column, unless the mechanism counted that lesson's check itself.
            row["cost: checks"] += cost.checks_executed + sum(
                decisions[recorded] == harness.Decision.RECHECK and recorded not in checked for recorded in in_section
            )
            row["wall time (s)"] = round(row["wall time (s)"] + cost.wall_time_seconds, 3)
            row["tokens"] += cost.tokens
            section = {lesson_id: decisions[recorded] for recorded, lesson_id in in_section.items()}
            _score_decisions(row, section, {lid: labels.get((lid, pair_id)) for lid in section})
            if kind == Section.CONSTRUCTED:
                _score_controls(row["unnecessary rejection"], section, labels, pair_id, self._stale_of_control())
        return list(rows.values())

    def _section_lessons(self, kind: Section, pair_id: str, decisions: dict[str, str]) -> dict[str, str]:
        """The decided lessons a section scores, as recorded id -> lesson id: every lesson of an original
        bank; of a variant bank only its kept constructed lessons (recorded under opaque ids)."""
        if kind == Section.NATURAL:
            return {lesson_id: lesson_id for lesson_id in decisions}
        return {
            entry.variant_lesson_id: entry.lesson_id
            for entry in variant_bank.variant_entries(self.store, pair_id)
            if entry.kind != Role.NATURAL and entry.variant_lesson_id in decisions
            and self.cases.kind.get(entry.lesson_id) == Section.CONSTRUCTED
        }

    def _stale_of_control(self) -> dict[str, str]:
        """Constructed lesson id of each kept matched control -> that of its constructed stale lesson."""
        records = constructor.case_records(self.store)
        stale = {
            r.case_key: r.lesson_id for r in records
            if r.role == Role.CONSTRUCTED_STALE and r.status == CaseStatus.KEPT
        }  # fmt: skip
        return {
            r.lesson_id: stale[r.stale_case_key] for r in records
            if r.role == Role.MATCHED_CONTROL and r.status == CaseStatus.KEPT and r.stale_case_key in stale
        }  # fmt: skip

    # Dataset export (story 43) ---------------------------------------------

    def dataset(self) -> dict[str, list[dict]]:
        """Lessons, assumptions, evidence and final labels, each record tagged with its case:
        natural lesson, constructed stale lesson or matched control."""
        records = constructor.case_records(self.store)
        case_of_lesson = {r.lesson_id: r.role for r in records}
        case_of_assumption = {r.assumption_id: r.role for r in records}
        constructed_pair = {lesson.lesson_id: pair_id for lesson, pair_id in ConstructedLessons(self.store).all()}

        def case(lesson_id: str) -> Role:
            return case_of_lesson.get(lesson_id, Role.NATURAL)

        lessons = [
            {**asdict(lesson), "case": case(lesson_id), "pair_id": constructed_pair.get(lesson_id, "")}
            for lesson_id, lesson in self.cases.lessons.items() if lesson_id in self.cases.kind
        ]
        assumptions = [_assumption_record(a, case(a.lesson_id)) for a in self.assumptions.all()]
        lesson_of = {a.assumption_id: a.lesson_id for a in self.assumptions.all()}
        evidence = [
            {
                **asdict(e),
                "lesson_id": lesson_of.get(e.assumption_id, ""),
                "case": case_of_assumption.get(e.assumption_id) or case(lesson_of.get(e.assumption_id, "")),
            }
            for e in EvidenceStore(self.store).evidence()
        ]
        finals = [
            {
                **asdict(final),
                "lesson_id": a.lesson_id,
                "repository": self.cases.lessons[a.lesson_id].repository,
                "assumption_type": str(a.content.assumption_type),
                "case": case(a.lesson_id),
            }
            for kind in Section
            for a, final in self._current_finals(kind)
        ]
        return {"lessons": lessons, "assumptions": assumptions, "evidence": evidence, "final_labels": finals}

    # Yield, exclusions and cost ------------------------------------------

    def _exclusions(self, kind: Section, finals: list[tuple[Assumption, FinalLabel]]) -> dict[str, int]:
        """Exclusion rows per reason, plus two reasons that no stage records as a row, derived here so
        nothing is counted twice: uncheckable (assumptions of no assumption type that review did not
        reject, one per assumption) and out of scope at T (current final labels inconclusive for that
        reason, one per assumption and revision pair)."""
        counts = Counter(e.reason for e in self.store.exclusions() if self._exclusion_kind(e) == kind)
        counts[str(ExclusionReason.UNCHECKABLE)] += sum(
            1 for a in self.assumptions.all()
            if self.cases.kind.get(a.lesson_id) == kind
            and not a.content.assumption_type.checkable and a.status is not ReviewStatus.REJECTED
        )  # fmt: skip
        counts[str(ExclusionReason.OUT_OF_SCOPE_AT_T)] += sum(
            final.label == Label.INCONCLUSIVE and final.reason == ExclusionReason.OUT_OF_SCOPE_AT_T
            for _, final in finals
        )
        return {reason: n for reason, n in counts.items() if n}

    def _exclusion_kind(self, exclusion: Exclusion) -> Section | None:
        """The section an exclusion counts in, or None for a `check` row about a constructed assumption
        whose case is no longer kept (that case already counts as gate failed or no matched control)."""
        if exclusion.stage == CONSTRUCT_STAGE:
            return Section.CONSTRUCTED
        noun, _, ident = exclusion.subject.partition(" ")
        if noun == "assumption":
            a = self.assumptions.get(ident)
            lesson_id = a.lesson_id if a else ""
        else:
            lesson_id = ident if noun == "lesson" else ""
        if not self.cases.counts(lesson_id):
            return None
        return self.cases.kind.get(lesson_id, Section.NATURAL)

    def _extraction_yield(self) -> dict:
        extracted = [a for a in self.assumptions.all() if a.origin == EXTRACT_STAGE]
        failed = [
            e for e in self.store.exclusions()
            if e.stage == EXTRACT_STAGE and e.reason == ExclusionReason.EXTRACTION_FAILED
        ]  # fmt: skip
        checkable = sum(a.content.assumption_type.checkable for a in extracted)
        return {
            "lessons processed": len({c.subject for c in call_log(self.store) if c.stage == EXTRACT_STAGE}),
            "assumptions": len(extracted),
            "checkable": checkable,
            "uncheckable": len(extracted) - checkable,
            "extraction failed": len(failed),
        }

    def _constructed_cases(self) -> dict:
        records = constructor.case_records(self.store)
        stale = [r for r in records if r.role == Role.CONSTRUCTED_STALE]
        kept = [r for r in stale if r.status == CaseStatus.KEPT]
        matched = {r.stale_case_key for r in records if r.role == Role.MATCHED_CONTROL and r.status == CaseStatus.KEPT}
        with_control = sum(r.case_key in matched for r in kept)
        dropped_controls = Counter(
            r.status for r in records if r.role == Role.MATCHED_CONTROL and r.status != CaseStatus.KEPT
        )
        return {
            "stale candidates drafted": len(stale),
            "constructed stale lessons kept": len(kept),
            "gate failed": sum(r.status == CaseStatus.GATE_FAILED for r in stale),
            "with a matched control": with_control,
            "without a matched control": len(kept) - with_control,
            # Control candidates dropped (V6): drafted but not matched to their stale lesson, or failing the gate.
            "control candidates not matched": dropped_controls[CaseStatus.NOT_MATCHED],
            "control candidates gate failed": dropped_controls[CaseStatus.GATE_FAILED],
        }

    def _llm_cost(self) -> list[dict]:
        """API calls (cache hits left out), tokens and dollars per pipeline stage."""
        rows: dict[str, dict] = {}
        for call in call_log(self.store):
            if call.cached:
                continue
            row = rows.setdefault(
                call.stage, {"stage": call.stage, "calls": 0, "input tokens": 0, "output tokens": 0, "cost_usd": 0.0}
            )
            row["calls"] += 1
            row["input tokens"] += call.input_tokens
            row["output tokens"] += call.output_tokens
            row["cost_usd"] += call.cost_usd or 0.0
        return list(rows.values())


REJECTED = (harness.Decision.FLAG, harness.Decision.WITHHOLD)


def _mechanism_row(mechanism: str, kind: Section) -> dict:
    return {
        "mechanism": mechanism,
        "revision pairs": 0,
        "lessons scored": 0,
        "contradicted": 0,
        "contradicted kept": 0,
        "contradicted rejected": 0,
        "recheck": 0,
        # Measured on constructed cases with a matched control only (V6).
        "unnecessary rejection": {"rejected": 0, "matched controls": 0} if kind == Section.CONSTRUCTED else None,
        "cost: checks": 0,
        "wall time (s)": 0.0,
        "tokens": 0,
    }


def _score_decisions(row: dict, decisions: dict[str, str], labels: dict[str, LessonLabel | None]) -> None:
    """Keep is kept, flag and withhold are rejected, recheck is neither (V23). Only scored lesson
    labels count (V22): inconclusive and unlabelled lessons are left out."""
    for lesson_id, decision in decisions.items():
        row["recheck"] += decision == harness.Decision.RECHECK
        label = labels[lesson_id]
        if label is None or not label.scored:
            continue
        row["lessons scored"] += 1
        if label.label == Label.CONTRADICTED:
            row["contradicted"] += 1
            row["contradicted kept"] += decision == harness.Decision.KEEP
            row["contradicted rejected"] += decision in REJECTED


def _score_controls(
    tally: dict, decisions: dict[str, str], labels: dict, pair_id: str, stale_of_control: dict[str, str]
) -> None:
    """Unnecessary rejection: a matched control supported within scope, whose stale lesson is in the same
    bank, rejected by the mechanism."""
    for lesson_id, decision in decisions.items():
        label = labels.get((lesson_id, pair_id))
        if stale_of_control.get(lesson_id) not in decisions or label is None or label.label != Label.SUPPORTED:
            continue
        tally["matched controls"] += 1
        tally["rejected"] += decision in REJECTED


def _assumption_record(a: Assumption, case: str) -> dict:
    content = a.content
    return {
        "assumption_id": a.assumption_id,
        "lesson_id": a.lesson_id,
        "statement": content.statement,
        "assumption_type": str(content.assumption_type),
        "scope": content.scope,
        "code_pointers": list(content.code_pointers),
        "check_command": content.check_command,
        "asserted_target": content.asserted_target,
        "assumption_hash": a.hash,
        "origin": a.origin,
        "status": str(a.status),
        "reviewer_id": a.reviewer_id,
        "case": case,
    }


def dataset(store: RunStore) -> dict[str, list[dict]]:
    return Scorer(store).dataset()


def score(store: RunStore) -> dict:
    return Scorer(store).score()


def _only(report: LessonLabelReport, lesson_ids: list[str]) -> LessonLabelReport:
    """The part of a lesson-label report about `lesson_ids`."""
    keep = set(lesson_ids)
    return LessonLabelReport(
        [label for label in report.labels if label.lesson_id in keep],
        [lesson_id for lesson_id in report.without_checkable_assumption if lesson_id in keep],
        [(lesson_id, pair_id) for lesson_id, pair_id in report.awaiting if lesson_id in keep],
    )
