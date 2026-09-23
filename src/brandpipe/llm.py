"""Provider-agnostic LLM client.

One interface, three backends:
  * ollama  - local, self-hosted models (default when an Ollama server is reachable)
  * openai  - any OpenAI-compatible endpoint (OpenAI, Groq, Together, vLLM, LM Studio)
  * anthropic - Claude models via the Messages API
  * mock    - deterministic, offline responses so the demo runs anywhere

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


def _post_json(url: str, payload: dict, headers: dict, timeout: float = 120) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
        if self.provider not in self.models:
            raise ValueError(f"Unknown provider '{self.provider}'. Options: {list(self.models)}")

    def _auto_detect(self) -> str:
        if ollama_available(self.ollama_host):
            return "ollama"
        if os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"
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
    ) -> LLMResponse:
        model = self.model_for(role)
        start = time.perf_counter()
        if self.provider == "mock":
            text = mock() if mock else "[mock] no mock handler supplied"
        elif self.provider == "ollama":
            text = self._ollama_chat(model, system, user, json_mode)
        elif self.provider == "openai":
            text = self._openai_chat(model, system, user, json_mode)
        else:
            text = self._anthropic_chat(model, system, user)
        latency = (time.perf_counter() - start) * 1000
        return LLMResponse(_strip_reasoning(text), model, self.provider, round(latency, 1))

    def _ollama_chat(self, model: str, system: str, user: str, json_mode: bool) -> str:
        payload = {
            "model": model,
            "stream": False,
            "options": {"temperature": 0.1},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_mode:
            payload["format"] = "json"
        data = _post_json(f"{self.ollama_host}/api/chat", payload, {})
        return data["message"]["content"]

    def _openai_chat(self, model: str, system: str, user: str, json_mode: bool) -> str:
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        payload = {
            "model": model,
            "temperature": 0.1,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = _post_json(
            f"{base}/chat/completions", payload, {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
        )
        return data["choices"][0]["message"]["content"]

    def _anthropic_chat(self, model: str, system: str, user: str) -> str:
        payload = {
            "model": model,
            "max_tokens": 1500,
            "temperature": 0.1,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
        )
        return "".join(block.get("text", "") for block in data["content"])

    # ------------------------------------------------------------- embeddings
    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.provider == "ollama":
            try:
                data = _post_json(
                    f"{self.ollama_host}/api/embed",
                    {"model": self.model_for("embed"), "input": texts},
                    {},
                )
                return data["embeddings"]
            except (urllib.error.URLError, KeyError):
                pass  # fall through to local embedding
        if self.provider == "openai" and os.getenv("OPENAI_EMBEDDINGS", "1") == "1":
            try:
                base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
                data = _post_json(
                    f"{base}/embeddings",
                    {"model": self.model_for("embed"), "input": texts},
                    {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
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
