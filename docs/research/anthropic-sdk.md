# Anthropic Python SDK: structured extraction with Sonnet 5.5

Sources: the bundled claude-api skill docs (model table cached 2026-10-06) and PyPI (`anthropic` 1.15.0, requires Python >= 3.10).

## Install and client

```
uv add "anthropic>=1.15,<2" pydantic
```
- `anthropic.Anthropic()` reads `ANTHROPIC_API_KEY`, then `ANTHROPIC_AUTH_TOKEN`, then an `ant auth login` profile. Don't hardcode keys.
- 1.x runs on `httpx2`, not `httpx`. Don't pass `httpx` objects. For HTTP-level test mocking, prefer mocking our own thin LLM interface (spec story 13) rather than respx.

## Model and price

| Model | id | input $/MTok | output $/MTok | cache read $/MTok |
|---|---|---|---|---|
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | 2.00 | 10.00 | 0.20 |
(For comparison: Opus 5.5 `claude-opus-5-5` is $4 / $20, Haiku 5.5 `claude-haiku-5-5` is $0.10 / $0.50.)
Use the id exactly as written, with no date suffix. Batch API is 50% off if extraction can run asynchronously.
Cost formula for the log (spec story 12):
`cost = (input_tokens*2 + output_tokens*10 + cache_read_input_tokens*0.2 + cache_creation_input_tokens*write_rate) / 1e6`
The cache write rate is 1.25x input for the 5-minute TTL, i.e. $2.50. Keep prices in one config table, not inline.

## Sonnet 5.5 gotchas (these return HTTP 400 errors, not warnings)
- `temperature` / `top_p` / `top_k` at non-default values give a 400. Leave them out, so you can't use temperature=0 for determinism. Get stability from caching outputs instead.
- `thinking={"type":"disabled"}` gives a 400. Thinking is adaptive by default and billed as output tokens. To turn it off use `thinking={"type":"between_tools"}` (allowed only at effort `high` or below), or just lower `output_config={"effort": "low"}`. For extraction, `low` or `medium` is a sensible start.
- Forced `tool_choice` `{"type":"tool"|"any"}` gives a 400. To get JSON, use structured outputs (below), not a forced tool call.
- Assistant-message prefill gives a 400.
- Check `stop_reason` before reading content: `end_turn` is OK. `max_tokens` means truncated, so count it as a failure or raise max_tokens. `refusal` should be counted as extraction failed, with `response.stop_details.category` recorded.

## Structured JSON output (recommended: `messages.parse` with Pydantic)

```python
import anthropic
from pydantic import BaseModel
from typing import Literal

class Assumption(BaseModel):
    statement: str
    assumption_type: Literal["t1", "t2", "t3", "t4", "t5", "uncheckable"]  # use the real 5 types from GLOSSARY
    scope: str
    code_pointers: list[str]
    check: str
    asserted_target: str

class Extraction(BaseModel):
    assumptions: list[Assumption]

client = anthropic.Anthropic(max_retries=4)
resp = client.messages.parse(
    model="claude-sonnet-5-5",
    max_tokens=16000,
    output_config={"effort": "low"},
    system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": lesson_text}],
    output_format=Extraction,
)
if resp.stop_reason != "end_turn":
    ...  # extraction failed (max_tokens / refusal)
result: Extraction = resp.parsed_output
```
`output_format=<PydanticModel>` on `.parse()` is the documented helper argument. Two cautions:
- On `messages.create`, use `output_config={"format": {"type": "json_schema", "schema": {...}}}`. The raw-dict `output_format={...}` form is deprecated/removed in 1.x.
- If `output_format` and `output_config` clash in your SDK version, put `effort` in `output_config` and the format as above. Test it once against the live API.

Raw-schema alternative, which needs no pydantic:
```python
resp = client.messages.create(model="claude-sonnet-5-5", max_tokens=16000,
    output_config={"format": {"type": "json_schema", "schema": SCHEMA}},  # SCHEMA needs additionalProperties: False + required
    messages=[...])
text = next(b.text for b in resp.content if b.type == "text")  # skip thinking blocks
data = json.loads(text)
```
`resp.content` can contain `thinking` blocks before the text block, so always select by `b.type`.

## Usage and logging (spec story 12)

```python
u = resp.usage
u.input_tokens, u.output_tokens                       # output includes thinking tokens
u.cache_read_input_tokens, u.cache_creation_input_tokens   # may be None/0
resp.model          # model that served the request
resp._request_id    # public despite the underscore; log it
resp.id, resp.stop_reason
```
Logging `model, input_tokens, output_tokens, cache_*, cost_usd, request_id, stop_reason, latency` per call is enough. The same system prompt across lessons can use caching (`cache_control={"type":"ephemeral"}` top-level). It only helps if the prefix exceeds the model's minimum cacheable length (512–4096 tokens).

## Retries and backoff built into the SDK

- `max_retries` defaults to 2. The SDK retries connection errors, 408, 409, 429 and >=500 with exponential backoff and honours `retry-after`. It does not retry other 4xx errors.
- `timeout` defaults to 10 minutes and is given in seconds. Timeouts are retried too, so worst-case wall time is timeout x (max_retries+1). For extraction, set something like `Anthropic(timeout=120.0, max_retries=4)`.
- Per call: `client.with_options(max_retries=5, timeout=60).messages.parse(...)`.
- Error classes, most specific first: `anthropic.BadRequestError` (400, don't retry, count as failed), `AuthenticationError`, `NotFoundError`, `RateLimitError`, `APIStatusError` (`.status_code`), `APIConnectionError`, `APITimeoutError`.
- Spec story 11 asks for retry with backoff, then "extraction failed". The SDK's built-in retry probably covers transport-level retries. Add an outer retry of your own only for schema/validation failures, e.g. `pydantic.ValidationError` or a `max_tokens` stop, if wanted. Count every exhausted retry as extraction failed, separately from uncheckable.

## Caching outputs (spec story 11)

Key the cache by sha256 of (model, system prompt version, schema version, lesson text, effort). Store the raw JSON response plus its usage, and on a hit log cost 0 / cached=true.
