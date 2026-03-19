from __future__ import annotations

from typing import AsyncIterator

from base import AdapterError, GenerateResult, ModelAdapter


class OpenAIAdapter(ModelAdapter):
    """
    Adapter for OpenAI-compatible APIs.

    Supports:
      - OpenAI API (set api_key; default model gpt-4o)
      - Azure OpenAI (set api_key, azure_endpoint, api_version, and deployment)

    Used as the 'copilot' or 'openai' provider in tenant config.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str = "",
        azure_endpoint: str = "",
        azure_api_version: str = "2024-02-01",
        deployment: str = "",
    ) -> None:
        self._model = deployment or model
        self._api_key = api_key
        self._azure_endpoint = azure_endpoint
        self._azure_api_version = azure_api_version
        self._is_azure = bool(azure_endpoint)

    def _get_client(self):
        if self._is_azure:
            from openai import AsyncAzureOpenAI
            return AsyncAzureOpenAI(
                api_key=self._api_key,
                azure_endpoint=self._azure_endpoint,
                api_version=self._azure_api_version,
            )
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=self._api_key)

    def _build_messages(self, prompt: str, context: list[str]) -> list[dict]:
        context_text = "\n\n".join(context) if context else ""
        user_content = f"Context:\n{context_text}\n\nQuestion:\n{prompt}" if context_text else prompt
        return [
            {
                "role": "system",
                "content": (
                    "You are an expert RFP response assistant. "
                    "Answer using only the provided context. "
                    "Be precise, factual, and cite specific details."
                ),
            },
            {"role": "user", "content": user_content},
        ]

    async def generate(self, prompt: str, context: list[str]) -> GenerateResult:
        try:
            client = self._get_client()
            messages = self._build_messages(prompt, context)
            response = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=2048,
            )
            text = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0
            return GenerateResult(text=text, model=self._model, tokens_used=tokens)
        except Exception as e:
            raise AdapterError(f"OpenAI error: {e}") from e

    async def async_stream(self, prompt: str, context: list[str]) -> AsyncIterator[str]:
        try:
            client = self._get_client()
            messages = self._build_messages(prompt, context)
            stream = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=2048,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as e:
            raise AdapterError(f"OpenAI stream error: {e}") from e
