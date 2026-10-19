"""LLM client: a thin interface for structured JSON calls, a fake for tests, and the real Claude client.

Stages never talk to an LLM directly. They build an `LLMRequest` and call `LLMClient.call`, which
adds retry with backoff, an output cache keyed by model and prompt, and a per-call log of model,
tokens and cost in the run database (tables `llm_cache` and `llm_calls`).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol, TypeVar

from memrev.store import RunError, RunStore

T = TypeVar("T")

sleep = time.sleep  # the clock is a system boundary; tests replace it

DEFAULT_MODEL = "claude-sonnet-5-5"

SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key TEXT PRIMARY KEY,           -- sha256 over model, system prompt, prompt and schema
    model TEXT NOT NULL,
    output TEXT NOT NULL,                 -- the JSON object the model returned
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS llm_calls (
    call_id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage TEXT NOT NULL,
    subject TEXT NOT NULL,
    model TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    cached INTEGER NOT NULL,              -- 1: answered from llm_cache, no API call, cost 0
    outcome TEXT NOT NULL,                -- ok | error
    error TEXT,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,       -- includes thinking tokens
    cache_read_input_tokens INTEGER NOT NULL,
    cache_creation_input_tokens INTEGER NOT NULL,
    cost_usd REAL,                        -- NULL if the model has no entry in PRICES
    stop_reason TEXT,
    request_id TEXT,
    latency_seconds REAL NOT NULL,
    called_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


# Interface -----------------------------------------------------------------


@dataclass(frozen=True)
class LLMRequest:
    """One structured call: the reply must be a JSON object matching `schema` (a JSON Schema dict
    with `additionalProperties: false` and `required` on every object)."""

    system: str
    prompt: str
    schema: dict


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True)
class LLMResponse:
    data: dict
    usage: Usage
    model: str
    stop_reason: str = "end_turn"
    request_id: str | None = None


class LLMError(Exception):
    """A call that produced no usable output. `usage` holds the tokens it still cost, if known.
    `retryable=False` means trying again cannot help (e.g. a malformed request)."""

    def __init__(
        self,
        message: str,
        usage: Usage | None = None,
        model: str | None = None,
        retryable: bool = True,
        stop_reason: str | None = None,
        request_id: str | None = None,
    ):
        super().__init__(message)
        self.usage = usage or Usage()
        self.model = model
        self.retryable = retryable
        self.stop_reason = stop_reason
        self.request_id = request_id


class LLMFailure(Exception):
    """A call that still failed after every retry: the stage counts it as "extraction failed"."""


class LLM(Protocol):
    """What every LLM implementation provides. `model` is the model id the calls go to.
    `complete` raises `LLMError` for a call without usable output, and `RunError` for problems
    no retry can fix (missing or rejected API key)."""

    model: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...


# Prices --------------------------------------------------------------------


@dataclass(frozen=True)
class Price:
    """US dollars per million tokens."""

    input: float
    output: float
    cache_read: float
    cache_write: float  # 5-minute TTL: 1.25 x input


PRICES = {
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_read=0.20, cache_write=2.50),
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_read=0.40, cache_write=5.00),
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125),
}


def cost_usd(model: str, usage: Usage) -> float | None:
    price = PRICES.get(model)
    if price is None:
        return None
    return (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_input_tokens * price.cache_read
        + usage.cache_creation_input_tokens * price.cache_write
    ) / 1e6


# Call log ------------------------------------------------------------------


@dataclass(frozen=True)
class LoggedCall:
    stage: str
    subject: str
    model: str
    attempt: int
    cached: bool
    outcome: str
    error: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    request_id: str | None


def call_log(store: RunStore) -> list[LoggedCall]:
    """Every logged LLM call in the run, oldest first."""
    store.conn.executescript(SCHEMA)
    rows = store.conn.execute(
        "SELECT stage, subject, model, attempt, cached, outcome, error, input_tokens, output_tokens, "
        "cost_usd, request_id FROM llm_calls ORDER BY call_id"
    )
    return [
        LoggedCall(stage, subject, model, attempt, bool(cached), outcome, error, tin, tout, cost, rid)
        for stage, subject, model, attempt, cached, outcome, error, tin, tout, cost, rid in rows
    ]


# Client --------------------------------------------------------------------


def cache_key(model: str, request: LLMRequest) -> str:
    canonical = json.dumps(
        [model, request.system, request.prompt, request.schema], sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class LLMClient:
    """Wraps an `LLM` for one stage of a run.

    - A cached output for the same model and request is reused without calling the LLM.
    - A failed or unparseable call is retried with exponential backoff (`backoff_seconds`, then
      doubling) up to `attempts` times; after that `call` raises `LLMFailure`.
    - Every attempt and every cache hit is logged in `llm_calls`; `cost_usd` totals this client's calls.
    """

    llm: LLM
    store: RunStore
    stage: str
    attempts: int = 3
    backoff_seconds: float = 2.0
    cost_usd: float = field(default=0.0, init=False)
    unpriced_calls: int = field(default=0, init=False)

    def __post_init__(self):
        self.store.conn.executescript(SCHEMA)

    def call(self, request: LLMRequest, parse: Callable[[dict], T], subject: str) -> T:
        """Return `parse(output)`. `parse` raises ValueError, KeyError, TypeError or AttributeError
        for output it cannot use; that counts as a failed attempt and the output is not cached."""
        key = cache_key(self.llm.model, request)
        cached = self._cached_output(key)
        if cached is not None:
            try:
                result = parse(cached)
            except (ValueError, KeyError, TypeError, AttributeError):
                pass  # a cache entry the current parser rejects is ignored and replaced
            else:
                self._log(subject, key, attempt=0, cached=True, outcome="ok", latency=0.0)
                return result

        last_error = "no attempt made"
        attempt = 0
        for attempt in range(1, self.attempts + 1):
            if attempt > 1:
                sleep(self.backoff_seconds * 2 ** (attempt - 2))
            started = time.monotonic()
            try:
                response = self.llm.complete(request)
            except LLMError as exc:
                last_error = str(exc)
                self._log(
                    subject, key, attempt, cached=False, outcome="error", latency=time.monotonic() - started,
                    error=last_error, usage=exc.usage, model=exc.model, stop_reason=exc.stop_reason,
                    request_id=exc.request_id,
                )
                if not exc.retryable:
                    break
                continue
            latency = time.monotonic() - started
            log = dict(usage=response.usage, model=response.model, stop_reason=response.stop_reason,
                       request_id=response.request_id)
            try:
                result = parse(response.data)
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                last_error = f"unusable output: {exc!r}"
                self._log(subject, key, attempt, cached=False, outcome="error", latency=latency,
                          error=last_error, **log)
                continue
            self._store_output(key, response.data)
            self._log(subject, key, attempt, cached=False, outcome="ok", latency=latency, **log)
            return result
        plural = "s" if attempt != 1 else ""
        raise LLMFailure(f"{last_error} (after {attempt} attempt{plural})")

    # Internals -----------------------------------------------------------

    def _cached_output(self, key: str) -> dict | None:
        row = self.store.conn.execute("SELECT output FROM llm_cache WHERE cache_key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def _store_output(self, key: str, data: dict) -> None:
        with self.store.conn:
            self.store.conn.execute(
                "INSERT OR REPLACE INTO llm_cache (cache_key, model, output) VALUES (?, ?, ?)",
                (key, self.llm.model, json.dumps(data, ensure_ascii=False)),
            )

    def _log(
        self,
        subject: str,
        key: str,
        attempt: int,
        cached: bool,
        outcome: str,
        latency: float,
        error: str | None = None,
        usage: Usage | None = None,
        model: str | None = None,
        stop_reason: str | None = None,
        request_id: str | None = None,
    ) -> None:
        usage = usage or Usage()
        model = model or self.llm.model
        cost = 0.0 if cached else cost_usd(model, usage)
        if cost is None:
            self.unpriced_calls += 1
        else:
            self.cost_usd += cost
        with self.store.conn:
            self.store.conn.execute(
                "INSERT INTO llm_calls (stage, subject, model, cache_key, attempt, cached, outcome, error, "
                "input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens, "
                "cost_usd, stop_reason, request_id, latency_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.stage, subject, model, key, attempt, int(cached), outcome, error,
                    usage.input_tokens, usage.output_tokens, usage.cache_read_input_tokens,
                    usage.cache_creation_input_tokens, cost, stop_reason, request_id, latency,
                ),
            )


# Fake ----------------------------------------------------------------------


class FakeLLM:
    """Returns canned outputs. `answer(marker, *outcomes)` makes every request whose prompt contains
    `marker` get the outcomes in order (dicts are returned, exceptions raised); the last one repeats.
    Every request is kept in `calls`."""

    def __init__(self, model: str = DEFAULT_MODEL, usage: Usage | None = None):
        self.model = model
        self.usage = usage or Usage(input_tokens=1000, output_tokens=500)
        self.calls: list[LLMRequest] = []
        self._answers: list[tuple[str, list]] = []

    def answer(self, marker: str, *outcomes) -> None:
        """Set (or replace) the outcomes for prompts containing `marker`."""
        self._answers = [a for a in self._answers if a[0] != marker]
        self._answers.append((marker, list(outcomes)))

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        for marker, outcomes in self._answers:
            if marker in request.prompt:
                outcome = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]
                if isinstance(outcome, BaseException):
                    raise outcome
                return LLMResponse(data=outcome, usage=self.usage, model=self.model)
        raise LLMError("fake LLM has no answer for this prompt", model=self.model)


# Real: Claude via the Anthropic API ------------------------------------------


def api_key(env_file: Path = Path(".env")) -> str | None:
    """ANTHROPIC_API_KEY from the environment, else from a git-ignored `.env` in the working directory."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            name, sep, value = line.strip().removeprefix("export ").partition("=")
            if sep and name.strip() == "ANTHROPIC_API_KEY":
                return value.strip().strip("'\"") or None
    return None


class AnthropicLLM:
    """Claude through the Anthropic Messages API with structured JSON output.

    Sonnet 5.5 rejects (HTTP 400) non-default temperature/top_p/top_k, `thinking: disabled`, forced
    tool_choice and assistant prefill, so none are sent. Stability comes from the output cache.
    The SDK retries connection errors, 408/409/429 and 5xx itself (`max_retries`); `LLMClient`
    retries on top of that for anything else that left no usable output.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        effort: str = "low",
        max_tokens: int = 16000,
        timeout_seconds: float = 120.0,
        sdk_retries: int = 4,
    ):
        key = api_key()
        if not key:
            raise RunError(
                "no Anthropic API key: set ANTHROPIC_API_KEY, or put ANTHROPIC_API_KEY=... in a .env file "
                "in the directory you run memrev from (.env is git-ignored)"
            )
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=key, timeout=timeout_seconds, max_retries=sdk_retries)
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    def complete(self, request: LLMRequest) -> LLMResponse:
        anthropic = self._anthropic
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.prompt}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": request.schema},
                },
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise RunError(f"Anthropic API rejected the key: {exc}") from exc
        except anthropic.NotFoundError as exc:
            raise RunError(f"Anthropic API: model {self.model!r} not found: {exc}") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"bad request: {exc}", model=self.model, retryable=False) from exc
        except anthropic.APIError as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}", model=self.model) from exc

        u = resp.usage
        usage = Usage(
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_input_tokens=getattr(u, "cache_read_input_tokens", None) or 0,
            cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", None) or 0,
        )
        request_id = getattr(resp, "_request_id", None)
        if resp.stop_reason != "end_turn":
            detail = resp.stop_reason
            category = getattr(getattr(resp, "stop_details", None), "category", None)
            if category:
                detail = f"{detail} ({category})"
            raise LLMError(
                f"stop_reason {detail}", usage=usage, model=resp.model, stop_reason=resp.stop_reason,
                request_id=request_id,
            )
        text = next((b.text for b in resp.content if b.type == "text"), None)
        try:
            data = json.loads(text) if text is not None else None
        except json.JSONDecodeError as exc:
            data = None
            text = f"invalid JSON: {exc}"
        if not isinstance(data, dict):
            raise LLMError(
                f"no JSON object in the reply: {str(text)[:200]}", usage=usage, model=resp.model,
                stop_reason=resp.stop_reason, request_id=request_id,
            )
        return LLMResponse(data, usage, resp.model, resp.stop_reason, request_id)
