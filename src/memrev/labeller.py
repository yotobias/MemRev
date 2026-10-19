"""Labeller: fixed rules from the outcomes of repeated check runs to a verdict or proposed label.

Pure functions, no store access. V15 (3 runs, disagreement is inconclusive), V20 (3/3 pass at S),
V21 (asserted target, harness errors, out of scope at T).
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from memrev.check_runner import Outcome
from memrev.store import ExclusionReason


class Label(StrEnum):
    SUPPORTED = "supported within scope"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"


VALID = "valid"
INVALID_AT_S = str(ExclusionReason.INVALID_AT_S)

# Reasons for an inconclusive label.
HARNESS_ERROR = "harness error"
OUT_OF_SCOPE_AT_T = str(ExclusionReason.OUT_OF_SCOPE_AT_T)
DISAGREEMENT = "check disagrees with itself"


def _listing(outcomes: Sequence[Outcome]) -> str:
    return ", ".join(str(o) for o in outcomes)


def source_verdict(outcomes: Sequence[Outcome]) -> tuple[str, str]:
    """(VALID, "") if every run at S passed, else (INVALID_AT_S, the outcomes)."""
    if outcomes and all(o is Outcome.PASS for o in outcomes):
        return VALID, ""
    return INVALID_AT_S, f"runs at S: {_listing(outcomes)}"


def target_label(outcomes: Sequence[Outcome]) -> tuple[Label, str]:
    """The proposed label at T and, for inconclusive, its reason (one of the fixed reasons above;
    the individual outcomes stay in the evidence)."""
    if Outcome.HARNESS_ERROR in outcomes:
        return Label.INCONCLUSIVE, HARNESS_ERROR
    if len(set(outcomes)) != 1:
        return Label.INCONCLUSIVE, DISAGREEMENT
    only = outcomes[0]
    if only is Outcome.PASS:
        return Label.SUPPORTED, ""
    if only is Outcome.FAIL_ON_TARGET:
        return Label.CONTRADICTED, ""
    return Label.INCONCLUSIVE, OUT_OF_SCOPE_AT_T


def lesson_label(assumption_labels: Sequence[str]) -> Label:
    """V22: contradicted if any assumption is contradicted, supported within scope only if all are,
    otherwise inconclusive. An assumption invalid at S is neither, so pass it as inconclusive."""
    if Label.CONTRADICTED in assumption_labels:
        return Label.CONTRADICTED
    if assumption_labels and all(label == Label.SUPPORTED for label in assumption_labels):
        return Label.SUPPORTED
    return Label.INCONCLUSIVE
