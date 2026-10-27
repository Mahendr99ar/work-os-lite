"""Calls the LLM over plain HTTP. No SDK, no framework.

complete() hides the difference between providers:
- anthropic uses its own Messages API.
- groq, gemini and openai use the OpenAI chat completions format, so one function covers all three.
Tests replace complete() with a fake, so they never call a real API.
"""

import json
import re

import httpx

from app.config import settings

TIMEOUT_SECONDS = 120


class LLMError(Exception):
    """The provider failed: bad key, rate limit, timeout, outage."""


class LLMNotConfigured(LLMError):
    """No API key is set on the server."""


def complete(system: str, user: str, max_tokens: int = 1500) -> str:
    if not settings.llm_configured:
        raise LLMNotConfigured("LLM_API_KEY is not set")
    try:
        if settings.llm_provider == "anthropic":
            return _anthropic(system, user, max_tokens)
        return _openai_compatible(system, user, max_tokens)
    except httpx.HTTPError as exc:  # timeouts, DNS failures, dropped connections
        raise LLMError(f"Could not reach {settings.llm_provider}: {exc}") from exc


def _anthropic(system: str, user: str, max_tokens: int) -> str:
    response = httpx.post(
        f"{settings.llm_base_url}/messages",
        headers={
            "x-api-key": settings.llm_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": settings.llm_model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=TIMEOUT_SECONDS,
    )
    _raise_for_status(response)
    return "".join(block.get("text", "") for block in response.json()["content"])


def _openai_compatible(system: str, user: str, max_tokens: int) -> str:
    response = httpx.post(
        f"{settings.llm_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={
            "model": settings.llm_model,
            "max_tokens": max_tokens,
            "temperature": 0.2,  # low, so plans and answers stay close to the input
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        timeout=TIMEOUT_SECONDS,
    )
    _raise_for_status(response)
    return response.json()["choices"][0]["message"]["content"] or ""


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 429:
        raise LLMError(f"{settings.llm_provider} rate limit reached. Wait a minute and try again.")
    if response.status_code in (401, 403):
        raise LLMError(f"{settings.llm_provider} rejected the API key.")
    if response.status_code != 200:
        raise LLMError(f"{settings.llm_provider} returned {response.status_code}: {response.text[:300]}")


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
