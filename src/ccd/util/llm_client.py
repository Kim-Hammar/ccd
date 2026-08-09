"""
Minimal clients for querying the LLM-baseline providers (Anthropic, OpenAI, Gemini).
"""

from __future__ import annotations
import time
from typing import Callable, Dict

PROVIDERS = ("anthropic", "openai", "gemini")
_MAX_TOKENS = 8192


def _query_anthropic(model: str, prompt: str, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"anthropic model {model} refused the request "
                           f"(stop_details={getattr(response, 'stop_details', None)})")
    return "".join(block.text for block in response.content if block.type == "text")


def _query_openai(model: str, prompt: str, api_key: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


def _query_gemini(model: str, prompt: str, api_key: str) -> str:
    from google import genai
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text or ""


_QUERY_FUNCTIONS: Dict[str, Callable[[str, str, str], str]] = {
    "anthropic": _query_anthropic,
    "openai": _query_openai,
    "gemini": _query_gemini,
}


def query_llm(provider: str, model: str, prompt: str, *, api_key: str,
              retries: int = 1, retry_delay: float = 5.0) -> str:
    """Send ``prompt`` to ``provider``'s ``model`` and return the raw reply text."""
    if provider not in _QUERY_FUNCTIONS:
        raise ValueError(f"unknown provider {provider!r} (choose from {', '.join(PROVIDERS)})")
    query = _QUERY_FUNCTIONS[provider]
    for attempt in range(retries + 1):
        try:
            return query(model, prompt, api_key)
        except Exception:
            if attempt == retries:
                raise
            time.sleep(retry_delay)
    raise RuntimeError("unreachable")
