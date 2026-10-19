# 04: LLM extraction

**Status:** done
**Blocked by:** 03
**Estimate:** ~100k tokens

## What to build
A researcher can run extraction over the imported lessons. An LLM proposes the assumptions in each lesson, which then flow into the review CSV from ticket 03. Extraction stops after a configurable number of lessons (default 30) and prints the extraction yield, so the team can decide before scaling.

Covers stories 9, 10, 11, 12, 13, 40. Decisions V2, V9, V16, V17, V28.

## Acceptance criteria
- [x] The LLM sits behind a thin interface with a real implementation (Claude Sonnet 5.5 via the Anthropic API, key from a git-ignored .env) and a fake one for tests.
- [x] Calls retry with backoff; successful outputs are cached by prompt and model so reruns don't call the API again.
- [x] Every call's model, input and output tokens and cost are logged in the run.
- [x] Extracted assumptions are typed as one of the five assumption types; anything else is stored as uncheckable and counted.
- [x] Persistent LLM failures are counted as "extraction failed", separate from uncheckable.
- [x] The stage stops after the lesson limit and prints yield: lessons processed, checkable assumptions, uncheckable, extraction failed, cost.
- [x] Tests use the fake LLM only.

## Notes
- Research: docs/research/anthropic-sdk.md. Sonnet 5.5 returns HTTP 400 for non-default temperature/top_p/top_k, `thinking: disabled`, forced `tool_choice` and assistant prefill; use `messages.parse` with a Pydantic model and `output_config={"effort": "low"}`. Pricing $2 / $10 per MTok in/out, thinking tokens bill as output. The SDK already retries (default 2); add our own backoff on top only for persistent failures.

Built by an AI agent (Claude Code), test-first on seam N1 with the fake LLM only (`tests/test_extraction.py`). No test calls the real API, and no real call was made while building.

**Running extraction for real**
- Put the key in the environment (`export ANTHROPIC_API_KEY=sk-ant-...`) or in a `.env` file in the directory you run `memrev` from, one line `ANTHROPIC_API_KEY=sk-ant-...`. `.env` is git-ignored (`git check-ignore .env` confirms it). Without a key, `extract` exits 2 with a message before any call.
- `uv run memrev --run <dir> extract [--limit 30] [--model claude-sonnet-5-5]`, after `init` and `import`. Then `review-export` / `review-import` as in ticket 03.
- Output: `extract: N lessons processed, C checkable assumptions, U uncheckable, F extraction failed, cost $X.XXXX`, plus `stopped at the lesson limit (30): K lessons not processed; ...` when lessons are left. The cost is what this invocation spent; cache hits cost $0.
- To scale after the yield check, rerun with a higher `--limit`. The first lessons come from the cache (no API call, no cost) and their assumptions are not duplicated (`Assumptions.add` skips content already present for a lesson).
- The first real call has not been made. If the API rejects the request shape, the place to look is `AnthropicLLM.complete` in `src/memrev/llm.py` (`messages.create` with `output_config={"effort": "low", "format": {"type": "json_schema", "schema": ...}}`; no temperature, thinking, tool_choice or prefill). A 400 is not retried and counts as extraction failed, so run with `--limit 1` first.

**Layout**
- `src/memrev/llm.py`, the shared LLM client (ticket 08 uses it for drafting):
  - `LLMRequest(system, prompt, schema)`: one structured call; `schema` is a JSON Schema dict (every object needs `required` and `additionalProperties: false` for structured outputs).
  - `LLM` protocol: attribute `model`, method `complete(request) -> LLMResponse(data, usage, model, stop_reason, request_id)`. Raises `LLMError(message, usage=, model=, retryable=)` when a call yields no usable output, and `RunError` for things no retry fixes (missing or rejected key, unknown model).
  - `AnthropicLLM(model="claude-sonnet-5-5", effort="low", max_tokens=16000, timeout_seconds=120, sdk_retries=4)`: the real one. The SDK retries transport errors, 429 and 5xx itself. A stop reason other than `end_turn` (`max_tokens`, `refusal` with its category) or a reply that is not a JSON object is an `LLMError` that keeps the tokens it cost.
  - `FakeLLM(model=..., usage=...)`: `answer(marker, *outcomes)` gives every request whose prompt contains `marker` those outcomes in order (dict returned, exception raised; the last one repeats). Requests are kept in `.calls`.
  - `LLMClient(llm, store, stage, attempts=3, backoff_seconds=2.0)`: `call(request, parse, subject=...)` returns `parse(output)`. It checks the cache first; otherwise it tries up to `attempts` times with backoff 2 s, 4 s, and raises `LLMFailure` when all fail. `parse` raising ValueError/KeyError/TypeError/AttributeError counts as a failed attempt, and that output is not cached. `.cost_usd` totals this client's calls.
  - `call_log(store) -> list[LoggedCall]`, `PRICES` (one table, $/MTok), `cost_usd(model, usage)`, `cache_key(model, request)`.
  - Backoff sleeps through the module attribute `memrev.llm.sleep`; tests replace it.
- `src/memrev/extraction.py`: the `extract` stage, its system prompt, the JSON schema, and `make_llm(model)` (tests monkeypatch this to return the fake; see the `fake_llm` fixture in `tests/test_extraction.py`).
- Tables (created on first use, `store.py` untouched): `llm_cache(cache_key, model, output)` and `llm_calls` (stage, subject, model, attempt, cached, outcome ok/error, error, input/output/cache tokens, cost_usd, stop_reason, request_id, latency_seconds). Every attempt is logged, failed ones too, since failed attempts can still cost tokens. Cache hits are logged with `cached = 1`, zero tokens and cost 0, so summing `cost_usd` gives the real spend.

**Decisions made while building** (small, not grilled)
- Cache key = sha256 over (model, system prompt, prompt, schema). Changing the prompt or schema text invalidates the cache, so no separate prompt version is needed. Effort and max_tokens are not in the key.
- Structured output goes through `messages.create` with a raw JSON schema rather than `messages.parse` with Pydantic. The interface stays a plain dict, and Pydantic is not a direct dependency. The schema has an enum of the five types plus `uncheckable`. Any other type string (from another model or the fake) is stored as `uncheckable`, and the original label is not kept.
- The lesson limit takes the first N lessons in import order, every time. Lessons already done are cache hits, so a rerun is free. This also covers resumability (story 42) for this stage.
- "Extraction failed" is recorded as an exclusion `(stage "extract", subject "lesson <id>", reason "extraction failed")` with the last error as detail, and cleared when a later run succeeds. Uncheckable assumptions are not written as exclusions: they are assumptions with type `uncheckable` (ticket 10 can count them from the assumptions table, which also reflects reviewer edits).
- Retry policy: 3 attempts in our client on top of the SDK's 4 transport retries. A 400 (`BadRequestError`) is not retried. An auth or permission error aborts the stage (exit 2) instead of marking every lesson failed.
- The prompt gives the repository, source revision, task id and lesson text only. The model does not see the code. Code pointers and checks are its proposals, which the reviewer fixes in the CSV.

**Review 2026-10-19:** `make_llm(model)` now lives in `memrev.llm` and stages call `llm.make_llm`, so tests monkeypatch `llm.make_llm` once (for `extract` and `construct` alike).
