from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from base import AdapterError, GenerateResult, ModelAdapter


class OllamaAdapter(ModelAdapter):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    def _build_prompt(self, prompt: str, context: list[str]) -> str:
        if context:
            return f"Context:\n{chr(10).join(context)}\n\nQuestion:\n{prompt}"
        return prompt

    async def generate(self, prompt: str, context: list[str]) -> GenerateResult:
        full_prompt = self._build_prompt(prompt, context)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/generate",
                    json={"model": self._model, "prompt": full_prompt, "stream": False},
                )
                resp.raise_for_status()
                data = resp.json()
                return GenerateResult(
                    text=data.get("response", ""),
                    model=self._model,
                    tokens_used=data.get("eval_count", 0),
                )
        except httpx.HTTPError as e:
            raise AdapterError(f"Ollama HTTP error: {e}") from e
        except Exception as e:
            raise AdapterError(f"Ollama error: {e}") from e

    async def async_stream(self, prompt: str, context: list[str]) -> AsyncIterator[str]:
        full_prompt = self._build_prompt(prompt, context)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/api/generate",
                    json={"model": self._model, "prompt": full_prompt, "stream": True},
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                if "response" in data:
                                    yield data["response"]
                            except json.JSONDecodeError:
                                pass
        except httpx.HTTPError as e:
            raise AdapterError(f"Ollama stream error: {e}") from e
