"""Gemini and Ollama. Templates never call this module."""

from __future__ import annotations

import os
import time

import httpx

NO_MODEL_ANSWER = (
    "No model is configured, so this question was not sent to a SQL model and no figure was calculated. "
    "Set GOOGLE_API_KEY or GEMINI_API_KEY, or run Ollama and set OLLAMA_BASE_URL. "
    "Templates still answer the suggested questions."
)

_PROBE = {"at": 0.0, "url": None}


def gemini_key() -> str:
    return os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""


def ollama_url() -> str | None:
    now = time.time()
    if now - _PROBE["at"] < 30:
        return _PROBE["url"]
    candidates = []
    if os.environ.get("OLLAMA_BASE_URL"):
        candidates.append(os.environ["OLLAMA_BASE_URL"])
    else:
        candidates.extend(["http://ollama:11434", "http://localhost:11434"])
    found = None
    for candidate in candidates:
        try:
            response = httpx.get(candidate.rstrip("/") + "/api/tags", timeout=1.5)
            if response.status_code < 500:
                found = candidate.rstrip("/")
                break
        except Exception:
            continue
    _PROBE.update(at=now, url=found)
    return found


def provider_order() -> list[str]:
    order = []
    if gemini_key():
        order.append("gemini")
    if ollama_url():
        order.append("ollama")
    return order


def _gemini(prompt: str) -> str:
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key()}"
    response = httpx.post(
        url,
        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def _ollama(prompt: str) -> str:
    base = ollama_url()
    if not base:
        raise RuntimeError("Ollama is not reachable")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    response = httpx.post(
        base + "/api/generate",
        json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["response"]


def complete(prompt: str) -> str | None:
    for name in provider_order():
        try:
            if name == "gemini":
                return _gemini(prompt)
            return _ollama(prompt)
        except Exception:
            continue
    return None
