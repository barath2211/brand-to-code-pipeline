"""Provider-agnostic LLM client.

Providers (pick with LLM_PROVIDER or --provider):
  * ollama        - local, self-hosted models, full-size profile (needs ~16 GB+ RAM)
  * ollama-small  - local models that fit an 8 GB laptop
  * openai        - any OpenAI-compatible endpoint (OpenAI, Groq, Together, vLLM, LM Studio)
  * gemini        - Google Gemini through its OpenAI-compatible endpoint (GEMINI_API_KEY)
  * anthropic     - Claude models via the Messages API
  * mock          - deterministic, offline responses so the demo runs anywhere

Models are chosen per *role* (reasoning, code, writer, classifier, embed) rather
than per call site, so swapping a model is a config change, not a code change.
Only the standard library is used for HTTP to keep the install light.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "models.json"


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    latency_ms: float


def _load_models() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# provider name -> (backend, base url env, default base url, key env)
BACKENDS = {
    "ollama": ("ollama", None, None, None),
    "ollama-small": ("ollama", None, None, None),
    "openai": ("openai", "OPENAI_BASE_URL", "https://api.openai.com/v1", "OPENAI_API_KEY"),
    "gemini": ("openai", "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "anthropic": ("anthropic", None, None, "ANTHROPIC_API_KEY"),
    "mock": ("mock", None, None, None),
}


def _post_json(url: str, payload: dict, headers: dict, timeout: float = 180, retries: int = 5) -> dict:
    """POST JSON with backoff on rate limits and transient errors (free API tiers hit 429 often)."""
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 529) or attempt == retries:
                raise
            wait = float(exc.headers.get("Retry-After") or 0) or min(60, 2 ** (attempt + 2))
            time.sleep(wait)
    raise RuntimeError("unreachable")


def ollama_available(host: str) -> bool:
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _strip_reasoning(text: str) -> str:
    """Reasoning models (e.g. DeepSeek-R1) emit <think>...</think>; keep only the answer."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def hashed_embedding(text: str, dims: int = 256) -> list[float]:
    """Cheap, deterministic bag-of-words embedding used in mock mode."""
    vec = [0.0] * dims
    for tok in re.findall(r"[a-z0-9_]+", text.lower()):
        if len(tok) < 3:
            continue
        idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % dims
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class LLMClient:
    def __init__(self, provider: Optional[str] = None):
        self.models = _load_models()
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.provider = (provider or os.getenv("LLM_PROVIDER") or self._auto_detect()).lower()
        if self.provider not in self.models or self.provider not in BACKENDS:
            raise ValueError(f"Unknown provider '{self.provider}'. Options: {list(BACKENDS)}")
        self.backend, base_env, base_default, key_env = BACKENDS[self.provider]
        self.base_url = (os.getenv(base_env, base_default) if base_env else "").rstrip("/")
        self.api_key = os.getenv(key_env, "") if key_env else ""

    def _auto_detect(self) -> str:
        if ollama_available(self.ollama_host):
            return "ollama"
        if os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.getenv("GEMINI_API_KEY"):
            return "gemini"
        if os.getenv("OPENAI_API_KEY"):
            return "openai"
        return "mock"

    def model_for(self, role: str) -> str:
        return self.models[self.provider].get(role, self.models[self.provider]["default"])

    # ------------------------------------------------------------------ chat
    def chat(
        self,
        role: str,
        system: str,
        user: str,
        mock: Optional[Callable[[], str]] = None,
        json_mode: bool = False,
        temperature: float = 0.1,
    ) -> LLMResponse:
        model = self.model_for(role)
        start = time.perf_counter()
        if self.backend == "mock":
            text = mock() if mock else "[mock] no mock handler supplied"
        elif self.backend == "ollama":
            text = self._ollama_chat(model, system, user, json_mode, temperature)
        elif self.backend == "openai":
            text = self._openai_chat(model, system, user, json_mode, temperature)
        else:
            text = self._anthropic_chat(model, system, user, temperature)
        latency = (time.perf_counter() - start) * 1000
        return LLMResponse(_strip_reasoning(text), model, self.provider, round(latency, 1))

    def _ollama_chat(self, model: str, system: str, user: str, json_mode: bool, temperature: float) -> str:
        payload = {
            "model": model,
            "stream": False,
            "options": {"temperature": temperature},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_mode:
            payload["format"] = "json"
        data = _post_json(f"{self.ollama_host}/api/chat", payload, {})
        return data["message"]["content"]

    def _openai_chat(self, model: str, system: str, user: str, json_mode: bool, temperature: float) -> str:
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = _post_json(f"{self.base_url}/chat/completions", payload, {"Authorization": f"Bearer {self.api_key}"})
        return data["choices"][0]["message"]["content"]

    def _anthropic_chat(self, model: str, system: str, user: str, temperature: float) -> str:
        payload = {
            "model": model,
            "max_tokens": 1500,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
        )
        return "".join(block.get("text", "") for block in data["content"])

    # ------------------------------------------------------------- embeddings
    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.backend == "ollama":
            try:
                data = _post_json(
                    f"{self.ollama_host}/api/embed",
                    {"model": self.model_for("embed"), "input": texts},
                    {},
                )
                return data["embeddings"]
            except (urllib.error.URLError, KeyError):
                pass  # fall through to local embedding
        if self.backend == "openai" and os.getenv("OPENAI_EMBEDDINGS", "1") == "1":
            try:
                data = _post_json(
                    f"{self.base_url}/embeddings",
                    {"model": self.model_for("embed"), "input": texts},
                    {"Authorization": f"Bearer {self.api_key}"},
                )
                return [row["embedding"] for row in data["data"]]
            except Exception:
                pass
        # Anthropic has no embeddings endpoint; mock and fallbacks use hashed vectors.
        return [hashed_embedding(t) for t in texts]


def parse_json_loose(text: str) -> dict:
    """Pull the first JSON object out of a model reply (models love wrapping JSON in prose)."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {}
