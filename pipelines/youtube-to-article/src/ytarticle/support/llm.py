"""Unified LLM client — call any OpenAI-compatible API."""
from __future__ import annotations
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("ytarticle.llm")

_CLIENTS: dict[str, object] = {}


def _get_client(api_key: str, base_url: str, timeout: int = 120):
    cache_key = f"{api_key[:8]}::{base_url}"
    if cache_key not in _CLIENTS:
        from openai import OpenAI
        _CLIENTS[cache_key] = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    return _CLIENTS[cache_key]


def call_llm(system_prompt: str, user_prompt: str,
             max_tokens: int = 8192, temperature: float = 0.8) -> str:
    """Call any OpenAI-compatible API, with Ollama fallback.

    Configure via .env or environment:
      LLM_API_KEY   — API key (required for cloud, optional for Ollama)
      LLM_BASE_URL  — API base URL
      LLM_MODEL     — Model name
      OLLAMA_BASE_URL — Ollama server (default: http://localhost:11434)
      OLLAMA_MODEL  — Ollama model (default: qwen2.5:7b)
    """
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("LLM_MODEL", "deepseek-chat")

    # Primary: cloud LLM
    if api_key:
        try:
            client = _get_client(api_key, base_url)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Cloud LLM error: {e}, falling back to Ollama...")

    # Fallback: Ollama
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    try:
        client = _get_client("ollama", f"{ollama_url}/v1", timeout=300)
        resp = client.chat.completions.create(
            model=ollama_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        raise RuntimeError(f"Both cloud LLM and Ollama failed: {e}") from e