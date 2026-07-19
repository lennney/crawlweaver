"""LLM client — DeepSeek → Ollama fallback with disk cache.

Factor #2: Own your prompts (caller provides system/user prompts).
Factor #3: Own your context window (caller decides what goes in).
"""

from dataclasses import dataclass
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

logger = logging.getLogger("crawler.llm")

# Pricing per 1M tokens (USD)
PRICING = {
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "qwen2.5:7b": {"input": 0.0, "output": 0.0},  # local, free
}


@dataclass
class CostRecord:
    step: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @classmethod
    def from_usage(cls, step: str, usage: dict, model: str = "") -> "CostRecord":
        inp = usage.get("prompt_tokens", 0)
        out = usage.get("completion_tokens", 0)
        pricing = PRICING.get(model, {"input": 0, "output": 0})
        cost = (inp * pricing["input"] + out * pricing["output"]) / 1_000_000
        return cls(step=step, input_tokens=inp, output_tokens=out, model=model, cost_usd=round(cost, 6))


_cache_dir = Path(__file__).parent / "cache" / "llm"
_clients: dict[str, Any] = {}

# In-memory LRU cache — front layer before disk I/O
_memory_cache: dict[str, tuple[float, Any]] = {}  # key -> (expiry_ts, result)
_MEMORY_MAX = 500
_MEMORY_TTL = 3600  # 1h memory cache; disk cache still has its own 7d TTL


def _cache_key(step: str, text: str) -> str:
    return hashlib.sha256(f"{step}:::{text}".encode()).hexdigest()[:32]


def _memory_cache_get(key: str) -> Any | None:
    """Fast in-memory lookup — μs vs ms for disk."""
    entry = _memory_cache.get(key)
    if entry is None:
        return None
    expiry, result = entry
    if time.time() < expiry:
        return result
    del _memory_cache[key]
    return None


def _memory_cache_set(key: str, result: Any):
    """Store in memory with LRU eviction."""
    _memory_cache[key] = (time.time() + _MEMORY_TTL, result)
    if len(_memory_cache) > _MEMORY_MAX:
        # Simple FIFO eviction — fine for this use case
        oldest = next(iter(_memory_cache))
        del _memory_cache[oldest]


def cache_get(step: str, text: str, ttl: int = 604800) -> Any | None:
    key = _cache_key(step, text)

    # 1. Memory cache (fast path)
    cached = _memory_cache_get(key)
    if cached is not None:
        return cached

    # 2. Disk cache (slow path, promote to memory)
    p = _cache_dir / f"{key}.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if time.time() - data["ts"] > ttl:
            p.unlink(missing_ok=True)
            return None
        _memory_cache_set(key, data["result"])
        return data["result"]
    except Exception:
        return None


def cache_set(step: str, text: str, result: Any):
    key = _cache_key(step, text)

    # Memory cache
    _memory_cache_set(key, result)

    # Disk cache (persistence across restarts)
    _cache_dir.mkdir(parents=True, exist_ok=True)
    p = _cache_dir / f"{key}.json"
    p.write_text(json.dumps({"ts": time.time(), "result": result}, ensure_ascii=False),
                 encoding="utf-8")


class LLM:
    """Minimal LLM client with fallback chain: DeepSeek → Ollama.
    
    Usage:
        llm = LLM()
        result = llm.call("You are a writer", "Write about X")
    """

    def __init__(self, timeout: int = 120):
        self.timeout = timeout
        self.last_cost: CostRecord | None = None

    def call(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        cache_step: str = "",
        cache_input: str = "",
    ) -> str:
        # Cache check
        if cache_step and cache_input:
            cached = cache_get(cache_step, cache_input)
            if cached is not None:
                logger.debug(f"Cache hit for {cache_step}")
                return cached

        result = self._call_with_fallback(system, user, max_tokens, temperature, cache_step or "unknown")

        # Cache store
        if cache_step and cache_input:
            cache_set(cache_step, cache_input, result)

        return result

    def _call_with_fallback(self, system: str, user: str, max_tokens: int, temperature: float, step: str = "unknown") -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        # Provider 1: DeepSeek / OpenAI-compatible
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
        model = os.getenv("LLM_MODEL", "deepseek-chat")

        if api_key:
            retry_max_tokens = max_tokens
            for attempt in range(3):
                try:
                    client = self._get_client(api_key, base_url)
                    resp = client.chat.completions.create(
                        model=model, messages=messages,
                        max_tokens=retry_max_tokens, temperature=temperature,
                        extra_body={"thinking": {"type": "disabled"}},
                    )
                    usage = resp.usage
                    if usage:
                        self.last_cost = CostRecord.from_usage(
                            step=step,
                            usage={"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens},
                            model=model,
                        )
                    # Get content: check both content and reasoning_content
                    msg = resp.choices[0].message
                    content = (msg.content or "").strip()
                    
                    # If content is empty but reasoning exists, the model
                    # spent all tokens on reasoning. Retry with 2x budget.
                    if not content:
                        reasoning = getattr(msg, "reasoning_content", None)
                        if reasoning and attempt < 2:
                            retry_max_tokens = min(retry_max_tokens * 2, 65536)
                            logger.info(
                                f"Model {model} returned empty content "
                                f"(reasoning={len(str(reasoning))} chars). "
                                f"Retrying with max_tokens={retry_max_tokens}"
                            )
                            time.sleep(2 ** attempt)
                            continue
                    return content

                except Exception as e:
                    logger.warning(f"DeepSeek attempt {attempt+1}/3 failed: {e}")
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                    else:
                        logger.info("DeepSeek exhausted, trying Ollama")

        # Provider 2: Ollama local
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

        for attempt in range(2):
            try:
                client = self._get_client("ollama", f"{ollama_url}/v1")
                resp = client.chat.completions.create(
                    model=ollama_model, messages=messages,
                    max_tokens=max_tokens, temperature=temperature,
                )
                usage = resp.usage
                if usage:
                    self.last_cost = CostRecord.from_usage(
                        step=step,
                        usage={"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens},
                        model=ollama_model,
                    )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"Ollama attempt {attempt+1}/2 failed: {e}")
                if attempt < 1:
                    time.sleep(1)
                else:
                    raise RuntimeError(f"All LLM providers failed. Last: {e}")

    def _get_client(self, api_key: str, base_url: str):
        cache_key = f"{api_key[:8]}::{base_url}"
        if cache_key not in _clients:
            from openai import OpenAI
            _clients[cache_key] = OpenAI(api_key=api_key, base_url=base_url, timeout=self.timeout)
        return _clients[cache_key]
