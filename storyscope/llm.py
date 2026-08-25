"""
Minimal LLM client used for narrative-feature extraction.

Only `requests` is required. Supports three providers:

- openai   : OpenAI-compatible chat completions (OpenAI, DeepSeek, OpenRouter,
             local vLLM/Ollama gateways, ...). Set STORYSCOPE_LLM_BASE_URL to
             point at a compatible endpoint.
- anthropic: Anthropic Messages API.
- gemini   : Google Generative Language API.

Configuration (environment variables):

  STORYSCOPE_LLM_PROVIDER   openai (default) | anthropic | gemini
  STORYSCOPE_LLM_MODEL      model id (provider-specific default if unset)
  STORYSCOPE_LLM_API_KEY    falls back to OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY
  STORYSCOPE_LLM_BASE_URL   OpenAI-compatible base URL (default https://api.openai.com/v1)
  STORYSCOPE_LLM_TIMEOUT    seconds per call (default 120)
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any, Dict, Optional

import requests

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5",
    "gemini": "gemini-3.5-flash",
}

_lock = threading.Lock()
_cache: Dict[str, Any] = {}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def get_config() -> Dict[str, str]:
    """Read LLM config from environment once and cache it."""
    with _lock:
        if _cache:
            return dict(_cache)
        provider = _env("STORYSCOPE_LLM_PROVIDER", "openai").lower().strip()
        if provider not in ("openai", "anthropic", "gemini"):
            raise ValueError(
                f"Unsupported STORYSCOPE_LLM_PROVIDER '{provider}'. "
                "Use openai, anthropic or gemini."
            )
        fallback_keys = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GOOGLE_API_KEY",
        }
        api_key = _env("STORYSCOPE_LLM_API_KEY") or _env(fallback_keys[provider])
        if not api_key:
            raise ValueError(
                f"StoryScope needs an LLM API key for feature extraction. "
                f"Set STORYSCOPE_LLM_API_KEY (or {fallback_keys[provider]}) "
                f"for provider '{provider}'."
            )
        cfg = {
            "provider": provider,
            "model": _env("STORYSCOPE_LLM_MODEL", DEFAULT_MODELS[provider]),
            "api_key": api_key,
            "base_url": _env("STORYSCOPE_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            "timeout": int(_env("STORYSCOPE_LLM_TIMEOUT", "120")),
        }
        _cache.update(cfg)
        return dict(cfg)


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of an LLM response (handles ``` fences and prose)."""
    text = text.strip()
    # Strip markdown code fences
    fence = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # Find the outermost {...} block
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in LLM response")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("Unterminated JSON object in LLM response")


def _post(url: str, headers: Dict[str, str], payload: dict, timeout: int) -> dict:
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise RuntimeError(f"LLM API error {resp.status_code}: {detail}")
    return resp.json()


def _is_rate_limited(err: Exception) -> bool:
    """True when the API error is a quota / rate-limit response."""
    s = str(err)
    return "429" in s or "quota" in s.lower() or "rate limit" in s.lower()


def generate_json(prompt: str, system: str = "", retries: int = 3) -> dict:
    """Send a prompt, ask for a single JSON object, return parsed dict.

    Retries transient failures; quota/rate-limit responses get a longer
    exponential backoff (some providers throttle hard on bursty workloads).
    """
    cfg = get_config()
    provider = cfg["provider"]
    last_error: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            if provider == "openai":
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                messages.append({"role": "user", "content": prompt})
                payload = {
                    "model": cfg["model"],
                    "messages": messages,
                    "temperature": 0.0,
                }
                data = _post(
                    f"{cfg['base_url']}/chat/completions",
                    {"Authorization": f"Bearer {cfg['api_key']}"},
                    payload,
                    cfg["timeout"],
                )
                content = data["choices"][0]["message"]["content"]
                return _extract_json(content)

            elif provider == "anthropic":
                messages = []
                if system:
                    messages.append({"role": "user", "content": system})
                messages.append({"role": "user", "content": prompt})
                payload = {
                    "model": cfg["model"],
                    "max_tokens": 8192,
                    "temperature": 0.0,
                    "messages": messages,
                }
                data = _post(
                    "https://api.anthropic.com/v1/messages",
                    {
                        "x-api-key": cfg["api_key"],
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    payload,
                    cfg["timeout"],
                )
                content = "".join(
                    b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
                )
                return _extract_json(content)

            else:  # gemini
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.0,
                        "responseMimeType": "application/json",
                    },
                }
                if system:
                    payload["systemInstruction"] = {"parts": [{"text": system}]}
                data = _post(
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{cfg['model']}:generateContent?key={cfg['api_key']}",
                    {"content-type": "application/json"},
                    payload,
                    cfg["timeout"],
                )
                content = data["candidates"][0]["content"]["parts"][0]["text"]
                return _extract_json(content)

        except Exception as e:  # noqa: BLE001 - retry on transient failures
            last_error = e
            if attempt < retries:
                # Rate limits: a short bounded backoff so a per-minute burst can
                # recover, but never hang for minutes on an exhausted daily quota.
                wait = (2 ** attempt) * (4.0 if _is_rate_limited(e) else 1.5)
                time.sleep(wait)

    raise RuntimeError(f"StoryScope LLM feature extraction failed: {last_error}")
