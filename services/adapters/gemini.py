from __future__ import annotations

from typing import AsyncIterator

from base import AdapterError, GenerateResult, ModelAdapter


class GeminiAdapter(ModelAdapter):
    def __init__(self, model: str = "gemini-1.5-pro", api_key: str = "") -> None:
        self._model = model
        self._api_key = api_key

    def _get_model(self):
        import google.generativeai as genai
        genai.configure(api_key=self._api_key)
        return genai.GenerativeModel(self._model)

    def _build_prompt(self, prompt: str, context: list[str]) -> str:
        if context:
            return f"Context:\n{chr(10).join(context)}\n\nQuestion:\n{prompt}"
        return prompt

    async def generate(self, prompt: str, context: list[str]) -> GenerateResult:
        try:
            model = self._get_model()
            full_prompt = self._build_prompt(prompt, context)
            response = await model.generate_content_async(full_prompt)
            text = response.text
            return GenerateResult(text=text, model=self._model, tokens_used=0)
        except Exception as e:
            raise AdapterError(f"Gemini error: {e}") from e

    async def async_stream(self, prompt: str, context: list[str]) -> AsyncIterator[str]:
        try:
            model = self._get_model()
            full_prompt = self._build_prompt(prompt, context)
            async for chunk in await model.generate_content_async(full_prompt, stream=True):
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            raise AdapterError(f"Gemini stream error: {e}") from e
