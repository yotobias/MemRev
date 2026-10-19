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
src/memrev/            the Pilot B pipeline (one CLI: `memrev`)
tests/                 pytest, seam N1 (stages driven through the CLI)
fixtures/django/       hand-written django fixture memory bank
```

## Running the pipeline

```
uv sync                                   # install into .venv
uv run pytest                             # run the tests
uv run memrev --run ~/memrev-runs/r1 init --repo django/django=/path/to/django-clone
uv run memrev --run ~/memrev-runs/r1 import fixtures/django/lessons.jsonl
uv run memrev --run ~/memrev-runs/r1 pairs
uv run memrev --run ~/memrev-runs/r1 extract --limit 30              # LLM extraction; needs ANTHROPIC_API_KEY (env or .env)
uv run memrev --run ~/memrev-runs/r1 seed-assumptions my-seed.csv     # optional, hand-written assumptions
uv run memrev --run ~/memrev-runs/r1 review-export review.csv
uv run memrev --run ~/memrev-runs/r1 review-import review.csv --reviewer <your-id>
uv run memrev --run ~/memrev-runs/r1 drift      # SWE-bench Docker images; Docker must be running (--runner fake=script.json for a scripted runner)
uv run memrev --run ~/memrev-runs/r1 check
uv run memrev --run ~/memrev-runs/r1 label-export labels.csv
uv run memrev --run ~/memrev-runs/r1 label-import labels.csv --reviewer <your-id>          # accept, inconclusive or rewrite
uv run memrev --run ~/memrev-runs/r1 label-import sample.csv --reviewer <other-id> --second  # optional second reviewer
uv run memrev --run ~/memrev-runs/r1 lesson-labels
uv run memrev --run ~/memrev-runs/r1 construct     # constructed stale lessons + matched controls; needs ANTHROPIC_API_KEY and Docker
uv run memrev --run ~/memrev-runs/r1 review-export review.csv           # then review-import, check, label-export/import as above
uv run memrev --run ~/memrev-runs/r1 variant-bank                       # blinded variant memory bank per pair
uv run memrev --run ~/memrev-runs/r1 run-mechanism file-change-invalidation --pair <pair_id>   # or --repository R --source S --target T
uv run memrev --run ~/memrev-runs/r1 run-mechanism file-change-invalidation --pair <pair_id> --bank variant
uv run memrev --run ~/memrev-runs/r1 report                             # report.md + report.json in the run dir (--out FILE)
uv run memrev --run ~/memrev-runs/r1 export ~/memrev-runs/r1-dataset    # lessons, assumptions, evidence, final labels as JSONL + CSV
```

The run directory holds `run.db` (SQLite) and `work/`, and must be outside any repository checkout. The lesson-bank format is in [docs/lesson-bank-schema.md](docs/lesson-bank-schema.md).

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
- Each run gets its own database and work directory outside any repository checkout.
- LLM calls go through the shared client interface so model, tokens and cost are logged.
- Results from natural and constructed cases are always reported separately.

## Current work

| Feature | Spec | Status |
|---------|------|--------|
| Pilot A: experience acquisition | [pilot-a/](pilot-a/) | not started |
| Pilot B: assumption applicability across revisions | [specs/pilot-b/spec.md](specs/pilot-b/spec.md) | 01–06 and 08–10 done; 07 waits for the real-Docker test (N2); 11 waits for Docker and an LLM backend |

## Status, 19 October 2026

### Where Pilot B stands

The Pilot B pipeline is built on branch `spec/pilot-b` and has been tested only with fakes. It has not run on real data yet.

- **Done (9 of 11 tickets):**
  - lesson import;
  - revision pairs from SWE-bench Verified;
  - assumption extraction and review;
  - checks run 3 times at S and T, with the drift guard;
  - label sign-off and lesson labels;
  - constructed stale lessons, matched controls and the blinded variant memory bank;
  - the mechanism harness, shipping no maintenance and file-change invalidation;
  - the scorer, report and export.
- **Tests:** 198 pass; 10 skipped (they need Docker or a real repository clone).
- **Review:** the whole branch had a spec review and a standards review, and every finding was fixed. Two real bugs were found and fixed. A constructed lesson stayed counted as stale after its check was edited. Some non-test failures were counted as contradicted instead of inconclusive.
- **Data source:** we build our own revision pairs from SWE-bench Verified, because SWE-ContextBench has not released its data ([ADR 0001](docs/adr/0001-own-revision-pairs-from-swe-bench-verified.md)). On the real django history, the 12 fixture lessons give 36 revision pairs, and none failed the ancestry check.
- **Not done:**
  - **Ticket 07 (Docker check runner)** is built, but its test against a real SWE-bench image has not run.
  - **Ticket 11** is the first real django run on about 30 lessons. It ends with a go / narrow / stop recommendation.
- **Decisions:** V1–V32 are in [docs/decisions.md](docs/decisions.md). The small choices made while building are listed in each ticket's Notes. Please read them and object where you disagree.

### Decisions the team needs to make

**1. Which LLM do we use for extraction and drafting?**

Two stages need a language model:
- `extract` proposes the checkable assumptions in each lesson.
- `construct` drafts constructed stale lessons and matched controls from the S..T diff.

Everything else runs without one. The code puts the LLM behind one interface, so switching costs one small adapter. V9 currently says "Anthropic API", which is paid per token.

| Option | Cost | Trade-off |
|--------|------|-----------|
| **A. Anthropic API (current)** | Pay per token. Rough estimate for the pilot (30 lessons, ~36 pairs): a few dollars | Needs an API key and a budget owner. Most reproducible: model and token counts are logged exactly. |
| **B. Claude Code subscription (`claude -p`)** | No API tokens; counts toward a team member's subscription limits | Runs on one person's account. The model version is less pinned. Fine for a pilot, weaker for the paper's reproducibility claims. |
| **C. Hand-written** | Free | We already support hand-written assumptions. Constructed lessons would need a small CSV import. Slow, and less like what agents really write. |
| **D. Local open model (Ollama)** | Free after setup | Weaker at structured extraction, so we would need to measure its quality. Needs a capable machine. |

Suggestion: use **B or C for the pilot** to answer the go/no-go question cheaply. Move to **A** (or a supervisor-funded key) for anything that goes into the paper.

**2. Where do the checks run?**

Checks run inside SWE-bench Docker images. These images are x86-only (about 1.15 GB each).

| Option | Trade-off |
|--------|-----------|
| **A. A team member's Mac (Docker Desktop + Rosetta)** | Works now, but emulation is slow. Fine for ~30 lessons, painful at scale. |
| **B. A Linux x86 machine (lab PC, TU Delft cluster, or a cloud VM)** | Native speed. Someone has to arrange access, and Docker must be allowed on it. |

Suggestion: A for ticket 11, and look into B before scaling up.

**3. How do we count cross-version exclusions? (V31, open)**

The `pairs` stage records one "cross-version" exclusion for every later task in a different SWE-bench version. For 12 lessons that is 984 rows, which would swamp the report.

Proposal: record one row per source revision instead, with the count in the details. Also record a source whose commit is missing from the clone, instead of skipping it silently.

**4. Pilot A: who runs it, and with which agent?**

Pilot B currently runs on 12 hand-written fixture lessons. Real lessons need Pilot A: an agent solving SWE-bench Verified tasks in django (then sympy and scikit-learn) and writing lessons in the [lesson-bank format](docs/lesson-bank-schema.md). The open questions are in [pilot-a/README.md](pilot-a/README.md). The model choice in decision 1 applies here as well, at a much larger token cost, because the agent has to solve tasks and not just read lessons.

**5. Data source follow-up**

Someone should email the SWE-ContextBench authors (arXiv 2602.08316) to ask for their related-task groups. If the data arrives, it can replace or supplement our own pairs.

### Next steps once these are decided

1. Finish ticket 07: run the real-image test.
2. Run ticket 11, the first real django run, and share the yield and timing.
3. Open a PR from `spec/pilot-b` into `main` for team review.
4. Start the Pilot A grilling.
