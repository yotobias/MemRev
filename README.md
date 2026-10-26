# MemRev

Research code for checking whether lessons a coding agent learned at one repository revision still hold at later revisions. The project follows the pilot plan in the proposal (Overleaf): Pilot A acquires lessons, Pilot B labels their assumptions across revisions, Pilot C compares maintenance mechanisms, Pilot D measures effects on later tasks.

Read [GLOSSARY.md](GLOSSARY.md) first. Use its terms in code, issues, commits and the paper.

## Repository layout

```
GLOSSARY.md            one word per concept, with the words to avoid
docs/decisions.md      every design decision, numbered (V1, V2, ...)
docs/adr/              decisions that are hard to reverse, one file each
specs/<feature>/       spec.md + tickets/NN-<slug>.md per feature
specs/_done/           finished specs are moved here
pilot-a/               Pilot A: experience acquisition (part 1)
```

Lane N's pipeline lives in `src/memrev/`, with tests in `tests/`. Lane R's scripts live in `pilot-a/scripts/`. Follow the [Pilot A runbook](pilot-a/START_HERE.md) for setup and commands in order. Launch prerequisites and remaining Lane R work are in [RUN_READINESS.md](pilot-a/RUN_READINESS.md).

## Workflow

Every feature goes through the same route. Skipping a step means someone fills in a decision silently, and that decision then has to be found and undone later.

### 1. Grill before building

Before any code, list the open decisions for the feature and answer them one round at a time. Each question comes with a recommended answer, so most can be answered "yes".

- Facts (what a dataset contains, what a library does) are looked up, not asked.
- Choices (scope, behaviour, edge cases, metrics) are decided by the people doing the work, and by the supervisor when they affect the research question.
- Every answer goes into [docs/decisions.md](docs/decisions.md) as the next number, with its topic and the decision in one or two sentences. Never edit an old decision; add a new one that supersedes it and say which.
- A new or changed term goes into [GLOSSARY.md](GLOSSARY.md) straight away.
- A decision that is hard to reverse, would surprise a later reader, and came from a real trade-off also gets an ADR in `docs/adr/NNNN-<slug>.md`.

### 2. Write the spec

`specs/<feature>/spec.md` records the problem, the solution, a numbered list of user stories, implementation decisions, test decisions, what is out of scope, and open points. It is written only from decisions already made.

Before the spec is fixed, someone who did not write the stories walks each one with 2–4 concrete edge cases (missing data, failures of Docker or the LLM API, reruns, two reviewers disagreeing). Every gap or conflict becomes a new grilling round.

### 3. Split into tickets

`specs/<feature>/tickets/NN-<slug>.md`, numbered so blockers come first. Each ticket:

- is a vertical slice: it works end to end and can be demonstrated on its own;
- fits in one working session (for an AI agent: well under ~150k tokens of context);
- lists the tickets that block it and a size estimate;
- has acceptance criteria written as observable behaviour.

Ticket status is one of `ready-for-agent`, `in-progress`, `done`. A ticket can be picked up when it is `ready-for-agent` and all its blockers are `done`.

### 4. Implement one ticket at a time

- Set the ticket to `in-progress` and put your name in its Notes before you start, so nobody else picks it up.
- Work test-first against the agreed test seams in the spec: write a failing test that shows the behaviour, make it pass, repeat.
- Tests assert on observable results (what the run database or exported files contain), not on internal calls.
- Add anything the next person needs (commands, gotchas, paths) to the ticket's Notes section.
- When the acceptance criteria pass, set the ticket to `done`.

If you use an AI coding agent, start a fresh session per ticket and point it at the ticket file.

### 5. Review before merge

Every branch is reviewed on two axes before it merges:

- **Spec:** does the code do what the spec and ticket asked, no more and no less?
- **Standards:** does it follow the project conventions below, and is it free of obvious code smells (duplication, long functions, unclear names)?

Preferably the reviewer is someone who did not write the code.

### 6. Retro

After a feature is done, spend ten minutes on what went wrong in the workflow itself and change this README if needed. Move the finished spec to `specs/_done/`.

## Git

- `main` is always in a working state. No direct pushes.
- One branch per feature (`pilot-b`, `pilot-a`, ...) or per ticket for larger features (`pilot-b/05-checks`).
- Merge through a pull request with at least one review.
- Commit messages: imperative, one line, reference the ticket (`pilot-b 05: run checks 3x at S and T`).
- Never commit API keys. Put them in a local `.env` that git ignores.

## Conventions

- Python 3.11, [uv](https://docs.astral.sh/uv/) for environments, pytest for tests, SQLite for run data.
- Each run gets its own database and work directory outside any repository checkout. Pilot A acquisition packages may instead use this project's gitignored `runs/acquisitions/` directory (V39); keep artifacts separate from the benchmark repository under test.
- LLM calls go through the shared client interface so model, tokens and cost are logged.
- Results from natural and constructed cases are always reported separately.

## Current work

| Feature | Spec | Status |
|---------|------|--------|
| Pilot A: experience acquisition | [pilot-a/](pilot-a/) | extraction/evaluation and offline handoff plumbing implemented ([guide](pilot-a/HANDOFF.md)); contracts proposed, production runs and research judgments pending |
| Pilot B: assumption applicability across revisions | [specs/pilot-b/spec.md](specs/pilot-b/spec.md) | 11 tickets ready, start with 01 |
