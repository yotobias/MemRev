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


# Source verdicts: the check passed 3/3 at S, or it is invalid at S (V20).
PASSES_AT_S = "passes at S"
INVALID_AT_S = str(ExclusionReason.INVALID_AT_S)

# Reasons for an inconclusive label (besides the runner's own `Outcome.HARNESS_ERROR`).
OUT_OF_SCOPE_AT_T = str(ExclusionReason.OUT_OF_SCOPE_AT_T)
DISAGREEMENT = "check disagrees with itself"


def listing(outcomes: Sequence[Outcome]) -> str:
    """The outcomes of repeated runs as one line, e.g. `pass, pass, harness error`."""
    return ", ".join(str(o) for o in outcomes)


def source_verdict(outcomes: Sequence[Outcome]) -> tuple[str, str]:
    """(PASSES_AT_S, "") if every run at S passed, else (INVALID_AT_S, the outcomes)."""
    if outcomes and all(o is Outcome.PASS for o in outcomes):
        return PASSES_AT_S, ""
    return INVALID_AT_S, f"runs at S: {listing(outcomes)}"


def target_label(outcomes: Sequence[Outcome]) -> tuple[Label, str]:
    """The proposed label at T and, for inconclusive, its reason (one of the fixed reasons above;
    the individual outcomes stay in the evidence)."""
    if Outcome.HARNESS_ERROR in outcomes:
        return Label.INCONCLUSIVE, str(Outcome.HARNESS_ERROR)
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
