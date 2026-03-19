from __future__ import annotations

from typing import AsyncIterator

from base import AdapterError, GenerateResult, ModelAdapter


class ClaudeAdapter(ModelAdapter):
    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str = "") -> None:
        self._model = model
        self._api_key = api_key

    def _get_client(self):
        import anthropic
        return anthropic.AsyncAnthropic(api_key=self._api_key)

    def _build_messages(self, prompt: str, context: list[str]) -> list[dict]:
        context_text = "\n\n".join(context) if context else ""
        user_content = f"Context:\n{context_text}\n\nQuestion:\n{prompt}" if context_text else prompt
        return [{"role": "user", "content": user_content}]

    async def generate(self, prompt: str, context: list[str]) -> GenerateResult:
        try:
            client = self._get_client()
            messages = self._build_messages(prompt, context)
            response = await client.messages.create(
                model=self._model,
                max_tokens=2048,
                messages=messages,
            )
            text = response.content[0].text
            return GenerateResult(
                text=text,
                model=self._model,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            )
        except Exception as e:
            raise AdapterError(f"Claude error: {e}") from e

    async def async_stream(self, prompt: str, context: list[str]) -> AsyncIterator[str]:
        try:
            client = self._get_client()
            messages = self._build_messages(prompt, context)
            async with client.messages.stream(
                model=self._model, max_tokens=2048, messages=messages
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as e:
            raise AdapterError(f"Claude stream error: {e}") from e
