# MemRev

Research code for checking whether lessons a coding agent learned at one repository revision still hold at a later revision. Pilot B builds a labelled dataset of such assumptions and a harness for scoring maintenance mechanisms against it.

## Language

**Lesson**:
A short piece of advice an agent wrote after a task, tied to the task and the revision it was written at.
_Avoid_: experience, experience entry, memory, memory entry

**Memory bank**:
The set of lessons available to an agent or a maintenance mechanism in one run.
_Avoid_: memory store, lesson store

**Variant memory bank**:
A memory bank for one revision pair in which some natural lessons are replaced by constructed stale lessons and matched controls, all under opaque ids and with no provenance. Only the scorer knows which lesson is which.
_Avoid_: mixed bank, poisoned bank, test bank

**Assumption**:
One concrete, checkable statement about repository behaviour that a lesson relies on (e.g. "`get_user` returns `None` for a missing id").
_Avoid_: claim, fact, belief

**Assumption type**:
One of the fixed kinds of checkable assumption: symbol exists, signature, return/raise behaviour, config or default value, named test passes.
_Avoid_: claim family, category

**Uncheckable assumption**:
An assumption that fits no assumption type; it is recorded and counted but not labelled.
_Avoid_: vague lesson, unverified claim

**Scope**:
The conditions under which an assumption is stated to hold (files, symbols, backend, configuration).
_Avoid_: context, applicability

**Check**:
An executable test or small probe whose outcome decides an assumption at a given revision.
_Avoid_: verification, probe (as a general term), test (when meaning the check itself)

**Source revision (S)**:
The commit at which a lesson was written.
_Avoid_: base revision, original commit

**Target revision (T)**:
A later commit, ancestor-reachable from S in the same repository and SWE-bench version, at which assumptions are re-assessed.
_Avoid_: later revision, new commit

**Revision pair**:
One (S, T) combination that passed the ancestry check and the drift guard.
_Avoid_: transition, revision sequence

**Drift guard**:
A fixed set of sanity tests run at both S and T; if unrelated tests break, the revision pair is dropped.
_Avoid_: environment check

**Supported within scope**:
Label: the check passes at T within the assumption's stated scope.
_Avoid_: valid, holds, true

**Contradicted**:
Label: the check fails at T within the assumption's stated scope.
_Avoid_: invalid, stale (as a label), false

**Inconclusive**:
Label: the check could not decide the assumption, because of a setup error or a check that disagreed with itself across repeated runs.
_Avoid_: unknown, error

**Invalid at S**:
An assumption whose check does not pass 3/3 at its source revision; it is counted but never labelled at T.
_Avoid_: wrong from the start, broken check

**Asserted target**:
The symbol or behaviour a check declares it tests; an error on it counts as evidence, an error elsewhere does not.
_Avoid_: subject, target (alone, to avoid confusion with target revision)

**Check outcome**:
What one execution of a check says: pass, fail on asserted target, harness error (container, timeout, crash or an error away from the asserted target) or out of scope (a fixture, backend or test the check needs is missing at that revision). Labels are derived from the outcomes of three runs.
_Avoid_: result, verdict, status

**Source verdict**:
Whether an assumption's check passes 3/3 at S ("passes at S") or not (invalid at S). Only an assumption that passes at S is checked at T.
_Avoid_: valid, validity, S label

**Proposed label**:
The label the labeller derives from the three check outcomes at T, before a reviewer signs it off.
_Avoid_: suggested label, auto label, prediction

**Final label**:
The label after sign-off: the reviewer's accepted or downgraded label, or inconclusive when a second reviewer disagrees. Only final labels enter the dataset and the scores.
_Avoid_: ground truth, gold label, verdict

**Evidence**:
The stored record of one check execution: revision, command, exit status, output excerpt, run index, time.
_Avoid_: result, log

**Exclusion reason**:
A fixed code saying why a lesson, assumption or revision pair left the pipeline (e.g. no target, environment unavailable, invalid at S, extraction failed, no behaviour change found).
_Avoid_: drop reason, skip reason

**Natural case**:
An assumption from a lesson the agent actually wrote, assessed at a real target revision.
_Avoid_: real case, organic case

**Constructed stale lesson**:
A lesson written by us whose assumption passes its check at S and fails at T, based on a real behaviour change between them.
_Avoid_: injected lesson, synthetic memory, poisoned lesson

**Drafted candidate**:
A lesson with one assumption that the LLM drafted from the S..T diff as a possible constructed stale lesson or matched control, before its gate. It becomes a constructed stale lesson or matched control only if it passes.
_Avoid_: proposal, suggestion, generated lesson

**Gate**:
The execution test a drafted candidate must pass to be kept: 3/3 pass at S and 3/3 fail on asserted target at T for a constructed stale lesson, 3/3 pass at S and at T (plus matching) for a matched control. It is decided again whenever review changes the candidate's assumption.
_Avoid_: filter, validation, acceptance test

**Matched control**:
A lesson paired 1:1 with a constructed stale lesson, about the same file or symbol area and of similar length and type, whose check passes at both S and T.
_Avoid_: control lesson, negative

**Maintenance mechanism**:
A procedure that decides, without access to labels, which lessons in a memory bank to keep, recheck, flag or withhold at T.
_Avoid_: maintenance method, invalidation strategy

**Unnecessary rejection**:
A maintenance mechanism withholding or flagging a lesson whose assumptions are supported within scope at T.
_Avoid_: false rejection, false positive
