"""Calls the LLM over plain HTTP. No SDK, no framework.

complete() hides the difference between providers:
- anthropic uses its own Messages API.
- groq, gemini and openai use the OpenAI chat completions format, so one function covers all three.
Tests replace complete() with a fake, so they never call a real API.

Reliability rules:
- Connect timeout is short (10 s); read timeout comes from LLM_TIMEOUT_SECONDS.
- Temporary failures (429, 5xx, timeouts, dropped connections) are retried
  MAX_ATTEMPTS times in total, waiting a little longer each time.
- A rejected key or a bad request is not retried: trying again cannot fix it.
- The provider's raw error text is logged on the server, never sent to users.
"""

import json
import logging
import re
import time

import httpx

from app.config import settings

log = logging.getLogger("workos.llm")

MAX_ATTEMPTS = 2
CONNECT_TIMEOUT_SECONDS = 10
MAX_BACKOFF_SECONDS = 10
RETRY_STATUSES = {429, 500, 502, 503, 504}


class LLMError(Exception):
    """The provider failed. `public_message` is safe to show to users."""

    def __init__(self, public_message: str):
        super().__init__(public_message)
        self.public_message = public_message


class LLMNotConfigured(LLMError):
    """No API key is set on the server."""


class _Retryable(Exception):
    def __init__(self, error: LLMError, wait: float | None = None):
        self.error = error
        self.wait = wait


def complete(system: str, user: str, max_tokens: int = 1500) -> str:
    if not settings.llm_configured:
        raise LLMNotConfigured("LLM_API_KEY is not set")

    call = _anthropic if settings.llm_provider == "anthropic" else _openai_compatible
    last_error: LLMError | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return call(system, user, max_tokens)
        except _Retryable as exc:
            last_error = exc.error
            if attempt == MAX_ATTEMPTS:
                break
            wait = exc.wait if exc.wait is not None else 2 ** (attempt - 1)
            time.sleep(min(wait, MAX_BACKOFF_SECONDS))
    raise last_error  # type: ignore[misc]


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(settings.llm_timeout_seconds, connect=CONNECT_TIMEOUT_SECONDS)


def _post(url: str, headers: dict, body: dict) -> dict:
    provider = settings.llm_provider
    try:
        response = httpx.post(url, headers=headers, json=body, timeout=_timeout())
    except httpx.TimeoutException as exc:
        raise _Retryable(LLMError(f"{provider} did not answer within {settings.llm_timeout_seconds:.0f} seconds.")) from exc
    except httpx.HTTPError as exc:  # DNS failures, refused or dropped connections
        raise _Retryable(LLMError(f"Could not reach {provider}.")) from exc

    status = response.status_code
    if status == 200:
        try:
            return response.json()
        except ValueError as exc:
            raise LLMError(f"{provider} sent a reply that is not JSON.") from exc

    log.warning("LLM provider %s returned HTTP %s: %s", provider, status, response.text[:500])
    if status in (401, 403):
        raise LLMError(f"{provider} rejected the API key.")
    if status == 429:
        raise _Retryable(LLMError(f"{provider} rate limit reached. Wait a minute and try again."),
                         wait=_retry_after(response))
    if status in RETRY_STATUSES:
        raise _Retryable(LLMError(f"{provider} is having problems (HTTP {status}). Try again shortly."))
    raise LLMError(f"{provider} refused the request (HTTP {status}). Check LLM_MODEL and LLM_BASE_URL.")


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _anthropic(system: str, user: str, max_tokens: int) -> str:
    data = _post(
        f"{settings.llm_base_url}/messages",
        {"x-api-key": settings.llm_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        {"model": settings.llm_model, "max_tokens": max_tokens, "system": system,
         "messages": [{"role": "user", "content": user}]},
    )
    try:
        return "".join(block.get("text", "") for block in data["content"])
    except (KeyError, TypeError) as exc:
        raise LLMError("anthropic sent a reply in an unexpected shape.") from exc


def _openai_compatible(system: str, user: str, max_tokens: int) -> str:
    data = _post(
        f"{settings.llm_base_url}/chat/completions",
        {"Authorization": f"Bearer {settings.llm_api_key}"},
        {"model": settings.llm_model, "max_tokens": max_tokens,
         "temperature": 0.2,  # low, so plans and answers stay close to the input
         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
    )
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"{settings.llm_provider} sent a reply in an unexpected shape.") from exc


def extract_json(text: str) -> dict:
    """Pull the JSON object out of a model reply.

    Models sometimes wrap JSON in ```json fences or add a sentence before it,
    so we take everything from the first "{" to the last "}".
    """
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in the reply")
    return json.loads(text[start : end + 1])
